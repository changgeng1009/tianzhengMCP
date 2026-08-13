using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using TianzhengCadPlugin.Protocol;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

namespace TianzhengCadPlugin
{
    /// <summary>Snapshot of one native Tianzheng equipment object. Never a DBObject or pointer.</summary>
    internal sealed class TianzhengEquipmentSnapshot
    {
        public string LogicalType { get; set; } = "equipment";
        public string EquipmentType { get; set; } = "";
        public string RuntimeClass { get; set; } = "";
        public string DxfName { get; set; } = "";
        public string Handle { get; set; } = "";
        public string ObjectId { get; set; } = "";
        public bool NativeIdentityConfirmed { get; set; }
        public double[]? Position { get; set; }
        public PropertyValue? Rotation { get; set; }
        public string Layer { get; set; } = "";
        public List<string> Ancestry { get; set; } = new();
        public List<string> RelatedObjects { get; set; } = new();
        public Dictionary<string, PropertyValue> Properties { get; set; } = new();
        public string IdempotencyStatus { get; set; } = "none";
        public List<string> Warnings { get; set; } = new();
        public string? Error { get; set; }
    }

    internal static class TianzhengEquipmentQuery
    {
        public const string PumpClass = "TDbPump";

        public static int CountByClass(Database db, string className)
        {
            int count = 0;
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);
            foreach (ObjectId id in ms)
            {
                try { if (id.ObjectClass.Name == className) count++; }
                catch (Exception) { /* unreadable entries are not matches */ }
            }
            return count;
        }

