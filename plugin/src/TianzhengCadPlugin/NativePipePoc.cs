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
    /// <summary>One database object as observed during a model-space scan.</summary>
    internal sealed class DbObjectRecord
    {
        public string Handle { get; set; } = "";
        public string ObjectId { get; set; } = "";
        public string RuntimeClass { get; set; } = "";
        public string DxfName { get; set; } = "";
        public string ParentClass { get; set; } = "";
        public List<string> Ancestry { get; set; } = new();
        public bool IsEntity { get; set; }
        public string Layer { get; set; } = "";

        /// <summary>Geometry read back FROM the object, never echoed from the request.</summary>
        public double[]? StartPoint { get; set; }
        public double[]? EndPoint { get; set; }
        public double? Length { get; set; }
        public string? PropertyReadNote { get; set; }
    }

    /// <summary>
    /// Read-only model-space scanner used to build before/after snapshots.
    ///
    /// Object identity is taken from <see cref="Autodesk.AutoCAD.DatabaseServices.ObjectId.ObjectClass"/>,
    /// which reports the true runtime class without opening the object. That matters here: a
    /// Tianzheng custom object must be identified by what it actually IS, not by whichever
    /// managed base class the .NET wrapper happens to hand back.
    /// </summary>
    internal static class DatabaseScanner
    {
        public static List<DbObjectRecord> ScanModelSpace(Database db, bool readGeometry)
        {
            var records = new List<DbObjectRecord>();
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);

            foreach (ObjectId id in ms)
            {
                var record = new DbObjectRecord
                {
                    Handle = SafeHandle(id),
                    ObjectId = id.OldIdPtr.ToString(),
                };

                try
                {
                    RXClass cls = id.ObjectClass;
                    record.RuntimeClass = cls.Name;
                    record.DxfName = cls.DxfName ?? "";
                    RXClass? parent = cls.MyParent;
                    record.ParentClass = parent?.Name ?? "";

                    RXClass? cursor = parent;
                    int guard = 0;
                    while (cursor != null && guard++ < 32)
                    {
                        record.Ancestry.Add(cursor.Name);
                        if (cursor.Name == "AcDbEntity") record.IsEntity = true;
                        cursor = cursor.MyParent;
                    }
                }
                catch (Exception ex)
                {
                    record.PropertyReadNote = $"class read failed ({ex.GetType().Name})";
                }

                if (readGeometry) ReadGeometry(tr, id, record);
                records.Add(record);
            }

            return records;
        }

        /// <summary>
        /// Read what the object itself reports. Values that cannot be obtained are left null and
        /// noted, never substituted from the creation request.
        /// </summary>
        private static void ReadGeometry(Transaction tr, ObjectId id, DbObjectRecord record)
        {
            try
            {
                DBObject obj = tr.GetObject(id, OpenMode.ForRead);
                if (obj is Entity entity) record.Layer = entity.Layer;

                if (obj is Curve curve)
                {
                    Point3d s = curve.StartPoint;
                    Point3d e = curve.EndPoint;
                    record.StartPoint = new[] { s.X, s.Y, s.Z };
                    record.EndPoint = new[] { e.X, e.Y, e.Z };
                    try { record.Length = curve.GetDistanceAtParameter(curve.EndParam); }
                    catch (Exception) { /* some custom curves refuse parameter queries */ }
                }
                else
                {
                    record.PropertyReadNote =
                        $"managed wrapper is {obj.GetType().Name}; no curve geometry reachable from managed code";
                }
            }
            catch (Exception ex)
            {
                record.PropertyReadNote = $"open failed ({ex.GetType().Name})";
            }
        }

        private static string SafeHandle(ObjectId id)
        {
            try { return id.Handle.ToString(); }
            catch (Exception) { return ""; }
        }
    }

    /// <summary>Outcome of one native-pipe creation attempt.</summary>
    internal sealed class NativePipePocResult
    {
        /// <summary>created | already_applied | equivalent | no_native_pipe_in_diff | failed</summary>
        public string Status { get; set; } = "pending";
        public string CreationMethod { get; set; } = "";
        public string CreationEntryPoint { get; set; } = "";
        public double[]? RequestedStart { get; set; }
        public double[]? RequestedEnd { get; set; }

        public int BeforeEntityCount { get; set; }
        public int AfterEntityCount { get; set; }
        public int NewObjectCount { get; set; }
        public List<DbObjectRecord> NewObjects { get; set; } = new();
        public List<DbObjectRecord> BeforeObjects { get; set; } = new();
        public List<DbObjectRecord> AfterObjects { get; set; } = new();

        // --- primary vs related, per S8.2: one HZGX yields a pipe AND its nodes ---
        public string? PrimaryHandle { get; set; }
        public string? PrimaryRuntimeClass { get; set; }
        public List<string> RelatedHandles { get; set; } = new();
        public List<string> RelatedRuntimeClasses { get; set; } = new();
        public int NativeObjectCount { get; set; }

        // --- inventory, so replay can prove no duplicates ---
        public int PipeCountBefore { get; set; }
        public int PipeCountAfter { get; set; }
        public int FittingCountBefore { get; set; }
        public int FittingCountAfter { get; set; }

        // --- idempotency ---
        public string? IdempotencyKey { get; set; }
        public string? PlanHash { get; set; }
        public bool ReplayedFromRecord { get; set; }
        public bool DuplicateCreated { get; set; }
        public bool RecordPersisted { get; set; }

        public bool NativeIdentityConfirmed { get; set; }
        public string DocumentName { get; set; } = "";
        public TianzhengPipeSnapshot? Snapshot { get; set; }
        public List<string> Warnings { get; set; } = new();
        public string? Error { get; set; }
        public string? ErrorCode { get; set; }

        // Kept for S8.1 evidence compatibility.
        public string? TdbPipeObjectId { get; set; }
        public string? TdbPipeHandle { get; set; }
        public string? RuntimeClass { get; set; }
        public string? DxfName { get; set; }
    }

    /// <summary>
    /// The Tianzheng pipe creation adapter.
    ///
    /// WHY A FIXED COMMAND: Tianzheng ships ObjectARX modules only. TDbPipe's constructor is
    /// exported from tch_pipewire.arx as a native C++ symbol, but there is no managed wrapper
    /// and no supported managed construction path, and a bare instance would carry none of the
    /// node/linkage state a real pipe needs. Tianzheng's own HZGX command runs the complete
    /// creation lifecycle, so it is the only entry that yields a genuine, fully-formed object.
    ///
    /// SCOPE OF THE COMMAND SURFACE: <see cref="TianzhengPipeCommand"/> is the single place in
    /// the entire codebase where a Tianzheng command name appears. Callers supply two
    /// coordinates and nothing else. There is deliberately no way to pass a command string, a
    /// LISP expression, raw keystrokes, or any extra command tokens through this path.
    ///
    /// THREADING: the body runs in AutoCAD's own command context, which is what makes
    /// Editor.Command usable. The transport thread only starts it and later reads the result;
    /// it never blocks the main thread waiting, which would deadlock the command it queued.
    /// </summary>
    internal static class NativePipePoc
    {
        /// <summary>The single Tianzheng command this adapter is allowed to invoke.</summary>
        public const string TianzhengPipeCommand = "HZGX";

        /// <summary>Runtime class that constitutes a successful native identity.</summary>
        public const string TargetRuntimeClass = TianzhengClasses.Pipe;

        /// <summary>
        /// Name of the plugin command that carries out the work. It is registered by
        /// <see cref="NativePipeCommands"/>: AutoCAD's command registration ignores static
        /// classes, so the attribute cannot live on this type.
        /// </summary>
        internal const string PocCommandName = "TZS8NATIVEPIPEPOC";

        private static readonly object Gate = new();
        private static NativePipePocResult? _result;
        private static bool _running;
        private static Point3d _start;
        private static Point3d _end;
        private static string _idempotencyKey = "";

        public static NativePipePocResult? LatestResult
        {
            get { lock (Gate) return _result; }
        }

        public static bool IsRunning
        {
            get { lock (Gate) return _running; }
        }

        /// <summary>
        /// Queue a creation. Returns false if one is already in flight. Must be called on the
        /// main thread; it returns immediately rather than waiting, so the queued command can run.
        /// </summary>
        public static bool Start(Point3d start, Point3d end, string idempotencyKey)
        {
            lock (Gate)
            {
                if (_running) return false;
                _running = true;
                _result = null;
                _start = start;
                _end = end;
                _idempotencyKey = idempotencyKey ?? "";
            }

            Document doc = AcApp.DocumentManager.MdiActiveDocument;
            doc.SendStringToExecute($"{PocCommandName} ", true, false, true);
            return true;
        }

        internal static void RunPoc()
        {
            Point3d start, end;
            string key;
            lock (Gate)
            {
                start = _start;
                end = _end;
                key = _idempotencyKey;
            }

            var result = new NativePipePocResult
            {
                CreationMethod = "tianzheng_fixed_command",
                CreationEntryPoint = $"{TianzhengPipeCommand} (twt_pipecmd.arx, group TWT_PIPECMD)",
                RequestedStart = new[] { start.X, start.Y, start.Z },
                RequestedEnd = new[] { end.X, end.Y, end.Z },
                IdempotencyKey = string.IsNullOrEmpty(key) ? null : key,
                PlanHash = TianzhengPipePlan.ComputeHash(start, end),
            };

            try
            {
                Document doc = AcApp.DocumentManager.MdiActiveDocument;
                Database db = doc.Database;
                Editor ed = doc.Editor;
                result.DocumentName = doc.Name;

                TianzhengPipeInventory inventoryBefore = TianzhengPipeQuery.TakeInventory(db);
                result.PipeCountBefore = inventoryBefore.PipeCount;
                result.FittingCountBefore = inventoryBefore.FittingCount;

                // ---- persistent idempotency: consult the record stored INSIDE the drawing ----
                if (!string.IsNullOrEmpty(key) && TryReplay(db, key, result))
                {
                    result.PipeCountAfter = result.PipeCountBefore;
                    result.FittingCountAfter = result.FittingCountBefore;
                    return;
                }

                result.BeforeObjects = DatabaseScanner.ScanModelSpace(db, readGeometry: false);
                result.BeforeEntityCount = result.BeforeObjects.Count;
                var beforeHandles = new HashSet<string>(
                    result.BeforeObjects.Select(o => o.Handle), StringComparer.Ordinal);

                // The command name is a constant and the only variable input is two points.
                // The trailing empty string is the ENTER that ends HZGX's point loop.
                ed.Command(TianzhengPipeCommand, start, end, "");

                result.AfterObjects = DatabaseScanner.ScanModelSpace(db, readGeometry: true);
                result.AfterEntityCount = result.AfterObjects.Count;

                // Tianzheng creates a pipe plus nodes and helper objects in one go, so the diff
                // is a set, never an assumed single object.
                result.NewObjects = result.AfterObjects
                    .Where(o => !beforeHandles.Contains(o.Handle))
                    .ToList();
                result.NewObjectCount = result.NewObjects.Count;
                result.NativeObjectCount = result.NewObjects.Count;

                DbObjectRecord? pipe = result.NewObjects.FirstOrDefault(
                    o => string.Equals(o.RuntimeClass, TargetRuntimeClass, StringComparison.Ordinal));

                foreach (DbObjectRecord related in result.NewObjects.Where(o => o != pipe))
                {
                    result.RelatedHandles.Add(related.Handle);
                    result.RelatedRuntimeClasses.Add(related.RuntimeClass);
                }

                TianzhengPipeInventory inventoryAfter = TianzhengPipeQuery.TakeInventory(db);
                result.PipeCountAfter = inventoryAfter.PipeCount;
                result.FittingCountAfter = inventoryAfter.FittingCount;

                if (pipe == null)
                {
                    result.Status = "no_native_pipe_in_diff";
                    result.ErrorCode = TianzhengErrorCodes.NativeIdentityMismatch;
                    result.NativeIdentityConfirmed = false;
                    result.Warnings.Add(result.NewObjectCount == 0
                        ? "command produced no new model-space objects"
                        : "new objects appeared but none had runtime class " + TargetRuntimeClass +
                          "; classes seen: " +
                          string.Join(",", result.NewObjects.Select(o => o.RuntimeClass).Distinct()));
                    return;
                }

                result.PrimaryHandle = pipe.Handle;
                result.PrimaryRuntimeClass = pipe.RuntimeClass;
                result.TdbPipeObjectId = pipe.ObjectId;
                result.TdbPipeHandle = pipe.Handle;
                result.RuntimeClass = pipe.RuntimeClass;
                result.DxfName = pipe.DxfName;
                result.NativeIdentityConfirmed = true;
                result.DuplicateCreated = result.PipeCountAfter > result.PipeCountBefore + 1;
                result.Status = "created";
                result.Snapshot = TianzhengPipeQuery.Query(db, pipe.Handle, result.RelatedHandles);

                // Record the outcome inside the drawing so it survives save -> close -> reopen.
                if (!string.IsNullOrEmpty(key))
                    result.RecordPersisted = WriteRecord(db, key, result);
            }
            catch (Exception ex)
            {
                result.Status = "failed";
                result.ErrorCode = TianzhengErrorCodes.PersistenceFailed;
                result.Error = $"{ex.GetType().Name}: {ex.Message}";
            }
            finally
            {
                lock (Gate)
                {
                    _result = result;
                    _running = false;
                }
            }
        }

        /// <summary>
        /// Return true when a stored record proves this key already created a live native pipe.
        ///
        /// The stored handles are re-resolved and their runtime classes re-read from the current
        /// database: a record alone is not trusted, because the drawing is the source of truth.
        /// </summary>
        private static bool TryReplay(Database db, string key, NativePipePocResult result)
        {
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            IdempotencyRecord? record = IdempotencyStore.TryRead(tr, db, key);
            if (record == null) return false;

            if (!string.Equals(record.PlanHash, result.PlanHash, StringComparison.Ordinal))
            {
                result.Status = "failed";
                result.ErrorCode = TianzhengErrorCodes.IdempotencyConflict;
                result.Error = "the same idempotency key was previously used for a different pipe";
                return true;
            }

            string? primary = null;
            var related = new List<string>();
            foreach (string handle in record.Handles)
            {
                if (!TianzhengPipeQuery.TryResolveHandle(db, handle, out ObjectId id)) continue;
                string name;
                try { name = id.ObjectClass.Name; }
                catch (Exception) { continue; }

                if (name == TargetRuntimeClass && primary == null) primary = handle;
                else related.Add(handle);
            }

            if (primary == null) return false;  // record exists but the pipe is gone: create again

            result.Status = "already_applied";
            result.ReplayedFromRecord = true;
            result.DuplicateCreated = false;
            result.RecordPersisted = true;
            result.PrimaryHandle = primary;
            result.PrimaryRuntimeClass = TargetRuntimeClass;
            result.RelatedHandles = related;
            result.NativeObjectCount = 1 + related.Count;
            result.Snapshot = TianzhengPipeQuery.Query(db, primary, related);
            result.RelatedRuntimeClasses = result.Snapshot.RelatedRuntimeClasses;
            result.NativeIdentityConfirmed = result.Snapshot.NativeIdentityConfirmed;
            result.RuntimeClass = result.Snapshot.RuntimeClass;
            result.DxfName = result.Snapshot.DxfName;
            result.TdbPipeHandle = primary;
            return true;
        }

        private static bool WriteRecord(Database db, string key, NativePipePocResult result)
        {
            try
            {
                using Transaction tr = db.TransactionManager.StartTransaction();
                var handles = new List<string> { result.PrimaryHandle! };
                handles.AddRange(result.RelatedHandles);
                IdempotencyStore.Write(tr, db, key, result.PlanHash!, handles, handles.Count);
                tr.Commit();
                return true;
            }
            catch (Exception ex)
            {
                // Honest failure: the pipe exists but the replay guard does not.
                result.Warnings.Add(
                    $"idempotency record could not be written ({ex.GetType().Name}); " +
                    "a replay would create a duplicate");
                return false;
            }
        }
    }

    /// <summary>
    /// Command host for the pipe creation adapter.
    ///
    /// This type exists purely because AutoCAD's command registration walks the assembly's
    /// instantiable types: a [CommandMethod] on a static class is silently never registered,
    /// which shows up only as "unknown command" at run time.
    /// </summary>
    public sealed class NativePipeCommands
    {
        [CommandMethod("TZS8NATIVEPIPEPOC", CommandFlags.Modal)]
        public void RunNativePipePoc() => NativePipePoc.RunPoc();
    }
}
