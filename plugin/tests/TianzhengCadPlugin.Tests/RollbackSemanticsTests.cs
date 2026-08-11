using System.Text.Json;
using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// Contract for how a rolled-back batch reports itself.
    ///
    /// The rule under test: <c>success</c> means "this operation's effect is COMMITTED".
    /// After an abort nothing committed, so no operation in the batch may report success —
    /// including operations that executed cleanly before the failure. This is what stops the
    /// future Python backend from mistaking a rolled-back create for a durable one.
    ///
    /// These assert the RESULT SHAPE. Proof that AutoCAD actually discards the entities comes
    /// only from the real-AutoCAD smoke run.
    /// </summary>
    public class RollbackSemanticsTests
    {
        /// <summary>Reproduces exactly what the executor builds when a batch aborts.</summary>
        private static BatchResult AbortedBatch()
        {
            var op0 = new OperationResult
            {
                OperationIndex = 0,
                OperationId = "b0-line",
                OperationType = OperationType.CreateLine,
                // op0 succeeded inside the transaction before the failure...
                Success = true,
                EntityStatusValue = EntityStatus.Created,
                ExecutionStatusValue = ExecutionStatus.Committed,
                CreatedCount = 1,
            };
            op0.Entities.Add(new EntityResult { Handle = "9F", EntityId = "(123)", EntityType = "line" });
            op0.EntityIds.Add("(123)");
            op0.Handles.Add("9F");

            // ...then the transaction aborted, so it is demoted.
            op0.MarkRolledBack();

            var op1 = new OperationResult
            {
                OperationIndex = 1,
                OperationId = "b1-bad-circle",
                OperationType = OperationType.CreateCircle,
                Success = false,
                ErrorCode = ErrorCodes.InvalidGeometry,
                EntityStatusValue = EntityStatus.Failed,
                ExecutionStatusValue = ExecutionStatus.Failed,
                SanitizedMessage = "circle radius must be greater than the geometry tolerance",
            };

            var batch = new BatchResult
            {
                BatchId = "b-rollback",
                TransactionStatusValue = TransactionStatus.Aborted,
                FailedOperationIndex = 1,
                FailedOperationId = "b1-bad-circle",
                RollbackStatus = RollbackStatus.RolledBack,
                PartialCommitStatus = false,
                CreatedCount = 0,
            };
            batch.OperationResults.Add(op0);
            batch.OperationResults.Add(op1);
            return batch;
        }

        // ---------- batch level ----------

        [Fact]
        public void Aborted_batch_reports_abort_and_rollback()
        {
            BatchResult batch = AbortedBatch();

            Assert.Equal(TransactionStatus.Aborted, batch.TransactionStatusValue);
            Assert.Equal(RollbackStatus.RolledBack, batch.RollbackStatus);
            Assert.False(batch.PartialCommitStatus);
            Assert.Equal(0, batch.CreatedCount);
            Assert.Equal(1, batch.FailedOperationIndex);
            Assert.Equal("b1-bad-circle", batch.FailedOperationId);
        }

        [Fact]
        public void No_operation_in_an_aborted_batch_reports_success()
        {
            // The core anti-misinterpretation guarantee.
            foreach (OperationResult op in AbortedBatch().OperationResults)
                Assert.False(op.Success, $"operation {op.OperationIndex} must not report success");
        }

        // ---------- rolled-back operation (op0) ----------

        [Fact]
        public void Rolled_back_operation_reports_rolled_back_status()
        {
            OperationResult op0 = AbortedBatch().OperationResults[0];

            Assert.False(op0.Success);
            Assert.Equal(EntityStatus.RolledBack, op0.EntityStatusValue);
            Assert.Equal(ExecutionStatus.RolledBack, op0.ExecutionStatusValue);
        }

        [Fact]
        public void Rolled_back_operation_exposes_no_identifiers_or_counts()
        {
            OperationResult op0 = AbortedBatch().OperationResults[0];

            Assert.Empty(op0.Handles);
            Assert.Empty(op0.EntityIds);
            Assert.Empty(op0.Entities);
            Assert.Equal(0, op0.CreatedCount);
            Assert.Equal(0, op0.ModifiedCount);
        }

        [Fact]
        public void Rolled_back_operation_explains_itself()
            => Assert.Equal(
                "operation executed but was rolled back with the transaction",
                AbortedBatch().OperationResults[0].SanitizedMessage);

        // ---------- failing operation (op1) ----------

        [Fact]
        public void Failing_operation_reports_failure_with_a_specific_error_code()
        {
            OperationResult op1 = AbortedBatch().OperationResults[1];

            Assert.False(op1.Success);
            Assert.Equal(ErrorCodes.InvalidGeometry, op1.ErrorCode);
            Assert.Equal(EntityStatus.Failed, op1.EntityStatusValue);
            Assert.Equal(ExecutionStatus.Failed, op1.ExecutionStatusValue);
            Assert.Empty(op1.Handles);
        }

        [Fact]
        public void Rolled_back_and_failed_operations_stay_distinguishable()
        {
            BatchResult batch = AbortedBatch();

            // Both are success=false, but a backend can still tell what happened to each.
            Assert.NotEqual(
                batch.OperationResults[0].ExecutionStatusValue,
                batch.OperationResults[1].ExecutionStatusValue);
            Assert.Equal(ErrorCodes.None, batch.OperationResults[0].ErrorCode);
            Assert.NotEqual(ErrorCodes.None, batch.OperationResults[1].ErrorCode);
        }

        // ---------- wire shape ----------

        [Fact]
        public void Rolled_back_batch_serializes_with_the_expected_fields()
        {
            using JsonDocument doc = JsonDocument.Parse(
                JsonSerializer.Serialize(AbortedBatch(), ProtocolJson.Options));
            JsonElement json = doc.RootElement;

            Assert.Equal("ABORTED", json.GetProperty("transaction_status").GetString());
            Assert.Equal("ROLLED_BACK", json.GetProperty("rollback_status").GetString());
            Assert.False(json.GetProperty("partial_commit_status").GetBoolean());

            JsonElement op0 = json.GetProperty("operation_results")[0];
            Assert.False(op0.GetProperty("success").GetBoolean());
            Assert.Equal("ROLLED_BACK", op0.GetProperty("entity_status").GetString());
            Assert.Equal("EXECUTED_THEN_ROLLED_BACK", op0.GetProperty("execution_status").GetString());
            Assert.Empty(op0.GetProperty("handles").EnumerateArray());
            Assert.Empty(op0.GetProperty("entity_ids").EnumerateArray());
            Assert.Equal(0, op0.GetProperty("created_count").GetInt32());
        }

        [Fact]
        public void MarkRolledBack_is_idempotent()
        {
            OperationResult op = AbortedBatch().OperationResults[0];
            op.MarkRolledBack();
            op.MarkRolledBack();

            Assert.False(op.Success);
            Assert.Empty(op.Handles);
            Assert.Equal(EntityStatus.RolledBack, op.EntityStatusValue);
        }

        // ---------- committed batch keeps success=true ----------

        [Fact]
        public void Committed_operations_still_report_success()
        {
            var op = new OperationResult
            {
                OperationIndex = 0,
                OperationType = OperationType.CreateLine,
                Success = true,
                EntityStatusValue = EntityStatus.Created,
                ExecutionStatusValue = ExecutionStatus.Committed,
                CreatedCount = 1,
            };
            op.Handles.Add("80");

            Assert.True(op.Success);
            Assert.Equal(ExecutionStatus.Committed, op.ExecutionStatusValue);
            Assert.Single(op.Handles);
        }
    }
}
