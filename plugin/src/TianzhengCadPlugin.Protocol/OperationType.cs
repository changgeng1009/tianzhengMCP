using System.Collections.Generic;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// Strict operation whitelist. Any operation_type not in <see cref="All"/> is rejected
    /// with UNKNOWN_OPERATION. Operation NAMES mirror the S6 lifecycle/plan vocabulary so the
    /// plugin adapts to S6 rather than the reverse. There is no arbitrary/passthrough op.
    /// </summary>
    public static class OperationType
    {
        // --- Read-only / control (available in S7.1-A) ---
        public const string Health = "health";
        public const string Capabilities = "capabilities";

        // --- Declared for the protocol surface but NOT executable in S7.1-A ---
        // (host returns a structured NOT_IMPLEMENTED_IN_STAGE result; no AutoCAD access)
        public const string CreateSyntheticDocument = "create_synthetic_document";
        public const string CreateLayer = "create_layer";
        public const string CreateLine = "create_line";
        public const string CreateCircle = "create_circle";
        public const string CreatePolyline = "create_polyline";
        public const string QueryEntities = "query_entities";
        public const string BatchExecute = "batch_execute";
        public const string Save = "save";
        public const string Close = "close";
        public const string Reopen = "reopen";
        public const string Shutdown = "shutdown";

        /// <summary>
        /// S8 read-only diagnostic: resolve a runtime (RX) class by name from the live AutoCAD
        /// process. Creates nothing, opens no document, mutates no database. It exists to prove
        /// whether a native class such as Tianzheng's TDbPipe is actually registered, rather
        /// than inferring it from binary strings.
        /// </summary>
        public const string DiagnosticQueryRxClass = "diagnostic_query_rxclass";

        /// <summary>
        /// S8 read-only diagnostic: snapshot model space (handles + runtime classes) so a
        /// creation attempt can be judged by an actual before/after database difference rather
        /// than by what appeared on screen.
        /// </summary>
        public const string DiagnosticScanDatabase = "diagnostic_scan_database";

        /// <summary>
        /// S8.1 proof-of-concept: create one native Tianzheng pipe by invoking Tianzheng's own
        /// fixed creation command. The command name is a compile-time constant and the only
        /// caller-supplied values are two coordinates; there is no command-string, LISP or
        /// passthrough surface behind this operation.
        /// </summary>
        public const string DiagnosticCreateNativePipe = "diagnostic_create_native_pipe";

        /// <summary>Read the outcome of the queued creation PoC (it runs in AutoCAD's own command context).</summary>
        public const string DiagnosticNativePipeResult = "diagnostic_native_pipe_result";

        // --- S8.2 TianzhengBackend minimal surface -------------------------------------------
        // Structured pipe parameters only. No command name, command text, LISP or keystrokes
        // cross this boundary: the Tianzheng command is an internal implementation detail of
        // the creation adapter.

        /// <summary>Create one native Tianzheng pipe from a structured spec, honouring idempotency_key.</summary>
        public const string TianzhengCreatePipe = "tianzheng_create_pipe";

        /// <summary>Query one native pipe by handle. Returns a snapshot, never a DBObject or native pointer.</summary>
        public const string TianzhengQueryPipe = "tianzheng_query_pipe";

        /// <summary>Re-validate that a handle still denotes a live native TDbPipe.</summary>
        public const string TianzhengValidatePipeIdentity = "tianzheng_validate_pipe_identity";

        /// <summary>Count native pipes and their related fittings, so replay can prove no duplicates.</summary>
        public const string TianzhengPipeInventory = "tianzheng_pipe_inventory";

        /// <summary>Every operation_type the protocol will ACCEPT (parse without UNKNOWN_OPERATION).</summary>
        public static readonly IReadOnlySet<string> All = new HashSet<string>
        {
            Health, Capabilities,
            CreateSyntheticDocument, CreateLayer, CreateLine, CreateCircle, CreatePolyline,
            QueryEntities, BatchExecute, Save, Close, Reopen, Shutdown,
            DiagnosticQueryRxClass, DiagnosticScanDatabase,
            DiagnosticCreateNativePipe, DiagnosticNativePipeResult,
            TianzhengCreatePipe, TianzhengQueryPipe,
            TianzhengValidatePipeIdentity, TianzhengPipeInventory,
        };

        /// <summary>Operations actually IMPLEMENTED and answerable in S7.1-A (read-only host skeleton).</summary>
        public static readonly IReadOnlySet<string> ImplementedInStage = new HashSet<string>
        {
            Health, Capabilities,
        };

        public static bool IsKnown(string? op) => op != null && All.Contains(op);

        public static bool IsImplementedInStage(string? op) => op != null && ImplementedInStage.Contains(op);
    }
}
