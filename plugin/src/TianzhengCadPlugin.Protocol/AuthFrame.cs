using System.Collections.Generic;
using System.Text.Json;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// The connection-level authentication handshake frame.
    ///
    /// WIRE FLOW: the token travels ONLY in this frame, which must be the FIRST frame on
    /// every connection. It is not part of the business request envelope, so
    /// <see cref="PluginRequest"/> has no token field at all and a token can never reach
    /// business metadata, the operation queue, or the AutoCAD main thread.
    ///
    /// Until this frame is accepted the connection is unauthenticated and the server
    /// performs NO business validation, so an unauthenticated caller cannot enumerate
    /// fields, operations, capabilities or plugin state.
    /// </summary>
    public sealed class AuthFrame
    {
        public const string FrameType = "auth";

        public string AuthToken { get; init; } = "";
        public string ProtocolVersion { get; init; } = "";

        public static readonly IReadOnlySet<string> AllowedFields = new HashSet<string>
        {
            "type", "auth_token", "protocol_version",
        };
    }

    /// <summary>
    /// Parses the auth frame.
    ///
    /// Deliberately returns only a boolean: every failure mode (bad JSON, wrong type,
    /// unknown field, missing token, bad version) is indistinguishable to the caller, so
    /// the handshake cannot be used as an oracle to probe the schema.
    /// </summary>
    public static class AuthFrameParser
    {
        public static bool TryParse(string json, out AuthFrame frame)
        {
            frame = new AuthFrame();

            JsonDocument doc;
            try { doc = JsonDocument.Parse(json); }
            catch (JsonException) { return false; }

            using (doc)
            {
                JsonElement root = doc.RootElement;
                if (root.ValueKind != JsonValueKind.Object) return false;

                foreach (JsonProperty prop in root.EnumerateObject())
                {
                    if (!AuthFrame.AllowedFields.Contains(prop.Name)) return false;
                }

                if (!root.TryGetProperty("type", out JsonElement typeEl)
                    || typeEl.ValueKind != JsonValueKind.String
                    || typeEl.GetString() != AuthFrame.FrameType)
                {
                    return false;
                }

                if (!root.TryGetProperty("auth_token", out JsonElement tokenEl)
                    || tokenEl.ValueKind != JsonValueKind.String)
                {
                    return false;
                }

                string protocolVersion = ProtocolConstants.ProtocolVersion;
                if (root.TryGetProperty("protocol_version", out JsonElement versionEl))
                {
                    if (versionEl.ValueKind != JsonValueKind.String) return false;
                    protocolVersion = versionEl.GetString() ?? "";
                    if (!RequestValidator.IsCompatibleProtocolVersion(protocolVersion)) return false;
                }

                frame = new AuthFrame
                {
                    AuthToken = tokenEl.GetString() ?? "",
                    ProtocolVersion = protocolVersion,
                };
                return true;
            }
        }

        /// <summary>Build the auth frame payload (used by clients and tests).</summary>
        public static string Build(string authToken, string? protocolVersion = null)
        {
            return JsonSerializer.Serialize(new Dictionary<string, object?>
            {
                ["type"] = AuthFrame.FrameType,
                ["auth_token"] = authToken,
                ["protocol_version"] = protocolVersion ?? ProtocolConstants.ProtocolVersion,
            });
        }
    }
}
