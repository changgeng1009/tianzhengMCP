using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using AcadPolyline = Autodesk.AutoCAD.DatabaseServices.Polyline;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;
using ProtoTransactionStatus = TianzhengCadPlugin.Protocol.TransactionStatus;

namespace TianzhengCadPlugin
{
    /// <summary>
    /// The only component in the plugin that touches the AutoCAD Database.
    ///
    /// THREADING: every public method is invoked exclusively by MainThreadDispatcher from the
    /// Application.Idle handler, i.e. on the AutoCAD main thread. The transport thread never
    /// reaches this type — it only enqueues.
    ///
    /// WRITE PATH (identical for single ops and batches):
    ///     resolve(document_token)      -- fails closed; never falls back to MdiActiveDocument
    ///       -> using DocumentLock       -- taken on the resolved owned document only
    ///         -> StartTransaction       -- ONE transaction per batch
    ///           -> BlockTable (read) -> ModelSpace BTR (write)
    ///             -> create entity -> AppendEntity -> AddNewlyCreatedDBObject
    ///           -> Commit  (all operations succeeded)
    ///           -- or --
    ///           -> no Commit; dispose aborts  (any operation failed)
    ///
    /// all_or_nothing is enforced by the transaction itself, not by bookkeeping: on failure we
    /// simply never call Commit, so AutoCAD discards every change made inside it.
    /// </summary>
    internal sealed class CadOperationExecutor : IOperationExecutor
    {
        private readonly DocumentOwnershipRegistry _registry;
        private readonly PluginLog _log;
        private readonly string _sessionId;
        private readonly Func<int> _mainThreadIdProvider;

        /// <summary>Counters surfaced as sanitized run evidence.</summary>
        public int TransactionsStarted;
        public int TransactionsCommitted;
        public int TransactionsAborted;
        public int EntitiesCreated;
        public int DocumentLocksTaken;
        public int DocumentsSaved;
        public int DocumentsClosed;
        public int DocumentsReopened;

        private readonly string? _sandboxRoot;

        public CadOperationExecutor(
            DocumentOwnershipRegistry registry,
            PluginLog log,
            string sessionId,
            Func<int> mainThreadIdProvider,
            string? sandboxRoot)
        {
            _registry = registry;
            _log = log;
            _sessionId = sessionId;
            _mainThreadIdProvider = mainThreadIdProvider;
            _sandboxRoot = sandboxRoot;
        }

        public PluginResponse Execute(PluginRequest request)
        {
            try
            {
                return request.OperationType switch
                {
                    OperationType.CreateSyntheticDocument => CreateSyntheticDocument(request),
                    OperationType.QueryEntities => QueryEntities(request),
                    OperationType.Save => SaveDocument(request),
                    OperationType.Close => CloseDocument(request),
                    OperationType.Reopen => ReopenDocument(request),
                    OperationType.BatchExecute => ExecuteBatch(request, single: false),
                    OperationType.CreateLayer or OperationType.CreateLine
                        or OperationType.CreateCircle or OperationType.CreatePolyline
                        => ExecuteBatch(request, single: true),
                    _ => NotImplemented(request),
                };
            }
            catch (Exception ex)
            {
                // Nothing Autodesk-specific escapes: only the exception type name is logged.
                _log.Error(LogCategory.Entity, $"executor fault: {ex.GetType().Name}");
                return Failure(request, ErrorCodes.InternalError, Stages.Entity, "internal execution error");
            }
        }

        // ---------------------------------------------------------------- document

        private PluginResponse CreateSyntheticDocument(PluginRequest request)
        {
            AutoCadDocumentFactory.CreationOutcome outcome = AutoCadDocumentFactory.CreateBlankDocument();
            if (!outcome.Success)
            {
                _log.Error(LogCategory.Document, $"synthetic document creation failed: {outcome.FailureDetail}");
                return Failure(request, ErrorCodes.DocumentCreateFailed, Stages.Document,
                    "could not create a synthetic document");
            }

            var handle = new AutoCadDocumentHandle(outcome.Document!, outcome.Fingerprint);
            DocumentRecord record = _registry.Register(
                handle, request.JobId, DateTimeOffset.UtcNow, outcome.CreationMethod);

            _log.Info(LogCategory.Document,
                $"registered job-owned synthetic document job={record.JobId} " +
                $"fingerprint={Short(record.DatabaseFingerprint)} method={record.CreationMethod}");

            var result = new SyntheticDocumentResult
            {
                DocumentToken = record.DocumentToken,
                DocumentStatusValue = DocumentStatus.JobOwnedSynthetic,
                DatabaseFingerprint = record.DatabaseFingerprint,
                CreatedBySession = record.SessionId,
                CreatedByJob = record.JobId,
                CreatedAt = record.CreatedAt.ToString("O"),
                Synthetic = true,
                CreationMethod = record.CreationMethod,
            };

            PluginResponse response = Success(request, Stages.Document, ToElement(result));
            response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
            response.SanitizedMessage = "synthetic document created";
            AddDispatchMarker(response);
            return response;
        }

