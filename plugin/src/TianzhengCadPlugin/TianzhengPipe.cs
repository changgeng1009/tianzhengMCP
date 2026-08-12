using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Exception = System.Exception;

namespace TianzhengCadPlugin
{
    /// <summary>Runtime class names that make up the pipe object family.</summary>
    internal static class TianzhengClasses
    {
        public const string Pipe = "TDbPipe";
        public const string PipeFitting = "TDbPipeFitting";
        public const string PipeNode = "TDbPipeNode";

        /// <summary>Objects Tianzheng creates alongside a pipe and manages as part of its lifecycle.</summary>
        public static readonly IReadOnlySet<string> RelatedClasses = new HashSet<string>(StringComparer.Ordinal)
        {
            PipeFitting, PipeNode,
        };

        /// <summary>A proxy means the defining module was NOT loaded: never a valid native identity.</summary>
        public static bool IsProxy(string runtimeClass) =>
            runtimeClass.StartsWith("AcDbProxy", StringComparison.Ordinal) ||
            runtimeClass.StartsWith("AcDbZombie", StringComparison.Ordinal);
    }

    /// <summary>Is the Tianzheng object model live in this very process?</summary>
    internal static class TianzhengRuntime
    {
        /// <summary>
        /// Answered by resolving TDbPipe in the runtime class registry. That can only succeed
        /// if Tianzheng's modules loaded and registered their object model here, so it cannot
        /// be faked by configuration or an environment variable.
        /// </summary>
        public static bool IsAvailable(out string detail)
        {
            try
            {
                RxClassInfo pipe = RxClassProbe.Query(TianzhengClasses.Pipe);
                if (pipe.Found)
                {
                    detail = $"{TianzhengClasses.Pipe} resolved in this process";
                    return true;
                }
                detail = $"{TianzhengClasses.Pipe} is not a registered runtime class in this " +
                         "AutoCAD session; start Tianzheng through its own launcher";
                return false;
            }
            catch (Exception ex)
            {
                detail = $"Tianzheng runtime probe failed ({ex.GetType().Name})";
                return false;
            }
        }
    }

    /// <summary>One property value plus where it actually came from.</summary>
    internal sealed class PropertyValue
    {
        public object? Value { get; set; }
        public string Source { get; set; } = "";
        public string? Detail { get; set; }

        public static PropertyValue FromObject(object? value, string detail) =>
            new() { Value = value, Source = "native_object", Detail = detail };

        /// <summary>No readable route exists yet. The value stays null - it is never invented.</summary>
        public static PropertyValue Unavailable(string detail) =>
            new() { Value = null, Source = "NOT_READABLE_WITH_CURRENT_SURFACE", Detail = detail };
    }

    /// <summary>
    /// Identity of a pipe that must survive save/close/reopen.
    ///
    /// Handle is included because it is the database's own persistent id, but semantic
    /// equivalence deliberately does NOT rest on the handle alone - a drawing could be
    /// rebuilt with different handles and still hold the same pipe.
    /// </summary>
    internal sealed class TianzhengPipeSignature
    {
        public string NativeRuntimeClass { get; set; } = "";
        public double[]? Start { get; set; }
        public double[]? End { get; set; }
        public double GeometryTolerance { get; set; } = 1e-6;
        public PropertyValue? Diameter { get; set; }
        public PropertyValue? System { get; set; }
        public PropertyValue? Elevation { get; set; }

        /// <summary>Compare on native class and geometry; readable properties join only when present.</summary>
        public bool Matches(TianzhengPipeSignature other, out string reason)
        {
            if (!string.Equals(NativeRuntimeClass, other.NativeRuntimeClass, StringComparison.Ordinal))
            {
                reason = $"runtime class {NativeRuntimeClass} != {other.NativeRuntimeClass}";
                return false;
            }
            double tolerance = Math.Max(GeometryTolerance, other.GeometryTolerance);
            if (!PointsMatch(Start, other.Start, tolerance))
            {
                reason = "start point differs";
                return false;
            }
            if (!PointsMatch(End, other.End, tolerance))
            {
                reason = "end point differs";
                return false;
            }
            reason = "native class and geometry match";
            return true;
        }

        private static bool PointsMatch(double[]? a, double[]? b, double tolerance)
        {
            if (a == null || b == null) return a == null && b == null;
            if (a.Length != b.Length) return false;
            return !a.Where((t, i) => Math.Abs(t - b[i]) > tolerance).Any();
        }
    }

