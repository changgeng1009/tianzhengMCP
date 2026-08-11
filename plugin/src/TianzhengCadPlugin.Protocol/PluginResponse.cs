using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// Structured response. Every field in the S7 response contract is always emitted,
    /// so the Python backend can rely on a stable shape. Never emits a bare FAILED/ERROR,
    /// and never carries tokens, secrets, full user paths, stack traces or drawing content.
    /// </summary>
    public sealed class PluginResponse
    {
        [JsonPropertyName("success")] public bool Success { get; set; }
        [JsonPropertyName("error_code")] public string ErrorCode { get; set; } = ErrorCodes.None;
        [JsonPropertyName("stage")] public string Stage { get; set; } = Stages.Transport;
        [JsonPropertyName("request_id")] public string RequestId { get; set; } = "";
        [JsonPropertyName("operation_id")] public string OperationId { get; set; } = "";
        [JsonPropertyName("entity_ids")] public List<string> EntityIds { get; set; } = new();
        [JsonPropertyName("handles")] public List<string> Handles { get; set; } = new();
        [JsonPropertyName("created_count")] public int CreatedCount { get; set; }
        [JsonPropertyName("modified_count")] public int ModifiedCount { get; set; }
        [JsonPropertyName("skipped_count")] public int SkippedCount { get; set; }
        [JsonPropertyName("idempotency_status")] public string IdempotencyStatus { get; set; } = "not_applicable";
        [JsonPropertyName("warnings")] public List<string> Warnings { get; set; } = new();
        [JsonPropertyName("duration_ms")] public long DurationMs { get; set; }
        [JsonPropertyName("plugin_version")] public string PluginVersion { get; set; } = ProtocolConstants.PluginVersion;
        [JsonPropertyName("capability_version")] public string CapabilityVersion { get; set; } = ProtocolConstants.CapabilityVersion;
        [JsonPropertyName("retryable")] public bool Retryable { get; set; }
        [JsonPropertyName("transaction_status")] public string TransactionStatus { get; set; } = "none";
        [JsonPropertyName("document_status")] public string DocumentStatus { get; set; } = "none";
        [JsonPropertyName("plugin_state")] public string PluginState { get; set; } = PluginStates.Ready;

        /// <summary>Operator-safe message. Must never include secrets, paths, or stack traces.</summary>
        [JsonPropertyName("sanitized_message")] public string SanitizedMessage { get; set; } = "";

        /// <summary>Optional payload for read-only operations (health / capabilities).</summary>
        [JsonPropertyName("result")] public JsonElement? Result { get; set; }

        public static PluginResponse Failure(
            string errorCode,
            string stage,
            string sanitizedMessage,
            string requestId = "",
            string operationId = "",
            bool retryable = false,
            string pluginState = PluginStates.Ready)
        {
            return new PluginResponse
            {
                Success = false,
                ErrorCode = errorCode,
                Stage = stage,
                RequestId = requestId,
                OperationId = operationId,
                Retryable = retryable,
                SanitizedMessage = sanitizedMessage,
                PluginState = pluginState,
            };
        }

        /// <summary>
        /// Response for a connection that has not completed the auth handshake.
        ///
        /// Deliberately starved of information: no result payload, no plugin/capability
        /// version, no plugin state, and a fixed generic message. An unauthenticated caller
        /// therefore cannot enumerate fields or operations, or probe internal state, and
        /// cannot distinguish "bad frame" from "bad token".
        /// </summary>
        public static PluginResponse Unauthenticated(string errorCode)
        {
            return new PluginResponse
            {
                Success = false,
                ErrorCode = errorCode,
                Stage = Stages.Authentication,
                RequestId = "",
                OperationId = "",
                Retryable = false,
                SanitizedMessage = "authentication required",
                PluginVersion = "",
                CapabilityVersion = "",
                PluginState = "",
                IdempotencyStatus = "not_applicable",
                TransactionStatus = "none",
                DocumentStatus = "none",
                Result = null,
            };
        }

        public static PluginResponse Ok(
            string requestId,
            string operationId,
            string stage,
            JsonElement? result = null,
            string pluginState = PluginStates.Ready)
        {
            return new PluginResponse
            {
                Success = true,
                ErrorCode = ErrorCodes.None,
                Stage = stage,
                RequestId = requestId,
                OperationId = operationId,
                Result = result,
                PluginState = pluginState,
            };
        }

        public string ToJson() => JsonSerializer.Serialize(this, ProtocolJson.Options);
    }

    /// <summary>Single shared serializer configuration.</summary>
    public static class ProtocolJson
    {
        public static readonly JsonSerializerOptions Options = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            WriteIndented = false,
        };
    }
}