        /// <summary>Resolve the caller's document token. Never returns the active document.</summary>
        private bool TryResolve(PluginRequest request, out DocumentRecord record, out PluginResponse? rejection)
        {
            string? token = ReadDocumentToken(request);
            OwnershipResolution resolution = _registry.Resolve(token, _sessionId, request.JobId);

            if (!resolution.Success)
            {
                _log.Warn(LogCategory.Document, $"ownership rejected: {resolution.ErrorCode}");
                rejection = Failure(request, resolution.ErrorCode, Stages.Document, resolution.Message);
                rejection.DocumentStatus = DocumentStatus.NotTracked;
                record = null!;
                return false;
            }

            record = resolution.Record!;
            rejection = null;
            return true;
        }

        private static string? ReadDocumentToken(PluginRequest request)
        {
            if (request.DocumentContext.ValueKind == JsonValueKind.Object &&
                request.DocumentContext.TryGetProperty("document_token", out JsonElement element) &&
                element.ValueKind == JsonValueKind.String)
            {
                return element.GetString();
            }
            return null;
        }

        // ---------------------------------------------------------------- write path

        private PluginResponse ExecuteBatch(PluginRequest request, bool single)
        {
            if (!TryResolve(request, out DocumentRecord record, out PluginResponse? rejection))
                return rejection!;

            // Parse and validate BEFORE any lock or transaction.
            CadOperationPlan plan;
            try
            {
                plan = single
                    ? CadOperationPlanner.PlanSingle(request, record.DocumentToken)
                    : CadOperationPlanner.PlanBatch(request, record.DocumentToken);
            }
            catch (PlanParseException ex)
            {
                var invalid = new BatchResult
                {
                    BatchId = request.RequestId,
                    TransactionStatusValue = ProtoTransactionStatus.NotStarted,
                    FailedOperationIndex = ex.OperationIndex,
                    FailedOperationId = ex.OperationId,
                    RollbackStatus = RollbackStatus.NotApplicable,
                    PartialCommitStatus = false,
                };
                PluginResponse response = Failure(request, ex.ErrorCode, Stages.Validation, ex.Message);
                response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
                response.TransactionStatus = ProtoTransactionStatus.NotStarted;
                response.Result = ToElement(invalid);
                return response;
            }

            // Dry run: validation only. No lock, no transaction, no entity.
            if (request.DryRun)
            {
                var dryRun = new BatchResult
                {
                    BatchId = plan.BatchId,
                    TransactionStatusValue = ProtoTransactionStatus.DryRun,
                    RollbackStatus = RollbackStatus.NotApplicable,
                    PartialCommitStatus = false,
                };
                foreach (PlannedOperation op in plan.Operations)
                {
                    var opResult = new OperationResult
                    {
                        OperationIndex = op.Index,
                        OperationId = op.OperationId,
                        OperationType = op.OperationType,
                        EntityStatusValue = EntityStatus.NotCreated,
                        ExecutionStatusValue = ExecutionStatus.DryRunValidated,
                        SanitizedMessage = "validated; dry_run performed no write",
                    };

                    // Semantic validation runs for real, but no lock/transaction/entity.
                    // success=false because nothing was committed — consistent with the
                    // batch-level rule that success means "the effect is durable".
                    try
                    {
                        op.ValidateSemantics();
                        opResult.Success = false;
                    }
                    catch (GeometryValidationException ex)
                    {
                        opResult.ErrorCode = ex.ErrorCode;
                        opResult.EntityStatusValue = EntityStatus.Failed;
                        opResult.ExecutionStatusValue = ExecutionStatus.Failed;
                        opResult.SanitizedMessage = ex.Message;
                        dryRun.FailedOperationIndex = op.Index;
                        dryRun.FailedOperationId = op.OperationId;
                    }

                    dryRun.OperationResults.Add(opResult);
                }

                bool dryRunValid = dryRun.FailedOperationIndex < 0;
                PluginResponse response = dryRunValid
                    ? Success(request, Stages.Validation, ToElement(dryRun))
                    : Failure(request, ErrorCodes.InvalidGeometry, Stages.Validation,
                        "dry run rejected the plan; no transaction started");
                response.Result = ToElement(dryRun);
                response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
                response.TransactionStatus = ProtoTransactionStatus.DryRun;
                response.CreatedCount = 0;
                if (dryRunValid)
                    response.SanitizedMessage = "dry run validated; no lock, no transaction, no entity";
                AddDispatchMarker(response);
                return response;
            }

            return RunTransactional(request, record, plan);
        }

