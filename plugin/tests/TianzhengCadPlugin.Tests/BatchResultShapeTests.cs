using System.Text.Json;
using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// Shape contracts for batch/rollback results. These verify the DTO the client will parse.
    /// They are NOT evidence that a real AutoCAD transaction rolled back — that requires the
    /// real-AutoCAD stage and is asserted only there.
    /// </summary>
    public class BatchResultShapeTests
    {
        private static JsonElement Serialize<T>(T value)
        {
            using JsonDocument document = JsonDocument.Parse(JsonSerializer.Serialize(value, ProtocolJson.Options));
            return document.RootElement.Clone();
        }

        [Fact]
        public void Successful_batch_shape_carries_every_required_field()
        {
            var batch = new BatchResult
            {
                BatchId = "b-1",
                TransactionStatusValue = TransactionStatus.Committed,
                CreatedCount = 3,
            };

            JsonElement json = Serialize(batch);
            foreach (string field in new[]
            {
                "batch_id", "transaction_mode", "transaction_status", "failed_operation_index",
                "rollback_status", "partial_commit_status", "operation_results", "created_count",
            })
            {
                Assert.True(json.TryGetProperty(field, out _), $"batch result must expose '{field}'");
            }

            Assert.Equal("all_or_nothing", json.GetProperty("transaction_mode").GetString());
            Assert.Equal(-1, json.GetProperty("failed_operation_index").GetInt32());
            Assert.False(json.GetProperty("partial_commit_status").GetBoolean());
        }

        [Fact]
        public void Rolled_back_batch_shape_reports_index_id_and_rollback()
        {
            var batch = new BatchResult
            {
                BatchId = "b-2",
                TransactionStatusValue = TransactionStatus.Aborted,
                FailedOperationIndex = 1,
                FailedOperationId = "op-bad",
                RollbackStatus = RollbackStatus.RolledBack,
                PartialCommitStatus = false,
                CreatedCount = 0,
            };

            JsonElement json = Serialize(batch);

            Assert.Equal(TransactionStatus.Aborted, json.GetProperty("transaction_status").GetString());
            Assert.Equal(1, json.GetProperty("failed_operation_index").GetInt32());
            Assert.Equal("op-bad", json.GetProperty("failed_operation_id").GetString());
            Assert.Equal(RollbackStatus.RolledBack, json.GetProperty("rollback_status").GetString());
            Assert.False(json.GetProperty("partial_commit_status").GetBoolean());
            Assert.Equal(0, json.GetProperty("created_count").GetInt32());
        }

        [Fact]
        public void Partial_commit_is_false_by_default_under_all_or_nothing()
            => Assert.False(new BatchResult().PartialCommitStatus);

        [Fact]
        public void Entity_result_exposes_only_safe_identifiers()
        {
            JsonElement json = Serialize(new EntityResult
            {
                Handle = "1A2",
                EntityId = "(8796093022345)",
                EntityType = "line",
                Layer = "S7_ENTITY_MVP",
            });

            foreach (string field in new[] { "handle", "entity_id", "entity_type", "layer", "geometry", "status" })
                Assert.True(json.TryGetProperty(field, out _), $"entity result must expose '{field}'");

            // No raw pointer / native handle surface.
            string raw = json.GetRawText();
            Assert.DoesNotContain("IntPtr", raw);
            Assert.DoesNotContain("UnmanagedObject", raw);
        }

        [Fact]
        public void Synthetic_document_result_shape_is_complete()
        {
            JsonElement json = Serialize(new SyntheticDocumentResult
            {
                DocumentToken = "t",
                DatabaseFingerprint = "f",
                CreatedBySession = "s",
                CreatedByJob = "j",
                CreatedAt = "2026-08-11T00:00:00Z",
                CreationMethod = "DocumentManager.Add(default_template)",
            });

            foreach (string field in new[]
            {
                "document_token", "document_status", "database_fingerprint",
                "created_by_session", "created_by_job", "created_at", "synthetic", "creation_method",
            })
            {
                Assert.True(json.TryGetProperty(field, out _), $"document result must expose '{field}'");
            }

            Assert.Equal(DocumentStatus.JobOwnedSynthetic, json.GetProperty("document_status").GetString());
            Assert.True(json.GetProperty("synthetic").GetBoolean());
        }

        [Fact]
        public void All_new_s7_2_error_codes_exist_and_are_distinct()
        {
            string[] codes =
            {
                ErrorCodes.DocumentTokenRequired, ErrorCodes.DocumentTokenInvalid,
                ErrorCodes.DocumentNotJobOwned, ErrorCodes.DocumentSessionMismatch,
                ErrorCodes.DocumentJobMismatch, ErrorCodes.DocumentDatabaseMismatch,
                ErrorCodes.DocumentLockFailed, ErrorCodes.TransactionStartFailed,
                ErrorCodes.TransactionAborted, ErrorCodes.InvalidGeometry,
                ErrorCodes.InvalidLayer, ErrorCodes.EntityCreateFailed,
                ErrorCodes.EntityQueryFailed, ErrorCodes.BatchRolledBack,
            };

            Assert.Equal(codes.Length, new System.Collections.Generic.HashSet<string>(codes).Count);
            foreach (string code in codes) Assert.False(string.IsNullOrWhiteSpace(code));
        }
    }
}
