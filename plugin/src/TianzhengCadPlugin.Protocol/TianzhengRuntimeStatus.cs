using System.Collections.Generic;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// What the plugin found when it looked for Tianzheng in its own process.
    ///
    /// This is filled in from a live runtime class probe at plugin start, never from
    /// configuration or an environment variable, because "someone told us Tianzheng is here"
    /// is not evidence. A plain AutoCAD session therefore reports Loaded = false and the
    /// create path refuses to run rather than silently degrading to ordinary entities.
    /// </summary>
    public sealed class TianzhengRuntimeStatus
    {
        public bool Loaded { get; init; }
        public string Product { get; init; } = "";
        public string Version { get; init; } = "";

        /// <summary>Tianzheng is loaded AND the classes native work depends on are registered.</summary>
        public bool RuntimeAvailable { get; init; }

        public bool TdbPipeAvailable { get; init; }

        /// <summary>Empty unless the runtime is genuinely available.</summary>
        public IReadOnlyList<string> Operations { get; init; } = new List<string>();

        /// <summary>The honest default: assume nothing is there until a probe says otherwise.</summary>
        public static readonly TianzhengRuntimeStatus NotLoaded = new();

        /// <summary>Operations the plugin can serve once the Tianzheng runtime is confirmed.</summary>
        public static readonly IReadOnlyList<string> PipeOperations = new List<string>
        {
            OperationType.TianzhengCreatePipe,
            OperationType.TianzhengQueryPipe,
            OperationType.TianzhengValidatePipeIdentity,
            OperationType.TianzhengPipeInventory,
        };
    }
}
