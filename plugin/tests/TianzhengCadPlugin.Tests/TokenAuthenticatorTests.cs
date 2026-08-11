using System;
using TianzhengCadPlugin.Transport;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class TokenAuthenticatorTests
    {
        private const string Token = "abcdefghijklmnopqrstuvwxyz0123456789";

        [Fact]
        public void Accepts_the_injected_token()
        {
            TokenAuthenticator auth = TokenAuthenticator.FromToken(Token);
            Assert.True(auth.Verify(Token));
        }

        [Theory]
        [InlineData("")]
        [InlineData(null)]
        [InlineData("wrong-token-wrong-token-wrong-token")]
        public void Rejects_wrong_or_empty_tokens(string? candidate)
        {
            TokenAuthenticator auth = TokenAuthenticator.FromToken(Token);
            Assert.False(auth.Verify(candidate));
        }

        [Fact]
        public void Rejects_a_token_differing_only_in_the_last_character()
        {
            TokenAuthenticator auth = TokenAuthenticator.FromToken(Token);
            Assert.False(auth.Verify(Token[..^1] + "X"));
        }

        [Theory]
        [InlineData("")]
        [InlineData("short")]
        [InlineData("still-too-short-under-32-chars")]
        public void Refuses_to_configure_a_weak_token(string weak)
        {
            Assert.Throws<ArgumentException>(() => TokenAuthenticator.FromToken(weak));
        }

        [Fact]
        public void Redact_never_reveals_the_token()
        {
            string redacted = TokenAuthenticator.Redact(Token);

            Assert.DoesNotContain(Token, redacted);
            Assert.StartsWith("sha256:", redacted);
            Assert.True(redacted.Length < 24);
        }

        [Fact]
        public void Redact_handles_empty_input()
        {
            Assert.Equal("<empty>", TokenAuthenticator.Redact(""));
            Assert.Equal("<empty>", TokenAuthenticator.Redact(null));
        }

        [Fact]
        public void No_default_token_exists_in_the_environment_resolver()
        {
            // Guards against reintroducing a hardcoded fallback like "lab-default-token".
            string? previousToken = Environment.GetEnvironmentVariable(TokenProvider.TokenEnvVar);
            string? previousFile = Environment.GetEnvironmentVariable(TokenProvider.TokenFileEnvVar);
            try
            {
                Environment.SetEnvironmentVariable(TokenProvider.TokenEnvVar, null);
                Environment.SetEnvironmentVariable(TokenProvider.TokenFileEnvVar, null);

                Assert.Null(TokenProvider.TryResolve());
            }
            finally
            {
                Environment.SetEnvironmentVariable(TokenProvider.TokenEnvVar, previousToken);
                Environment.SetEnvironmentVariable(TokenProvider.TokenFileEnvVar, previousFile);
            }
        }
    }
}