        private PluginResponse RunTransactional(
            PluginRequest request, DocumentRecord record, CadOperationPlan plan)
        {
            var handle = (AutoCadDocumentHandle)record.Handle;
            Document document = handle.Document;
            Database database = document.Database;

            var batch = new BatchResult
            {
                BatchId = plan.BatchId,
                TransactionMode = "all_or_nothing",
                DocumentStatusValue = DocumentStatus.JobOwnedSynthetic,
            };

            DocumentLock? documentLock = null;
            try
            {
                try
                {
                    documentLock = document.LockDocument();
                    Interlocked.Increment(ref DocumentLocksTaken);
                    _log.Info(LogCategory.Document, $"document lock acquired batch={plan.BatchId}");
                }
                catch (Exception ex)
                {
                    _log.Error(LogCategory.Document, $"document lock failed: {ex.GetType().Name}");
                    return LockOrTransactionFailure(
                        request, batch, ErrorCodes.DocumentLockFailed, "could not lock the owned document");
                }

                Transaction transaction;
                try
                {
                    transaction = database.TransactionManager.StartTransaction();
                    Interlocked.Increment(ref TransactionsStarted);
                    _log.Info(LogCategory.Transaction, $"transaction started batch={plan.BatchId}");
                }
                catch (Exception ex)
                {
                    _log.Error(LogCategory.Transaction, $"transaction start failed: {ex.GetType().Name}");
                    return LockOrTransactionFailure(
                        request, batch, ErrorCodes.TransactionStartFailed, "could not start a transaction");
                }

                // Disposing without Commit aborts, discarding every change in the batch.
                using (transaction)
                {
                    // ---- Persistent idempotency gate, INSIDE the transaction ----
                    // Read from the drawing itself, so a record written before a save/close
                    // /reopen cycle is still found afterwards.
                    string planHash = plan.ComputePlanHash();
                    string idempotencyKey = request.IdempotencyKey ?? "";

                    if (idempotencyKey.Length > 0)
                    {
                        IdempotencyRecord? existing = IdempotencyStore.TryRead(transaction, database, idempotencyKey);
                        if (existing != null)
                        {
                            if (!string.Equals(existing.PlanHash, planHash, StringComparison.Ordinal))
                            {
                                // Same key, different payload: refuse WITHOUT executing.
                                _log.Warn(LogCategory.Idempotency, $"idempotency conflict key={Short(idempotencyKey)}");
                                batch.TransactionStatusValue = ProtoTransactionStatus.NotStarted;
                                batch.IdempotencyStatusValue = Protocol.IdempotencyStatus.Conflict;
                                PluginResponse conflict = Failure(
                                    request, ErrorCodes.IdempotencyConflict, Stages.Idempotency,
                                    "idempotency_key was already applied with a different plan payload");
                                conflict.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
                                conflict.IdempotencyStatus = Protocol.IdempotencyStatus.Conflict;
                                conflict.Result = ToElement(batch);
                                AddDispatchMarker(conflict);
                                return conflict; // transaction disposes without Commit
                            }

                            // Same key, same payload: already committed. Do not re-create.
                            _log.Info(LogCategory.Idempotency, $"already applied key={Short(idempotencyKey)}");
                            batch.TransactionStatusValue = ProtoTransactionStatus.NotStarted;
                            batch.IdempotencyStatusValue = Protocol.IdempotencyStatus.AlreadyApplied;
                            batch.CreatedCount = 0;
                            batch.RollbackStatus = RollbackStatus.NotApplicable;

                            PluginResponse replay = Success(request, Stages.Idempotency, ToElement(batch));
                            replay.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
                            replay.TransactionStatus = ProtoTransactionStatus.NotStarted;
                            replay.IdempotencyStatus = Protocol.IdempotencyStatus.AlreadyApplied;
                            replay.CreatedCount = 0;
                            replay.Handles = new List<string>(existing.Handles);
                            replay.SanitizedMessage = "plan already applied to this document; nothing was created";
                            AddDispatchMarker(replay);
                            return replay; // transaction disposes without Commit
                        }
                    }

                    var blockTable = (BlockTable)transaction.GetObject(database.BlockTableId, OpenMode.ForRead);
                    var modelSpace = (BlockTableRecord)transaction.GetObject(
                        blockTable[BlockTableRecord.ModelSpace], OpenMode.ForWrite);

                    foreach (PlannedOperation operation in plan.Operations)
                    {
                        OperationResult result = ExecuteOne(transaction, database, modelSpace, operation);
                        batch.OperationResults.Add(result);

                        if (!result.Success)
                        {
                            // ABORT: never Commit. AutoCAD discards the whole transaction,
                            // including entities created by earlier operations in this batch.
                            batch.TransactionStatusValue = ProtoTransactionStatus.Aborted;
                            batch.FailedOperationIndex = operation.Index;
                            batch.FailedOperationId = operation.OperationId;
                            batch.RollbackStatus = RollbackStatus.RolledBack;
                            batch.PartialCommitStatus = false;
                            batch.CreatedCount = 0;

                            // success == "committed". The transaction is aborting, so NOTHING
                            // in this batch committed: every prior operation is demoted to
                            // success=false / ROLLED_BACK with all identifiers cleared. Only
                            // the operation that caused the abort keeps its FAILED status.
                            foreach (OperationResult prior in batch.OperationResults)
                            {
                                if (prior.OperationIndex == operation.Index) continue;
                                prior.MarkRolledBack();
                            }

                            Interlocked.Increment(ref TransactionsAborted);
                            _log.Warn(LogCategory.Transaction,
                                $"transaction aborted batch={plan.BatchId} failed_index={operation.Index} code={result.ErrorCode}");

                            PluginResponse aborted = Failure(
                                request, ErrorCodes.BatchRolledBack, Stages.Transaction,
                                $"batch rolled back at operation {operation.Index}: {result.SanitizedMessage}");
                            aborted.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
                            aborted.TransactionStatus = ProtoTransactionStatus.Aborted;
                            aborted.Result = ToElement(batch);
                            AddDispatchMarker(aborted);
                            return aborted;
                        }
                    }

                    // Collect committed identifiers before Commit so the idempotency record
                    // and the entities land in the SAME transaction.
                    int createdInTx = 0;
                    var committedHandles = new List<string>();
                    foreach (OperationResult result in batch.OperationResults)
                    {
                        foreach (EntityResult entity in result.Entities)
                        {
                            if (entity.Status == EntityStatus.Created) createdInTx++;
                            if (!string.IsNullOrEmpty(entity.Handle)) committedHandles.Add(entity.Handle);
                        }
                    }

                    if (idempotencyKey.Length > 0)
                    {
                        IdempotencyStore.Write(
                            transaction, database, idempotencyKey, planHash, committedHandles, createdInTx);
                        batch.IdempotencyStatusValue = Protocol.IdempotencyStatus.Applied;
                        _log.Info(LogCategory.Idempotency, $"idempotency record staged key={Short(idempotencyKey)}");
                    }

                    // Entities + idempotency record commit atomically here.
                    transaction.Commit();
                    Interlocked.Increment(ref TransactionsCommitted);
                    _log.Info(LogCategory.Transaction, $"transaction committed batch={plan.BatchId}");
                }

                int created = 0;
                var handles = new List<string>();
                var entityIds = new List<string>();
                foreach (OperationResult result in batch.OperationResults)
                {
                    foreach (EntityResult entity in result.Entities)
                    {
                        if (entity.Status == EntityStatus.Created) created++;
                        if (!string.IsNullOrEmpty(entity.Handle)) handles.Add(entity.Handle);
                        if (!string.IsNullOrEmpty(entity.EntityId)) entityIds.Add(entity.EntityId);
                    }
                }

                batch.TransactionStatusValue = ProtoTransactionStatus.Committed;
                batch.RollbackStatus = RollbackStatus.NotApplicable;
                batch.PartialCommitStatus = false;
                batch.CreatedCount = created;
                Interlocked.Add(ref EntitiesCreated, created);

                PluginResponse response = Success(request, Stages.Transaction, ToElement(batch));
                response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
                response.TransactionStatus = ProtoTransactionStatus.Committed;
                response.IdempotencyStatus = batch.IdempotencyStatusValue;
                response.CreatedCount = created;
                response.Handles = handles;
                response.EntityIds = entityIds;
                response.SanitizedMessage = "batch committed";
                AddDispatchMarker(response);
                return response;
            }
            finally
            {
                documentLock?.Dispose();
            }
        }

