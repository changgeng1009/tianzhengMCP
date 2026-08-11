using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class RequestRouterTests
    {
        private static (RequestRouter router, OperationQueue queue) NewRouter(
            string nonce = TestRequests.TestNonce, int maxDepth = 64)
        {
            var info = PluginRuntimeInfo.ForHostSkeleton("session-abc", 4242, "25.1s (LMS Tech)", nonce);
            var queue = new OperationQueue(maxDepth);
            return (new RequestRouter(info, queue, new PluginLog()), queue);
        }

        private static PluginRequest Parse(string json)
        {
            ValidationOutcome outcome = RequestValidator.Validate(json);
            Assert.True(outcome.IsValid, $"fixture must be valid: {outcome.Rejection?.ErrorCode}");
            return outcome.Request!;
        }

        // ---------- handshake ----------

        [Theory]
        [InlineData(OperationType.Health)]
        [InlineData(OperationType.Capabilities)]
        public async Task Handshake_is_answered_without_touching_the_queue(string op)
        {
            (RequestRouter router, OperationQueue queue) = NewRouter();

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(op)), CancellationToken.None);

            Assert.True(response.Success);
            Assert.Equal(Stages.Handshake, response.Stage);
            Assert.Equal(0, queue.Count);
            Assert.NotNull(response.Result);
        }

        [Theory]
        [InlineData(OperationType.Health)]
        [InlineData(OperationType.Capabilities)]
        public async Task Handshake_does_not_require_a_session_nonce(string op)
        {
            (RequestRouter router, _) = NewRouter();

            // No session_nonce supplied at all.
            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(op)), CancellationToken.None);

            Assert.True(response.Success);
        }

        [Fact]
        public async Task Handshake_reports_the_required_fields()
        {
            (RequestRouter router, _) = NewRouter();

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(OperationType.Health)), CancellationToken.None);

            JsonElement result = response.Result!.Value;
            foreach (string field in new[]
            {
                "plugin_name", "plugin_version", "protocol_version", "capability_version",
                "autocad_version", "process_id", "session_id", "active_document_status",
                "supported_operations", "supported_entity_types", "transaction_support",
                "batch_support", "dry_run_support", "idempotency_support", "tianzheng_support",
                "readiness",
            })
            {
                Assert.True(result.TryGetProperty(field, out _), $"handshake must expose '{field}'");
            }
        }

        [Fact]
        public async Task Capabilities_discloses_the_session_nonce()
        {
            (RequestRouter router, _) = NewRouter(nonce: "nonce-xyz");

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(OperationType.Capabilities)), CancellationToken.None);

            Assert.True(response.Result!.Value.TryGetProperty("session_nonce", out JsonElement nonce));
            Assert.Equal("nonce-xyz", nonce.GetString());
        }

        [Fact]
        public async Task Health_does_not_disclose_the_session_nonce()
        {
            (RequestRouter router, _) = NewRouter(nonce: "nonce-xyz");

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(OperationType.Health)), CancellationToken.None);

            Assert.False(response.Result!.Value.TryGetProperty("session_nonce", out _));
        }

        // ---------- stage capability boundary ----------

        [Fact]
        public async Task Handshake_never_claims_tianzheng_support()
        {
            (RequestRouter router, _) = NewRouter();

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(OperationType.Capabilities)), CancellationToken.None);

            Assert.Equal(CapabilityStatus.NotAvailable,
                response.Result!.Value.GetProperty("tianzheng_support").GetString());
        }

        [Fact]
        public async Task Stage_boundary_reports_no_supported_operations_or_entities()
        {
            (RequestRouter router, _) = NewRouter();

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(OperationType.Capabilities)), CancellationToken.None);

            // This router is built from ForHostSkeleton, which claims no CAD capability.
            JsonElement result = response.Result!.Value;
            Assert.Empty(result.GetProperty("supported_operations").EnumerateArray());
            Assert.Empty(result.GetProperty("supported_entity_types").EnumerateArray());
            Assert.False(result.GetProperty("transaction_support").GetBoolean());
            Assert.False(result.GetProperty("batch_support").GetBoolean());
            Assert.False(result.GetProperty("document_ownership_support").GetBoolean());
            Assert.False(result.GetProperty("dry_run_support").GetBoolean());
            Assert.Equal(CapabilityStatus.NotImplemented, result.GetProperty("idempotency_support").GetString());
        }

        [Theory]
        [InlineData(OperationType.CreateSyntheticDocument)]
        [InlineData(OperationType.CreateLayer)]
        [InlineData(OperationType.CreateLine)]
        [InlineData(OperationType.CreateCircle)]
        [InlineData(OperationType.CreatePolyline)]
        [InlineData(OperationType.QueryEntities)]
        [InlineData(OperationType.BatchExecute)]
        [InlineData(OperationType.Save)]
        [InlineData(OperationType.Close)]
        [InlineData(OperationType.Reopen)]
        public async Task Future_operations_return_NOT_IMPLEMENTED_IN_STAGE(string op)
        {
            (RequestRouter router, OperationQueue queue) = NewRouter();
            using var pump = new QueuePump(queue); // stands in for Application.Idle

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.ValidOperation(op)), CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.NotImplementedInStage, response.ErrorCode);
            Assert.Equal("none", response.TransactionStatus);
            Assert.Equal("none", response.DocumentStatus);
            Assert.Equal(0, response.CreatedCount);
        }

        // ---------- session nonce ----------

        [Fact]
        public async Task Non_handshake_operation_without_nonce_is_rejected()
        {
            (RequestRouter router, OperationQueue queue) = NewRouter();

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Valid(OperationType.CreateLine)), CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.SessionNonceRequired, response.ErrorCode);
            Assert.False(response.Retryable);
            Assert.Equal(0, queue.Count); // never scheduled
        }

        [Fact]
        public async Task Non_handshake_operation_with_wrong_nonce_is_rejected()
        {
            (RequestRouter router, OperationQueue queue) = NewRouter();

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.ValidOperation(OperationType.CreateLine, "not-the-right-nonce")),
                CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.SessionNonceInvalid, response.ErrorCode);
            Assert.Equal(0, queue.Count);
        }

        [Fact]
        public async Task Nonce_from_a_previous_plugin_session_is_invalid()
        {
            // Session 1 hands out its nonce...
            (RequestRouter first, _) = NewRouter(nonce: "session-1-nonce");
            PluginResponse caps = await first.HandleAsync(
                Parse(TestRequests.Valid(OperationType.Capabilities)), CancellationToken.None);
            string oldNonce = caps.Result!.Value.GetProperty("session_nonce").GetString()!;

            // ...the plugin restarts with a fresh nonce.
            (RequestRouter second, _) = NewRouter(nonce: "session-2-nonce");

            PluginResponse response = await second.HandleAsync(
                Parse(TestRequests.ValidOperation(OperationType.CreateLine, oldNonce)),
                CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal(ErrorCodes.SessionNonceInvalid, response.ErrorCode);
        }

        [Fact]
        public async Task Correct_nonce_allows_the_operation_to_be_scheduled()
        {
            (RequestRouter router, OperationQueue queue) = NewRouter();
            using var pump = new QueuePump(queue);

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.ValidOperation(OperationType.CreateLine)), CancellationToken.None);

            // It reached the executor rather than being rejected at the nonce gate.
            Assert.Equal(ErrorCodes.NotImplementedInStage, response.ErrorCode);
        }

        // ---------- scheduling ----------

        [Fact]
        public async Task Non_handshake_operations_are_queued_for_the_main_thread()
        {
            (RequestRouter router, OperationQueue queue) = NewRouter();

            Task<PluginResponse> pending = router.HandleAsync(
                Parse(TestRequests.ValidOperation(OperationType.CreateLine)), CancellationToken.None);

            await WaitForQueueAsync(queue);
            Assert.Equal(1, queue.Count); // not executed inline on the transport thread

            queue.TryDequeue(out QueuedOperation? op);
            op!.Complete(PluginResponse.Ok("req-1", "op-1", Stages.Scheduling));

            Assert.True((await pending).Success);
        }

        [Fact]
        public async Task Queued_operation_times_out_when_no_dispatcher_runs()
        {
            (RequestRouter router, _) = NewRouter();
            var fields = TestRequests.BaseFields(OperationType.CreateLine, TestRequests.TestNonce);
            fields["timeout_ms"] = 150;

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.Json(fields)), CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal("OPERATION_TIMEOUT", response.ErrorCode);
            Assert.True(response.Retryable);
        }

        [Fact]
        public async Task Saturated_queue_returns_retryable_backpressure()
        {
            (RequestRouter router, OperationQueue queue) = NewRouter(maxDepth: 1);

            _ = router.HandleAsync(
                Parse(TestRequests.ValidOperation(OperationType.CreateLine)), CancellationToken.None);
            await WaitForQueueAsync(queue);

            PluginResponse response = await router.HandleAsync(
                Parse(TestRequests.ValidOperation(OperationType.CreateCircle)), CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal("QUEUE_SATURATED", response.ErrorCode);
            Assert.True(response.Retryable);
        }

        private static async Task WaitForQueueAsync(OperationQueue queue)
        {
            for (int i = 0; i < 200 && queue.Count == 0; i++) await Task.Delay(10);
        }
    }
}
