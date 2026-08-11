using System;
using System.Threading.Tasks;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class OperationQueueTests
    {
        private static QueuedOperation NewOperation(string requestId = "req-1")
        {
            var fields = TestRequests.BaseFields(OperationType.CreateLine, TestRequests.TestNonce);
            fields["request_id"] = requestId;

            ValidationOutcome outcome = RequestValidator.Validate(TestRequests.Json(fields));
            Assert.True(outcome.IsValid);

            return new QueuedOperation(outcome.Request!, DateTimeOffset.UtcNow);
        }

        [Fact]
        public void Enqueues_and_dequeues_in_fifo_order()
        {
            var queue = new OperationQueue();
            Assert.True(queue.TryEnqueue(NewOperation("a")));
            Assert.True(queue.TryEnqueue(NewOperation("b")));
            Assert.Equal(2, queue.Count);

            Assert.True(queue.TryDequeue(out QueuedOperation? first));
            Assert.True(queue.TryDequeue(out QueuedOperation? second));

            Assert.Equal("a", first!.Request.RequestId);
            Assert.Equal("b", second!.Request.RequestId);
            Assert.Equal(0, queue.Count);
        }

        [Fact]
        public void Refuses_to_enqueue_beyond_max_depth()
        {
            var queue = new OperationQueue(maxDepth: 2);

            Assert.True(queue.TryEnqueue(NewOperation()));
            Assert.True(queue.TryEnqueue(NewOperation()));
            Assert.False(queue.TryEnqueue(NewOperation())); // back-pressure
        }

        [Fact]
        public async Task Completion_resolves_when_the_dispatcher_completes_the_item()
        {
            var queue = new OperationQueue();
            QueuedOperation op = NewOperation();
            queue.TryEnqueue(op);

            queue.TryDequeue(out QueuedOperation? dequeued);
            dequeued!.Complete(PluginResponse.Ok("req-1", "op-1", Stages.Scheduling));

            PluginResponse response = await op.Completion;
            Assert.True(response.Success);
        }

        [Fact]
        public async Task DrainWith_completes_every_pending_item()
        {
            var queue = new OperationQueue();
            QueuedOperation first = NewOperation("a");
            QueuedOperation second = NewOperation("b");
            queue.TryEnqueue(first);
            queue.TryEnqueue(second);

            queue.DrainWith(op => PluginResponse.Failure(
                "PLUGIN_SHUTTING_DOWN", Stages.Shutdown, "shutting down", op.Request.RequestId));

            Assert.Equal(0, queue.Count);
            Assert.Equal("PLUGIN_SHUTTING_DOWN", (await first.Completion).ErrorCode);
            Assert.Equal("PLUGIN_SHUTTING_DOWN", (await second.Completion).ErrorCode);
        }
    }
}
