using System;
using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// End-to-end transport tests over real loopback TCP.
    /// These exercise the NETWORK layer only — no AutoCAD is involved, and no result here
    /// may be presented as AutoCAD integration evidence.
    /// </summary>
    public class TcpTransportListenerTests : IDisposable
    {
        private readonly TcpTransportListener _listener;
        private readonly OperationQueue _queue = new();
        private readonly QueuePump _pump;

        public TcpTransportListenerTests()
        {
            var info = PluginRuntimeInfo.ForHostSkeleton(
                "session-test", 1234, "25.1s (LMS Tech)", TestRequests.TestNonce);
            var log = new PluginLog();
            var router = new RequestRouter(info, _queue, log);
            _pump = new QueuePump(_queue); // stands in for Application.Idle, NOT AutoCAD
            _listener = new TcpTransportListener(
                TokenAuthenticator.FromToken(TestRequests.ValidToken), router, log,
                idleTimeout: TimeSpan.FromSeconds(10));
            _listener.Start(0); // OS-assigned free port
        }

        public void Dispose()
        {
            _listener.Dispose();
            _pump.Dispose();
        }

        // ---------- bind ----------

        [Fact]
        public void Binds_only_to_loopback()
        {
            Assert.True(_listener.IsRunning);
            Assert.True(_listener.Port > 0);

            using var loopback = new TcpClient();
            loopback.Connect(IPAddress.Loopback, _listener.Port);
            Assert.True(loopback.Connected);
        }

        // ---------- authentication wire flow ----------

        [Fact]
        public async Task Valid_token_completes_the_handshake()
        {
            using Conn conn = await ConnectAsync();
            PluginResponse auth = await conn.SendAsync(TestRequests.AuthFrame());

            Assert.True(auth.Success);
            Assert.Equal(Stages.Authentication, auth.Stage);
        }

        [Fact]
        public async Task Wrong_token_is_rejected_and_not_retryable()
        {
            using Conn conn = await ConnectAsync();
            PluginResponse auth = await conn.SendAsync(
                TestRequests.AuthFrame("wrong-token-wrong-token-wrong-token-xx"));

            Assert.False(auth.Success);
            Assert.Equal(ErrorCodes.AuthFailed, auth.ErrorCode);
            Assert.Equal(Stages.Authentication, auth.Stage);
            Assert.False(auth.Retryable);
        }

        [Fact]
        public async Task Missing_auth_handshake_blocks_business_requests()
        {
            using Conn conn = await ConnectAsync();

            // Send a business request as the FIRST frame: must be refused.
            PluginResponse response = await conn.SendAsync(TestRequests.Valid(OperationType.Health));

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.AuthFailed, response.ErrorCode);
            Assert.Null(response.Result);
        }

        [Fact]
        public async Task Unauthenticated_client_learns_nothing_about_the_schema()
        {
            using Conn conn = await ConnectAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.WithExtra("bogus_field", 1));
            string json = response.ToJson();

            // No field enumeration, no capability detail, no plugin/internal state.
            Assert.DoesNotContain("bogus_field", json);
            Assert.DoesNotContain("supported_operations", json);
            Assert.DoesNotContain("tianzheng", json);
            Assert.DoesNotContain("session_nonce", json);
            Assert.Equal("", response.PluginVersion);
            Assert.Equal("", response.PluginState);
            Assert.Equal("authentication required", response.SanitizedMessage);
        }

        [Fact]
        public async Task Bad_token_and_bad_frame_are_indistinguishable_before_auth()
        {
            using Conn badToken = await ConnectAsync();
            PluginResponse a = await badToken.SendAsync(TestRequests.AuthFrame("bad-token-bad-token-bad-token-xyz"));

            using Conn badFrame = await ConnectAsync();
            PluginResponse b = await badFrame.SendAsync("""{"type":"auth","nope":1}""");

            Assert.Equal(a.ErrorCode, b.ErrorCode);
            Assert.Equal(a.SanitizedMessage, b.SanitizedMessage);
        }

        [Fact]
        public async Task Auth_failure_response_never_contains_the_token()
        {
            const string attempted = "another-wrong-token-1234567890ab";
            using Conn conn = await ConnectAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.AuthFrame(attempted));

            string json = response.ToJson();
            Assert.DoesNotContain(attempted, json);
            Assert.DoesNotContain(TestRequests.ValidToken, json);
        }

        // ---------- authenticated business requests ----------

        [Fact]
        public async Task Health_request_returns_the_handshake_after_auth()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.Valid(OperationType.Health));

            Assert.True(response.Success);
            Assert.Equal(Stages.Handshake, response.Stage);
            Assert.Equal("req-1", response.RequestId);
            Assert.Equal(ProtocolConstants.PluginVersion, response.PluginVersion);
        }

        [Fact]
        public async Task Capabilities_returns_the_session_nonce_after_auth()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.Valid(OperationType.Capabilities));

            Assert.True(response.Success);
            Assert.Equal(TestRequests.TestNonce,
                response.Result!.Value.GetProperty("session_nonce").GetString());
        }

        [Fact]
        public async Task Operation_without_nonce_is_rejected_over_the_wire()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.Valid(OperationType.CreateLine));

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.SessionNonceRequired, response.ErrorCode);
        }

        [Fact]
        public async Task Operation_with_wrong_nonce_is_rejected_over_the_wire()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(
                TestRequests.ValidOperation(OperationType.CreateLine, "stale-nonce"));

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.SessionNonceInvalid, response.ErrorCode);
        }

        [Fact]
        public async Task Operation_with_valid_nonce_reaches_the_stage_executor()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(
                TestRequests.ValidOperation(OperationType.CreateLine));

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.NotImplementedInStage, response.ErrorCode);
            Assert.Equal(0, response.CreatedCount);
        }

        [Fact]
        public async Task Unknown_field_is_rejected_after_auth()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.WithExtra("evil", "x"));

            Assert.Equal(ErrorCodes.UnknownField, response.ErrorCode);
            Assert.Equal(Stages.Validation, response.Stage);
        }

        [Fact]
        public async Task Missing_field_is_rejected_after_auth()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.Without("job_id"));

            Assert.Equal(ErrorCodes.MissingField, response.ErrorCode);
        }

        [Fact]
        public async Task Unknown_operation_is_rejected_after_auth()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.Valid("send_command"));

            Assert.Equal(ErrorCodes.UnknownOperation, response.ErrorCode);
        }

        [Fact]
        public async Task Incompatible_protocol_version_is_rejected_after_auth()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync(TestRequests.With("protocol_version", "9.0.0"));

            Assert.Equal(ErrorCodes.IncompatibleProtocolVersion, response.ErrorCode);
        }

        [Fact]
        public async Task Invalid_json_is_rejected_structurally_after_auth()
        {
            using Conn conn = await AuthenticatedAsync();
            PluginResponse response = await conn.SendAsync("{ not json");

            Assert.Equal(ErrorCodes.InvalidJson, response.ErrorCode);
            Assert.NotEqual("", response.SanitizedMessage);
        }

        [Fact]
        public async Task Multiple_sequential_requests_share_one_authenticated_connection()
        {
            using Conn conn = await AuthenticatedAsync();

            for (int i = 0; i < 3; i++)
            {
                PluginResponse response = await conn.SendAsync(TestRequests.Valid(OperationType.Health));
                Assert.True(response.Success);
            }
        }

        // ---------- framing limits ----------

        [Fact]
        public async Task Oversized_frame_declaration_is_rejected()
        {
            using Conn conn = await AuthenticatedAsync();

            byte[] header = new byte[4];
            BinaryPrimitives.WriteUInt32BigEndian(header, (uint)ProtocolConstants.MaxPayloadBytes + 1);
            await conn.Stream.WriteAsync(header, Cts().Token);
            await conn.Stream.FlushAsync(Cts().Token);

            FrameReadResult frame = await FrameCodec.ReadFrameAsync(conn.Stream, Cts().Token);
            PluginResponse response = Deserialize(frame.Payload!);

            Assert.Equal(ErrorCodes.FrameTooLarge, response.ErrorCode);
            Assert.Equal(Stages.Transport, response.Stage);
        }

        // ---------- helpers ----------

        private sealed class Conn : IDisposable
        {
            public required TcpClient Client { get; init; }
            public required NetworkStream Stream { get; init; }

            public async Task<PluginResponse> SendAsync(string payload)
            {
                await FrameCodec.WriteFrameAsync(Stream, payload, Cts().Token);
                FrameReadResult frame = await FrameCodec.ReadFrameAsync(Stream, Cts().Token);
                Assert.Equal(FrameReadStatus.Ok, frame.Status);
                return Deserialize(frame.Payload!);
            }

            public void Dispose()
            {
                Stream.Dispose();
                Client.Dispose();
            }
        }

        private async Task<Conn> ConnectAsync()
        {
            var client = new TcpClient();
            await client.ConnectAsync(IPAddress.Loopback, _listener.Port);
            return new Conn { Client = client, Stream = client.GetStream() };
        }

        private async Task<Conn> AuthenticatedAsync()
        {
            Conn conn = await ConnectAsync();
            PluginResponse auth = await conn.SendAsync(TestRequests.AuthFrame());
            Assert.True(auth.Success, "handshake must succeed for this fixture");
            return conn;
        }

        private static PluginResponse Deserialize(string json) =>
            JsonSerializer.Deserialize<PluginResponse>(json, ProtocolJson.Options)!;

        private static CancellationTokenSource Cts() => new(TimeSpan.FromSeconds(10));
    }
}
