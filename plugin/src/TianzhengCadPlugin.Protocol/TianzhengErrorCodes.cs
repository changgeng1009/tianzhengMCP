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
        /// <summary>
        /// This AutoCAD session has no Tianzheng runtime. Native work refuses to run rather
        /// than silently degrading to an ordinary Polyline, which would be a fake.
        /// </summary>
        public const string NotLoaded = "TIANZHENG_NOT_LOADED";

        /// <summary>Tianzheng is loaded but the required native class is not registered.</summary>
        public const string NativeClassNotFound = "TIANZHENG_NATIVE_CLASS_NOT_FOUND";

        /// <summary>The creation adapter ran but did not produce a native pipe.</summary>
        public const string PipeCreateFailed = "TIANZHENG_PIPE_CREATE_FAILED";

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
