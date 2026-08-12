using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
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
        public string? TdbPipeObjectId { get; set; }
        public string? TdbPipeHandle { get; set; }
        public string? RuntimeClass { get; set; }
        public string? DxfName { get; set; }
        public bool NativeIdentityConfirmed { get; set; }
        public string DocumentName { get; set; } = "";
        public List<string> Warnings { get; set; } = new();
        public string? Error { get; set; }
    }

    /// <summary>
    /// S8.1 native creation proof-of-concept.
    ///
    /// WHY A FIXED COMMAND: Tianzheng ships ObjectARX modules only. TDbPipe's constructor is
    /// exported from tch_pipewire.arx as a native C++ symbol, but there is no managed wrapper
    /// and no supported managed construction path, and a bare instance would carry none of the
    /// node/linkage state a real pipe needs. Tianzheng's own HZGX command runs the complete
    /// creation lifecycle, so it is the only entry that yields a genuine, fully-formed object.
    ///
    /// SCOPE OF THE COMMAND SURFACE: the command name is a hard-coded constant. Callers supply
    /// two coordinates and nothing else. There is deliberately no way to pass a command string,
    /// a LISP expression, or any additional command tokens through this path.
    ///
    /// THREADING: the command body runs in AutoCAD's own command context, which is what makes
    /// Editor.Command usable. The transport thread only starts it and later reads the result;
    /// it never blocks the main thread waiting, which would deadlock the command it queued.
    /// </summary>
    internal static class NativePipePoc
    {
        /// <summary>The single Tianzheng command this PoC is allowed to invoke.</summary>
        public const string TianzhengPipeCommand = "HZGX";

        /// <summary>Runtime class that constitutes a successful native identity.</summary>
        public const string TargetRuntimeClass = "TDbPipe";

        private static readonly object Gate = new();
        private static NativePipePocResult? _result;
        private static bool _running;
        private static Point3d _start;
        private static Point3d _end;

        public static NativePipePocResult? LatestResult
        {
            get { lock (Gate) return _result; }
        }

        public static bool IsRunning
        {
            get { lock (Gate) return _running; }
        }

        /// <summary>
        /// Queue the PoC. Returns false if one is already in flight. Must be called on the main
        /// thread; it returns immediately rather than waiting, so the queued command can run.
        /// </summary>
        public static bool Start(Point3d start, Point3d end)
        {
            lock (Gate)
            {
                if (_running) return false;
                _running = true;
                _result = null;
                _start = start;
                _end = end;
            }

            Document doc = AcApp.DocumentManager.MdiActiveDocument;
            doc.SendStringToExecute($"{PocCommandName} ", true, false, true);
            return true;
        }

        internal static void Abandon(string reason)
        {
            lock (Gate)
            {
                _running = false;
                _result = new NativePipePocResult { Status = "failed", Error = reason };
            }
        }

        /// <summary>
        /// Name of the plugin command that carries out the PoC. It is registered by
        /// <see cref="NativePipeCommands"/>: AutoCAD's command registration ignores static
        /// classes, so the attribute cannot live on this type.
        /// </summary>
        internal const string PocCommandName = "TZS8NATIVEPIPEPOC";

        internal static void RunPoc()
        {
            var result = new NativePipePocResult
            {
                CreationMethod = "tianzheng_fixed_command",
                CreationEntryPoint = $"{TianzhengPipeCommand} (twt_pipecmd.arx, group TWT_PIPECMD)",
            };

            Point3d start, end;
            lock (Gate)
            {
                start = _start;
                end = _end;
            }
            result.RequestedStart = new[] { start.X, start.Y, start.Z };
            result.RequestedEnd = new[] { end.X, end.Y, end.Z };

            try
            {
                Document doc = AcApp.DocumentManager.MdiActiveDocument;
                Database db = doc.Database;
                Editor ed = doc.Editor;
                result.DocumentName = doc.Name;

                result.BeforeObjects = DatabaseScanner.ScanModelSpace(db, readGeometry: false);
                result.BeforeEntityCount = result.BeforeObjects.Count;
                var beforeHandles = new HashSet<string>(
                    result.BeforeObjects.Select(o => o.Handle), StringComparer.Ordinal);

                // The command name is a constant and the only variable input is two points.
                // The trailing empty string is the ENTER that ends HZGX's point loop.
                ed.Command(TianzhengPipeCommand, start, end, "");

                result.AfterObjects = DatabaseScanner.ScanModelSpace(db, readGeometry: true);
                result.AfterEntityCount = result.AfterObjects.Count;

                // Tianzheng may create a pipe plus nodes, fittings and helper objects in one go,
                // so the diff is a set, never an assumed single object.
                result.NewObjects = result.AfterObjects
                    .Where(o => !beforeHandles.Contains(o.Handle))
                    .ToList();
                result.NewObjectCount = result.NewObjects.Count;

                DbObjectRecord? pipe = result.NewObjects
                    .FirstOrDefault(o => string.Equals(o.RuntimeClass, TargetRuntimeClass, StringComparison.Ordinal));

                if (pipe != null)
                {
                    result.TdbPipeObjectId = pipe.ObjectId;
                    result.TdbPipeHandle = pipe.Handle;
                    result.RuntimeClass = pipe.RuntimeClass;
                    result.DxfName = pipe.DxfName;
                    result.NativeIdentityConfirmed = true;
                    result.Status = "created";
                }
                else
                {
                    result.Status = "no_native_pipe_in_diff";
                    result.NativeIdentityConfirmed = false;
                    if (result.NewObjectCount == 0)
                        result.Warnings.Add("command produced no new model-space objects");
                    else
                        result.Warnings.Add(
                            "new objects appeared but none had runtime class " + TargetRuntimeClass +
                            "; classes seen: " +
                            string.Join(",", result.NewObjects.Select(o => o.RuntimeClass).Distinct()));
                }
            }
            catch (Exception ex)
            {
                result.Status = "failed";
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
    }

    /// <summary>
    /// Command host for the native-pipe PoC.
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
