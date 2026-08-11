using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>
    /// One entity as reported back over the wire.
    ///
    /// Only stable, safe identifiers cross the boundary: the AutoCAD Handle string and a
    /// string form of the ObjectId. No managed pointer, no raw ObjectId struct, and no file
    /// path is ever exposed.
    /// </summary>
    public sealed class EntityResult
    {
        [JsonPropertyName("handle")] public string Handle { get; set; } = "";
        [JsonPropertyName("entity_id")] public string EntityId { get; set; } = "";
        [JsonPropertyName("entity_type")] public string EntityType { get; set; } = "";
        [JsonPropertyName("layer")] public string Layer { get; set; } = "";

        /// <summary>Geometry echoed back from the database, not from the request.</summary>
        [JsonPropertyName("geometry")] public Dictionary<string, object?> Geometry { get; set; } = new();

        [JsonPropertyName("status")] public string Status { get; set; } = EntityStatus.Created;
    }

    /// <summary>
    /// Result of a single operation inside a batch.
    ///
    /// SUCCESS SEMANTICS (contract for the future Python backend):
    /// <c>success == true</c> means "this operation's effect is COMMITTED and durable in the
    /// database". It does NOT mean "this operation ran without raising". Therefore, when a
    /// batch aborts, EVERY operation in that batch reports <c>success = false</c> — including
    /// operations that executed cleanly before the failure — because nothing persisted.
    /// <see cref="ExecutionStatusValue"/> preserves the distinction between "never ran",
    /// "ran then rolled back", and "failed".
    /// </summary>
    public sealed class OperationResult
    {
        [JsonPropertyName("operation_index")] public int OperationIndex { get; set; }
        [JsonPropertyName("operation_id")] public string OperationId { get; set; } = "";
        [JsonPropertyName("operation_type")] public string OperationType { get; set; } = "";

        /// <summary>True only if the effect was committed. False for anything rolled back.</summary>
        [JsonPropertyName("success")] public bool Success { get; set; }

        [JsonPropertyName("error_code")] public string ErrorCode { get; set; } = ErrorCodes.None;
        [JsonPropertyName("entity_status")] public string EntityStatusValue { get; set; } = EntityStatus.None;

        /// <summary>How far the operation got, independent of commit.</summary>
        [JsonPropertyName("execution_status")] public string ExecutionStatusValue { get; set; } = ExecutionStatus.NotExecuted;

        [JsonPropertyName("created_count")] public int CreatedCount { get; set; }
        [JsonPropertyName("modified_count")] public int ModifiedCount { get; set; }
        [JsonPropertyName("entity_ids")] public List<string> EntityIds { get; set; } = new();
        [JsonPropertyName("handles")] public List<string> Handles { get; set; } = new();
        [JsonPropertyName("entities")] public List<EntityResult> Entities { get; set; } = new();
        [JsonPropertyName("sanitized_message")] public string SanitizedMessage { get; set; } = "";

        /// <summary>
        /// Collapse this operation to its rolled-back form: nothing committed, so no handle,
        /// no entity id, no count, and success is false.
        /// </summary>
        public void MarkRolledBack()
        {
            Success = false;
            EntityStatusValue = EntityStatus.RolledBack;
            ExecutionStatusValue = ExecutionStatus.RolledBack;
            CreatedCount = 0;
            ModifiedCount = 0;
            EntityIds.Clear();
            Handles.Clear();
            Entities.Clear();
            SanitizedMessage = "operation executed but was rolled back with the transaction";
        }
    }

    /// <summary>
    /// Batch outcome. In S7.2 the only supported mode is <c>all_or_nothing</c>: every
    /// operation runs inside ONE DocumentLock and ONE AutoCAD Transaction, so either all
    /// operations commit or the transaction is aborted and nothing persists.
    /// </summary>
    public sealed class BatchResult
    {
        [JsonPropertyName("batch_id")] public string BatchId { get; set; } = "";
        [JsonPropertyName("transaction_mode")] public string TransactionMode { get; set; } = "all_or_nothing";
        [JsonPropertyName("transaction_status")] public string TransactionStatusValue { get; set; } = TransactionStatus.NotStarted;

        /// <summary>Index of the first failing operation, or -1 when all succeeded.</summary>
        [JsonPropertyName("failed_operation_index")] public int FailedOperationIndex { get; set; } = -1;

        [JsonPropertyName("failed_operation_id")] public string? FailedOperationId { get; set; }
        [JsonPropertyName("rollback_status")] public string RollbackStatus { get; set; } = Protocol.RollbackStatus.NotApplicable;

        /// <summary>Always false under all_or_nothing: a batch never half-commits.</summary>
        [JsonPropertyName("partial_commit_status")] public bool PartialCommitStatus { get; set; }

        [JsonPropertyName("operation_results")] public List<OperationResult> OperationResults { get; set; } = new();
        [JsonPropertyName("document_status")] public string DocumentStatusValue { get; set; } = DocumentStatus.JobOwnedSynthetic;
        [JsonPropertyName("created_count")] public int CreatedCount { get; set; }

        /// <summary>Persistent-idempotency outcome for this batch.</summary>
        [JsonPropertyName("idempotency_status")] public string IdempotencyStatusValue { get; set; } = IdempotencyStatus.NotApplicable;

        /// <summary>Plugin-computed hash of the batch payload, used for conflict detection.</summary>
        [JsonPropertyName("plan_hash")] public string PlanHash { get; set; } = "";
    }

    /// <summary>Result of save / close / reopen. These are lifecycle stages, not entity transactions.</summary>
    public sealed class LifecycleResult
    {
        [JsonPropertyName("lifecycle_stage")] public string LifecycleStage { get; set; } = "";
        [JsonPropertyName("save_status")] public string SaveStatus { get; set; } = "NOT_APPLICABLE";
        [JsonPropertyName("document_status")] public string DocumentStatusValue { get; set; } = DocumentStatus.JobOwnedSynthetic;

        /// <summary>Bare file name only. The absolute sandbox path never crosses the wire.</summary>
        [JsonPropertyName("sandbox_identity")] public string SandboxIdentity { get; set; } = "";

        /// <summary>Set by reopen: the freshly issued token. The previous token is dead.</summary>
        [JsonPropertyName("document_token")] public string? DocumentToken { get; set; }

        [JsonPropertyName("database_fingerprint")] public string? DatabaseFingerprint { get; set; }
        [JsonPropertyName("previous_token_invalidated")] public bool PreviousTokenInvalidated { get; set; }
        [JsonPropertyName("entity_count")] public int EntityCount { get; set; }
    }

    /// <summary>Result of <c>create_synthetic_document</c>.</summary>
    public sealed class SyntheticDocumentResult
    {
        [JsonPropertyName("document_token")] public string DocumentToken { get; set; } = "";
        [JsonPropertyName("document_status")] public string DocumentStatusValue { get; set; } = DocumentStatus.JobOwnedSynthetic;
        [JsonPropertyName("database_fingerprint")] public string DatabaseFingerprint { get; set; } = "";
        [JsonPropertyName("created_by_session")] public string CreatedBySession { get; set; } = "";
        [JsonPropertyName("created_by_job")] public string CreatedByJob { get; set; } = "";
        [JsonPropertyName("created_at")] public string CreatedAt { get; set; } = "";
        [JsonPropertyName("synthetic")] public bool Synthetic { get; set; } = true;

        /// <summary>How the blank drawing was produced (documented, never a user file path).</summary>
        [JsonPropertyName("creation_method")] public string CreationMethod { get; set; } = "";
    }

    /// <summary>Result of <c>query_entities</c>.</summary>
    public sealed class QueryResult
    {
        [JsonPropertyName("document_token_valid")] public bool DocumentTokenValid { get; set; }
        [JsonPropertyName("entity_count")] public int EntityCount { get; set; }
        [JsonPropertyName("entities")] public List<EntityResult> Entities { get; set; } = new();
        [JsonPropertyName("filters_applied")] public Dictionary<string, string> FiltersApplied { get; set; } = new();
    }
}
