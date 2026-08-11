namespace TianzhengCadPlugin.Protocol
{
    /// <summary>Structured error codes. Never return a bare FAILED/ERROR/Exception.</summary>
    public static class ErrorCodes
    {
        public const string None = "";
        public const string FrameTooLarge = "FRAME_TOO_LARGE";
        public const string MalformedFrame = "MALFORMED_FRAME";
        public const string InvalidJson = "INVALID_JSON";
        public const string UnknownField = "UNKNOWN_FIELD";
        public const string MissingField = "MISSING_FIELD";
        public const string InvalidFieldType = "INVALID_FIELD_TYPE";
        public const string UnknownOperation = "UNKNOWN_OPERATION";
        public const string IncompatibleProtocolVersion = "INCOMPATIBLE_PROTOCOL_VERSION";

        /// <summary>Connection has not completed the auth handshake yet.</summary>
        public const string AuthRequired = "AUTH_REQUIRED";
        public const string AuthFailed = "AUTH_FAILED";

        /// <summary>Non-handshake operation supplied no session_nonce.</summary>
        public const string SessionNonceRequired = "SESSION_NONCE_REQUIRED";

        /// <summary>session_nonce did not match the current plugin session.</summary>
        public const string SessionNonceInvalid = "SESSION_NONCE_INVALID";
        public const string InvalidTimeout = "INVALID_TIMEOUT";
        public const string NotImplementedInStage = "NOT_IMPLEMENTED_IN_STAGE";
        public const string InternalError = "INTERNAL_ERROR";

        // --- S7.2: document ownership ---
        public const string DocumentTokenRequired = "DOCUMENT_TOKEN_REQUIRED";
        public const string DocumentTokenInvalid = "DOCUMENT_TOKEN_INVALID";
        public const string DocumentNotJobOwned = "DOCUMENT_NOT_JOB_OWNED";
        public const string DocumentSessionMismatch = "DOCUMENT_SESSION_MISMATCH";
        public const string DocumentJobMismatch = "DOCUMENT_JOB_MISMATCH";
        public const string DocumentDatabaseMismatch = "DOCUMENT_DATABASE_MISMATCH";
        public const string DocumentCreateFailed = "DOCUMENT_CREATE_FAILED";

        // --- S7.2: lock / transaction ---
        public const string DocumentLockFailed = "DOCUMENT_LOCK_FAILED";
        public const string TransactionStartFailed = "TRANSACTION_START_FAILED";
        public const string TransactionAborted = "TRANSACTION_ABORTED";
        public const string BatchRolledBack = "BATCH_ROLLED_BACK";

        // --- S7.4: persistence / sandbox ---
        public const string SandboxNotConfigured = "SANDBOX_NOT_CONFIGURED";
        public const string InvalidSandboxPath = "INVALID_SANDBOX_PATH";
        public const string PathTraversalRejected = "PATH_TRAVERSAL_REJECTED";
        public const string SandboxEscapeRejected = "SANDBOX_ESCAPE_REJECTED";
        public const string SaveFailed = "SAVE_FAILED";
        public const string CloseFailed = "CLOSE_FAILED";
        public const string ReopenFailed = "REOPEN_FAILED";
        public const string DocumentNotSaved = "DOCUMENT_NOT_SAVED";
        public const string DocumentAlreadyClosed = "DOCUMENT_ALREADY_CLOSED";

        // --- S7.4: persistent idempotency ---
        public const string IdempotencyConflict = "IDEMPOTENCY_CONFLICT";
        public const string IdempotencyKeyRequired = "IDEMPOTENCY_KEY_REQUIRED";

        // --- S7.2: entity ---
        public const string InvalidGeometry = "INVALID_GEOMETRY";
        public const string InvalidLayer = "INVALID_LAYER";
        public const string EntityCreateFailed = "ENTITY_CREATE_FAILED";
        public const string EntityQueryFailed = "ENTITY_QUERY_FAILED";
    }

    /// <summary>Pipeline stage at which a request was handled or rejected.</summary>
    public static class Stages
    {
        public const string Transport = "transport";
        public const string Authentication = "authentication";
        public const string Validation = "validation";
        public const string Scheduling = "scheduling";
        public const string Document = "document";
        public const string Transaction = "transaction";
        public const string Entity = "entity";
        public const string Save = "save";
        public const string Persistence = "persistence";
        public const string Idempotency = "idempotency";
        public const string Shutdown = "shutdown";
        public const string Handshake = "handshake";
    }

    /// <summary>Coarse plugin lifecycle state surfaced in responses.</summary>
    public static class PluginStates
    {
        public const string Starting = "STARTING";
        public const string Ready = "READY";
        public const string Draining = "DRAINING";
        public const string Stopped = "STOPPED";
    }

    /// <summary>Capability maturity levels. Never mark unverified capability as available.</summary>
    public static class CapabilityStatus
    {
        public const string NotImplemented = "NOT_IMPLEMENTED";
        public const string ImplementedNotVerified = "IMPLEMENTED_NOT_VERIFIED";
        public const string AvailableSandboxMvp = "AVAILABLE_SANDBOX_MVP";
        public const string NotAvailable = "NOT_AVAILABLE";
    }

    /// <summary>Outcome of the persistent idempotency check for a batch.</summary>
    public static class IdempotencyStatus
    {
        public const string NotApplicable = "not_applicable";

        /// <summary>First execution of this key; the batch ran and committed.</summary>
        public const string Applied = "APPLIED";

        /// <summary>
        /// The key was already committed to this document with the SAME plan hash, so the
        /// batch was skipped and the previously created handles are returned.
        /// </summary>
        public const string AlreadyApplied = "ALREADY_APPLIED";

        /// <summary>Same key, different plan hash. The batch is refused, not executed.</summary>
        public const string Conflict = "CONFLICT";
    }

    /// <summary>Readiness levels reported via <c>readiness_state</c>.</summary>
    public static class ReadinessState
    {
        /// <summary>Host answers protocol requests; no CAD capability verified.</summary>
        public const string HandshakeOnly = "READY_HANDSHAKE_ONLY";

        /// <summary>Entity MVP implemented but not yet verified in a real AutoCAD run.</summary>
        public const string EntityMvpUnverified = "IMPLEMENTED_NOT_VERIFIED_ENTITY_MVP";

        /// <summary>Entity MVP verified against real AutoCAD in a synthetic sandbox.</summary>
        public const string EntityMvpAvailable = "AVAILABLE_SANDBOX_ENTITY_MVP";
    }

    /// <summary>Per-operation / per-document lifecycle statuses used in responses.</summary>
    public static class DocumentStatus
    {
        public const string None = "none";
        public const string NotTracked = "NOT_TRACKED";
        public const string JobOwnedSynthetic = "JOB_OWNED_SYNTHETIC";
    }

    public static class TransactionStatus
    {
        public const string None = "none";
        public const string Committed = "COMMITTED";
        public const string Aborted = "ABORTED";
        public const string NotStarted = "NOT_STARTED";
        public const string DryRun = "DRY_RUN_NOT_STARTED";
    }

    public static class RollbackStatus
    {
        public const string NotApplicable = "NOT_APPLICABLE";
        public const string RolledBack = "ROLLED_BACK";
    }

    public static class EntityStatus
    {
        public const string None = "none";
        public const string Created = "CREATED";
        public const string Existing = "EXISTING_EQUIVALENT";
        public const string Queried = "QUERIED";
        public const string NotCreated = "NOT_CREATED";

        /// <summary>
        /// The operation executed inside the transaction but the transaction was aborted,
        /// so nothing persisted. Distinct from NOT_CREATED (never executed) and from
        /// FAILED (this operation is what caused the abort).
        /// </summary>
        public const string RolledBack = "ROLLED_BACK";

        /// <summary>This operation failed and caused the batch to abort.</summary>
        public const string Failed = "FAILED";
    }

    /// <summary>
    /// What physically happened to an operation, independent of whether it committed.
    /// <c>success</c> answers "did the effect commit?"; this answers "how far did it get?".
    /// </summary>
    public static class ExecutionStatus
    {
        public const string NotExecuted = "NOT_EXECUTED";
        public const string Committed = "EXECUTED_AND_COMMITTED";
        public const string RolledBack = "EXECUTED_THEN_ROLLED_BACK";
        public const string Failed = "EXECUTION_FAILED";
        public const string DryRunValidated = "DRY_RUN_VALIDATED_NOT_EXECUTED";
    }
}
