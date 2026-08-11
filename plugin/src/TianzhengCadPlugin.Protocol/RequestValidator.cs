using System;
using System.Text.Json;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>Either a validated request, or the structured rejection to send back.</summary>
    public readonly struct ValidationOutcome
    {
        public PluginRequest? Request { get; }
        public PluginResponse? Rejection { get; }
        public bool IsValid => Request != null;

        private ValidationOutcome(PluginRequest? request, PluginResponse? rejection)
        {
            Request = request;
            Rejection = rejection;
        }

        public static ValidationOutcome Valid(PluginRequest request) => new(request, null);
        public static ValidationOutcome Invalid(PluginResponse rejection) => new(null, rejection);
    }

    /// <summary>
    /// Fail-closed request validation. Rejects, in order: malformed JSON, non-object roots,
    /// UNKNOWN fields, MISSING required fields, wrong field types, incompatible protocol
    /// versions, unknown operation_type, and out-of-range timeouts.
    ///
    /// There is no passthrough/eval/command field anywhere in the accepted schema, so no
    /// arbitrary code, LISP, script or command string can be expressed by a valid request.
    /// </summary>
    public static class RequestValidator
    {
        public static ValidationOutcome Validate(string json)
        {
            JsonDocument doc;
            try
            {
                doc = JsonDocument.Parse(json);
            }
            catch (JsonException)
            {
                return Reject(ErrorCodes.InvalidJson, "request payload is not valid JSON");
            }

            using (doc)
            {
                JsonElement root = doc.RootElement;
                if (root.ValueKind != JsonValueKind.Object)
                {
                    return Reject(ErrorCodes.InvalidJson, "request root must be a JSON object");
                }

                // --- Unknown fields: reject by default ---
                foreach (JsonProperty prop in root.EnumerateObject())
                {
                    if (!PluginRequest.AllowedFields.Contains(prop.Name))
                    {
                        return Reject(ErrorCodes.UnknownField, $"unknown field '{Sanitize(prop.Name)}'");
                    }
                }

                // --- Required fields present ---
                foreach (string required in PluginRequest.RequiredFields)
                {
                    if (!root.TryGetProperty(required, out _))
                    {
                        return Reject(ErrorCodes.MissingField, $"missing required field '{required}'");
                    }
                }

                // --- Types ---
                if (!TryGetString(root, "protocol_version", out string protocolVersion))
                    return Reject(ErrorCodes.InvalidFieldType, "protocol_version must be a string");
                if (!TryGetString(root, "request_id", out string requestId))
                    return Reject(ErrorCodes.InvalidFieldType, "request_id must be a string");
                if (!TryGetString(root, "job_id", out string jobId))
                    return Reject(ErrorCodes.InvalidFieldType, "job_id must be a string");
                if (!TryGetString(root, "operation_id", out string operationId))
                    return Reject(ErrorCodes.InvalidFieldType, "operation_id must be a string");
                if (!TryGetString(root, "operation_type", out string operationType))
                    return Reject(ErrorCodes.InvalidFieldType, "operation_type must be a string");
                if (!TryGetString(root, "idempotency_key", out string idempotencyKey))
                    return Reject(ErrorCodes.InvalidFieldType, "idempotency_key must be a string");
                if (!TryGetString(root, "expected_capability", out string expectedCapability))
                    return Reject(ErrorCodes.InvalidFieldType, "expected_capability must be a string");

                JsonElement dryRunEl = root.GetProperty("dry_run");
                if (dryRunEl.ValueKind != JsonValueKind.True && dryRunEl.ValueKind != JsonValueKind.False)
                    return Reject(ErrorCodes.InvalidFieldType, "dry_run must be a boolean");

                JsonElement timeoutEl = root.GetProperty("timeout_ms");
                if (timeoutEl.ValueKind != JsonValueKind.Number || !timeoutEl.TryGetInt32(out int timeoutMs))
                    return Reject(ErrorCodes.InvalidFieldType, "timeout_ms must be an integer");

                if (!IsObjectOrNull(root.GetProperty("document_context")))
                    return Reject(ErrorCodes.InvalidFieldType, "document_context must be an object or null");
                if (!IsObjectOrNull(root.GetProperty("parameters")))
                    return Reject(ErrorCodes.InvalidFieldType, "parameters must be an object or null");
                if (!IsObjectOrNull(root.GetProperty("metadata")))
                    return Reject(ErrorCodes.InvalidFieldType, "metadata must be an object or null");

                string? sessionNonce = null;
                if (root.TryGetProperty("session_nonce", out JsonElement nonceEl))
                {
                    if (nonceEl.ValueKind == JsonValueKind.String) sessionNonce = nonceEl.GetString();
                    else if (nonceEl.ValueKind != JsonValueKind.Null)
                        return Reject(ErrorCodes.InvalidFieldType, "session_nonce must be a string or null");
                }

                // --- Semantic checks ---
                if (requestId.Length == 0)
                    return Reject(ErrorCodes.MissingField, "request_id must not be empty");

                if (!IsCompatibleProtocolVersion(protocolVersion))
                {
                    return Reject(
                        ErrorCodes.IncompatibleProtocolVersion,
                        $"protocol_version '{Sanitize(protocolVersion)}' is incompatible with '{ProtocolConstants.ProtocolVersion}'",
                        requestId, operationId);
                }

                if (!OperationType.IsKnown(operationType))
                {
                    return Reject(
                        ErrorCodes.UnknownOperation,
                        $"operation_type '{Sanitize(operationType)}' is not in the whitelist",
                        requestId, operationId);
                }

                if (timeoutMs <= 0 || timeoutMs > ProtocolConstants.MaxTimeoutMs)
                {
                    return Reject(
                        ErrorCodes.InvalidTimeout,
                        $"timeout_ms must be in (0, {ProtocolConstants.MaxTimeoutMs}]",
                        requestId, operationId);
                }

                var request = new PluginRequest
                {
                    ProtocolVersion = protocolVersion,
                    RequestId = requestId,
                    JobId = jobId,
                    OperationId = operationId,
                    OperationType = operationType,
                    DocumentContext = Clone(root.GetProperty("document_context")),
                    Parameters = Clone(root.GetProperty("parameters")),
                    IdempotencyKey = idempotencyKey,
                    ExpectedCapability = expectedCapability,
                    DryRun = dryRunEl.ValueKind == JsonValueKind.True,
                    TimeoutMs = timeoutMs,
                    Metadata = Clone(root.GetProperty("metadata")),
                    SessionNonce = sessionNonce,
                };
                return ValidationOutcome.Valid(request);
            }
        }

        /// <summary>Compatible when the MAJOR component matches exactly.</summary>
        public static bool IsCompatibleProtocolVersion(string candidate)
        {
            if (string.IsNullOrWhiteSpace(candidate)) return false;
            string candidateMajor = candidate.Split('.')[0];
            string currentMajor = ProtocolConstants.ProtocolVersion.Split('.')[0];
            return candidateMajor == currentMajor;
        }

        private static bool TryGetString(JsonElement root, string name, out string value)
        {
            JsonElement el = root.GetProperty(name);
            if (el.ValueKind == JsonValueKind.String)
            {
                value = el.GetString() ?? "";
                return true;
            }
            value = "";
            return false;
        }

        private static bool IsObjectOrNull(JsonElement el) =>
            el.ValueKind == JsonValueKind.Object || el.ValueKind == JsonValueKind.Null;

        // JsonDocument is disposed with the using-block; detach a standalone copy.
        private static JsonElement Clone(JsonElement el) => el.Clone();

        /// <summary>Bound and strip echoed input so responses can't be used to reflect payloads.</summary>
        private static string Sanitize(string value)
        {
            const int max = 64;
            string trimmed = value.Length > max ? value.Substring(0, max) + "..." : value;
            return trimmed.Replace('\r', ' ').Replace('\n', ' ').Replace('"', '\'');
        }

        private static ValidationOutcome Reject(
            string code, string message, string requestId = "", string operationId = "")
        {
            return ValidationOutcome.Invalid(PluginResponse.Failure(
                code, Stages.Validation, message, requestId, operationId, retryable: false));
        }
    }
}
