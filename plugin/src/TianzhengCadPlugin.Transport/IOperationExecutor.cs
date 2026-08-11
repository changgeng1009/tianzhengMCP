using TianzhengCadPlugin.Protocol;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>
    /// Executes one dequeued operation. Implementations are invoked ONLY from the AutoCAD
    /// main thread by MainThreadDispatcher.
    /// </summary>
    public interface IOperationExecutor
    {
        PluginResponse Execute(PluginRequest request);
    }

    /// <summary>
    /// The S7.1-A executor: no CAD operation is implemented in this stage, so every queued
    /// operation is answered with a structured NOT_IMPLEMENTED_IN_STAGE.
    ///
    /// It never returns success and never touches an AutoCAD Document or Database — it has
    /// no AutoCAD reference at all, which is what makes the stage boundary testable.
    /// </summary>
    public sealed class StageNotImplementedExecutor : IOperationExecutor
    {
        private readonly string _stageName;

        public StageNotImplementedExecutor(string stageName = "S7.1-A") => _stageName = stageName;

        public PluginResponse Execute(PluginRequest request)
        {
            return new PluginResponse
            {
                Success = false,
                ErrorCode = ErrorCodes.NotImplementedInStage,
                Stage = Stages.Scheduling,
                RequestId = request.RequestId,
                OperationId = request.OperationId,
                Retryable = false,
                TransactionStatus = "none",
                DocumentStatus = "none",
                SanitizedMessage =
                    $"operation '{request.OperationType}' is accepted by the protocol but not implemented in stage {_stageName}",
                PluginState = PluginStates.Ready,
            };
        }
    }
}
