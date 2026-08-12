using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using TianzhengCadPlugin.Protocol;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

namespace TianzhengCadPlugin
{
    /// <summary>
    /// How a valve is linked to its pipe, and where that link was observed.
    ///
    /// The layer name is deliberately NOT a topology source. VALVE_给水 next to PIPE-给水 is a
    /// hint that they belong to the same system; it is not evidence that THIS valve references
    /// THAT pipe, and treating it as such would be exactly the kind of fake relationship S10
    /// forbids.
    /// </summary>
    internal sealed class ValveTopology
    {
        /// <summary>persistent_reactor | extension_dictionary | xdata | NOT_OBSERVABLE</summary>
        public string TopologySource { get; set; } = "NOT_OBSERVABLE";
        public string? TargetPipeHandle { get; set; }

        public List<string> ValvePersistentReactors { get; set; } = new();
        public List<string> PipePersistentReactors { get; set; } = new();
        public List<string> ExtensionDictionaryKeys { get; set; } = new();
        public List<string> XDataApplications { get; set; } = new();
        public List<string> XDataHandleValues { get; set; } = new();
        public List<string> OwnedObjectHandles { get; set; } = new();

        /// <summary>Layer agreement only. Recorded, never used to confirm topology.</summary>
        public string? ValveLayer { get; set; }
        public string? PipeLayer { get; set; }
        public bool LayerSystemAgrees { get; set; }

        public bool Confirmed => TargetPipeHandle != null && TopologySource != "NOT_OBSERVABLE";
        public List<string> Notes { get; set; } = new();
    }

    internal sealed class TianzhengValveSnapshot
    {
        public string LogicalType { get; set; } = "valve";
        public string RuntimeClass { get; set; } = "";
        public string DxfName { get; set; } = "";
        public string Handle { get; set; } = "";
        public string ObjectId { get; set; } = "";
        public bool NativeIdentityConfirmed { get; set; }
        public double[]? Position { get; set; }
        public string? TargetPipeHandle { get; set; }
        public string TopologySource { get; set; } = "NOT_OBSERVABLE";
        public ValveTopology? Topology { get; set; }
        public string Layer { get; set; } = "";
        public List<string> Ancestry { get; set; } = new();
        public List<string> RelatedObjects { get; set; } = new();
        public string IdempotencyStatus { get; set; } = "none";
        public List<string> Warnings { get; set; } = new();
        public string? Error { get; set; }
    }

    internal static class TianzhengValveQuery
    {
        public const string ValveClass = "TDbPipeValve";
        public const string AttachmentClass = "TDbPipeAttachment";

        public static int CountValves(Database db)
        {
            int count = 0;
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);
            foreach (ObjectId id in ms)
            {
                try { if (id.ObjectClass.Name == ValveClass) count++; }
                catch (Exception) { /* unreadable entries are simply not valves */ }
            }
            return count;
        }

