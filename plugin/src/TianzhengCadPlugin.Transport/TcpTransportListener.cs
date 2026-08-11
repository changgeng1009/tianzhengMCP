using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using TianzhengCadPlugin.Protocol;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>Handles a validated+authenticated request. Implemented by the plugin host.</summary>
    public interface IRequestHandler
    {
        Task<PluginResponse> HandleAsync(PluginRequest request, CancellationToken ct);
    }

    /// <summary>
    /// Loopback-only, length-prefixed, token-authenticated request listener.
    ///
    /// THREADING CONTRACT: everything in this class runs on .NET thread-pool / socket
    /// threads. It NEVER touches the AutoCAD API (Database, DocumentManager, Transaction,
    /// Editor, Entity). CAD work is reached only by handing a validated request to
    /// <see cref="IRequestHandler"/>, whose implementation marshals to the AutoCAD main
    /// thread through <see cref="OperationQueue"/>.
    ///
    /// SECURITY: binds strictly to 127.0.0.1 (never 0.0.0.0 / LAN / public), additionally
    /// re-checks that each accepted peer is loopback, enforces the frame size cap, applies
    /// an idle read timeout, and limits concurrent connections.
    /// </summary>
    public sealed class TcpTransportListener : IDisposable
    {
        private readonly TokenAuthenticator _authenticator;
        private readonly IRequestHandler _handler;
        private readonly PluginLog _log;
        private readonly int _maxConcurrentConnections;
        private readonly TimeSpan _idleTimeout;

        private TcpListener? _listener;
        private CancellationTokenSource? _cts;
        private Task? _acceptLoop;
        private int _activeConnections;

        public int Port { get; private set; }
        public bool IsRunning => _listener != null;

        public TcpTransportListener(
            TokenAuthenticator authenticator,
            IRequestHandler handler,
            PluginLog log,
            int maxConcurrentConnections = 4,
            TimeSpan? idleTimeout = null)
        {
            _authenticator = authenticator ?? throw new ArgumentNullException(nameof(authenticator));
            _handler = handler ?? throw new ArgumentNullException(nameof(handler));
            _log = log ?? throw new ArgumentNullException(nameof(log));
            _maxConcurrentConnections = Math.Max(1, maxConcurrentConnections);
            _idleTimeout = idleTimeout ?? TimeSpan.FromSeconds(60);
        }

        /// <summary>Bind and begin accepting. Port 0 lets the OS choose (used by tests).</summary>
        public void Start(int port)
        {
            if (_listener != null) throw new InvalidOperationException("listener already started");

            // Hard-bound to loopback. There is no configuration path to any other interface.
            IPAddress bindAddress = IPAddress.Loopback; // 127.0.0.1
            _listener = new TcpListener(bindAddress, port);
            _listener.Start();
            Port = ((IPEndPoint)_listener.LocalEndpoint).Port;

            _cts = new CancellationTokenSource();
            _acceptLoop = Task.Run(() => AcceptLoopAsync(_cts.Token));

            _log.Info(LogCategory.Transport, $"listening on {ProtocolConstants.BindAddress}:{Port}");
        }

        public void Stop()
        {
            if (_listener == null) return;
            _log.Info(LogCategory.Shutdown, "stopping listener");
            try { _cts?.Cancel(); } catch (ObjectDisposedException) { }
            try { _listener.Stop(); } catch (SocketException) { }

            try { _acceptLoop?.Wait(TimeSpan.FromSeconds(5)); }
            catch (AggregateException) { /* cancellation is expected */ }

            _listener = null;
            _cts?.Dispose();
            _cts = null;
            _log.Info(LogCategory.Shutdown, "listener stopped");
        }

        private async Task AcceptLoopAsync(CancellationToken ct)
        {
            TcpListener listener = _listener!;
            while (!ct.IsCancellationRequested)
            {
                TcpClient client;
                try
                {
                    client = await listener.AcceptTcpClientAsync(ct).ConfigureAwait(false);
                }
                catch (OperationCanceledException) { break; }
                catch (ObjectDisposedException) { break; }
                catch (SocketException ex)
                {
                    _log.Warn(LogCategory.Transport, $"accept failed: {ex.SocketErrorCode}");
                    continue;
                }

                // Defense in depth: even bound to loopback, refuse any non-loopback peer.
                if (client.Client.RemoteEndPoint is not IPEndPoint remote || !IPAddress.IsLoopback(remote.Address))
                {
                    _log.Warn(LogCategory.Transport, "rejected non-loopback peer");
                    SafeClose(client);
                    continue;
                }

                if (Interlocked.Increment(ref _activeConnections) > _maxConcurrentConnections)
                {
                    Interlocked.Decrement(ref _activeConnections);
                    _log.Warn(LogCategory.Transport, "connection refused: concurrency limit reached");
                    SafeClose(client);
                    continue;
                }

                _ = Task.Run(async () =>
                {
                    try { await ServeConnectionAsync(client, ct).ConfigureAwait(false); }
                    catch (Exception ex) { _log.Error(LogCategory.Transport, $"connection aborted: {ex.GetType().Name}"); }
                    finally
                    {
                        Interlocked.Decrement(ref _activeConnections);
                        SafeClose(client);
                    }
                }, CancellationToken.None);
            }
        }

        private async Task ServeConnectionAsync(TcpClient client, CancellationToken ct)
        {
            using NetworkStream stream = client.GetStream();
            _log.Info(LogCategory.Transport, "connection accepted (loopback)");

            // Connection state machine: the FIRST frame must be the auth handshake.
            // Until it succeeds no business validation runs at all, so an unauthenticated
            // caller learns nothing about fields, operations, capabilities or state.
            bool authenticated = false;

            while (!ct.IsCancellationRequested)
            {
                using var idleCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                idleCts.CancelAfter(_idleTimeout);

                FrameReadResult frame;
                try
                {
                    frame = await FrameCodec.ReadFrameAsync(stream, idleCts.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    _log.Info(LogCategory.Transport, "connection closed: idle timeout");
                    return;
                }
                catch (IOException)
                {
                    _log.Info(LogCategory.Transport, "connection closed by peer");
                    return;
                }

                switch (frame.Status)
                {
                    case FrameReadStatus.Closed:
                        _log.Info(LogCategory.Transport, "peer closed on frame boundary");
                        return;

                    case FrameReadStatus.TooLarge:
                        // Cannot trust the stream position after an oversized declaration: close.
                        _log.Warn(LogCategory.Transport, $"frame rejected: declared {frame.DeclaredLength} bytes exceeds cap");
                        await TryWriteAsync(stream, authenticated
                            ? PluginResponse.Failure(ErrorCodes.FrameTooLarge, Stages.Transport,
                                $"payload exceeds {ProtocolConstants.MaxPayloadBytes} bytes")
                            : PluginResponse.Unauthenticated(ErrorCodes.FrameTooLarge), ct).ConfigureAwait(false);
                        return;

                    case FrameReadStatus.Malformed:
                        _log.Warn(LogCategory.Transport, "frame rejected: malformed");
                        await TryWriteAsync(stream, authenticated
                            ? PluginResponse.Failure(ErrorCodes.MalformedFrame, Stages.Transport, "malformed frame")
                            : PluginResponse.Unauthenticated(ErrorCodes.MalformedFrame), ct).ConfigureAwait(false);
                        return;
                }

                if (!authenticated)
                {
                    // Only the auth frame is parsed here. Any failure — bad JSON, wrong
                    // type, unknown field, missing or wrong token — yields the SAME
                    // generic response, then the connection is closed.
                    bool parsed = AuthFrameParser.TryParse(frame.Payload!, out AuthFrame authFrame);
                    bool accepted = parsed && _authenticator.Verify(authFrame.AuthToken);

                    if (!accepted)
                    {
                        _log.Warn(LogCategory.Authentication,
                            $"handshake rejected token={TokenAuthenticator.Redact(parsed ? authFrame.AuthToken : null)}");
                        await TryWriteAsync(stream,
                            PluginResponse.Unauthenticated(ErrorCodes.AuthFailed), ct).ConfigureAwait(false);
                        return;
                    }

                    authenticated = true;
                    _log.Info(LogCategory.Authentication, "handshake accepted");
                    await TryWriteAsync(stream, new PluginResponse
                    {
                        Success = true,
                        ErrorCode = ErrorCodes.None,
                        Stage = Stages.Authentication,
                        SanitizedMessage = "authenticated",
                    }, ct).ConfigureAwait(false);
                    continue;
                }

                PluginResponse response = await ProcessPayloadAsync(frame.Payload!, ct).ConfigureAwait(false);
                await TryWriteAsync(stream, response, ct).ConfigureAwait(false);
            }
        }

        /// <summary>
        /// Business-request path, reached ONLY after the connection handshake succeeded.
        /// Validates then hands off; never executes CAD work itself, and never sees a token
        /// (the token is not part of the business request schema).
        /// </summary>
        private async Task<PluginResponse> ProcessPayloadAsync(string payload, CancellationToken ct)
        {
            var stopwatch = Stopwatch.StartNew();

            ValidationOutcome outcome = RequestValidator.Validate(payload);
            if (!outcome.IsValid)
            {
                PluginResponse rejection = outcome.Rejection!;
                _log.Warn(LogCategory.Validation, $"rejected: {rejection.ErrorCode}");
                rejection.DurationMs = stopwatch.ElapsedMilliseconds;
                return rejection;
            }

            PluginRequest request = outcome.Request!;

            _log.Info(LogCategory.Scheduling,
                $"accepted request_id={request.RequestId} op={request.OperationType}");

            PluginResponse response = await _handler.HandleAsync(request, ct).ConfigureAwait(false);
            response.RequestId = request.RequestId;
            response.OperationId = request.OperationId;
            response.DurationMs = stopwatch.ElapsedMilliseconds;
            return response;
        }

        private async Task TryWriteAsync(NetworkStream stream, PluginResponse response, CancellationToken ct)
        {
            try { await FrameCodec.WriteFrameAsync(stream, response.ToJson(), ct).ConfigureAwait(false); }
            catch (Exception ex) { _log.Warn(LogCategory.Transport, $"response write failed: {ex.GetType().Name}"); }
        }

        private static void SafeClose(TcpClient client)
        {
            try { client.Close(); } catch { /* best effort */ }
        }

        public void Dispose() => Stop();
    }
}
