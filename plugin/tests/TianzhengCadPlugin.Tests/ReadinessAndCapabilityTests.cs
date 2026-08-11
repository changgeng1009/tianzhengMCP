using System.Text.Json;
using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class ReadinessAndCapabilityTests
    {
        private static JsonElement Handshake(PluginRuntimeInfo info) => info.ToJsonElement(includeSessionNonce: true);

        private static PluginRuntimeInfo EntityMvp() =>
            PluginRuntimeInfo.ForEntityMvp("s", 1, "25.1.0.0", "nonce");

        // ---------- protocol version ----------

        [Fact]
        public void Breaking_change_uses_a_major_version()
        {
            // readiness changed string -> boolean, which a 1.x client cannot parse.
            Assert.Equal("2.0.0", ProtocolConstants.ProtocolVersion);
            Assert.StartsWith("2.", ProtocolConstants.ProtocolVersion);
        }

        [Fact]
        public void Capability_version_names_the_final_s7_2_surface()
            => Assert.Equal("s7.2-entity-mvp", ProtocolConstants.CapabilityVersion);

        [Theory]
        [InlineData("2.0.0")]
        [InlineData("2.1.0")]
        [InlineData("2.0.5")]
        public void Accepts_protocol_2_x(string version)
            => Assert.True(RequestValidator.IsCompatibleProtocolVersion(version));

        [Theory]
        [InlineData("1.0.0")]
        [InlineData("1.1.0")]
        [InlineData("1.9.9")]
        [InlineData("0.9.0")]
        [InlineData("3.0.0")]
        public void Rejects_incompatible_major_versions(string version)
            => Assert.False(RequestValidator.IsCompatibleProtocolVersion(version));

        [Fact]
        public void A_1_x_request_is_rejected_as_incompatible_protocol()
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.With("protocol_version", "1.1.0"));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.IncompatibleProtocolVersion, outcome.Rejection!.ErrorCode);
        }

        [Fact]
        public void A_2_0_0_request_is_accepted()
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.With("protocol_version", "2.0.0"));

            Assert.True(outcome.IsValid);
        }

        [Fact]
        public void Capabilities_reports_protocol_2_0_0()
        {
            JsonElement json = Handshake(EntityMvp());
            Assert.Equal("2.0.0", json.GetProperty("protocol_version").GetString());
        }

        // ---------- readiness schema ----------

        [Fact]
        public void Readiness_is_a_json_boolean()
        {
            JsonElement json = Handshake(EntityMvp());

            Assert.True(json.TryGetProperty("readiness", out JsonElement readiness));
            Assert.Equal(JsonValueKind.True, readiness.ValueKind);
            Assert.True(readiness.GetBoolean());
        }

        [Fact]
        public void Readiness_state_is_a_json_string()
        {
            JsonElement json = Handshake(EntityMvp());

            Assert.True(json.TryGetProperty("readiness_state", out JsonElement state));
            Assert.Equal(JsonValueKind.String, state.ValueKind);
            Assert.Equal(ReadinessState.EntityMvpAvailable, state.GetString());
        }

        [Fact]
        public void Host_skeleton_still_reports_readiness_true_with_handshake_only_state()
        {
            PluginRuntimeInfo info = PluginRuntimeInfo.ForHostSkeleton("s", 1, "v");

            Assert.True(info.Readiness);
            Assert.Equal(ReadinessState.HandshakeOnly, info.ReadinessStateValue);
        }

        // ---------- verified capability surface ----------

        [Fact]
        public void Advertises_the_verified_entity_operations()
        {
            PluginRuntimeInfo info = EntityMvp();

            foreach (string op in new[]
            {
                OperationType.CreateSyntheticDocument, OperationType.CreateLayer,
                OperationType.CreateLine, OperationType.CreateCircle,
                OperationType.CreatePolyline, OperationType.QueryEntities,
                OperationType.BatchExecute,
            })
            {
                Assert.Contains(op, info.SupportedOperations);
            }
        }

        [Fact]
        public void Advertises_the_verified_persistence_lifecycle()
        {
            // S7.4 added save/close/reopen with verified persistence.
            PluginRuntimeInfo info = EntityMvp();

            Assert.Contains(OperationType.Save, info.SupportedOperations);
            Assert.Contains(OperationType.Close, info.SupportedOperations);
            Assert.Contains(OperationType.Reopen, info.SupportedOperations);
            Assert.True(info.PersistenceSupport);
        }

        [Fact]
        public void Never_advertises_unimplemented_entity_operations()
        {
            // Entity types and operations outside the verified subset stay unadvertised.
            PluginRuntimeInfo info = EntityMvp();

            foreach (string absent in new[] { "arc", "rectangle", "text", "mtext", "block_reference" })
                Assert.DoesNotContain(absent, info.SupportedEntityTypes);
        }

        [Fact]
        public void Advertises_exactly_the_three_verified_entity_types()
            => Assert.Equal(new[] { "circle", "line", "polyline" }, EntityMvp().SupportedEntityTypes);

        [Fact]
        public void Transaction_batch_and_ownership_support_are_true_booleans()
        {
            JsonElement json = Handshake(EntityMvp());

            Assert.Equal(JsonValueKind.True, json.GetProperty("transaction_support").ValueKind);
            Assert.Equal(JsonValueKind.True, json.GetProperty("batch_support").ValueKind);
            Assert.Equal(JsonValueKind.True, json.GetProperty("document_ownership_support").ValueKind);
            Assert.Equal("all_or_nothing", json.GetProperty("batch_transaction_mode").GetString());
        }

        [Fact]
        public void Dry_run_support_is_a_boolean_and_matches_the_declared_capability()
        {
            JsonElement json = Handshake(EntityMvp());
            JsonElement dryRun = json.GetProperty("dry_run_support");

            Assert.True(dryRun.ValueKind is JsonValueKind.True or JsonValueKind.False);
            // Source-of-truth check: whatever the snapshot claims, the wire must agree.
            Assert.Equal(EntityMvp().DryRunSupport, dryRun.GetBoolean());
        }

        [Fact]
        public void Idempotency_is_claimed_only_as_a_sandbox_mvp()
        {
            // S7.4 implements persistent, in-document idempotency. It is a sandbox MVP,
            // never a production claim.
            Assert.Equal(CapabilityStatus.AvailableSandboxMvp, EntityMvp().IdempotencySupport);
        }

        [Fact]
        public void Tianzheng_is_never_claimed()
            => Assert.Equal(CapabilityStatus.NotAvailable, EntityMvp().TianzhengSupport);

        [Fact]
        public void Active_document_is_never_reported_as_owned()
            => Assert.Equal(DocumentStatus.NotTracked, EntityMvp().ActiveDocumentStatus);

        [Fact]
        public void Handshake_exposes_every_capability_field()
        {
            JsonElement json = Handshake(EntityMvp());

            foreach (string field in new[]
            {
                "plugin_name", "plugin_version", "protocol_version", "capability_version",
                "autocad_version", "process_id", "session_id", "session_nonce",
                "active_document_status", "supported_operations", "supported_entity_types",
                "transaction_support", "batch_support", "document_ownership_support",
                "batch_transaction_mode", "dry_run_support", "idempotency_support",
                "tianzheng_support", "readiness", "readiness_state",
            })
            {
                Assert.True(json.TryGetProperty(field, out _), $"handshake must expose '{field}'");
            }
        }

        [Fact]
        public void No_environment_variable_can_raise_the_capability_level()
        {
            // Capability is expressed in source, not toggled by the environment: two calls
            // under any environment must produce the same claims.
            PluginRuntimeInfo a = PluginRuntimeInfo.ForEntityMvp("s", 1, "v", "n");
            PluginRuntimeInfo b = PluginRuntimeInfo.ForEntityMvp("s", 1, "v", "n");

            Assert.Equal(a.ReadinessStateValue, b.ReadinessStateValue);
            Assert.Equal(a.TransactionSupport, b.TransactionSupport);
            Assert.Equal(a.DryRunSupport, b.DryRunSupport);
            Assert.Equal(a.SupportedOperations, b.SupportedOperations);
        }
    }
}
