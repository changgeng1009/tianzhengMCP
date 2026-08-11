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

        /// <summary>Every operation_type the protocol will ACCEPT (parse without UNKNOWN_OPERATION).</summary>
        public static readonly IReadOnlySet<string> All = new HashSet<string>
        {
            Health, Capabilities,
            CreateSyntheticDocument, CreateLayer, CreateLine, CreateCircle, CreatePolyline,
            QueryEntities, BatchExecute, Save, Close, Reopen, Shutdown,
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