        private PluginResponse LockOrTransactionFailure(
            PluginRequest request, BatchResult batch, string errorCode, string message)
        {
            batch.TransactionStatusValue = ProtoTransactionStatus.NotStarted;
            batch.RollbackStatus = RollbackStatus.NotApplicable;
            batch.PartialCommitStatus = false;

            PluginResponse response = Failure(request, errorCode, Stages.Transaction, message);
            response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
            response.TransactionStatus = ProtoTransactionStatus.NotStarted;
            response.Result = ToElement(batch);
            return response;
        }

        /// <summary>Execute one operation inside the caller's open transaction.</summary>
        private OperationResult ExecuteOne(
            Transaction transaction, Database database, BlockTableRecord modelSpace, PlannedOperation operation)
        {
            var result = new OperationResult
            {
                OperationIndex = operation.Index,
                OperationId = operation.OperationId,
                OperationType = operation.OperationType,
            };

            try
            {
                // Semantic validation happens HERE, inside the open transaction, so a bad
                // operation aborts a real transaction and discards earlier entities.
                operation.ValidateSemantics();

                if (operation.OperationType == OperationType.CreateLayer)
                {
                    (string status, string message) = EnsureLayer(transaction, database, operation);
                    // Provisionally successful: demoted to ROLLED_BACK if the batch aborts later.
                    result.Success = true;
                    result.EntityStatusValue = status;
                    result.ExecutionStatusValue = ExecutionStatus.Committed;
                    result.SanitizedMessage = message;
                    return result;
                }

                // Geometry operations need their layer to exist first.
                EnsureLayer(transaction, database, operation);

                Entity entity = operation.OperationType switch
                {
                    OperationType.CreateLine => new Line(ToPoint3d(operation.Start), ToPoint3d(operation.End)),
                    OperationType.CreateCircle => new Circle(ToPoint3d(operation.Center), Vector3d.ZAxis, operation.Radius),
                    OperationType.CreatePolyline => BuildPolyline(operation),
                    _ => throw new InvalidOperationException("unsupported entity operation"),
                };

                entity.Layer = operation.Layer;

                modelSpace.AppendEntity(entity);
                transaction.AddNewlyCreatedDBObject(entity, true);

                EntityResult described = Describe(entity);

                // Provisionally successful: demoted to ROLLED_BACK if the batch aborts later.
                result.Success = true;
                result.EntityStatusValue = EntityStatus.Created;
                result.ExecutionStatusValue = ExecutionStatus.Committed;
                result.CreatedCount = 1;
                result.Entities.Add(described);
                result.EntityIds.Add(described.EntityId);
                result.Handles.Add(described.Handle);
                result.SanitizedMessage = "created";
                return result;
            }
            catch (GeometryValidationException ex)
            {
                return Fail(result, ex.ErrorCode, ex.Message);
            }
            catch (Autodesk.AutoCAD.Runtime.Exception ex)
            {
                // Autodesk error status only; never the Autodesk stack.
                return Fail(result, ErrorCodes.EntityCreateFailed,
                    $"AutoCAD rejected the entity ({ex.ErrorStatus})");
            }
            catch (Exception ex)
            {
                return Fail(result, ErrorCodes.EntityCreateFailed,
                    $"entity creation failed ({ex.GetType().Name})");
            }
        }