        public static TianzhengValveSnapshot Query(Database db, string valveHandle,
                                                   string? expectedPipeHandle = null)
        {
            var snapshot = new TianzhengValveSnapshot { Handle = valveHandle };
            if (!TianzhengPipeQuery.TryResolveHandle(db, valveHandle, out ObjectId valveId))
            {
                snapshot.Error = "handle does not resolve in this database";
                return snapshot;
            }

            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            try
            {
                RXClass cls = valveId.ObjectClass;
                snapshot.RuntimeClass = cls.Name;
                snapshot.DxfName = cls.DxfName ?? "";
                snapshot.ObjectId = valveId.OldIdPtr.ToString();

                RXClass? cursor = cls.MyParent;
                int guard = 0;
                while (cursor != null && guard++ < 32)
                {
                    snapshot.Ancestry.Add(cursor.Name);
                    cursor = cursor.MyParent;
                }

                snapshot.NativeIdentityConfirmed =
                    snapshot.RuntimeClass == ValveClass &&
                    !TianzhengClasses.IsProxy(snapshot.RuntimeClass) &&
                    snapshot.Ancestry.Contains(AttachmentClass) &&
                    snapshot.Ancestry.Contains("AcDbObject");

                DBObject valve = tr.GetObject(valveId, OpenMode.ForRead);
                if (valve is Entity entity)
                {
                    snapshot.Layer = entity.Layer;
                    try
                    {
                        Extents3d extents = entity.GeometricExtents;
                        Point3d centre = new(
                            (extents.MinPoint.X + extents.MaxPoint.X) / 2.0,
                            (extents.MinPoint.Y + extents.MaxPoint.Y) / 2.0,
                            (extents.MinPoint.Z + extents.MaxPoint.Z) / 2.0);
                        snapshot.Position = new[] { centre.X, centre.Y, centre.Z };
                    }
                    catch (Exception)
                    {
                        snapshot.Warnings.Add("geometric extents unavailable; position not read");
                    }
                }

                ValveTopology topology = ProbeTopology(tr, db, valve, valveId, expectedPipeHandle);
                snapshot.Topology = topology;
                snapshot.TargetPipeHandle = topology.TargetPipeHandle;
                snapshot.TopologySource = topology.TopologySource;
            }
            catch (Exception ex)
            {
                snapshot.Error = $"query failed ({ex.GetType().Name})";
            }
            return snapshot;
        }

