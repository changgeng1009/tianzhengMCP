using System.Collections.Generic;
using System.Text.Json;
using TianzhengCadPlugin.Protocol;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// Builds wire-shaped payloads for tests.
    /// NOTE: <see cref="ValidToken"/> is a TEST FIXTURE ONLY. It is never a default in
    /// production code — TokenProvider has no fallback whatsoever.
    /// </summary>
    internal static class TestRequests
    {
        public const string ValidToken = "test-token-0123456789abcdef0123456789abcdef";
        public const string TestNonce = "test-nonce-abcdef0123456789";

        /// <summary>Business request fields. Contains NO auth_token by design.</summary>
        public static Dictionary<string, object?> BaseFields(
            string operationType = OperationType.Health,
            string? sessionNonce = null)
        {
            var fields = new Dictionary<string, object?>
            {
                ["protocol_version"] = ProtocolConstants.ProtocolVersion,
                ["request_id"] = "req-1",
                ["job_id"] = "job-1",
                ["operation_id"] = "op-1",
                ["operation_type"] = operationType,
                ["document_context"] = new Dictionary<string, object?>(),
                ["parameters"] = new Dictionary<string, object?>(),
                ["idempotency_key"] = "idem-1",
                ["expected_capability"] = "autocad_plugin_backend",
                ["dry_run"] = false,
                ["timeout_ms"] = 5000,
                ["metadata"] = new Dictionary<string, object?>(),
            };
            if (sessionNonce != null) fields["session_nonce"] = sessionNonce;
            return fields;
        }

        public static string Json(Dictionary<string, object?> fields) => JsonSerializer.Serialize(fields);

        public static string Valid(
            string operationType = OperationType.Health,
            string? sessionNonce = null)
            => Json(BaseFields(operationType, sessionNonce));

        /// <summary>A non-handshake operation carrying the correct nonce.</summary>
        public static string ValidOperation(
            string operationType = OperationType.CreateLine,
            string sessionNonce = TestNonce)
            => Json(BaseFields(operationType, sessionNonce));

        public static string Without(string field)
        {
            Dictionary<string, object?> fields = BaseFields();
            fields.Remove(field);
            return Json(fields);
        }

        public static string WithExtra(string field, object? value)
        {
            Dictionary<string, object?> fields = BaseFields();
            fields[field] = value;
            return Json(fields);
        }

        public static string With(string field, object? value)
        {
            Dictionary<string, object?> fields = BaseFields();
            fields[field] = value;
            return Json(fields);
        }

        /// <summary>Connection-level auth handshake frame.</summary>
        public static string AuthFrame(string token = ValidToken) => AuthFrameParser.Build(token);
    }
}
