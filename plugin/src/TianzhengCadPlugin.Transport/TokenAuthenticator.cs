using System;
using System.Security.Cryptography;
using System.Text;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>
    /// Local session-token authentication.
    ///
    /// The token is INJECTED at plugin start (environment variable or a local, git-ignored
    /// file). It is never hardcoded, never written to the repo, and never logged in full.
    /// Only the SHA-256 digest is retained, and comparison is constant-time so a timing
    /// side channel cannot reveal the secret.
    /// </summary>
    public sealed class TokenAuthenticator
    {
        /// <summary>Minimum accepted token length; short/guessable tokens are refused outright.</summary>
        public const int MinimumTokenLength = 32;

        private readonly byte[] _expectedDigest;

        private TokenAuthenticator(byte[] expectedDigest) => _expectedDigest = expectedDigest;

        public static TokenAuthenticator FromToken(string token)
        {
            if (string.IsNullOrEmpty(token) || token.Length < MinimumTokenLength)
            {
                throw new ArgumentException(
                    $"injected auth token must be at least {MinimumTokenLength} characters", nameof(token));
            }
            return new TokenAuthenticator(SHA256.HashData(Encoding.UTF8.GetBytes(token)));
        }

        /// <summary>Constant-time verification. Returns false for null/empty without short-circuit leaks.</summary>
        public bool Verify(string? candidate)
        {
            if (string.IsNullOrEmpty(candidate)) return false;
            byte[] candidateDigest = SHA256.HashData(Encoding.UTF8.GetBytes(candidate));
            return CryptographicOperations.FixedTimeEquals(candidateDigest, _expectedDigest);
        }

        /// <summary>
        /// Redact a secret for logging. Never returns more than a short prefix of the DIGEST
        /// (not the token itself), so logs can correlate sessions without leaking credentials.
        /// </summary>
        public static string Redact(string? secret)
        {
            if (string.IsNullOrEmpty(secret)) return "<empty>";
            byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(secret));
            return "sha256:" + Convert.ToHexString(digest, 0, 4).ToLowerInvariant() + "...";
        }
    }
}
