using System;
using System.Threading;
using System.Threading.Tasks;
using TianzhengCadPlugin.Transport;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// Test-only stand-in for the AutoCAD main-thread pump.
    ///
    /// It drains the OperationQueue on a background thread using the SAME
    /// <see cref="IOperationExecutor"/> the real MainThreadDispatcher uses, so the stage
    /// behaviour (NOT_IMPLEMENTED_IN_STAGE) is exercised through the real code path.
    ///
    /// IMPORTANT: this is NOT AutoCAD, and results obtained through it must never be
    /// presented as AutoCAD integration evidence. It only substitutes for the
    /// Application.Idle tick, which cannot fire outside acad.exe.
    /// </summary>
    internal sealed class QueuePump : IDisposable
    {
        private readonly OperationQueue _queue;
        private readonly IOperationExecutor _executor;
        private readonly CancellationTokenSource _cts = new();
        private readonly Task _loop;

        public QueuePump(OperationQueue queue, IOperationExecutor? executor = null)
        {
            _queue = queue;
            _executor = executor ?? new StageNotImplementedExecutor();
            _loop = Task.Run(PumpAsync);
        }

        private async Task PumpAsync()
        {
            while (!_cts.IsCancellationRequested)
            {
                if (_queue.TryDequeue(out QueuedOperation? op) && op != null)
                {
                    op.Complete(_executor.Execute(op.Request));
                    continue;
                }
                try { await Task.Delay(5, _cts.Token); }
                catch (OperationCanceledException) { return; }
            }
        }

        public void Dispose()
        {
            _cts.Cancel();
            try { _loop.Wait(TimeSpan.FromSeconds(2)); } catch (AggregateException) { }
            _cts.Dispose();
        }
    }
}