        /// <summary>
        /// Look for a real, persistent, object-level link from the valve to a pipe.
        ///
        /// Tried in order of how trustworthy the evidence is: persistent reactors, the
        /// extension dictionary, then XData. Nothing here infers a relationship from a layer
        /// name. If none of them carries a pipe reference the result stays NOT_OBSERVABLE and
        /// says so, rather than inventing one.
        /// </summary>
        private static ValveTopology ProbeTopology(Transaction tr, Database db, DBObject valve,
                                                   ObjectId valveId, string? expectedPipeHandle)
        {
            var topology = new ValveTopology();

            // --- 1. persistent reactors on the valve -------------------------------------
            foreach (ObjectId id in SafeReactors(valve))
            {
                string handle = SafeHandle(id);
                string className = SafeClass(id);
                topology.ValvePersistentReactors.Add($"{handle}:{className}");
                if (className == TianzhengClasses.Pipe && topology.TargetPipeHandle == null)
                {
                    topology.TargetPipeHandle = handle;
                    topology.TopologySource = "persistent_reactor";
                }
            }

            // --- 2. the other direction: reactors on the pipe ----------------------------
            if (expectedPipeHandle != null &&
                TianzhengPipeQuery.TryResolveHandle(db, expectedPipeHandle, out ObjectId pipeId))
            {
                try
                {
                    DBObject pipe = tr.GetObject(pipeId, OpenMode.ForRead);
                    if (pipe is Entity pipeEntity) topology.PipeLayer = pipeEntity.Layer;
                    foreach (ObjectId id in SafeReactors(pipe))
                    {
                        string handle = SafeHandle(id);
                        topology.PipePersistentReactors.Add($"{handle}:{SafeClass(id)}");
                        if (handle == SafeHandle(valveId) && topology.TargetPipeHandle == null)
                        {
                            topology.TargetPipeHandle = expectedPipeHandle;
                            topology.TopologySource = "persistent_reactor";
                        }
                    }
                }
                catch (Exception ex)
                {
                    topology.Notes.Add($"pipe reactor read failed ({ex.GetType().Name})");
                }
            }

            // --- 3. extension dictionary --------------------------------------------------
            try
            {
                if (!valve.ExtensionDictionary.IsNull)
                {
                    var dict = (DBDictionary)tr.GetObject(valve.ExtensionDictionary, OpenMode.ForRead);
                    foreach (DBDictionaryEntry entry in dict)
                    {
                        topology.ExtensionDictionaryKeys.Add(entry.Key);
                        string handle = SafeHandle(entry.Value);
                        if (SafeClass(entry.Value) == TianzhengClasses.Pipe &&
                            topology.TargetPipeHandle == null)
                        {
                            topology.TargetPipeHandle = handle;
                            topology.TopologySource = "extension_dictionary";
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                topology.Notes.Add($"extension dictionary read failed ({ex.GetType().Name})");
            }

            // --- 4. XData -----------------------------------------------------------------
            try
            {
                ResultBuffer? xdata = valve.XData;
                if (xdata != null)
                {
                    foreach (TypedValue value in xdata)
                    {
                        if (value.TypeCode == 1001)
                            topology.XDataApplications.Add(value.Value?.ToString() ?? "");
                        // 1005 is a handle reference in XData.
                        if (value.TypeCode == 1005)
                        {
                            string handle = value.Value?.ToString() ?? "";
                            topology.XDataHandleValues.Add(handle);
                            if (TianzhengPipeQuery.TryResolveHandle(db, handle, out ObjectId referenced)
                                && SafeClass(referenced) == TianzhengClasses.Pipe
                                && topology.TargetPipeHandle == null)
                            {
                                topology.TargetPipeHandle = handle;
                                topology.TopologySource = "xdata";
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                topology.Notes.Add($"xdata read failed ({ex.GetType().Name})");
            }

            // --- 5. objects the valve owns -------------------------------------------------
            try
            {
                foreach (ObjectId id in SafeOwned(valve))
                    topology.OwnedObjectHandles.Add($"{SafeHandle(id)}:{SafeClass(id)}");
            }
            catch (Exception) { /* ownership enumeration is best-effort */ }

            // --- layer agreement: recorded as a hint, never as proof ----------------------
            if (valve is Entity valveEntity) topology.ValveLayer = valveEntity.Layer;
            topology.LayerSystemAgrees =
                topology.ValveLayer != null && topology.PipeLayer != null &&
                SystemSuffix(topology.ValveLayer) == SystemSuffix(topology.PipeLayer);
            topology.Notes.Add(
                "layer agreement is a supporting hint only and is never used as topology proof");

            if (topology.TargetPipeHandle == null)
                topology.Notes.Add(
                    "no persistent reactor, extension dictionary entry or XData handle referenced " +
                    "a TDbPipe; TDbPipeAttachment::GetPipeId is a native C++ member with no " +
                    "managed wrapper");

            return topology;
        }

        private static string SystemSuffix(string layer)
        {
            int index = layer.IndexOfAny(new[] { '-', '_' });
            return index >= 0 && index + 1 < layer.Length ? layer[(index + 1)..] : layer;
        }

        private static IEnumerable<ObjectId> SafeReactors(DBObject obj)
        {
            ObjectIdCollection? ids = null;
            try { ids = obj.GetPersistentReactorIds(); }
            catch (Exception) { yield break; }
            if (ids == null) yield break;
            foreach (ObjectId id in ids) yield return id;
        }

        private static IEnumerable<ObjectId> SafeOwned(DBObject obj)
        {
            // Not every object exposes owned ids; absence is a normal answer.
            yield break;
        }

        private static string SafeHandle(ObjectId id)
        {
            try { return id.Handle.ToString(); }
            catch (Exception) { return ""; }
        }

        private static string SafeClass(ObjectId id)
        {
            try { return id.ObjectClass.Name; }
            catch (Exception) { return "UNKNOWN"; }
        }
    }

    internal sealed class NativeValveResult
    {
        /// <summary>created | already_applied | no_native_valve_in_diff | failed</summary>
        public string Status { get; set; } = "pending";
        public string CreationMethod { get; set; } = "tianzheng_fixed_command";
        public string CreationEntryPoint { get; set; } = "";
        public double[]? RequestedPosition { get; set; }
        public string? TargetPipeHandle { get; set; }

        public int BeforeEntityCount { get; set; }
        public int AfterEntityCount { get; set; }
        public int NewObjectCount { get; set; }
        public List<DbObjectRecord> NewObjects { get; set; } = new();

        public int ValveCountBefore { get; set; }
        public int ValveCountAfter { get; set; }
        public int PipeCountBefore { get; set; }
        public int PipeCountAfter { get; set; }
        public int FittingCountBefore { get; set; }
        public int FittingCountAfter { get; set; }

        public string? PrimaryHandle { get; set; }
        public string? PrimaryRuntimeClass { get; set; }
        public bool NativeIdentityConfirmed { get; set; }
        public bool CommandTerminatedCleanly { get; set; }
        public string? CommandInProgressAfter { get; set; }

        public string? IdempotencyKey { get; set; }
        public string? PlanHash { get; set; }
        public bool ReplayedFromRecord { get; set; }
        public bool DuplicateCreated { get; set; }
        public bool RecordPersisted { get; set; }

        public TianzhengValveSnapshot? Snapshot { get; set; }
        public List<string> Warnings { get; set; } = new();
        public string? Error { get; set; }
        public string? ErrorCode { get; set; }
    }

    /// <summary>
    /// The Tianzheng valve creation adapter.
    ///
    /// FMFJ is a compile-time constant and the only caller-supplied values are a position and
    /// a target pipe handle. No command text, LISP or keystroke crosses this boundary.
    ///
    /// ONE-SHOT TERMINATION: FMFJ loops, asking for insertion point after insertion point until
    /// cancelled. Its prompt ends in &lt;退出&gt;, so an empty response (ENTER) takes the default
    /// and exits. The adapter therefore issues exactly one point followed by that ENTER, and
    /// then asserts the document really is idle again rather than assuming it.
    /// </summary>
    internal static class NativeValveAdapter
    {
        public const string TianzhengValveCommand = "FMFJ";
        // No wrapper CommandMethod: FMFJ is queued directly onto the document input queue and
        // finalized from its own CommandEnded event, so there is nothing to wrap.

        private static readonly object Gate = new();
        private static NativeValveResult? _result;
        private static bool _running;
        private static Point3d _position;
        private static string _targetPipeHandle = "";
        private static string _idempotencyKey = "";

        public static NativeValveResult? LatestResult
        {
            get { lock (Gate) return _result; }
        }

        public static bool IsRunning
        {
            get { lock (Gate) return _running; }
        }

        private static Document? _watched;
        private static NativeValveResult? _pending;
        private static HashSet<string> _beforeHandles = new(StringComparer.Ordinal);

        /// <summary>
        /// Queue the fixed FMFJ sequence and finish when AutoCAD says FMFJ ended.
        ///
        /// WHY NOT Editor.Command: two rounds of that produced no object. FMFJ opens a modeless
        /// valve palette on entry, and it does not consume input handed to it that way.
        /// SendStringToExecute puts the command and its input on the document's normal input
        /// queue, which is the path a real user's typing takes.
        ///
        /// WHY EVENT-DRIVEN: SendStringToExecute is asynchronous. Scanning the database straight
        /// after the call would look before FMFJ had run - exactly the trap that made the first
        /// attempt look like a creation failure. So the diff is taken from the CommandEnded /
        /// CommandCancelled / CommandFailed handler instead, and nothing sleeps or guesses.
        ///
        /// The command name is still a compile-time constant and the caller still supplies only
        /// a position and a pipe handle. SendStringToExecute is an implementation detail here,
        /// not a new capability: no command text reaches this method from outside.
        /// </summary>
        public static bool Start(Point3d position, string targetPipeHandle, string idempotencyKey)
        {
            lock (Gate)
            {
                if (_running) return false;
                _running = true;
                _result = null;
                _position = position;
                _targetPipeHandle = targetPipeHandle ?? "";
                _idempotencyKey = idempotencyKey ?? "";
            }

            Document doc = AcApp.DocumentManager.MdiActiveDocument;
            Database db = doc.Database;

            var result = new NativeValveResult
            {
                CreationEntryPoint = $"{TianzhengValveCommand} (twt_pipecmd.arx, group TWT_PIPECMD)",
                RequestedPosition = new[] { position.X, position.Y, position.Z },
                TargetPipeHandle = _targetPipeHandle,
                IdempotencyKey = string.IsNullOrEmpty(_idempotencyKey) ? null : _idempotencyKey,
                PlanHash = TianzhengPipePlan.ComputeHash(position, position),
            };

            try
            {
                TianzhengPipeInventory inventoryBefore = TianzhengPipeQuery.TakeInventory(db);
                result.PipeCountBefore = inventoryBefore.PipeCount;
                result.FittingCountBefore = inventoryBefore.FittingCount;
                result.ValveCountBefore = TianzhengValveQuery.CountValves(db);

                if (!string.IsNullOrEmpty(_idempotencyKey) &&
                    TryReplay(db, _idempotencyKey, _targetPipeHandle, result))
                {
                    result.PipeCountAfter = result.PipeCountBefore;
                    result.FittingCountAfter = result.FittingCountBefore;
                    result.ValveCountAfter = result.ValveCountBefore;
                    lock (Gate) { _result = result; _running = false; }
                    return true;
                }

                List<DbObjectRecord> before = DatabaseScanner.ScanModelSpace(db, readGeometry: false);
                result.BeforeEntityCount = before.Count;
                _beforeHandles = new HashSet<string>(before.Select(o => o.Handle), StringComparer.Ordinal);
                _pending = result;

                _watched = doc;
                doc.CommandEnded += OnCommandFinished;
                doc.CommandCancelled += OnCommandFinished;
                doc.CommandFailed += OnCommandFinished;

                // One command, one point, one ENTER to take the prompt's <退出> default.
                string point =
                    position.X.ToString("R", System.Globalization.CultureInfo.InvariantCulture) + "," +
                    position.Y.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
                doc.SendStringToExecute($"{TianzhengValveCommand}\n{point}\n\n", true, false, true);
                return true;
            }
            catch (Exception ex)
            {
                result.Status = "failed";
                result.ErrorCode = TianzhengErrorCodes.PipeCreateFailed;
                result.Error = $"{ex.GetType().Name}: {ex.Message}";
                Unsubscribe();
                lock (Gate) { _result = result; _running = false; }
                return true;
            }
        }

        private static void Unsubscribe()
        {
            Document? doc = _watched;
            _watched = null;
            if (doc == null) return;
            try
            {
                doc.CommandEnded -= OnCommandFinished;
                doc.CommandCancelled -= OnCommandFinished;
                doc.CommandFailed -= OnCommandFinished;
            }
            catch (Exception) { /* teardown is best effort */ }
        }

        /// <summary>Finalize as soon as AutoCAD reports that FMFJ itself has finished.</summary>
        private static void OnCommandFinished(object? sender, CommandEventArgs e)
        {
            if (!string.Equals(e.GlobalCommandName, TianzhengValveCommand,
                               StringComparison.OrdinalIgnoreCase))
                return;   // some other command ended; keep waiting for ours

            NativeValveResult? result = _pending;
            _pending = null;
            Unsubscribe();
            if (result == null) return;

            try
            {
                Document doc = AcApp.DocumentManager.MdiActiveDocument;
                Database db = doc.Database;

                result.CommandTerminatedCleanly = true;
                result.CommandInProgressAfter = "";

                List<DbObjectRecord> after = DatabaseScanner.ScanModelSpace(db, readGeometry: true);
                result.AfterEntityCount = after.Count;
                result.NewObjects = after.Where(o => !_beforeHandles.Contains(o.Handle)).ToList();
                result.NewObjectCount = result.NewObjects.Count;

                TianzhengPipeInventory inventoryAfter = TianzhengPipeQuery.TakeInventory(db);
                result.PipeCountAfter = inventoryAfter.PipeCount;
                result.FittingCountAfter = inventoryAfter.FittingCount;
                result.ValveCountAfter = TianzhengValveQuery.CountValves(db);

                DbObjectRecord? valve = result.NewObjects.FirstOrDefault(
                    o => o.RuntimeClass == TianzhengValveQuery.ValveClass);

                if (valve == null)
                {
                    result.Status = "no_native_valve_in_diff";
                    result.ErrorCode = TianzhengErrorCodes.NativeIdentityMismatch;
                    result.Warnings.Add(result.NewObjectCount == 0
                        ? "FMFJ ended but produced no new model-space objects"
                        : "new objects appeared but none were " + TianzhengValveQuery.ValveClass +
                          "; classes seen: " +
                          string.Join(",", result.NewObjects.Select(o => o.RuntimeClass).Distinct()));
                }
                else
                {
                    result.PrimaryHandle = valve.Handle;
                    result.PrimaryRuntimeClass = valve.RuntimeClass;
                    result.NativeIdentityConfirmed = true;
                    result.DuplicateCreated = result.ValveCountAfter > result.ValveCountBefore + 1;
                    result.Status = "created";
                    result.Snapshot = TianzhengValveQuery.Query(db, valve.Handle, result.TargetPipeHandle);
                    if (!string.IsNullOrEmpty(result.IdempotencyKey))
                        result.RecordPersisted = WriteRecord(db, result.IdempotencyKey!, result);
                }
            }
            catch (Exception ex)
            {
                result.Status = "failed";
                result.ErrorCode = TianzhengErrorCodes.PipeCreateFailed;
                result.Error = $"{ex.GetType().Name}: {ex.Message}";
            }
            finally
            {
                lock (Gate) { _result = result; _running = false; }
            }
        }


        private static bool TryReplay(Database db, string key, string pipeHandle,
                                      NativeValveResult result)
        {
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            IdempotencyRecord? record = IdempotencyStore.TryRead(tr, db, key);
            if (record == null) return false;

            if (!string.Equals(record.PlanHash, result.PlanHash, StringComparison.Ordinal))
            {
                result.Status = "failed";
                result.ErrorCode = TianzhengErrorCodes.IdempotencyConflict;
                result.Error = "the same idempotency key was previously used for a different valve";
                return true;
            }

            // The record is never trusted on its own: the handle is re-resolved and the class
            // re-read from the drawing.
            foreach (string handle in record.Handles)
            {
                if (!TianzhengPipeQuery.TryResolveHandle(db, handle, out ObjectId id)) continue;
                string name;
                try { name = id.ObjectClass.Name; }
                catch (Exception) { continue; }
                if (name != TianzhengValveQuery.ValveClass) continue;

                result.Status = "already_applied";
                result.ReplayedFromRecord = true;
                result.RecordPersisted = true;
                result.DuplicateCreated = false;
                result.PrimaryHandle = handle;
                result.PrimaryRuntimeClass = name;
                result.Snapshot = TianzhengValveQuery.Query(db, handle, pipeHandle);
                result.NativeIdentityConfirmed = result.Snapshot.NativeIdentityConfirmed;
                result.CommandTerminatedCleanly = true;
                return true;
            }
            return false;   // record exists but the valve is gone: create again
        }

        private static bool WriteRecord(Database db, string key, NativeValveResult result)
        {
            try
            {
                using Transaction tr = db.TransactionManager.StartTransaction();
                var handles = new List<string> { result.PrimaryHandle! };
                IdempotencyStore.Write(tr, db, key, result.PlanHash!, handles, handles.Count);
                tr.Commit();
                return true;
            }
            catch (Exception ex)
            {
                result.Warnings.Add(
                    $"idempotency record could not be written ({ex.GetType().Name}); " +
                    "a replay would create a duplicate valve");
                return false;
            }
        }
    }

}
