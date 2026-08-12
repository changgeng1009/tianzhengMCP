namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// Structured failure codes for the Tianzheng native pipe surface.
    ///
    /// A bare FAILED is never acceptable: the caller has to be able to tell "the drawing has no
    /// such pipe" from "the object is no longer native" from "saving went wrong", because those
    /// three lead to completely different responses.
    /// </summary>
    public static class TianzhengErrorCodes
    {
        /// <summary>The requested handle or identity does not resolve in this drawing.</summary>
        public const string PipeNotFound = "TIANZHENG_PIPE_NOT_FOUND";

        /// <summary>An object was found but is not a live native TDbPipe (wrong class, or a proxy).</summary>
        public const string NativeIdentityMismatch = "TIANZHENG_PIPE_NATIVE_IDENTITY_MISMATCH";

        /// <summary>The property exists on the object but no readable route to it exists yet.</summary>
        public const string PropertyUnavailable = "TIANZHENG_PIPE_PROPERTY_UNAVAILABLE";

        public const string SaveFailed = "TIANZHENG_PIPE_SAVE_FAILED";
        public const string ReopenFailed = "TIANZHENG_PIPE_REOPEN_FAILED";

        /// <summary>The object did not survive the save/close/reopen round trip as a native object.</summary>
        public const string PersistenceFailed = "TIANZHENG_PIPE_PERSISTENCE_FAILED";

        /// <summary>The idempotency key was reused for a materially different pipe.</summary>
        public const string IdempotencyConflict = "TIANZHENG_PIPE_IDEMPOTENCY_CONFLICT";
    }
}