    /// <summary>What a query returns. Never a DBObject and never a native pointer.</summary>
    internal sealed class TianzhengPipeSnapshot
    {
        public bool NativeIdentityConfirmed { get; set; }
        public string PrimaryHandle { get; set; } = "";
        public string RuntimeClass { get; set; } = "";
        public string DxfName { get; set; } = "";
        public string Layer { get; set; } = "";
        public List<string> Ancestry { get; set; } = new();
        public double[]? Start { get; set; }
        public double[]? End { get; set; }
        public double? Length { get; set; }
        public Dictionary<string, PropertyValue> Properties { get; set; } = new();
        public List<string> RelatedHandles { get; set; } = new();
        public List<string> RelatedRuntimeClasses { get; set; } = new();
        public string? Error { get; set; }

        public TianzhengPipeSignature ToSignature() => new()
        {
            NativeRuntimeClass = RuntimeClass,
            Start = Start,
            End = End,
            Diameter = Properties.GetValueOrDefault("diameter"),
            System = Properties.GetValueOrDefault("system"),
            Elevation = Properties.GetValueOrDefault("elevation"),
        };
    }

    /// <summary>How many native pipe-family objects a drawing currently holds.</summary>
    internal sealed class TianzhengPipeInventory
    {
        public int PipeCount { get; set; }
        public int FittingCount { get; set; }
        public List<string> PipeHandles { get; set; } = new();
        public List<string> FittingHandles { get; set; } = new();
    }

    /// <summary>
    /// Read-only queries over Tianzheng pipe objects.
    ///
    /// Runtime class always comes from <c>ObjectId.ObjectClass</c>, so identity reflects what the
    /// object IS rather than which managed base class the .NET wrapper happened to return.
    /// </summary>
    internal static class TianzhengPipeQuery
    {
        public static TianzhengPipeInventory TakeInventory(Database db)
        {
            var inventory = new TianzhengPipeInventory();
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);

            foreach (ObjectId id in ms)
            {
                string name;
                try { name = id.ObjectClass.Name; }
                catch (Exception) { continue; }

                if (name == TianzhengClasses.Pipe)
                {
                    inventory.PipeCount++;
                    inventory.PipeHandles.Add(SafeHandle(id));
                }
                else if (TianzhengClasses.RelatedClasses.Contains(name))
                {
                    inventory.FittingCount++;
                    inventory.FittingHandles.Add(SafeHandle(id));
                }
            }
            return inventory;
        }

        /// <summary>Resolve a handle to an object id within this database.</summary>
        public static bool TryResolveHandle(Database db, string handle, out ObjectId id)
        {
            id = ObjectId.Null;
            if (string.IsNullOrWhiteSpace(handle)) return false;
            try
            {
                long value = Convert.ToInt64(handle, 16);
                return db.TryGetObjectId(new Handle(value), out id) && !id.IsNull;
            }
            catch (Exception)
            {
                return false;
            }
        }

        public static TianzhengPipeSnapshot Query(Database db, string handle,
                                                  IEnumerable<string>? relatedHandles = null)
        {
            var snapshot = new TianzhengPipeSnapshot { PrimaryHandle = handle };
            if (!TryResolveHandle(db, handle, out ObjectId id))
            {
                snapshot.Error = "handle does not resolve in this database";
                return snapshot;
            }

            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            try
            {
                RXClass cls = id.ObjectClass;
                snapshot.RuntimeClass = cls.Name;
                snapshot.DxfName = cls.DxfName ?? "";

                RXClass? cursor = cls.MyParent;
                int guard = 0;
                while (cursor != null && guard++ < 32)
                {
                    snapshot.Ancestry.Add(cursor.Name);
                    cursor = cursor.MyParent;
                }

                snapshot.NativeIdentityConfirmed =
                    snapshot.RuntimeClass == TianzhengClasses.Pipe &&
                    !TianzhengClasses.IsProxy(snapshot.RuntimeClass) &&
                    snapshot.Ancestry.Contains("AcDbObject");

                DBObject obj = tr.GetObject(id, OpenMode.ForRead);
                if (obj is Entity entity) snapshot.Layer = entity.Layer;
                if (obj is Curve curve)
                {
                    Point3d s = curve.StartPoint, e = curve.EndPoint;
                    snapshot.Start = new[] { s.X, s.Y, s.Z };
                    snapshot.End = new[] { e.X, e.Y, e.Z };
                    try { snapshot.Length = curve.GetDistanceAtParameter(curve.EndParam); }
                    catch (Exception) { /* not all custom curves answer parameter queries */ }
                }

                snapshot.Properties = ReadProperties(tr, obj, snapshot);
            }
            catch (Exception ex)
            {
                snapshot.Error = $"query failed ({ex.GetType().Name})";
            }

            foreach (string related in relatedHandles ?? Enumerable.Empty<string>())
            {
                snapshot.RelatedHandles.Add(related);
                snapshot.RelatedRuntimeClasses.Add(
                    TryResolveHandle(db, related, out ObjectId rid) ? SafeClassName(rid) : "MISSING");
            }

            return snapshot;
        }

