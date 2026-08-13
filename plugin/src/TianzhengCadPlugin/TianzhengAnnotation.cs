using System;
using System.Collections.Generic;
using System.Globalization;
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
    /// Everything about one object that could change when it is annotated.
    ///
    /// This exists because GJBZ may not create anything: the leading hypothesis is that it sets
    /// label state ON the pipe. A new-objects-only diff would then show nothing at all, so the
    /// target object itself has to be compared before and after.
    /// </summary>
    internal sealed class ObjectStateFingerprint
    {
        public string Handle { get; set; } = "";
        public string RuntimeClass { get; set; } = "";
        public string DxfName { get; set; } = "";
        public string Layer { get; set; } = "";
        public double[]? ExtentsMin { get; set; }
        public double[]? ExtentsMax { get; set; }
        public List<string> ExtensionDictionaryKeys { get; set; } = new();
        public List<string> XDataApplications { get; set; } = new();
        public int XDataItemCount { get; set; }
        public List<string> PersistentReactors { get; set; } = new();
        public string? Error { get; set; }

        /// <summary>Field-by-field comparison, reported as a list of what actually differs.</summary>
        public static List<string> Differences(ObjectStateFingerprint a, ObjectStateFingerprint b)
        {
            var diffs = new List<string>();
            if (a.RuntimeClass != b.RuntimeClass) diffs.Add($"runtime_class {a.RuntimeClass} -> {b.RuntimeClass}");
            if (a.Layer != b.Layer) diffs.Add($"layer {a.Layer} -> {b.Layer}");
            if (!Same(a.ExtentsMin, b.ExtentsMin)) diffs.Add("extents_min changed");
            if (!Same(a.ExtentsMax, b.ExtentsMax)) diffs.Add("extents_max changed");
            if (!a.ExtensionDictionaryKeys.SequenceEqual(b.ExtensionDictionaryKeys))
                diffs.Add($"extension_dictionary [{string.Join(",", a.ExtensionDictionaryKeys)}] -> " +
                          $"[{string.Join(",", b.ExtensionDictionaryKeys)}]");
            if (!a.XDataApplications.SequenceEqual(b.XDataApplications))
                diffs.Add($"xdata_apps [{string.Join(",", a.XDataApplications)}] -> " +
                          $"[{string.Join(",", b.XDataApplications)}]");
            if (a.XDataItemCount != b.XDataItemCount)
                diffs.Add($"xdata_item_count {a.XDataItemCount} -> {b.XDataItemCount}");
            if (!a.PersistentReactors.SequenceEqual(b.PersistentReactors))
                diffs.Add($"persistent_reactors [{string.Join(",", a.PersistentReactors)}] -> " +
                          $"[{string.Join(",", b.PersistentReactors)}]");
            return diffs;
        }

        private static bool Same(double[]? a, double[]? b)
        {
            if (a == null || b == null) return a == null && b == null;
            if (a.Length != b.Length) return false;
            return !a.Where((t, i) => Math.Abs(t - b[i]) > 1e-9).Any();
        }

        public static ObjectStateFingerprint Capture(Database db, string handle)
        {
            var state = new ObjectStateFingerprint { Handle = handle };
            if (!TianzhengPipeQuery.TryResolveHandle(db, handle, out ObjectId id))
            {
                state.Error = "handle does not resolve";
                return state;
            }

            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            try
            {
                RXClass cls = id.ObjectClass;
                state.RuntimeClass = cls.Name;
                state.DxfName = cls.DxfName ?? "";

                DBObject obj = tr.GetObject(id, OpenMode.ForRead);
                if (obj is Entity entity)
                {
                    state.Layer = entity.Layer;
                    // Extents are the cheapest signal that a self-drawn label appeared: a pipe
                    // that now renders DN20 above itself occupies more space than it did.
                    try
                    {
                        Extents3d e = entity.GeometricExtents;
                        state.ExtentsMin = new[] { e.MinPoint.X, e.MinPoint.Y, e.MinPoint.Z };
                        state.ExtentsMax = new[] { e.MaxPoint.X, e.MaxPoint.Y, e.MaxPoint.Z };
                    }
                    catch (Exception) { /* absent extents are a normal answer */ }
                }

                try
                {
                    if (!obj.ExtensionDictionary.IsNull)
                    {
                        var dict = (DBDictionary)tr.GetObject(obj.ExtensionDictionary, OpenMode.ForRead);
                        state.ExtensionDictionaryKeys = dict.Cast<DBDictionaryEntry>()
                            .Select(x => x.Key).OrderBy(x => x, StringComparer.Ordinal).ToList();
                    }
                }
                catch (Exception) { /* no extension dictionary */ }

                try
                {
                    ResultBuffer? xdata = obj.XData;
                    if (xdata != null)
                    {
                        TypedValue[] values = xdata.AsArray();
                        state.XDataItemCount = values.Length;
                        state.XDataApplications = values.Where(v => v.TypeCode == 1001)
                            .Select(v => v.Value?.ToString() ?? "")
                            .OrderBy(x => x, StringComparer.Ordinal).ToList();
                    }
                }
                catch (Exception) { /* no xdata */ }

                try
                {
                    ObjectIdCollection? reactors = obj.GetPersistentReactorIds();
                    if (reactors != null)
                        state.PersistentReactors = reactors.Cast<ObjectId>()
                            .Select(SafeHandle).OrderBy(x => x, StringComparer.Ordinal).ToList();
                }
                catch (Exception) { /* no reactors */ }
            }
            catch (Exception ex)
            {
                state.Error = $"capture failed ({ex.GetType().Name})";
            }
            return state;
        }

        private static string SafeHandle(ObjectId id)
        {
            try { return $"{id.Handle}:{id.ObjectClass.Name}"; }
            catch (Exception) { return "?"; }
        }
    }

    internal sealed class NativeAnnotationResult
    {
        /// <summary>created_object | modified_target | already_applied | no_effect | failed</summary>
        public string Status { get; set; } = "pending";

        /// <summary>MODEL_A_SEPARATE_OBJECT | MODEL_B_PIPE_OWNED_STATE | UNDETERMINED</summary>
        public string StorageModel { get; set; } = "UNDETERMINED";

        public string CreationEntryPoint { get; set; } = "";
        public string? TargetPipeHandle { get; set; }

        public int BeforeEntityCount { get; set; }
        public int AfterEntityCount { get; set; }
        public List<DbObjectRecord> NewObjects { get; set; } = new();
        public List<string> DeletedHandles { get; set; } = new();

        public ObjectStateFingerprint? TargetBefore { get; set; }
        public ObjectStateFingerprint? TargetAfter { get; set; }
        public List<string> TargetDifferences { get; set; } = new();

        public bool CommandObservedStart { get; set; }
        public string CommandEndKind { get; set; } = "";
        public bool CommandTerminatedCleanly { get; set; }
        public bool CancelSequenceIssued { get; set; }

        /// <summary>Whether the target was brought into view before the command was driven.</summary>
        public bool ViewFramedTarget { get; set; }

        public string? IdempotencyKey { get; set; }
        public string? PlanHash { get; set; }
        public bool ReplayedFromRecord { get; set; }
        public bool RecordPersisted { get; set; }

        public List<string> Warnings { get; set; } = new();
        public string? Error { get; set; }
        public string? ErrorCode { get; set; }
    }

    /// <summary>
    /// Tianzheng single-pipe diameter annotation adapter (DGGJ, 单管管径).
    ///
    /// DGGJ is a compile-time constant; the caller supplies only a target pipe handle. The pick
    /// point is computed from the pipe's OWN read-back geometry, never supplied by the caller.
    ///
    /// The command was chosen by measured interaction discovery, not by its name. Its prompt is
    /// "请单击需要标注管径的管线(标注位置参照光标与管线的相对位置)" — a single POINT which Tianzheng
    /// hit-tests itself, and a typed coordinate is accepted as that point. That is why the pump's
    /// proven SendStringToExecute pattern applies here, and why GJBZ's entity-multi-select
    /// surface, which ignored both a queued coordinate and a managed SelectionSet, does not.
    ///
    /// DGGJ also exposes a graceful 退出 Enter-default, so the queued sequence ends it without a
    /// force kill; the owned cancel remains only as a fallback. The diff is taken from DGGJ's own
    /// lifecycle event, so the database it reports is settled rather than mid-command.
    /// </summary>
    internal static class NativeAnnotationAdapter
    {
        public const string TianzhengAnnotationCommand = "DGGJ";
        private const string QueuedEscape = "";
        private static readonly object Gate = new();
        private static NativeAnnotationResult? _result;
        private static bool _running;
        private static NativeAnnotationResult? _pending;
        private static Document? _watched;
        private static HashSet<string> _beforeHandles = new(StringComparer.Ordinal);
        private static string _targetHandle = "";

        public static NativeAnnotationResult? LatestResult { get { lock (Gate) return _result; } }
        public static bool IsRunning { get { lock (Gate) return _running; } }

        public static bool Start(string targetPipeHandle, Point3d pickPoint, string idempotencyKey)
        {
            lock (Gate)
            {
                if (_running) return false;
                _running = true;
                _result = null;
            }

            Document doc = AcApp.DocumentManager.MdiActiveDocument;
            Database db = doc.Database;
            _targetHandle = targetPipeHandle;

            var result = new NativeAnnotationResult
            {
                CreationEntryPoint = $"{TianzhengAnnotationCommand} (twt_pipecmd.arx, group TWT_PIPECMD)",
                TargetPipeHandle = targetPipeHandle,
                IdempotencyKey = string.IsNullOrEmpty(idempotencyKey) ? null : idempotencyKey,
                PlanHash = TianzhengPipePlan.ComputeHash(pickPoint, pickPoint),
            };

            try
            {
                if (!string.IsNullOrEmpty(idempotencyKey) && TryReplay(db, idempotencyKey, result))
                {
                    lock (Gate) { _result = result; _running = false; }
                    return true;
                }

                List<DbObjectRecord> before = DatabaseScanner.ScanModelSpace(db, readGeometry: false);
                result.BeforeEntityCount = before.Count;
                _beforeHandles = new HashSet<string>(before.Select(o => o.Handle), StringComparer.Ordinal);
                result.TargetBefore = ObjectStateFingerprint.Capture(db, targetPipeHandle);
                _pending = result;

                _watched = doc;
                doc.CommandEnded += OnEnded;
                doc.CommandCancelled += OnCancelled;
                doc.CommandFailed += OnFailed;

                // DGGJ hit-tests the point against what is ON SCREEN, so a point outside the
                // current view cannot hit even when it lies exactly on the pipe. Bring the target
                // into view first. This is a VIEW change made through the managed API - it touches
                // no entity and queues no command.
                result.ViewFramedTarget = TryFrameTarget(doc, targetPipeHandle, result);

                string point =
                    pickPoint.X.ToString("R", CultureInfo.InvariantCulture) + "," +
                    pickPoint.Y.ToString("R", CultureInfo.InvariantCulture);

                // command, the pipe-derived point, then Enter, then the owned cancel.
                //
                // The order is deliberate and both tokens are required. After a point that HITS,
                // DGGJ loops back to its own prompt and only its 退出 Enter-default closes it - a
                // queued ESC alone was observed not to. After a point that MISSES, DGGJ closes by
                // itself, and the Enter then lands on an idle command line where it means "repeat
                // the last command" and silently launches a second DGGJ. The trailing ESC absorbs
                // exactly that case, and is inert when the command line is already idle.
                doc.SendStringToExecute(
                    $"{TianzhengAnnotationCommand}\n{point}\n\n{QueuedEscape}",
                    true, false, true);
                result.CancelSequenceIssued = true;
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

        /// <summary>
        /// Centre the current view on the target pipe so DGGJ's screen-space hit test can reach it.
        /// Returns false if the view could not be framed; the run then continues and the diff
        /// simply reports what actually happened.
        /// </summary>
        private static bool TryFrameTarget(Document doc, string handle, NativeAnnotationResult result)
        {
            try
            {
                Database db = doc.Database;
                if (!TianzhengPipeQuery.TryResolveHandle(db, handle, out ObjectId id)) return false;

                Extents3d extents;
                using (Transaction tr = db.TransactionManager.StartOpenCloseTransaction())
                {
                    if (tr.GetObject(id, OpenMode.ForRead) is not Entity entity) return false;
                    extents = entity.GeometricExtents;
                }

                double width = Math.Max(extents.MaxPoint.X - extents.MinPoint.X, 1.0);
                double height = Math.Max(extents.MaxPoint.Y - extents.MinPoint.Y, 1.0);
                // Square the frame and leave margin, so a horizontal pipe is not edge-to-edge.
                double span = Math.Max(width, height) * 2.0;

                using var view = new ViewTableRecord
                {
                    CenterPoint = new Point2d((extents.MinPoint.X + extents.MaxPoint.X) / 2.0,
                                              (extents.MinPoint.Y + extents.MaxPoint.Y) / 2.0),
                    Width = span,
                    Height = span,
                };
                doc.Editor.SetCurrentView(view);
                return true;
            }
            catch (Exception ex)
            {
                result.Warnings.Add($"could not frame the target in the current view ({ex.GetType().Name})");
                return false;
            }
        }

        private static void Unsubscribe()
        {
            Document? doc = _watched;
            _watched = null;
            if (doc == null) return;
            try
            {
                doc.CommandEnded -= OnEnded;
                doc.CommandCancelled -= OnCancelled;
                doc.CommandFailed -= OnFailed;
            }
            catch (Exception) { /* the document may already be gone */ }
        }

        private static void OnEnded(object? s, CommandEventArgs e) => Finish(e.GlobalCommandName, "ended");
        private static void OnCancelled(object? s, CommandEventArgs e) => Finish(e.GlobalCommandName, "cancelled");
        private static void OnFailed(object? s, CommandEventArgs e) => Finish(e.GlobalCommandName, "failed");

        private static void Finish(string commandName, string kind)
        {
            if (!string.Equals(commandName, TianzhengAnnotationCommand, StringComparison.OrdinalIgnoreCase))
                return;

            NativeAnnotationResult? result = _pending;
            _pending = null;
            Unsubscribe();
            if (result == null) return;

            try
            {
                Database db = AcApp.DocumentManager.MdiActiveDocument.Database;
                result.CommandObservedStart = true;
                result.CommandEndKind = kind;
                result.CommandTerminatedCleanly = true;

                List<DbObjectRecord> after = DatabaseScanner.ScanModelSpace(db, readGeometry: true);
                result.AfterEntityCount = after.Count;
                var afterHandles = new HashSet<string>(after.Select(o => o.Handle), StringComparer.Ordinal);
                result.NewObjects = after.Where(o => !_beforeHandles.Contains(o.Handle)).ToList();
                result.DeletedHandles = _beforeHandles.Where(h => !afterHandles.Contains(h)).ToList();

                result.TargetAfter = ObjectStateFingerprint.Capture(db, _targetHandle);
                if (result.TargetBefore != null && result.TargetAfter != null)
                    result.TargetDifferences = ObjectStateFingerprint.Differences(
                        result.TargetBefore, result.TargetAfter);

                // Let the settled database decide the storage model. Nothing is assumed.
                DbObjectRecord? annotationObject = result.NewObjects.FirstOrDefault(
                    o => o.RuntimeClass.StartsWith("TDb", StringComparison.Ordinal));

                if (annotationObject != null)
                {
                    result.StorageModel = "MODEL_A_SEPARATE_OBJECT";
                    result.Status = "created_object";
                }
                else if (result.TargetDifferences.Count > 0)
                {
                    result.StorageModel = "MODEL_B_PIPE_OWNED_STATE";
                    result.Status = "modified_target";
                }
                else
                {
                    result.StorageModel = "UNDETERMINED";
                    result.Status = "no_effect";
                    result.Warnings.Add(
                        TianzhengAnnotationCommand + " finished but neither a new Tianzheng object " +
                        "nor any observable change to the target pipe was detected; the annotation " +
                        "state may live somewhere the current managed surface cannot see");
                }

                if (!string.IsNullOrEmpty(result.IdempotencyKey) && result.Status != "no_effect")
                    result.RecordPersisted = WriteRecord(db, result.IdempotencyKey!, result);
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

        private static bool TryReplay(Database db, string key, NativeAnnotationResult result)
        {
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            IdempotencyRecord? record = IdempotencyStore.TryRead(tr, db, key);
            if (record == null) return false;

            if (!string.Equals(record.PlanHash, result.PlanHash, StringComparison.Ordinal))
            {
                result.Status = "failed";
                result.ErrorCode = TianzhengErrorCodes.IdempotencyConflict;
                result.Error = "the same idempotency key was previously used for a different annotation";
                return true;
            }

            result.Status = "already_applied";
            result.ReplayedFromRecord = true;
            result.RecordPersisted = true;
            result.CommandTerminatedCleanly = true;
            result.TargetAfter = ObjectStateFingerprint.Capture(db, result.TargetPipeHandle ?? "");
            result.StorageModel = record.Handles.Count > 1
                ? "MODEL_A_SEPARATE_OBJECT" : "MODEL_B_PIPE_OWNED_STATE";
            return true;
        }

        private static bool WriteRecord(Database db, string key, NativeAnnotationResult result)
        {
            try
            {
                using Transaction tr = db.TransactionManager.StartTransaction();
                var handles = new List<string> { result.TargetPipeHandle! };
                handles.AddRange(result.NewObjects.Select(o => o.Handle));
                IdempotencyStore.Write(tr, db, key, result.PlanHash!, handles, handles.Count);
                tr.Commit();
                return true;
            }
            catch (Exception ex)
            {
                result.Warnings.Add($"idempotency record could not be written ({ex.GetType().Name})");
                return false;
            }
        }
    }
}