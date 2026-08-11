using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class AuthFrameTests
    {
        [Fact]
        public void Parses_a_well_formed_auth_frame()
        {
            Assert.True(AuthFrameParser.TryParse(TestRequests.AuthFrame(), out AuthFrame frame));
            Assert.Equal(TestRequests.ValidToken, frame.AuthToken);
        }

        [Theory]
        [InlineData("{not json")]
        [InlineData("[]")]
        [InlineData("\"string\"")]
        [InlineData("""{"type":"auth"}""")]                                  // no token
        [InlineData("""{"auth_token":"x"}""")]                               // no type
        [InlineData("""{"type":"hello","auth_token":"x"}""")]                // wrong type
        [InlineData("""{"type":"auth","auth_token":123}""")]                 // wrong token type
        [InlineData("""{"type":"auth","auth_token":"x","extra":1}""")]       // unknown field
        [InlineData("""{"type":"auth","auth_token":"x","protocol_version":"1.0.0"}""")] // bad major
        public void Rejects_malformed_auth_frames(string json)
        {
            Assert.False(AuthFrameParser.TryParse(json, out _));
        }

        [Fact]
        public void A_business_request_is_not_accepted_as_an_auth_frame()
        {
            // Guards the state machine: you cannot skip the handshake by sending a request.
            Assert.False(AuthFrameParser.TryParse(TestRequests.Valid(), out _));
        }

        [Fact]
        public void Build_round_trips_through_the_parser()
        {
            string json = AuthFrameParser.Build("a-token-that-is-long-enough-0123456789");

            Assert.True(AuthFrameParser.TryParse(json, out AuthFrame frame));
            Assert.Equal("a-token-that-is-long-enough-0123456789", frame.AuthToken);
            Assert.Equal(ProtocolConstants.ProtocolVersion, frame.ProtocolVersion);
        }

        [Fact]
        public void Unauthenticated_response_leaks_no_internal_state()
        {
            PluginResponse response = PluginResponse.Unauthenticated(ErrorCodes.AuthFailed);
            string json = response.ToJson();

            Assert.False(response.Success);
            Assert.Equal("", response.PluginVersion);
            Assert.Equal("", response.CapabilityVersion);
            Assert.Equal("", response.PluginState);
            Assert.Null(response.Result);
            Assert.Equal("authentication required", response.SanitizedMessage);

            // No capability vocabulary or field enumeration may appear.
            Assert.DoesNotContain("supported_operations", json);
            Assert.DoesNotContain("tianzheng", json);
            Assert.DoesNotContain("session_nonce", json);
            Assert.DoesNotContain(ProtocolConstants.PluginVersion, json);
        }
    }
}
