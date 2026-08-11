using System.Collections.Generic;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// The plan hash is what makes IDEMPOTENCY_CONFLICT possible: the plugin recomputes it
    /// from the parsed payload, so a caller cannot reuse a key with a different payload.
    /// </summary>
    public class PlanHashTests
    {
        private static CadOperationPlan Plan(object operations, string batchId = "b1", string token = "tok")
        {
            var fields = TestRequests.BaseFields(OperationType.BatchExecute, TestRequests.TestNonce);
            fields["request_id"] = batchId;
            fields["parameters"] = new Dictionary<string, object?> { ["operations"] = operations };
            fields["document_context"] = new Dictionary<string, object?> { ["document_token"] = token };

            ValidationOutcome outcome = RequestValidator.Validate(TestRequests.Json(fields));
            Assert.True(outcome.IsValid, outcome.Rejection?.ErrorCode);
            return CadOperationPlanner.PlanBatch(outcome.Request!, token);
        }

        private static Dictionary<string, object?> Line(double endX) => new()
        {
            ["operation_type"] = OperationType.CreateLine,
            ["parameters"] = new Dictionary<string, object?>
            {
                ["layer"] = "S7_ENTITY_MVP",
                ["start"] = new[] { 0, 0 },
                ["end"] = new[] { endX, 0 },
            },
        };

        private static Dictionary<string, object?> Circle(double radius) => new()
        {
            ["operation_type"] = OperationType.CreateCircle,
            ["parameters"] = new Dictionary<string, object?>
            {
                ["layer"] = "S7_ENTITY_MVP",
                ["center"] = new[] { 0, 0 },
                ["radius"] = radius,
            },
        };

        [Fact]
        public void Identical_payloads_hash_identically()
        {
            string a = Plan(new object[] { Line(100), Circle(5) }).ComputePlanHash();
            string b = Plan(new object[] { Line(100), Circle(5) }).ComputePlanHash();

            Assert.Equal(a, b);
            Assert.Equal(64, a.Length); // sha256 hex
        }

        [Fact]
        public void Hash_ignores_batch_id_and_document_token()
        {
            // A genuine replay differs in request id and may target a reopened document,
            // yet must still be recognised as the same plan.
            string a = Plan(new object[] { Line(100) }, batchId: "first", token: "token-a").ComputePlanHash();
            string b = Plan(new object[] { Line(100) }, batchId: "second", token: "token-b").ComputePlanHash();

            Assert.Equal(a, b);
        }

        [Fact]
        public void A_changed_radius_changes_the_hash()
        {
            // This is exactly the IDEMPOTENCY_CONFLICT scenario.
            string original = Plan(new object[] { Line(100), Circle(5) }).ComputePlanHash();
            string modified = Plan(new object[] { Line(100), Circle(9) }).ComputePlanHash();

            Assert.NotEqual(original, modified);
        }

        [Fact]
        public void A_changed_coordinate_changes_the_hash()
            => Assert.NotEqual(
                Plan(new object[] { Line(100) }).ComputePlanHash(),
                Plan(new object[] { Line(101) }).ComputePlanHash());

        [Fact]
        public void Operation_order_changes_the_hash()
            => Assert.NotEqual(
                Plan(new object[] { Line(100), Circle(5) }).ComputePlanHash(),
                Plan(new object[] { Circle(5), Line(100) }).ComputePlanHash());

        [Fact]
        public void A_changed_layer_changes_the_hash()
        {
            var other = new Dictionary<string, object?>
            {
                ["operation_type"] = OperationType.CreateLine,
                ["parameters"] = new Dictionary<string, object?>
                {
                    ["layer"] = "OTHER_LAYER",
                    ["start"] = new[] { 0, 0 },
                    ["end"] = new[] { 100, 0 },
                },
            };

            Assert.NotEqual(
                Plan(new object[] { Line(100) }).ComputePlanHash(),
                Plan(new object[] { other }).ComputePlanHash());
        }
    }
}
