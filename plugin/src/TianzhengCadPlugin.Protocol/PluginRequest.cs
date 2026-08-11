using System.Collections.Generic;
using System.Text.Json;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// Validated inbound request. Instances are only produced by
    /// <see cref="RequestValidator"/>, so every instance already satisfies the
    /// required-field, known-field, known-operation and version checks.
    /// </summary>
    public sealed class PluginRequest
    {
        public string ProtocolVersion { get; init; } = "";
        public string RequestId { get; init; } = "";
        public string JobId { get; init; } = "";
        public string OperationId { get; init; } = "";
        public string OperationType { get; init; } = "";

        /// <summary>
        /// Opaque document context (document_token etc.). NOT interpreted in S7.1-A:
        /// no document is created, opened, or written in this stage.
        /// </summary>
        public JsonElement DocumentContext { get; init; }

        public JsonElement Parameters { get; init; }
        public string IdempotencyKey { get; init; } = "";
        public string ExpectedCapability { get; init; } = "";
        public bool DryRun { get; init; }
        public int TimeoutMs { get; init; } = ProtocolConstants.DefaultTimeoutMs;
        public JsonElement Metadata { get; init; }

        /// <summary>
        /// Session nonce returned by <c>capabilities</c>. Required for every operation
        /// except the health/capabilities handshake. This is NOT a secret and is never a
        /// substitute for the connection-level token.
        /// </summary>
        public string? SessionNonce { get; init; }

        /// <summary>
        /// Exact wire field names accepted. Anything else is UNKNOWN_FIELD.
        /// NOTE: there is deliberately NO auth_token field — the token lives only in the
        /// connection handshake (<see cref="AuthFrame"/>), never in a business request.
        /// </summary>
        public static readonly IReadOnlySet<string> AllowedFields = new HashSet<string>
        {
            "protocol_version", "request_id", "job_id", "operation_id", "operation_type",
            "document_context", "parameters", "idempotency_key", "expected_capability",
            "dry_run", "timeout_ms", "metadata", "session_nonce",
        };

        /// <summary>Fields that must be present. Absence is MISSING_FIELD.</summary>
        public static readonly IReadOnlyList<string> RequiredFields = new List<string>
        {
            "protocol_version", "request_id", "job_id", "operation_id", "operation_type",
            "document_context", "parameters", "idempotency_key", "expected_capability",
            "dry_run", "timeout_ms", "metadata",
        };
    }
}