        /// <summary>The operation that causes the abort: FAILED, nothing created.</summary>
        private static OperationResult Fail(OperationResult result, string errorCode, string message)
        {
            result.Success = false;
            result.ErrorCode = errorCode;
            result.EntityStatusValue = EntityStatus.Failed;
            result.ExecutionStatusValue = ExecutionStatus.Failed;
            result.CreatedCount = 0;
            result.ModifiedCount = 0;
            result.EntityIds.Clear();
            result.Handles.Clear();
            result.Entities.Clear();
            result.SanitizedMessage = message;
            return result;
        }

        /// <summary>
        /// Create the layer if absent. An existing layer is reported as equivalent and is
        /// never overwritten, so a request can't redefine a layer another op relies on.
        /// </summary>
        private static (string Status, string Message) EnsureLayer(
            Transaction transaction, Database database, PlannedOperation operation)
        {
            var layerTable = (LayerTable)transaction.GetObject(database.LayerTableId, OpenMode.ForRead);

            if (layerTable.Has(operation.Layer))
                return (EntityStatus.Existing, "layer already exists; definition left unchanged");

            layerTable.UpgradeOpen();
            using var layer = new LayerTableRecord
            {
                Name = operation.Layer,
                Color = Color.FromColorIndex(ColorMethod.ByAci, (short)operation.ColorIndex),
            };
            layerTable.Add(layer);
            transaction.AddNewlyCreatedDBObject(layer, true);
            return (EntityStatus.Created, "layer created");
        }

        private static AcadPolyline BuildPolyline(PlannedOperation operation)
        {
            var polyline = new AcadPolyline();
            for (int i = 0; i < operation.Vertices.Count; i++)
            {
                Point3 vertex = operation.Vertices[i];
                polyline.AddVertexAt(i, new Point2d(vertex.X, vertex.Y), 0, 0, 0);
            }
            polyline.Closed = operation.Closed;
            return polyline;
        }

        private static Point3d ToPoint3d(Point3 point) => new(point.X, point.Y, point.Z);

        // ---------------------------------------------------------------- lifecycle

