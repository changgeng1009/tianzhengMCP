namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// Wire-level constants shared by plugin (C#) and backend (Python).
    /// Keep in lockstep with the Python <c>plugin_protocol</c> module.
    /// </summary>
    public static class ProtocolConstants
    {
        /// <summary>
        /// Semantic protocol version. Requests with an incompatible MAJOR are rejected.
        ///
        /// 1.0.0 -> 2.0.0 (S7.2). Response-side schema changes:
        ///   * CHANGED `readiness` from string ("READY_HANDSHAKE_ONLY") to BOOLEAN;
        ///   * ADDED   `readiness_state` (string) carrying the real capability level;
        ///   * ADDED   `batch_transaction_mode` (string);
        ///   * ADDED   `document_ownership_support` (string).
        ///
        /// The `readiness` type change is a BREAKING wire change: a 1.x client that read
        /// `readiness` as a string cannot parse a 2.x response. Semantic versioning therefore
        /// requires a MAJOR bump, and an interim 1.1.0 would have mislabelled a breaking
        /// change as additive. 1.x requests are now rejected outright with
        /// INCOMPATIBLE_PROTOCOL_VERSION rather than served a response they cannot read.
        ///
        /// This is a plugin-transport version only. It does not touch the S6 Contract, whose
        /// own schema version is independent and unchanged.
        /// </summary>
        public const string ProtocolVersion = "2.0.0";

        /// <summary>Capability set version surfaced in the handshake.</summary>
        public const string CapabilityVersion = "s7.2-entity-mvp";

        /// <summary>Plugin build version surfaced in the handshake / responses.</summary>
        public const string PluginVersion = "0.2.0-s7.2";

        /// <summary>Length-prefix header size in bytes (unsigned 32-bit, big-endian).</summary>
        public const int FrameHeaderBytes = 4;

        /// <summary>
        /// Hard maximum size of a single JSON payload, in bytes. A declared length
        /// larger than this is rejected BEFORE any body bytes are read.
        /// </summary>
        public const int MaxPayloadBytes = 1 * 1024 * 1024; // 1 MiB

        /// <summary>Loopback-only bind address. The listener never binds any other interface.</summary>
        public const string BindAddress = "127.0.0.1";

        /// <summary>Default per-request handling timeout (milliseconds) when a request omits one.</summary>
        public const int DefaultTimeoutMs = 15_000;

        /// <summary>Upper bound for a caller-supplied timeout_ms.</summary>
        public const int MaxTimeoutMs = 120_000;
    }
}
