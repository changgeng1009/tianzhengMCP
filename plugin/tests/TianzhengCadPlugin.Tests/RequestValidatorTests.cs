using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class RequestValidatorTests
    {
        [Fact]
        public void Accepts_a_well_formed_request()
        {
            ValidationOutcome outcome = RequestValidator.Validate(TestRequests.Valid());

            Assert.True(outcome.IsValid);
            Assert.Equal(OperationType.Health, outcome.Request!.OperationType);
            Assert.Equal("req-1", outcome.Request.RequestId);
            Assert.Equal(5000, outcome.Request.TimeoutMs);
        }

        [Fact]
        public void Rejects_unknown_field()
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.WithExtra("surprise_field", "x"));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.UnknownField, outcome.Rejection!.ErrorCode);
            Assert.Equal(Stages.Validation, outcome.Rejection.Stage);
            Assert.False(outcome.Rejection.Retryable);
        }

        [Theory]
        [InlineData("protocol_version")]
        [InlineData("request_id")]
        [InlineData("job_id")]
        [InlineData("operation_id")]
        [InlineData("operation_type")]
        [InlineData("document_context")]
        [InlineData("parameters")]
        [InlineData("idempotency_key")]
        [InlineData("expected_capability")]
        [InlineData("dry_run")]
        [InlineData("timeout_ms")]
        [InlineData("metadata")]
        public void Rejects_missing_required_field(string field)
        {
            ValidationOutcome outcome = RequestValidator.Validate(TestRequests.Without(field));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.MissingField, outcome.Rejection!.ErrorCode);
        }

        [Fact]
        public void Rejects_unknown_operation_type()
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.Valid(operationType: "run_arbitrary_command"));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.UnknownOperation, outcome.Rejection!.ErrorCode);
        }

        [Theory]
        [InlineData("send_command")]
        [InlineData("eval")]
        [InlineData("lisp")]
        [InlineData("netload")]
        [InlineData("exec")]
        public void Rejects_arbitrary_execution_style_operations(string op)
        {
            ValidationOutcome outcome = RequestValidator.Validate(TestRequests.Valid(operationType: op));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.UnknownOperation, outcome.Rejection!.ErrorCode);
        }

        [Theory]
        [InlineData("1.0.0")] // the pre-2.0.0 protocol: readiness was a string
        [InlineData("3.0.0")]
        public void Rejects_incompatible_protocol_major_version(string version)
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.With("protocol_version", version));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.IncompatibleProtocolVersion, outcome.Rejection!.ErrorCode);
        }

        [Fact]
        public void Accepts_compatible_minor_version()
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.With("protocol_version", "2.4.2"));

            Assert.True(outcome.IsValid);
        }

        [Fact]
        public void Rejects_malformed_json()
        {
            ValidationOutcome outcome = RequestValidator.Validate("{not json");

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.InvalidJson, outcome.Rejection!.ErrorCode);
        }

        [Fact]
        public void Rejects_non_object_root()
        {
            ValidationOutcome outcome = RequestValidator.Validate("[1,2,3]");

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.InvalidJson, outcome.Rejection!.ErrorCode);
        }

        [Theory]
        [InlineData("dry_run", "yes")]          // string where a boolean is required
        [InlineData("timeout_ms", "soon")]      // string where an integer is required
        [InlineData("operation_type", 123)]     // number where a string is required
        [InlineData("parameters", "not-an-object")]
        [InlineData("document_context", "not-an-object")]
        [InlineData("metadata", "not-an-object")]
        [InlineData("session_nonce", 42)]
        public void Rejects_wrong_field_types(string field, object badValue)
        {
            ValidationOutcome outcome = RequestValidator.Validate(TestRequests.With(field, badValue));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.InvalidFieldType, outcome.Rejection!.ErrorCode);
        }

        [Theory]
        [InlineData(0)]
        [InlineData(-1)]
        [InlineData(ProtocolConstants.MaxTimeoutMs + 1)]
        public void Rejects_out_of_range_timeout(int timeout)
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.With("timeout_ms", timeout));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.InvalidTimeout, outcome.Rejection!.ErrorCode);
        }

        [Fact]
        public void Rejection_message_does_not_echo_unbounded_input()
        {
            string huge = new('A', 5000);
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.Valid(operationType: huge));

            Assert.False(outcome.IsValid);
            Assert.True(outcome.Rejection!.SanitizedMessage.Length < 200);
        }

        [Fact]
        public void Business_request_schema_has_no_auth_token_field()
        {
            // The token must live only in the connection handshake, never in a business
            // request, so it can never reach business metadata or the operation queue.
            Assert.DoesNotContain("auth_token", PluginRequest.AllowedFields);
            Assert.DoesNotContain("auth_token", PluginRequest.RequiredFields);
        }

        [Fact]
        public void Rejects_a_request_that_tries_to_smuggle_a_token()
        {
            ValidationOutcome outcome = RequestValidator.Validate(
                TestRequests.WithExtra("auth_token", "some-token-value-0123456789abcdef"));

            Assert.False(outcome.IsValid);
            Assert.Equal(ErrorCodes.UnknownField, outcome.Rejection!.ErrorCode);
        }

        [Fact]
        public void Every_whitelisted_operation_is_accepted_by_the_parser()
        {
            foreach (string op in OperationType.All)
            {
                ValidationOutcome outcome = RequestValidator.Validate(TestRequests.Valid(operationType: op));
                Assert.True(outcome.IsValid, $"operation '{op}' should parse");
            }
        }
    }
}