        /// <summary>
        /// Save the owned document into the plugin's own sandbox.
        ///
        /// Save is a LIFECYCLE stage, deliberately separate from the entity transaction: it is
        /// never bundled into a batch's atomicity claim. The caller supplies only a bare file
        /// name; the sandbox root comes from this plugin's launch configuration.
        /// </summary>
        private PluginResponse SaveDocument(PluginRequest request)
        {
            if (!TryResolve(request, out DocumentRecord record, out PluginResponse? rejection))
                return rejection!;

            string? requestedName = ReadStringFilter(request.Parameters, "file_name");
            string fullPath;
            try
            {
                fullPath = SandboxPathPolicy.Resolve(_sandboxRoot, requestedName);
            }
            catch (SandboxPathException ex)
            {
                _log.Warn(LogCategory.Save, $"sandbox path rejected: {ex.ErrorCode}");
                return Failure(request, ex.ErrorCode, Stages.Save, ex.Message);
            }

            var handle = (AutoCadDocumentHandle)record.Handle;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
                using (DocumentLock documentLock = handle.Document.LockDocument())
                {
                    // SaveAs writes the whole database; no entity transaction is involved.
                    handle.Document.Database.SaveAs(fullPath, DwgVersion.Current);
                }
                _registry.RecordSaved(record.DocumentToken, fullPath);
                Interlocked.Increment(ref DocumentsSaved);
                _log.Info(LogCategory.Save, $"saved synthetic document as {SandboxPathPolicy.SanitizedIdentity(fullPath)}");
            }
            catch (Exception ex)
            {
                _log.Error(LogCategory.Save, $"save failed: {ex.GetType().Name}");
                return Failure(request, ErrorCodes.SaveFailed, Stages.Save, "could not save the synthetic document");
            }

            var result = new LifecycleResult
            {
                LifecycleStage = "save",
                SaveStatus = "SAVED",
                DocumentStatusValue = DocumentStatus.JobOwnedSynthetic,
                SandboxIdentity = SandboxPathPolicy.SanitizedIdentity(fullPath),
            };

            PluginResponse response = Success(request, Stages.Save, ToElement(result));
            response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
            response.SanitizedMessage = "synthetic document saved inside the sandbox";
            AddDispatchMarker(response);
            return response;
        }

        /// <summary>Close the owned document. Never falls back to the active document.</summary>
        private PluginResponse CloseDocument(PluginRequest request)
        {
            if (!TryResolve(request, out DocumentRecord record, out PluginResponse? rejection))
                return rejection!;

            if (string.IsNullOrEmpty(record.SavedPath))
            {
                // Refuse to close unsaved work: reopen would have nothing to open.
                return Failure(request, ErrorCodes.DocumentNotSaved, Stages.Save,
                    "document must be saved before it can be closed");
            }

            var handle = (AutoCadDocumentHandle)record.Handle;
            try
            {
                // AutoCAD refuses to close the MDI-active document. Move focus to another
                // ALREADY-OPEN document first (typically the default blank drawing). We only
                // change which document is active — the other document is never written to,
                // and it is never registered as owned.
                DocumentCollection documents = AcApp.DocumentManager;
                if (ReferenceEquals(documents.MdiActiveDocument, handle.Document))
                {
                    foreach (Document candidate in documents)
                    {
                        if (!ReferenceEquals(candidate, handle.Document))
                        {
                            documents.MdiActiveDocument = candidate;
                            break;
                        }
                    }
                }

                // Already saved; discard the in-memory copy without writing again.
                // CloseAndDiscard manages its own locking, so we hold no DocumentLock here.
                handle.Document.CloseAndDiscard();

                _registry.MarkClosed(record.DocumentToken);
                Interlocked.Increment(ref DocumentsClosed);
                _log.Info(LogCategory.Document, "closed job-owned synthetic document");
            }
            catch (Exception ex)
            {
                _log.Error(LogCategory.Document, $"close failed: {ex.GetType().Name}");
                return Failure(request, ErrorCodes.CloseFailed, Stages.Document,
                    $"could not close the synthetic document ({ex.GetType().Name})");
            }

            var result = new LifecycleResult
            {
                LifecycleStage = "close",
                SaveStatus = "ALREADY_SAVED",
                DocumentStatusValue = "CLOSED",
                SandboxIdentity = SandboxPathPolicy.SanitizedIdentity(record.SavedPath!),
            };

            PluginResponse response = Success(request, Stages.Document, ToElement(result));
            response.DocumentStatus = "CLOSED";
            response.SanitizedMessage = "synthetic document closed";
            AddDispatchMarker(response);
            return response;
        }

