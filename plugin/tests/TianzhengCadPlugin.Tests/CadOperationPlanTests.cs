using System.Collections.Generic;
using System.Text.Json;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class CadOperationPlanTests
    {
        private const string Token = "doc-token-abc";

        private static PluginRequest Request(string operationType, object parameters)
        {
            var fields = TestRequests.BaseFields(operationType, TestRequests.TestNonce);
            fields["parameters"] = parameters;
            fields["document_context"] = new Dictionary<string, object?> { ["document_token"] = Token };

            ValidationOutcome outcome = RequestValidator.Validate(TestRequests.Json(fields));
            Assert.True(outcome.IsValid, outcome.Rejection?.ErrorCode);
            return outcome.Request!;
        }

        private static Dictionary<string, object?> Op(string type, object parameters, string? id = null)
        {
            var op = new Dictionary<string, object?>
            {
                ["operation_type"] = type,
                ["parameters"] = parameters,
            };
            if (id != null) op["operation_id"] = id;
            return op;
        }

        // ---------- single ----------

        [Fact]
        public void Plans_a_single_line()
        {
            CadOperationPlan plan = CadOperationPlanner.PlanSingle(
                Request(OperationType.CreateLine, new Dictionary<string, object?>
                {
                    ["layer"] = "S7_ENTITY_MVP",
                    ["start"] = new[] { 0, 0 },
                    ["end"] = new[] { 100, 0 },
                }),
                Token);

            Assert.Single(plan.Operations);
            PlannedOperation op = plan.Operations[0];
            Assert.Equal(OperationType.CreateLine, op.OperationType);
            Assert.Equal("S7_ENTITY_MVP", op.Layer);
            Assert.Equal(100.0, op.End.X);
        }

        [Fact]
        public void Plan_time_parses_structure_but_defers_semantic_checks()
        {
            // A negative radius is STRUCTURALLY valid (a finite number), so planning succeeds.
            // The semantic rejection is deferred to execution inside the transaction, which is
            // what allows a failing batch to abort a real AutoCAD transaction.
            CadOperationPlan plan = CadOperationPlanner.PlanSingle(
                Request(OperationType.CreateCircle, new Dictionary<string, object?>
                {
                    ["layer"] = "S7_ENTITY_MVP",
                    ["center"] = new[] { 0, 0 },
                    ["radius"] = -5,
                }),
                Token);

            Assert.Single(plan.Operations);
            Assert.Equal(-5.0, plan.Operations[0].Radius);

            var ex = Assert.Throws<GeometryValidationException>(() => plan.Operations[0].ValidateSemantics());
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        [Fact]
        public void Plan_time_still_rejects_structurally_invalid_input()
        {
            // Non-numeric radius is a structural error and never reaches execution.
            var ex = Assert.Throws<PlanParseException>(() => CadOperationPlanner.PlanSingle(
                Request(OperationType.CreateCircle, new Dictionary<string, object?>
                {
                    ["layer"] = "S7_ENTITY_MVP",
                    ["center"] = new[] { 0, 0 },
                    ["radius"] = "big",
                }),
                Token));

            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
            Assert.Equal(0, ex.OperationIndex);
        }

        [Fact]
        public void Semantic_validation_rejects_degenerate_line_at_execution_time()
        {
            CadOperationPlan plan = CadOperationPlanner.PlanSingle(
                Request(OperationType.CreateLine, new Dictionary<string, object?>
                {
                    ["layer"] = "S7_ENTITY_MVP",
                    ["start"] = new[] { 5, 5 },
                    ["end"] = new[] { 5, 5 },
                }),
                Token);

            var ex = Assert.Throws<GeometryValidationException>(() => plan.Operations[0].ValidateSemantics());
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        [Fact]
        public void Semantic_validation_rejects_short_polyline_at_execution_time()
        {
            CadOperationPlan plan = CadOperationPlanner.PlanSingle(
                Request(OperationType.CreatePolyline, new Dictionary<string, object?>
                {
                    ["layer"] = "S7_ENTITY_MVP",
                    ["vertices"] = new object[] { new[] { 0, 0 } },
                }),
                Token);

            var ex = Assert.Throws<GeometryValidationException>(() => plan.Operations[0].ValidateSemantics());
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        [Fact]
        public void Valid_operations_pass_semantic_validation()
        {
            CadOperationPlan plan = CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["operations"] = new object[]
                    {
                        Op(OperationType.CreateLayer, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP" }),
                        Op(OperationType.CreateLine, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["start"] = new[] { 0, 0 }, ["end"] = new[] { 10, 0 } }),
                        Op(OperationType.CreateCircle, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["center"] = new[] { 0, 0 }, ["radius"] = 5 }),
                        Op(OperationType.CreatePolyline, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["vertices"] = new object[] { new[] { 0, 0 }, new[] { 1, 1 } } }),
                    },
                }),
                Token);

            foreach (PlannedOperation op in plan.Operations) op.ValidateSemantics(); // must not throw
        }

        // ---------- batch ----------

        [Fact]
        public void Plans_a_full_batch_in_order()
        {
            CadOperationPlan plan = CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["transaction_mode"] = "all_or_nothing",
                    ["operations"] = new object[]
                    {
                        Op(OperationType.CreateLayer, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["color_index"] = 3 }, "op-layer"),
                        Op(OperationType.CreateLine, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["start"] = new[] { 0, 0 }, ["end"] = new[] { 10, 0 } }, "op-line"),
                        Op(OperationType.CreateCircle, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["center"] = new[] { 5, 5 }, ["radius"] = 2.5 }, "op-circle"),
                        Op(OperationType.CreatePolyline, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["vertices"] = new object[] { new[] { 0, 0 }, new[] { 1, 1 }, new[] { 2, 0 } }, ["closed"] = false }, "op-poly"),
                    },
                }),
                Token);

            Assert.Equal(4, plan.Operations.Count);
            Assert.Equal(new[] { 0, 1, 2, 3 }, new[] { plan.Operations[0].Index, plan.Operations[1].Index, plan.Operations[2].Index, plan.Operations[3].Index });
            Assert.Equal("op-circle", plan.Operations[2].OperationId);
            Assert.Equal(3, plan.Operations[0].ColorIndex);
            Assert.Equal(3, plan.Operations[3].Vertices.Count);
        }

        [Fact]
        public void Structural_batch_failure_reports_the_failing_index_and_id()
        {
            var ex = Assert.Throws<PlanParseException>(() => CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["operations"] = new object[]
                    {
                        Op(OperationType.CreateLine, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["start"] = new[] { 0, 0 }, ["end"] = new[] { 10, 0 } }, "good"),
                        Op(OperationType.CreateCircle, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["center"] = new[] { 0, 0 }, ["radius"] = "NaN-ish" }, "bad"),
                    },
                }),
                Token));

            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
            Assert.Equal(1, ex.OperationIndex);
            Assert.Equal("bad", ex.OperationId);
        }

        [Fact]
        public void Rollback_shaped_batch_plans_fully_and_fails_only_at_operation_1()
        {
            // This is the exact Batch B shape used in real-AutoCAD acceptance: op0 valid,
            // op1 semantically invalid. Both plan cleanly, so BOTH reach the transaction and
            // op1's failure aborts it — discarding op0's entity.
            CadOperationPlan plan = CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["operations"] = new object[]
                    {
                        Op(OperationType.CreateLine, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["start"] = new[] { 9000, 9000 }, ["end"] = new[] { 9500, 9500 } }, "b0-line"),
                        Op(OperationType.CreateCircle, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["center"] = new[] { 9000, 9000 }, ["radius"] = -50 }, "b1-bad-circle"),
                    },
                }),
                Token);

            Assert.Equal(2, plan.Operations.Count);
            plan.Operations[0].ValidateSemantics(); // op0 is fine
            Assert.Throws<GeometryValidationException>(() => plan.Operations[1].ValidateSemantics());
        }

        [Fact]
        public void Batch_rejects_a_non_all_or_nothing_mode_instead_of_downgrading()
        {
            var ex = Assert.Throws<PlanParseException>(() => CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["transaction_mode"] = "best_effort",
                    ["operations"] = new object[]
                    {
                        Op(OperationType.CreateLine, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP", ["start"] = new[] { 0, 0 }, ["end"] = new[] { 1, 1 } }),
                    },
                }),
                Token));

            Assert.Equal(ErrorCodes.InvalidFieldType, ex.ErrorCode);
        }

        [Theory]
        [InlineData(OperationType.CreateSyntheticDocument)]
        [InlineData(OperationType.QueryEntities)]
        [InlineData(OperationType.Save)]
        [InlineData(OperationType.BatchExecute)]
        public void Batch_rejects_non_entity_operations(string operationType)
        {
            var ex = Assert.Throws<PlanParseException>(() => CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["operations"] = new object[] { Op(operationType, new Dictionary<string, object?> { ["layer"] = "S7_ENTITY_MVP" }) },
                }),
                Token));

            Assert.Equal(ErrorCodes.UnknownOperation, ex.ErrorCode);
        }

        [Fact]
        public void Batch_rejects_duplicate_operation_ids()
        {
            var ex = Assert.Throws<PlanParseException>(() => CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["operations"] = new object[]
                    {
                        Op(OperationType.CreateLine, new Dictionary<string, object?> { ["layer"] = "L", ["start"] = new[] { 0, 0 }, ["end"] = new[] { 1, 1 } }, "same"),
                        Op(OperationType.CreateLine, new Dictionary<string, object?> { ["layer"] = "L", ["start"] = new[] { 0, 0 }, ["end"] = new[] { 2, 2 } }, "same"),
                    },
                }),
                Token));

            Assert.Equal(ErrorCodes.InvalidFieldType, ex.ErrorCode);
        }

        [Fact]
        public void Batch_rejects_an_empty_operation_list()
        {
            var ex = Assert.Throws<PlanParseException>(() => CadOperationPlanner.PlanBatch(
                Request(OperationType.BatchExecute, new Dictionary<string, object?>
                {
                    ["operations"] = System.Array.Empty<object>(),
                }),
                Token));

            Assert.Equal(ErrorCodes.MissingField, ex.ErrorCode);
        }

        [Fact]
        public void Batchable_set_is_exactly_the_four_entity_resource_operations()
        {
            Assert.Equal(4, CadOperationPlanner.BatchableOperations.Count);
            Assert.Contains(OperationType.CreateLayer, CadOperationPlanner.BatchableOperations);
            Assert.Contains(OperationType.CreateLine, CadOperationPlanner.BatchableOperations);
            Assert.Contains(OperationType.CreateCircle, CadOperationPlanner.BatchableOperations);
            Assert.Contains(OperationType.CreatePolyline, CadOperationPlanner.BatchableOperations);
        }
    }
}
