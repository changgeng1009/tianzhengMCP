using System;
using System.Diagnostics;
using System.Threading;
using Autodesk.AutoCAD.Runtime;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using AcCoreApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
// Autodesk.AutoCAD.Runtime also defines an 'Exception' type, which is ambiguous with
// System.Exception once that namespace is imported. Bind the simple name explicitly.
using Exception = System.Exception;

[assembly: ExtensionApplication(typeof(TianzhengCadPlugin.PluginExtension))]

namespace TianzhengCadPlugin
{
    /// <summary>
    /// AutoCAD 2026 managed extension entry point (net8.0-windows).
    ///
    /// Initialize() runs on the AutoCAD main thread. It:
    ///   1. resolves the INJECTED auth token (no hardcoded secret; refuses to listen without one),
    ///   2. captures the AutoCAD-derived handshake snapshot while on the main thread,
    ///   3. starts the main-thread dispatcher (Application.Idle),
    ///   4. starts the loopback-only TCP listener.
    ///
    /// Terminate() stops the listener first, then the dispatcher, so no request can be
    /// accepted after CAD-side draining has begun.
    ///
    /// S7.1-A: no document is created, opened, locked, written, saved or closed.
    /// </summary>
    public sealed class PluginExtension : IExtensionApplication
    {
        /// <summary>Fixed loopback port for the MVP; override with TIANZHENG_PLUGIN_PORT.</summary>
        public const int DefaultPort = 5987;
        public const string PortEnvVar = "TIANZHENG_PLUGIN_PORT";

        /// <summary>
        /// Directory the plugin is permitted to save synthetic documents into. Injected at
        /// launch; without it, save is refused with SANDBOX_NOT_CONFIGURED.
        /// </summary>
        public const string SandboxRootEnvVar = "TIANZHENG_PLUGIN_SANDBOX_ROOT";

        private static PluginLog? _log;
        private static OperationQueue? _queue;
        private static MainThreadDispatcher? _dispatcher;
        private static TcpTransportListener? _listener;
        private static PluginRuntimeInfo? _runtimeInfo;
        private static DocumentOwnershipRegistry? _registry;
        private static CadOperationExecutor? _executor;
        private static string _pluginState = PluginStates.Stopped;

        public void Initialize()
        {
            _pluginState = PluginStates.Starting;
            _log = new PluginLog();

            try
            {
                string sessionId = Guid.NewGuid().ToString("N");    // fresh, unguessable, per start
                string sessionNonce = Guid.NewGuid().ToString("N"); // regenerated every start
                int processId = Environment.ProcessId;

                // AutoCAD-derived value captured HERE, on the main thread, once.
                string autoCadVersion = SafeGetAutoCadVersion();

                _runtimeInfo = PluginRuntimeInfo.ForEntityMvp(
                    sessionId, processId, autoCadVersion, sessionNonce);

                _queue = new OperationQueue();
                _registry = new DocumentOwnershipRegistry(sessionId);

                // The dispatcher is created first so the executor can report its main thread id.
                _dispatcher = new MainThreadDispatcher(_queue, _log);
                // Sandbox root comes from the plugin's own launch configuration, never the wire.
                string? sandboxRoot = Environment.GetEnvironmentVariable(SandboxRootEnvVar);
                _executor = new CadOperationExecutor(
                    _registry, _log, sessionId, () => _dispatcher?.MainThreadId ?? -1, sandboxRoot);
                _dispatcher.SetExecutor(_executor);
                _dispatcher.Start(); // subscribes Application.Idle on the main thread

                string? token = TokenProvider.TryResolve();
                if (string.IsNullOrEmpty(token))
                {
                    // Fail closed: never fall back to a default/hardcoded token.
                    _pluginState = PluginStates.Stopped;
                    _log.Error(LogCategory.Authentication,
                        $"no auth token injected ({TokenProvider.TokenEnvVar} / {TokenProvider.TokenFileEnvVar}); listener NOT started");
                    WriteLine("[TianzhengCadPlugin] loaded WITHOUT listener: no auth token injected.");
                    WriteLine($"[TianzhengCadPlugin] set {TokenProvider.TokenEnvVar} (>= {TokenAuthenticator.MinimumTokenLength} chars) then run TZPLUGINSTART.");
                    return;
                }

                StartListener(token);
                _pluginState = PluginStates.Ready;

                WriteLine($"[TianzhengCadPlugin] {ProtocolConstants.PluginVersion} listening on "
                          + $"{ProtocolConstants.BindAddress}:{_listener!.Port} session={sessionId[..8]}...");
            }
            catch (Exception ex)
            {
                _pluginState = PluginStates.Stopped;
                _log?.Error(LogCategory.Transport, $"initialize failed: {ex.GetType().Name}");
                WriteLine($"[TianzhengCadPlugin] initialize failed: {ex.GetType().Name}");
            }
        }