        /// <summary>
        /// S8.3 property access. Every entry records its source, and a value that cannot be
        /// obtained is reported as NOT_READABLE_WITH_CURRENT_SURFACE rather than guessed.
        /// </summary>
        private static Dictionary<string, PropertyValue> ReadProperties(
            Transaction tr, DBObject obj, TianzhengPipeSnapshot snapshot)
        {
            var properties = new Dictionary<string, PropertyValue>(StringComparer.Ordinal);

            if (snapshot.Start != null && snapshot.End != null)
            {
                properties["start"] = PropertyValue.FromObject(snapshot.Start, "AcDbCurve.StartPoint");
                properties["end"] = PropertyValue.FromObject(snapshot.End, "AcDbCurve.EndPoint");
            }
            if (snapshot.Length != null)
                properties["length"] = PropertyValue.FromObject(snapshot.Length, "AcDbCurve parameter length");

            // Elevation: the pipe's own Z. Read from the object's geometry, not from any request.
            if (snapshot.Start != null)
                properties["elevation"] = PropertyValue.FromObject(
                    snapshot.Start[2], "Z of AcDbCurve.StartPoint");
            else
                properties["elevation"] = PropertyValue.Unavailable("no curve geometry reachable");

            // Diameter and system live in Tianzheng's native property surface. Probe the two
            // managed-reachable stores before declaring them unreadable.
            var xdataApps = new List<string>();
            try
            {
                ResultBuffer? xdata = obj.XData;
                if (xdata != null)
                    xdataApps.AddRange(xdata.AsArray()
                        .Where(v => v.TypeCode == 1001)
                        .Select(v => v.Value?.ToString() ?? ""));
            }
            catch (Exception) { /* absent XData is a normal answer */ }

            var extensionKeys = new List<string>();
            try
            {
                if (!obj.ExtensionDictionary.IsNull)
                {
                    var dict = (DBDictionary)tr.GetObject(obj.ExtensionDictionary, OpenMode.ForRead);
                    extensionKeys.AddRange(dict.Cast<DBDictionaryEntry>().Select(e => e.Key));
                }
            }
            catch (Exception) { /* absent extension dictionary is a normal answer */ }

            string probed = $"XData apps: [{string.Join(",", xdataApps)}]; " +
                            $"extension dictionary keys: [{string.Join(",", extensionKeys)}]";

            properties["diameter"] = PropertyValue.Unavailable(
                "TDbPipe.GetDnDiameter is a native C++ member with no managed wrapper; " + probed);
            properties["system"] = PropertyValue.Unavailable(
                "TDbPipe/TDbPipePrototype GetSysType/GetPipeSystemName are native C++ members " +
                "with no managed wrapper; " + probed);

            // The layer Tianzheng assigns encodes the system, but it is an indirect indicator and
            // is reported as such rather than as the system property itself.
            if (!string.IsNullOrEmpty(snapshot.Layer))
                properties["system_layer_indicator"] = PropertyValue.FromObject(
                    snapshot.Layer, "Entity.Layer (INDIRECT: layer named by Tianzheng, not the system property)");

            return properties;
        }

        private static string SafeClassName(ObjectId id)
        {
            try { return id.ObjectClass.Name; }
            catch (Exception) { return "UNKNOWN"; }
        }

        private static string SafeHandle(ObjectId id)
        {
            try { return id.Handle.ToString(); }
            catch (Exception) { return ""; }
        }
    }

    /// <summary>Stable hash of the requested pipe, used as the idempotency plan hash.</summary>
    internal static class TianzhengPipePlan
    {
        public static string ComputeHash(Point3d start, Point3d end)
        {
            string canonical = string.Join("|", new[]
            {
                "tianzheng_pipe_v1",
                start.X.ToString("R", CultureInfo.InvariantCulture),
                start.Y.ToString("R", CultureInfo.InvariantCulture),
                start.Z.ToString("R", CultureInfo.InvariantCulture),
                end.X.ToString("R", CultureInfo.InvariantCulture),
                end.Y.ToString("R", CultureInfo.InvariantCulture),
                end.Z.ToString("R", CultureInfo.InvariantCulture),
            });
            byte[] hash = System.Security.Cryptography.SHA256.HashData(
                System.Text.Encoding.UTF8.GetBytes(canonical));
            return Convert.ToHexString(hash);
        }
    }
}
