using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using TianzhengCadPlugin.Protocol;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>A validated request awaiting execution on the AutoCAD main thread.</summary>
    public sealed class QueuedOperation
    {
        public PluginRequest Request { get; }
        public DateTimeOffset EnqueuedAt { get; }
        private readonly TaskCompletionSource<PluginResponse> _completion;

        public QueuedOperation(PluginRequest request, DateTimeOffset enqueuedAt)
        {
            Request = request;
            EnqueuedAt = enqueuedAt;
            // RunContinuationsAsynchronously: never resume transport continuations
            // inline on the AutoCAD main thread.
            _completion = new TaskCompletionSource<PluginResponse>(
                TaskCreationOptions.RunContinuationsAsynchronously);
        }

        public Task<PluginResponse> Completion => _completion.Task;

        /// <summary>Called by the main-thread dispatcher when the operation finishes.</summary>
        public void Complete(PluginResponse response) => _completion.TrySetResult(response);
    }

    /// <summary>
    /// The single hand-off point between the transport thread and the AutoCAD main thread.
    ///
    /// The transport thread ONLY enqueues; it never executes CAD work. The AutoCAD main
    /// thread is the only consumer (see MainThreadDispatcher), which is what keeps every
    /// AutoCAD API call on the correct thread.
    /// </summary>
    public sealed class OperationQueue
    {
        private readonly ConcurrentQueue<QueuedOperation> _queue = new();
        private readonly int _maxDepth;

        public OperationQueue(int maxDepth = 64) => _maxDepth = maxDepth;

        public int Count => _queue.Count;

        /// <summary>
        /// Enqueue for main-thread execution. Returns false when the queue is saturated,
        /// which the caller surfaces as a retryable back-pressure error.
        /// </summary>
        public bool TryEnqueue(QueuedOperation operation)
        {
            if (_queue.Count >= _maxDepth) return false;
            _queue.Enqueue(operation);
            return true;
        }

        /// <summary>Called ONLY from the AutoCAD main thread.</summary>
        public bool TryDequeue(out QueuedOperation? operation) => _queue.TryDequeue(out operation);

        /// <summary>Fail every pending item, e.g. during shutdown.</summary>
        public void DrainWith(Func<QueuedOperation, PluginResponse> responseFactory)
        {
            while (_queue.TryDequeue(out QueuedOperation? pending) && pending != null)
            {
                pending.Complete(responseFactory(pending));
            }
        }
    }
}