        public void Terminate()
        {
            _pluginState = PluginStates.Draining;
            try
            {
                _listener?.Stop();   // stop accepting first
                _listener?.Dispose();
                _dispatcher?.Stop(); // then release queued waiters
                _dispatcher?.Dispose();
            }
            catch (Exception ex)
            {
                _log?.Error(LogCategory.Shutdown, $"terminate error: {ex.GetType().Name}");
            }
            finally
            {
                _listener = null;
                _dispatcher = null;
                _queue = null;
                _executor = null;
                // Ownership tokens must never outlive the plugin session.
                _registry?.Clear();
                _registry = null;
                _pluginState = PluginStates.Stopped;
            }
        }


        private static void StartListener(string token)
        {
            TokenAuthenticator authenticator = TokenAuthenticator.FromToken(token);
            var router = new RequestRouter(_runtimeInfo!, _queue!, _log!, () => _pluginState);
            _listener = new TcpTransportListener(authenticator, router, _log!);
            _listener.Start(ResolvePort());
            _log!.Info(LogCategory.Authentication, $"auth configured token={TokenAuthenticator.Redact(token)}");
        }

        private static int ResolvePort()
        {
            string? raw = Environment.GetEnvironmentVariable(PortEnvVar);
            if (int.TryParse(raw, out int port) && port > 0 && port <= 65535) return port;
            return DefaultPort;
        }

        private static string SafeGetAutoCadVersion()
        {
            try { return AcCoreApp.Version.ToString(); }
            catch (Exception) { return "unknown"; }
        }

        private static void WriteLine(string message)
        {
            try
            {
                Autodesk.AutoCAD.ApplicationServices.Document? doc =
                    AcCoreApp.DocumentManager?.MdiActiveDocument;
                // Read-only editor write for operator feedback. This prints a status line;
                // it does not read, modify, lock or save the document in any way.
                doc?.Editor.WriteMessage("\n" + message);
            }
            catch (Exception) { /* console output must never break load */ }
        }

        // ---- Read-only operator commands (no document access, no CAD mutation) ----

        [CommandMethod("TZPLUGINSTATUS", CommandFlags.Modal)]
        public static void ShowStatus()
        {
            if (_runtimeInfo == null)
            {
                WriteLine("[TianzhengCadPlugin] not initialized.");
                return;
            }
            WriteLine($"[TianzhengCadPlugin] state={_pluginState} "
                      + $"listening={(_listener?.IsRunning == true ? $"{ProtocolConstants.BindAddress}:{_listener.Port}" : "no")} "
                      + $"protocol={ProtocolConstants.ProtocolVersion} "
                      + $"session={_runtimeInfo.SessionId[..8]}... "
                      + $"queue={_queue?.Count ?? 0} "
                      + $"dispatcher_thread={_dispatcher?.MainThreadId ?? -1} "
                      + $"idle_ticks={_dispatcher?.IdleTickCount ?? 0} "
                      + $"readiness_state={_runtimeInfo.ReadinessStateValue} "
                      + $"owned_docs={_registry?.Count ?? 0} "
                      + $"tx_started={_executor?.TransactionsStarted ?? 0} "
                      + $"tx_committed={_executor?.TransactionsCommitted ?? 0} "
                      + $"tx_aborted={_executor?.TransactionsAborted ?? 0} "
                      + $"locks={_executor?.DocumentLocksTaken ?? 0} "
                      + $"entities={_executor?.EntitiesCreated ?? 0} "
                      + $"acad={_runtimeInfo.AutoCadVersion}");
        }

        /// <summary>Start the listener after injecting a token into the AutoCAD process.</summary>
        [CommandMethod("TZPLUGINSTART", CommandFlags.Modal)]
        public static void StartCommand()
        {
            if (_listener?.IsRunning == true)
            {
                WriteLine("[TianzhengCadPlugin] listener already running.");
                return;
            }
            string? token = TokenProvider.TryResolve();
            if (string.IsNullOrEmpty(token))
            {
                WriteLine($"[TianzhengCadPlugin] no token: set {TokenProvider.TokenEnvVar} and retry.");
                return;
            }
            try
            {
                StartListener(token);
                _pluginState = PluginStates.Ready;
                WriteLine($"[TianzhengCadPlugin] listening on {ProtocolConstants.BindAddress}:{_listener!.Port}");
            }
            catch (Exception ex)
            {
                WriteLine($"[TianzhengCadPlugin] start failed: {ex.GetType().Name}");
            }
        }

        /// <summary>Graceful listener stop without unloading the assembly.</summary>
        [CommandMethod("TZPLUGINSTOP", CommandFlags.Modal)]
        public static void StopCommand()
        {
            _pluginState = PluginStates.Draining;
            _listener?.Stop();
            _listener?.Dispose();
            _listener = null;
            _pluginState = PluginStates.Stopped;
            WriteLine("[TianzhengCadPlugin] listener stopped.");
        }
    }
}
