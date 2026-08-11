using System;
using System.Threading;
using System.Threading.Tasks;
using TianzhengCadPlugin.Protocol;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>
    /// Routes an authenticated request.
    ///
    /// - health / capabilities are answered directly from the immutable
    ///   <see cref="PluginRuntimeInfo"/> snapshot captured on the AutoCAD main thread at
    ///   Initialize(). No AutoCAD API call happens on the transport thread.
    /// - Every other whitelisted operation is handed to the <see cref="OperationQueue"/>
    ///   for main-thread execution. In S7.1-A the dispatcher answers those with a
    ///   structured NOT_IMPLEMENTED_IN_STAGE; no CAD work exists yet.
    ///
    /// This type is deliberately free of AutoCAD references so it is fully unit-testable.
    /// </summary>
    public sealed class RequestRouter : IRequestHandler
    {
        private readonly PluginRuntimeInfo _runtimeInfo;
        private readonly OperationQueue _queue;
        private readonly PluginLog _log;
        private readonly Func<string> _pluginStateProvider;

        public RequestRouter(
            PluginRuntimeInfo runtimeInfo,
            OperationQueue queue,
            PluginLog log,
            Func<string>? pluginStateProvider = null)
        {
            _runtimeInfo = runtimeInfo ?? throw new ArgumentNullException(nameof(runtimeInfo));
            _queue = queue ?? throw new ArgumentNullException(nameof(queue));
            _log = log ?? throw new ArgumentNullException(nameof(log));
            _pluginStateProvider = pluginStateProvider ?? (() => PluginStates.Ready);
        }

        public async Task<PluginResponse> HandleAsync(PluginRequest request, CancellationToken ct)
        {
            string state = _pluginStateProvider();

            // --- Read-only handshake: served from the frozen snapshot ---
            // The connection is already token-authenticated at this point. The handshake
            // does NOT require a session_nonce: capabilities is precisely how a client
            // obtains the current nonce.
            if (request.OperationType is OperationType.Health or OperationType.Capabilities)
            {
                bool isCapabilities = request.OperationType == OperationType.Capabilities;
                _log.Info(LogCategory.Transport, $"handshake op={request.OperationType}");
                return new PluginResponse
                {
                    Success = true,
                    ErrorCode = ErrorCodes.None,
                    Stage = Stages.Handshake,
                    RequestId = request.RequestId,
                    OperationId = request.OperationId,
                    // Only capabilities discloses the session nonce.
                    Result = _runtimeInfo.ToJsonElement(includeSessionNonce: isCapabilities),
                    PluginState = state,
                    DocumentStatus = _runtimeInfo.ActiveDocumentStatus,
                    SanitizedMessage = "ok",
                };
            }

            // --- Every non-handshake operation must carry the current session nonce ---
            PluginResponse? nonceRejection = CheckSessionNonce(request, state);
            if (nonceRejection != null) return nonceRejection;

            // --- Everything else must cross to the AutoCAD main thread ---
            var queued = new QueuedOperation(request, DateTimeOffset.UtcNow);
            if (!_queue.TryEnqueue(queued))
            {
                _log.Warn(LogCategory.Scheduling, "queue saturated; applying back-pressure");
                return new PluginResponse
                {
                    Success = false,
                    ErrorCode = "QUEUE_SATURATED",
                    Stage = Stages.Scheduling,
                    RequestId = request.RequestId,
                    OperationId = request.OperationId,
                    Retryable = true, // transport-level back-pressure IS retryable
                    SanitizedMessage = "plugin queue is saturated",
                    PluginState = state,
                };
            }

            _log.Info(LogCategory.Scheduling, $"queued request_id={request.RequestId} depth={_queue.Count}");

            using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeoutCts.CancelAfter(request.TimeoutMs);

            try
            {
                return await queued.Completion.WaitAsync(timeoutCts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                _log.Warn(LogCategory.Scheduling, $"timeout request_id={request.RequestId}");
                return new PluginResponse
                {
                    Success = false,
                    ErrorCode = "OPERATION_TIMEOUT",
                    Stage = Stages.Scheduling,
                    RequestId = request.RequestId,
                    OperationId = request.OperationId,
                    Retryable = true, // a scheduling timeout is a transport-level condition
                    SanitizedMessage = $"operation exceeded {request.TimeoutMs} ms",
                    PluginState = state,
                };
            }
        }

        /// <summary>
        /// Enforce the per-session nonce. Returns null when the nonce is acceptable.
        ///
        /// A nonce from a previous plugin session cannot match, because a fresh nonce is
        /// generated on every start — so a stale client is rejected rather than silently
        /// driving a restarted plugin.
        /// </summary>
        private PluginResponse? CheckSessionNonce(PluginRequest request, string state)
        {
            if (string.IsNullOrEmpty(request.SessionNonce))
            {
                _log.Warn(LogCategory.Authentication, $"missing session nonce request_id={request.RequestId}");
                return Reject(ErrorCodes.SessionNonceRequired,
                    "session_nonce is required; obtain it from the capabilities handshake", request, state);
            }

            if (!string.Equals(request.SessionNonce, _runtimeInfo.SessionNonce, StringComparison.Ordinal))
            {
                _log.Warn(LogCategory.Authentication, $"stale/invalid session nonce request_id={request.RequestId}");
                return Reject(ErrorCodes.SessionNonceInvalid,
                    "session_nonce does not match the current plugin session", request, state);
            }

            return null;
        }

        private static PluginResponse Reject(string code, string message, PluginRequest request, string state)
        {
            return new PluginResponse
            {
                Success = false,
                ErrorCode = code,
                Stage = Stages.Authentication,
                RequestId = request.RequestId,
                OperationId = request.OperationId,
                Retryable = false, // a nonce problem is a client-state problem, never auto-retried
                SanitizedMessage = message,
                PluginState = state,
            };
        }
    }
}
