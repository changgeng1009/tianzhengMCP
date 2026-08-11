using System;
using System.IO;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>
    /// Resolves the injected auth token from the environment. There is NO fallback default
    /// and NO hardcoded token: if nothing is injected, the transport must refuse to start.
    ///
    /// Resolution order:
    ///   1. TIANZHENG_PLUGIN_TOKEN            (token value)
    ///   2. TIANZHENG_PLUGIN_TOKEN_FILE       (path to a local, git-ignored file)
    /// </summary>
    public static class TokenProvider
    {
        public const string TokenEnvVar = "TIANZHENG_PLUGIN_TOKEN";
        public const string TokenFileEnvVar = "TIANZHENG_PLUGIN_TOKEN_FILE";

        /// <summary>Returns the injected token, or null when none is configured.</summary>
        public static string? TryResolve()
        {
            string? direct = Environment.GetEnvironmentVariable(TokenEnvVar);
            if (!string.IsNullOrWhiteSpace(direct)) return direct.Trim();

            string? path = Environment.GetEnvironmentVariable(TokenFileEnvVar);
            if (!string.IsNullOrWhiteSpace(path) && File.Exists(path))
            {
                string fromFile = File.ReadAllText(path).Trim();
                if (!string.IsNullOrWhiteSpace(fromFile)) return fromFile;
            }
            return null;
        }
    }
}
