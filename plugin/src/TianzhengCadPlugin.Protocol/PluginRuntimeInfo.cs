using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// Immutable handshake snapshot.
    ///
    /// IMPORTANT: <see cref="AutoCadVersion"/> and <see cref="ActiveDocumentStatus"/> are the
    /// only AutoCAD-derived values, and they are captured ONCE on the AutoCAD main thread
    /// during Initialize(). The transport thread only ever reads this frozen snapshot, so
    /// answering health/capabilities never calls the AutoCAD API off-thread.
    ///
    /// Capability values are deliberately conservative: anything not yet executed and verified
    /// in a real AutoCAD run is reported as NOT_IMPLEMENTED, never as available.
    /// </summary>
    public sealed class PluginRuntimeInfo
    {
        [JsonPropertyName("plugin_name")] public string PluginName { get; init; } = "TianzhengCadPlugin";
        [JsonPropertyName("plugin_version")] public string PluginVersion { get; init; } = ProtocolConstants.PluginVersion;
        [JsonPropertyName("protocol_version")] public string ProtocolVersion { get; init; } = ProtocolConstants.ProtocolVersion;
        [JsonPropertyName("capability_version")] public string CapabilityVersion { get; init; } = ProtocolConstants.CapabilityVersion;

        /// <summary>Captured on the main thread at Initialize(); "unknown" if unavailable.</summary>
        [JsonPropertyName("autocad_version")] public string AutoCadVersion { get; init; } = "unknown";

        [JsonPropertyName("process_id")] public int ProcessId { get; init; }

        /// <summary>Fresh, unguessable id generated on every plugin start.</summary>
        [JsonPropertyName("session_id")] public string SessionId { get; init; } = "";

        /// <summary>
        /// Per-session nonce, regenerated on every plugin start. It is NOT a secret and is
        /// never a substitute for the connection token; it binds a request to the current
        /// plugin session so stale clients cannot drive a restarted plugin.
        ///
        /// [JsonIgnore]: it is emitted ONLY in the capabilities response, via
        /// <see cref="ToJsonElement(bool)"/>, never in health.
        /// </summary>
        [JsonIgnore] public string SessionNonce { get; init; } = "";

        /// <summary>
        /// S7.1-A: the host does not track or touch any document, so this is
        /// "NOT_TRACKED" rather than a claim about the user's active drawing.
        /// </summary>
        [JsonPropertyName("active_document_status")] public string ActiveDocumentStatus { get; init; } = "NOT_TRACKED";

        [JsonPropertyName("supported_operations")] public List<string> SupportedOperations { get; init; } = new();

        /// <summary>Empty in S7.1-A: no entity creation exists in this stage.</summary>
        [JsonPropertyName("supported_entity_types")] public List<string> SupportedEntityTypes { get; init; } = new();

        /// <summary>Real AutoCAD Transaction support. Boolean as of protocol 2.0.0.</summary>
        [JsonPropertyName("transaction_support")] public bool TransactionSupport { get; init; }

        /// <summary>Batch execution support. Boolean as of protocol 2.0.0.</summary>
        [JsonPropertyName("batch_support")] public bool BatchSupport { get; init; }

        /// <summary>Job-owned document token support. Boolean as of protocol 2.0.0.</summary>
        [JsonPropertyName("document_ownership_support")] public bool DocumentOwnershipSupport { get; init; }
        /// <summary>
        /// Dry-run support. Boolean as of protocol 2.0.0. May only be true once a real
        /// AutoCAD run has demonstrated that dry_run validates without locking, without
        /// starting a write transaction, and without changing the entity count.
        /// </summary>
        [JsonPropertyName("dry_run_support")] public bool DryRunSupport { get; init; }
        [JsonPropertyName("idempotency_support")] public string IdempotencySupport { get; init; } = CapabilityStatus.NotImplemented;

        /// <summary>Save / close / reopen lifecycle with verified persistence.</summary>
        [JsonPropertyName("persistence_support")] public bool PersistenceSupport { get; init; }

        /// <summary>Always NOT_AVAILABLE in S7. The plugin has no Tianzheng capability.</summary>
        [JsonPropertyName("tianzheng_support")] public string TianzhengSupport { get; init; } = CapabilityStatus.NotAvailable;

        /// <summary>
        /// Whether the host can accept protocol requests at all. This is a BOOLEAN and says
        /// nothing about CAD capability — read <see cref="ReadinessStateValue"/> for that.
        /// </summary>
        [JsonPropertyName("readiness")] public bool Readiness { get; init; } = true;

        /// <summary>Current real capability level (see <see cref="ReadinessState"/>).</summary>
        [JsonPropertyName("readiness_state")] public string ReadinessStateValue { get; init; } = ReadinessState.HandshakeOnly;

        /// <summary>Batch transaction semantics. Empty until batch support is real.</summary>
        [JsonPropertyName("batch_transaction_mode")] public string BatchTransactionMode { get; init; } = "";

        /// <summary>
        /// Build the S7.1-A snapshot.
        ///
        /// STAGE BOUNDARY: supported_operations and supported_entity_types are BOTH empty,
        /// because no CAD operation is implemented yet. health/capabilities are the
        /// protocol control surface, not a CAD capability, so they are not advertised here.
        /// </summary>
        public static PluginRuntimeInfo ForHostSkeleton(
            string sessionId, int processId, string autoCadVersion, string sessionNonce = "")
        {
            return new PluginRuntimeInfo
            {
                SessionId = sessionId,
                SessionNonce = sessionNonce,
                ProcessId = processId,
                AutoCadVersion = autoCadVersion,
                SupportedOperations = new List<string>(),
                SupportedEntityTypes = new List<string>(),
                TransactionSupport = false,
                BatchSupport = false,
                DocumentOwnershipSupport = false,
                DryRunSupport = false,
                IdempotencySupport = CapabilityStatus.NotImplemented,
                TianzhengSupport = CapabilityStatus.NotAvailable,
                ActiveDocumentStatus = DocumentStatus.NotTracked,
                Readiness = true,
                ReadinessStateValue = ReadinessState.HandshakeOnly,
                BatchTransactionMode = "",
            };
        }

        /// <summary>
        /// The verified S7.4 surface: the S7.2 entity MVP plus the save / close / reopen
        /// persistence lifecycle. Every entry here is exercised by the S7.4/S7.6 acceptance run.
        /// </summary>
        public static readonly IReadOnlyList<string> EntityMvpOperations = new List<string>
        {
            OperationType.BatchExecute,
            OperationType.Capabilities,
            OperationType.Close,
            OperationType.CreateCircle,
            OperationType.CreateLayer,
            OperationType.CreateLine,
            OperationType.CreatePolyline,
            OperationType.CreateSyntheticDocument,
            OperationType.Health,
            OperationType.QueryEntities,
            OperationType.Reopen,
            OperationType.Save,
        };

        public static readonly IReadOnlyList<string> EntityMvpEntityTypes = new List<string>
        {
            "circle", "line", "polyline",
        };

        /// <summary>
        /// The S7.2 capability snapshot.
        ///
        /// Every capability asserted here has been demonstrated against a real AutoCAD 2026
        /// session in the S7.2 acceptance run (job-owned synthetic document, DocumentLock,
        /// a single AutoCAD Transaction per batch, layer/line/circle/polyline creation,
        /// query read back from the database, and a genuine COMMIT and ABORT/ROLLBACK).
        ///
        /// This is stated directly in source rather than behind an environment switch:
        /// external environment is not acceptance evidence, and a build must not be able to
        /// advertise more capability than it was verified with. Anything NOT verified stays
        /// explicitly negative below.
        /// </summary>
        public static PluginRuntimeInfo ForEntityMvp(
            string sessionId, int processId, string autoCadVersion, string sessionNonce)
        {
            return new PluginRuntimeInfo
            {
                SessionId = sessionId,
                SessionNonce = sessionNonce,
                ProcessId = processId,
                AutoCadVersion = autoCadVersion,

                SupportedOperations = new List<string>(EntityMvpOperations),
                SupportedEntityTypes = new List<string>(EntityMvpEntityTypes),

                // --- verified against real AutoCAD ---
                TransactionSupport = true,
                BatchSupport = true,
                DocumentOwnershipSupport = true,
                BatchTransactionMode = "all_or_nothing",
                DryRunSupport = true,

                // Persistent idempotency: records live in the drawing's Named Objects
                // Dictionary and are written in the SAME transaction as the entities, so they
                // survive save/close/reopen and can never outlive a rolled-back batch.
                IdempotencySupport = CapabilityStatus.AvailableSandboxMvp,
                PersistenceSupport = true,

                // --- deliberately NOT claimed ---
                TianzhengSupport = CapabilityStatus.NotAvailable,

                ActiveDocumentStatus = DocumentStatus.NotTracked,
                Readiness = true,
                ReadinessStateValue = ReadinessState.EntityMvpAvailable,
            };
        }

        /// <summary>
        /// Serialize the handshake. <paramref name="includeSessionNonce"/> is true only for
        /// the capabilities response, which is how a client obtains the nonce it must then
        /// present on every non-handshake operation.
        /// </summary>
        public JsonElement ToJsonElement(bool includeSessionNonce = false)
        {
            JsonObject node = JsonSerializer.SerializeToNode(this, ProtocolJson.Options)!.AsObject();
            if (includeSessionNonce) node["session_nonce"] = SessionNonce;

            using JsonDocument doc = JsonDocument.Parse(node.ToJsonString());
            return doc.RootElement.Clone();
        }
    }
}
