using System;
using System.Threading;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace TianzhengCadPlugin
{
    /// <summary>
    /// Drains the <see cref="OperationQueue"/> on the AutoCAD main thread.
    ///
    /// This is the ONLY component permitted to call the AutoCAD API. It is driven by the
    /// Application.Idle event, which AutoCAD raises on its own main thread, so every
    /// callback here is already correctly-threaded. The transport thread never reaches
    /// AutoCAD; it only enqueues and awaits a completion source.
    ///
    /// S7.1-A SCOPE: no CAD operation is implemented. Any queued operation is completed
    /// with a structured NOT_IMPLEMENTED_IN_STAGE response. There is deliberately no
    /// document access, no DocumentLock and no Transaction in this stage — those arrive
    /// in S7.2 and must not be claimed before they are actually written and verified.
    /// </summary>
    public sealed class MainThreadDispatcher : IDisposable
    {
        /// <summary>Cap per idle tick so the AutoCAD UI is never starved.</summary>
        private const int MaxOperationsPerIdleTick = 8;

        private readonly OperationQueue _queue;
        private readonly PluginLog _log;
        private IOperationExecutor _executor;
        private int _mainThreadId = -1;
        private bool _subscribed;

        public MainThreadDispatcher(OperationQueue queue, PluginLog log, IOperationExecutor? executor = null)
        {
            _queue = queue ?? throw new ArgumentNullException(nameof(queue));
            _log = log ?? throw new ArgumentNullException(nameof(log));
            // Falls back to the stage executor until a real CAD executor is installed.
            _executor = executor ?? new StageNotImplementedExecutor();
        }

        /// <summary>
        /// Install the real CAD executor. Called from Initialize() before Start(), so the
        /// executor can capture this dispatcher's main-thread id.
        /// </summary>
        public void SetExecutor(IOperationExecutor executor)
            => _executor = executor ?? throw new ArgumentNullException(nameof(executor));

        /// <summary>The AutoCAD main thread id, captured at Start(). -1 before start.</summary>
        public int MainThreadId => _mainThreadId;

        /// <summary>MUST be called from the AutoCAD main thread (i.e. from Initialize()).</summary>
        public void Start()
        {
            if (_subscribed) return;
            _mainThreadId = Thread.CurrentThread.ManagedThreadId;
            AcApp.Idle += OnIdle;
            _subscribed = true;
            _log.Info(LogCategory.Scheduling, $"main-thread dispatcher started (thread={_mainThreadId})");
        }

        public void Stop()
        {
            if (!_subscribed) return;
            AcApp.Idle -= OnIdle;
            _subscribed = false;
            _log.Info(LogCategory.Shutdown, "main-thread dispatcher stopped");

            // Release anyone still waiting so no transport caller hangs on shutdown.
            _queue.DrainWith(op => new PluginResponse
            {
                Success = false,
                ErrorCode = "PLUGIN_SHUTTING_DOWN",
                Stage = Stages.Shutdown,
                RequestId = op.Request.RequestId,
                OperationId = op.Request.OperationId,
                Retryable = false,
                SanitizedMessage = "plugin is shutting down",
                PluginState = PluginStates.Draining,
            });
        }

        /// <summary>
        /// Number of Application.Idle ticks observed. Proves the event actually fires
        /// inside acad.exe rather than being assumed from source.
        /// </summary>
        public long IdleTickCount => Interlocked.Read(ref _idleTicks);
        private long _idleTicks;

        private void OnIdle(object? sender, EventArgs e)
        {
            Interlocked.Increment(ref _idleTicks);

            int processed = 0;
            while (processed < MaxOperationsPerIdleTick && _queue.TryDequeue(out QueuedOperation? op) && op != null)
            {
                processed++;
                try
                {
                    op.Complete(Execute(op));
                }
                catch (Exception ex)
                {
                    // Never let a dispatcher fault escape into AutoCAD's idle loop.
                    _log.Error(LogCategory.Scheduling, $"dispatch failed: {ex.GetType().Name}");
                    op.Complete(new PluginResponse
                    {
                        Success = false,
                        ErrorCode = ErrorCodes.InternalError,
                        Stage = Stages.Scheduling,
                        RequestId = op.Request.RequestId,
                        OperationId = op.Request.OperationId,
                        Retryable = false,
                        SanitizedMessage = "internal dispatch error",
                    });
                }
            }
        }

        /// <summary>
        /// Executes one operation on the AutoCAD main thread.
        /// S7.1-A implements none, and says so explicitly rather than faking success.
        /// </summary>
        private PluginResponse Execute(QueuedOperation op)
        {
            int executingThread = Thread.CurrentThread.ManagedThreadId;
            _log.Info(LogCategory.Scheduling,
                $"main-thread execute op={op.Request.OperationType} thread={executingThread}");

            PluginResponse response = _executor.Execute(op.Request);

            // Runtime proof that this ran on the AutoCAD main thread via Application.Idle,
            // rather than on a transport thread. The probe asserts these values instead of
            // inferring thread-safety from source. Contains no secret or user data.
            response.Warnings.Add(
                $"dispatch=application_idle;executing_thread={executingThread};" +
                $"initialize_main_thread={_mainThreadId};" +
                $"on_main_thread={(executingThread == _mainThreadId ? "true" : "false")};" +
                $"idle_ticks={IdleTickCount}");

            return response;
        }

        public void Dispose() => Stop();
    }
}
