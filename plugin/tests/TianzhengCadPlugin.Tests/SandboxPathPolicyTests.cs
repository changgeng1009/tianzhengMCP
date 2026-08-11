using System;
using System.IO;
using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class SandboxPathPolicyTests
    {
        private static readonly string Root = Path.Combine(Path.GetTempPath(), "tz_sandbox_root");

        [Fact]
        public void Resolves_a_simple_dwg_name_inside_the_root()
        {
            string full = SandboxPathPolicy.Resolve(Root, "s7_synthetic.dwg");

            Assert.StartsWith(Path.GetFullPath(Root), full, StringComparison.OrdinalIgnoreCase);
            Assert.Equal("s7_synthetic.dwg", Path.GetFileName(full));
        }

        [Fact]
        public void Requires_a_configured_sandbox_root()
        {
            var ex = Assert.Throws<SandboxPathException>(() => SandboxPathPolicy.Resolve(null, "a.dwg"));
            Assert.Equal(ErrorCodes.SandboxNotConfigured, ex.ErrorCode);
        }

        [Theory]
        [InlineData("../escape.dwg")]
        [InlineData("..\\escape.dwg")]
        [InlineData("sub/../../escape.dwg")]
        public void Rejects_path_traversal(string name)
        {
            var ex = Assert.Throws<SandboxPathException>(() => SandboxPathPolicy.Resolve(Root, name));
            Assert.Contains(ex.ErrorCode, new[] { ErrorCodes.PathTraversalRejected, ErrorCodes.InvalidSandboxPath });
        }

        [Theory]
        [InlineData("sub/child.dwg")]
        [InlineData("sub\\child.dwg")]
        [InlineData("C:\\Windows\\evil.dwg")]
        [InlineData("\\\\server\\share\\evil.dwg")]
        [InlineData("D:evil.dwg")]
        [InlineData("stream.dwg:hidden")]
        public void Rejects_anything_path_like(string name)
        {
            var ex = Assert.Throws<SandboxPathException>(() => SandboxPathPolicy.Resolve(Root, name));
            Assert.Contains(ex.ErrorCode, new[]
            {
                ErrorCodes.InvalidSandboxPath, ErrorCodes.PathTraversalRejected, ErrorCodes.SandboxEscapeRejected,
            });
        }

        [Theory]
        [InlineData("drawing.dxf")]
        [InlineData("drawing.dwt")]
        [InlineData("drawing.scr")]
        [InlineData("drawing.lsp")]
        [InlineData("drawing")]
        public void Only_dwg_may_be_written(string name)
        {
            var ex = Assert.Throws<SandboxPathException>(() => SandboxPathPolicy.Resolve(Root, name));
            Assert.Equal(ErrorCodes.InvalidSandboxPath, ex.ErrorCode);
        }

        [Theory]
        [InlineData("CON.dwg")]
        [InlineData("nul.dwg")]
        [InlineData("LPT1.dwg")]
        public void Rejects_reserved_device_names(string name)
        {
            var ex = Assert.Throws<SandboxPathException>(() => SandboxPathPolicy.Resolve(Root, name));
            Assert.Equal(ErrorCodes.InvalidSandboxPath, ex.ErrorCode);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        [InlineData(null)]
        public void Rejects_empty_names(string? name)
        {
            var ex = Assert.Throws<SandboxPathException>(() => SandboxPathPolicy.Resolve(Root, name));
            Assert.Equal(ErrorCodes.InvalidSandboxPath, ex.ErrorCode);
        }

        [Fact]
        public void Rejects_an_over_long_name()
        {
            string name = new string('a', 200) + ".dwg";
            var ex = Assert.Throws<SandboxPathException>(() => SandboxPathPolicy.Resolve(Root, name));
            Assert.Equal(ErrorCodes.InvalidSandboxPath, ex.ErrorCode);
        }

        [Fact]
        public void Sanitized_identity_exposes_only_the_file_name()
        {
            string full = SandboxPathPolicy.Resolve(Root, "keep_me.dwg");
            string identity = SandboxPathPolicy.SanitizedIdentity(full);

            Assert.Equal("keep_me.dwg", identity);
            Assert.DoesNotContain(Path.DirectorySeparatorChar, identity);
            Assert.DoesNotContain("Temp", identity, StringComparison.OrdinalIgnoreCase);
        }
    }
}
