using System;
using System.IO;
using System.Text.RegularExpressions;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>Raised when a requested save target violates the sandbox policy.</summary>
    public sealed class SandboxPathException : Exception
    {
        public string ErrorCode { get; }

        public SandboxPathException(string errorCode, string message) : base(message)
            => ErrorCode = errorCode;
    }

    /// <summary>
    /// Decides where a synthetic document may be written.
    ///
    /// THREAT MODEL: the caller supplies only a bare FILE NAME, never a path. The sandbox
    /// root comes from the plugin's own launch configuration, not from the wire. Anything
    /// that could escape the root — a directory separator, a drive letter, "..", a UNC
    /// prefix, an alternate data stream, a reserved device name — is rejected before the
    /// path is ever combined, and the combined result is then re-verified against the
    /// canonicalised root. Both checks must pass.
    ///
    /// Pure and AutoCAD-free, so every rejection path is unit-testable.
    /// </summary>
    public static class SandboxPathPolicy
    {
        /// <summary>Only DWG may be written. No DXF, no template, no script.</summary>
        public const string RequiredExtension = ".dwg";

        public const int MaxFileNameLength = 96;

        /// <summary>Conservative allow-list: letters, digits, underscore, dash, dot.</summary>
        private static readonly Regex SafeFileName =
            new(@"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}$", RegexOptions.Compiled);

        /// <summary>Windows reserved device names, which are illegal as file names.</summary>
        private static readonly string[] ReservedNames =
        {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        };

        /// <summary>
        /// Resolve <paramref name="fileName"/> inside <paramref name="sandboxRoot"/>.
        /// Returns the full path only when every check passes.
        /// </summary>
        public static string Resolve(string? sandboxRoot, string? fileName)
        {
            if (string.IsNullOrWhiteSpace(sandboxRoot))
                throw new SandboxPathException(
                    ErrorCodes.SandboxNotConfigured, "no sandbox root is configured for this plugin session");

            if (string.IsNullOrWhiteSpace(fileName))
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name is required");

            string candidate = fileName.Trim();

            if (candidate.Length > MaxFileNameLength)
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name is too long");

            // Reject anything path-like BEFORE touching the filesystem API.
            if (candidate.Contains('/') || candidate.Contains('\\'))
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name must not contain a path separator");
            if (candidate.Contains(':'))
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name must not contain a drive or stream separator");
            if (candidate.Contains(".."))
                throw new SandboxPathException(ErrorCodes.PathTraversalRejected, "file name must not contain '..'");
            if (Path.IsPathRooted(candidate))
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name must not be an absolute path");
            if (candidate.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name contains invalid characters");
            if (!SafeFileName.IsMatch(candidate))
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name contains unsupported characters");

            if (!candidate.EndsWith(RequiredExtension, StringComparison.OrdinalIgnoreCase))
                throw new SandboxPathException(
                    ErrorCodes.InvalidSandboxPath, $"file name must end with {RequiredExtension}");

            string stem = Path.GetFileNameWithoutExtension(candidate);
            foreach (string reserved in ReservedNames)
            {
                if (string.Equals(stem, reserved, StringComparison.OrdinalIgnoreCase))
                    throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "file name is a reserved device name");
            }

            string root;
            string full;
            try
            {
                root = Path.GetFullPath(sandboxRoot);
                full = Path.GetFullPath(Path.Combine(root, candidate));
            }
            catch (Exception)
            {
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "sandbox path could not be resolved");
            }

            // UNC / network locations are refused outright.
            if (root.StartsWith(@"\\", StringComparison.Ordinal) || full.StartsWith(@"\\", StringComparison.Ordinal))
                throw new SandboxPathException(ErrorCodes.InvalidSandboxPath, "network paths are not permitted");

            // Second, authoritative containment check on the canonicalised result.
            string rootWithSeparator = root.EndsWith(Path.DirectorySeparatorChar)
                ? root
                : root + Path.DirectorySeparatorChar;

            if (!full.StartsWith(rootWithSeparator, StringComparison.OrdinalIgnoreCase))
                throw new SandboxPathException(
                    ErrorCodes.SandboxEscapeRejected, "resolved path escapes the sandbox root");

            // Must be directly inside the root: no implicit subdirectories.
            string? parent = Path.GetDirectoryName(full);
            if (parent == null || !string.Equals(
                    parent.TrimEnd(Path.DirectorySeparatorChar),
                    root.TrimEnd(Path.DirectorySeparatorChar),
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new SandboxPathException(
                    ErrorCodes.SandboxEscapeRejected, "resolved path is not directly inside the sandbox root");
            }

            return full;
        }

        /// <summary>
        /// Sanitized identity for evidence and responses: the bare file name only.
        /// The absolute sandbox path never crosses the protocol boundary.
        /// </summary>
        public static string SanitizedIdentity(string fullPath)
        {
            try { return Path.GetFileName(fullPath); }
            catch (Exception) { return "<unresolved>"; }
        }
    }
}