        /// <summary>
        /// Reopen the exact sandbox path THIS plugin saved. The caller cannot supply a path;
        /// it supplies the old token, and the path is recovered from our own record.
        /// </summary>
        private PluginResponse ReopenDocument(PluginRequest request)
        {
            string? token = ReadDocumentToken(request);
            DocumentRecord? previous = _registry.Peek(token);

            if (previous == null)
                return Failure(request, ErrorCodes.DocumentTokenInvalid, Stages.Document,
                    "document_token is not registered");
            if (!string.Equals(previous.SessionId, _sessionId, StringComparison.Ordinal))
                return Failure(request, ErrorCodes.DocumentSessionMismatch, Stages.Document,
                    "document_token belongs to a different plugin session");
            if (!string.Equals(previous.JobId, request.JobId, StringComparison.Ordinal))
                return Failure(request, ErrorCodes.DocumentJobMismatch, Stages.Document,
                    "document_token belongs to a different job");
            if (string.IsNullOrEmpty(previous.SavedPath))
                return Failure(request, ErrorCodes.DocumentNotSaved, Stages.Document,
                    "document was never saved, so it cannot be reopened");

            Document reopened;
            try
            {
                // Exact path recorded by this plugin; re-validated against the sandbox root.
                string verified = SandboxPathPolicy.Resolve(
                    _sandboxRoot, SandboxPathPolicy.SanitizedIdentity(previous.SavedPath!));

                if (!File.Exists(verified))
                    return Failure(request, ErrorCodes.ReopenFailed, Stages.Persistence,
                        "the saved synthetic document is missing from the sandbox");

                reopened = AcApp.DocumentManager.Open(verified, forReadOnly: false);
                if (reopened?.Database == null)
                    return Failure(request, ErrorCodes.ReopenFailed, Stages.Persistence,
                        "reopen returned no database");

                var handle = new AutoCadDocumentHandle(reopened, reopened.Database.FingerprintGuid.ToString());
                DocumentRecord record = _registry.RegisterReopened(
                    handle, previous, DateTimeOffset.UtcNow, verified);
                Interlocked.Increment(ref DocumentsReopened);
                _log.Info(LogCategory.Persistence,
                    $"reopened synthetic document; previous token invalidated, fingerprint={Short(record.DatabaseFingerprint)}");

                var result = new LifecycleResult
                {
                    LifecycleStage = "reopen",
                    SaveStatus = "PERSISTED",
                    DocumentStatusValue = DocumentStatus.JobOwnedSynthetic,
                    SandboxIdentity = SandboxPathPolicy.SanitizedIdentity(verified),
                    DocumentToken = record.DocumentToken,
                    DatabaseFingerprint = record.DatabaseFingerprint,
                    PreviousTokenInvalidated = true,
                };

                PluginResponse response = Success(request, Stages.Persistence, ToElement(result));
                response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
                response.SanitizedMessage = "synthetic document reopened from its exact sandbox path";
                AddDispatchMarker(response);
                return response;
            }
            catch (SandboxPathException ex)
            {
                return Failure(request, ex.ErrorCode, Stages.Persistence, ex.Message);
            }
            catch (Exception ex)
            {
                _log.Error(LogCategory.Persistence, $"reopen failed: {ex.GetType().Name}");
                return Failure(request, ErrorCodes.ReopenFailed, Stages.Persistence,
                    "could not reopen the synthetic document");
            }
        }

        // ---------------------------------------------------------------- query

        private PluginResponse QueryEntities(PluginRequest request)
        {
            if (!TryResolve(request, out DocumentRecord record, out PluginResponse? rejection))
                return rejection!;

            var handle = (AutoCadDocumentHandle)record.Handle;
            Document document = handle.Document;
            Database database = document.Database;

            string? layerFilter = ReadStringFilter(request.Parameters, "layer");
            string? typeFilter = ReadStringFilter(request.Parameters, "entity_type");
            string? handleFilter = ReadStringFilter(request.Parameters, "handle");

            var query = new QueryResult { DocumentTokenValid = true };
            if (layerFilter != null) query.FiltersApplied["layer"] = layerFilter;
            if (typeFilter != null) query.FiltersApplied["entity_type"] = typeFilter;
            if (handleFilter != null) query.FiltersApplied["handle"] = handleFilter;

            DocumentLock? documentLock = null;
            try
            {
                documentLock = document.LockDocument();
                // Read-only transaction: nothing is modified and Commit is a no-op read close.
                using Transaction transaction = database.TransactionManager.StartTransaction();

                var blockTable = (BlockTable)transaction.GetObject(database.BlockTableId, OpenMode.ForRead);
                var modelSpace = (BlockTableRecord)transaction.GetObject(
                    blockTable[BlockTableRecord.ModelSpace], OpenMode.ForRead);

                foreach (ObjectId id in modelSpace)
                {
                    if (transaction.GetObject(id, OpenMode.ForRead) is not Entity entity) continue;

                    EntityResult described = Describe(entity);
                    described.Status = EntityStatus.Queried;

                    if (described.EntityType.Length == 0) continue;
                    if (layerFilter != null && !string.Equals(described.Layer, layerFilter, StringComparison.OrdinalIgnoreCase)) continue;
                    if (typeFilter != null && !string.Equals(described.EntityType, typeFilter, StringComparison.OrdinalIgnoreCase)) continue;
                    if (handleFilter != null && !string.Equals(described.Handle, handleFilter, StringComparison.OrdinalIgnoreCase)) continue;

                    query.Entities.Add(described);
                }

                transaction.Commit();
            }
            catch (Exception ex)
            {
                _log.Error(LogCategory.Entity, $"query failed: {ex.GetType().Name}");
                return Failure(request, ErrorCodes.EntityQueryFailed, Stages.Entity, "entity query failed");
            }
            finally
            {
                documentLock?.Dispose();
            }

            query.EntityCount = query.Entities.Count;

            PluginResponse response = Success(request, Stages.Entity, ToElement(query));
            response.DocumentStatus = DocumentStatus.JobOwnedSynthetic;
            response.TransactionStatus = ProtoTransactionStatus.Committed;
            response.SanitizedMessage = $"query returned {query.EntityCount} entities";
            AddDispatchMarker(response);
            return response;
        }