        public static TianzhengEquipmentSnapshot Query(Database db, string handle,
                                                       string equipmentType = "pump")
        {
            var snapshot = new TianzhengEquipmentSnapshot
            { Handle = handle, EquipmentType = equipmentType };

            if (!TianzhengPipeQuery.TryResolveHandle(db, handle, out ObjectId id))
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
                snapshot.ObjectId = id.OldIdPtr.ToString();

                RXClass? cursor = cls.MyParent;
                int guard = 0;
                while (cursor != null && guard++ < 32)
                {
                    snapshot.Ancestry.Add(cursor.Name);
                    cursor = cursor.MyParent;
                }

                // An ordinary BlockReference must never pass as native equipment.
                snapshot.NativeIdentityConfirmed =
                    snapshot.RuntimeClass == PumpClass &&
                    !TianzhengClasses.IsProxy(snapshot.RuntimeClass) &&
                    snapshot.Ancestry.Contains("AcDbObject");

                DBObject obj = tr.GetObject(id, OpenMode.ForRead);
                if (obj is Entity entity)
                {
                    snapshot.Layer = entity.Layer;
                    try
                    {
                        Extents3d extents = entity.GeometricExtents;
                        snapshot.Position = new[]
                        {
                            (extents.MinPoint.X + extents.MaxPoint.X) / 2.0,
                            (extents.MinPoint.Y + extents.MaxPoint.Y) / 2.0,
                            (extents.MinPoint.Z + extents.MaxPoint.Z) / 2.0,
                        };
                        snapshot.Properties["extents_min"] = PropertyValue.FromObject(
                            new[] { extents.MinPoint.X, extents.MinPoint.Y, extents.MinPoint.Z },
                            "Entity.GeometricExtents");
                        snapshot.Properties["extents_max"] = PropertyValue.FromObject(
                            new[] { extents.MaxPoint.X, extents.MaxPoint.Y, extents.MaxPoint.Z },
                            "Entity.GeometricExtents");
                    }
                    catch (Exception)
                    {
                        snapshot.Warnings.Add("geometric extents unavailable; position not read");
                    }
                }

                // Rotation lives in Tianzheng's native property surface, not the managed wrapper.
                snapshot.Rotation = PropertyValue.Unavailable(
                    "no managed accessor for the pump's rotation; the palette's 定位板转角 is not readable");
                snapshot.Properties["rotation"] = snapshot.Rotation;
                foreach (string absent in new[] { "pump_type", "base_size", "inlet_height",
                                                  "outlet_height", "pump_height" })
                {
                    snapshot.Properties[absent] = PropertyValue.Unavailable(
                        "palette parameter; not settable or readable through the current surface");
                }
            }
            catch (Exception ex)
            {
                snapshot.Error = $"query failed ({ex.GetType().Name})";
            }
            return snapshot;
        }
    }

    internal sealed class NativePumpResult
    {
        /// <summary>created | already_applied | no_native_pump_in_diff | failed</summary>
        public string Status { get; set; } = "pending";
        public string CreationMethod { get; set; } = "tianzheng_fixed_command";
        public string CreationEntryPoint { get; set; } = "";
        public double[]? RequestedPosition { get; set; }

        public int BeforeEntityCount { get; set; }
        public int AfterEntityCount { get; set; }
        public int NewObjectCount { get; set; }
        public List<DbObjectRecord> NewObjects { get; set; } = new();

        public int PumpCountBefore { get; set; }
        public int PumpCountAfter { get; set; }

        public string? PrimaryHandle { get; set; }
        public string? PrimaryRuntimeClass { get; set; }
        public bool NativeIdentityConfirmed { get; set; }

        // --- command termination evidence ---
        public bool CommandObservedStart { get; set; }
        public string CommandEndKind { get; set; } = "";      // ended | cancelled | failed
        public bool CommandTerminatedCleanly { get; set; }
        public bool CancelSequenceIssued { get; set; }

        public string? IdempotencyKey { get; set; }
        public string? PlanHash { get; set; }
        public bool ReplayedFromRecord { get; set; }
        public bool DuplicateCreated { get; set; }
        public bool RecordPersisted { get; set; }

        public TianzhengEquipmentSnapshot? Snapshot { get; set; }
        public List<string> Warnings { get; set; } = new();
        public string? Error { get; set; }
        public string? ErrorCode { get; set; }
    }

    /// <summary>
    /// Tianzheng pump creation adapter.
    ///
    /// HZSB is a compile-time constant; the caller supplies a position and nothing else.
    ///
    /// COMMAND TERMINATION. Every Tianzheng command probed so far (FMFJ, GXLJ, HZSB) stays in
    /// its own prompt loop afterwards, and a keyboard ESC delivered to the UI does not reach it
    /// — that ESC goes to the window, while the command is blocked reading the DOCUMENT's input
    /// queue. The fix is to put the cancel on that same queue: 0x03 is what AutoCAD reads as
    /// ESC there. Two are sent, because one closes an active sub-prompt and the second ends the
    /// command itself.
    ///
    /// This cancel is structurally owned: it is appended to the adapter's own queued sequence
    /// for its own whitelisted command. There is no general cancel operation, and no way for a
    /// caller to cancel or send keys to anything else.
    /// </summary>
    internal static class NativePumpAdapter
    {
        public const string TianzhengPumpCommand = "HZSB";

        /// <summary>What AutoCAD reads as ESC on the document input queue.</summary>
        private const string QueuedEscape = "";

        private static readonly object Gate = new();
        private static NativePumpResult? _result;
        private static bool _running;
        private static NativePumpResult? _pending;
        private static Document? _watched;
        private static HashSet<string> _beforeHandles = new(StringComparer.Ordinal);

        public static NativePumpResult? LatestResult { get { lock (Gate) return _result; } }
        public static bool IsRunning { get { lock (Gate) return _running; } }

        public static bool Start(Point3d position, string idempotencyKey)
        {
            lock (Gate)
            {
                if (_running) return false;
                _running = true;
                _result = null;
            }

            Document doc = AcApp.DocumentManager.MdiActiveDocument;
            Database db = doc.Database;

            var result = new NativePumpResult
            {
                CreationEntryPoint = $"{TianzhengPumpCommand} (twt_pipecmd.arx, group TWT_PIPECMD)",
                RequestedPosition = new[] { position.X, position.Y, position.Z },
                IdempotencyKey = string.IsNullOrEmpty(idempotencyKey) ? null : idempotencyKey,
                PlanHash = TianzhengPipePlan.ComputeHash(position, position),
            };

            try
            {
                result.PumpCountBefore = TianzhengEquipmentQuery.CountByClass(
                    db, TianzhengEquipmentQuery.PumpClass);

                if (!string.IsNullOrEmpty(idempotencyKey) && TryReplay(db, idempotencyKey, result))
                {
                    result.PumpCountAfter = result.PumpCountBefore;
                    lock (Gate) { _result = result; _running = false; }
                    return true;
                }

                List<DbObjectRecord> before = DatabaseScanner.ScanModelSpace(db, readGeometry: false);
                result.BeforeEntityCount = before.Count;
                _beforeHandles = new HashSet<string>(before.Select(o => o.Handle), StringComparer.Ordinal);
                _pending = result;

                _watched = doc;
                doc.CommandEnded += OnEnded;
                doc.CommandCancelled += OnCancelled;
                doc.CommandFailed += OnFailed;

                string point =
                    position.X.ToString("R", CultureInfo.InvariantCulture) + "," +
                    position.Y.ToString("R", CultureInfo.InvariantCulture);

                // command, placement point, then the owned cancel that ends its remaining loop.
                doc.SendStringToExecute(
                    $"{TianzhengPumpCommand}\n{point}\n{QueuedEscape}{QueuedEscape}",
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
            catch (Exception) { /* teardown is best effort */ }
        }

        private static void OnEnded(object? s, CommandEventArgs e) => Finish(e.GlobalCommandName, "ended");
        private static void OnCancelled(object? s, CommandEventArgs e) => Finish(e.GlobalCommandName, "cancelled");
        private static void OnFailed(object? s, CommandEventArgs e) => Finish(e.GlobalCommandName, "failed");

        /// <summary>
        /// Finalize when OUR command reports it has finished, however it finished.
        ///
        /// Cancelled counts: the question S10.3 must answer is whether the pump SURVIVES the
        /// cancel, and the only way to know is to read the database after the command is truly
        /// over. So the diff is always taken here, never mid-command.
        /// </summary>
        private static void Finish(string commandName, string kind)
        {
            if (!string.Equals(commandName, TianzhengPumpCommand, StringComparison.OrdinalIgnoreCase))
                return;

            NativePumpResult? result = _pending;
            _pending = null;
            Unsubscribe();
            if (result == null) return;

            try
            {
                Document doc = AcApp.DocumentManager.MdiActiveDocument;
                Database db = doc.Database;

                result.CommandObservedStart = true;
                result.CommandEndKind = kind;
                result.CommandTerminatedCleanly = true;

                List<DbObjectRecord> after = DatabaseScanner.ScanModelSpace(db, readGeometry: true);
                result.AfterEntityCount = after.Count;
                result.NewObjects = after.Where(o => !_beforeHandles.Contains(o.Handle)).ToList();
                result.NewObjectCount = result.NewObjects.Count;
                result.PumpCountAfter = TianzhengEquipmentQuery.CountByClass(
                    db, TianzhengEquipmentQuery.PumpClass);

                DbObjectRecord? pump = result.NewObjects.FirstOrDefault(
                    o => o.RuntimeClass == TianzhengEquipmentQuery.PumpClass);

                if (pump == null)
                {
                    result.Status = "no_native_pump_in_diff";
                    result.ErrorCode = TianzhengErrorCodes.NativeIdentityMismatch;
                    result.Warnings.Add(result.NewObjectCount == 0
                        ? $"{TianzhengPumpCommand} {kind} but produced no new model-space objects"
                        : "new objects appeared but none were " + TianzhengEquipmentQuery.PumpClass +
                          "; classes seen: " +
                          string.Join(",", result.NewObjects.Select(o => o.RuntimeClass).Distinct()));
                    return;
                }

                result.PrimaryHandle = pump.Handle;
                result.PrimaryRuntimeClass = pump.RuntimeClass;
                result.NativeIdentityConfirmed = true;
                result.DuplicateCreated = result.PumpCountAfter > result.PumpCountBefore + 1;
                result.Status = "created";
                result.Snapshot = TianzhengEquipmentQuery.Query(db, pump.Handle);

                if (!string.IsNullOrEmpty(result.IdempotencyKey))
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

        private static bool TryReplay(Database db, string key, NativePumpResult result)
        {
            using Transaction tr = db.TransactionManager.StartOpenCloseTransaction();
            IdempotencyRecord? record = IdempotencyStore.TryRead(tr, db, key);
            if (record == null) return false;

            if (!string.Equals(record.PlanHash, result.PlanHash, StringComparison.Ordinal))
            {
                result.Status = "failed";
                result.ErrorCode = TianzhengErrorCodes.IdempotencyConflict;
                result.Error = "the same idempotency key was previously used for a different pump";
                return true;
            }

            foreach (string handle in record.Handles)
            {
                if (!TianzhengPipeQuery.TryResolveHandle(db, handle, out ObjectId id)) continue;
                string name;
                try { name = id.ObjectClass.Name; }
                catch (Exception) { continue; }
                if (name != TianzhengEquipmentQuery.PumpClass) continue;

                result.Status = "already_applied";
                result.ReplayedFromRecord = true;
                result.RecordPersisted = true;
                result.DuplicateCreated = false;
                result.PrimaryHandle = handle;
                result.PrimaryRuntimeClass = name;
                result.CommandTerminatedCleanly = true;
                result.Snapshot = TianzhengEquipmentQuery.Query(db, handle);
                result.NativeIdentityConfirmed = result.Snapshot.NativeIdentityConfirmed;
                return true;
            }
            return false;
        }

        private static bool WriteRecord(Database db, string key, NativePumpResult result)
        {
            try
            {
                using Transaction tr = db.TransactionManager.StartTransaction();
                IdempotencyStore.Write(tr, db, key, result.PlanHash!,
                                       new List<string> { result.PrimaryHandle! }, 1);
                tr.Commit();
                return true;
            }
            catch (Exception ex)
            {
                result.Warnings.Add(
                    $"idempotency record could not be written ({ex.GetType().Name}); " +
                    "a replay would create a duplicate pump");
                return false;
            }
        }
    }
}