        private static string? ReadStringFilter(JsonElement parameters, string name)
        {
            if (parameters.ValueKind == JsonValueKind.Object &&
                parameters.TryGetProperty(name, out JsonElement element) &&
                element.ValueKind == JsonValueKind.String)
            {
                string? value = element.GetString();
                return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
            }
            return null;
        }

        /// <summary>Read geometry back OUT of the database, so results reflect what persisted.</summary>
        private static EntityResult Describe(Entity entity)
        {
            var result = new EntityResult
            {
                Handle = entity.Handle.ToString(),
                EntityId = entity.ObjectId.ToString(),
                Layer = entity.Layer,
            };

            switch (entity)
            {
                case Line line:
                    result.EntityType = "line";
                    result.Geometry["start"] = PointDictionary(line.StartPoint);
                    result.Geometry["end"] = PointDictionary(line.EndPoint);
                    break;

                case Circle circle:
                    result.EntityType = "circle";
                    result.Geometry["center"] = PointDictionary(circle.Center);
                    result.Geometry["radius"] = circle.Radius;
                    break;

                case AcadPolyline polyline:
                {
                    result.EntityType = "polyline";
                    var vertices = new List<Dictionary<string, double>>();
                    for (int i = 0; i < polyline.NumberOfVertices; i++)
                    {
                        Point2d point = polyline.GetPoint2dAt(i);
                        vertices.Add(new Dictionary<string, double> { ["x"] = point.X, ["y"] = point.Y, ["z"] = 0.0 });
                    }
                    result.Geometry["vertices"] = vertices;
                    result.Geometry["closed"] = polyline.Closed;
                    break;
                }

                default:
                    result.EntityType = "";
                    break;
            }

            return result;
        }

        private static Dictionary<string, double> PointDictionary(Point3d point) =>
            new() { ["x"] = point.X, ["y"] = point.Y, ["z"] = point.Z };

        // ---------------------------------------------------------------- helpers

        private PluginResponse NotImplemented(PluginRequest request)
        {
            PluginResponse response = Failure(
                request, ErrorCodes.NotImplementedInStage, Stages.Scheduling,
                $"operation '{request.OperationType}' is not implemented in stage S7.2");
            AddDispatchMarker(response);
            return response;
        }

        private static PluginResponse Success(PluginRequest request, string stage, JsonElement result) =>
            new()
            {
                Success = true,
                ErrorCode = ErrorCodes.None,
                Stage = stage,
                RequestId = request.RequestId,
                OperationId = request.OperationId,
                Result = result,
                PluginState = PluginStates.Ready,
            };

        private static PluginResponse Failure(
            PluginRequest request, string errorCode, string stage, string message) =>
            new()
            {
                Success = false,
                ErrorCode = errorCode,
                Stage = stage,
                RequestId = request.RequestId,
                OperationId = request.OperationId,
                Retryable = false,
                SanitizedMessage = message,
                PluginState = PluginStates.Ready,
                TransactionStatus = ProtoTransactionStatus.None,
                DocumentStatus = DocumentStatus.None,
            };

        /// <summary>Runtime proof the work ran on the AutoCAD main thread via Application.Idle.</summary>
        private void AddDispatchMarker(PluginResponse response)
        {
            int executing = Thread.CurrentThread.ManagedThreadId;
            int main = _mainThreadIdProvider();
            response.Warnings.Add(
                $"cad_dispatch=application_idle;executing_thread={executing};" +
                $"initialize_main_thread={main};on_main_thread={(executing == main ? "true" : "false")}");
        }

        private static JsonElement ToElement<T>(T value)
        {
            string json = JsonSerializer.Serialize(value, ProtocolJson.Options);
            using JsonDocument document = JsonDocument.Parse(json);
            return document.RootElement.Clone();
        }

        private static string Short(string value) =>
            value.Length <= 8 ? value : value[..8] + "...";
    }
}
