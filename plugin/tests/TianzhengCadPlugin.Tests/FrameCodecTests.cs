using System;
using System.Buffers.Binary;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class FrameCodecTests
    {
        [Fact]
        public void Encode_uses_4_byte_big_endian_length_header()
        {
            byte[] frame = FrameCodec.Encode("hi");

            Assert.Equal(ProtocolConstants.FrameHeaderBytes + 2, frame.Length);
            Assert.Equal(new byte[] { 0x00, 0x00, 0x00, 0x02 }, frame[..4]);
            Assert.Equal("hi", Encoding.UTF8.GetString(frame, 4, 2));
        }

        [Fact]
        public void Encode_length_counts_utf8_bytes_not_chars()
        {
            // 3-byte UTF-8 character: the header must describe BYTES.
            byte[] frame = FrameCodec.Encode("图");
            uint declared = BinaryPrimitives.ReadUInt32BigEndian(frame.AsSpan(0, 4));

            Assert.Equal(3u, declared);
            Assert.Equal(7, frame.Length);
        }

        [Fact]
        public async Task Roundtrip_preserves_payload()
        {
            const string payload = """{"a":1,"b":"图纸"}""";
            using var stream = new MemoryStream();

            await FrameCodec.WriteFrameAsync(stream, payload, CancellationToken.None);
            stream.Position = 0;
            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);

            Assert.Equal(FrameReadStatus.Ok, result.Status);
            Assert.Equal(payload, result.Payload);
        }

        [Fact]
        public async Task DeclaredLength_is_utf8_bytes_not_characters()
        {
            // "图纸" = 2 characters but 6 UTF-8 bytes. DeclaredLength must report 6.
            const string payload = "图纸";
            Assert.Equal(2, payload.Length);
            Assert.Equal(6, Encoding.UTF8.GetByteCount(payload));

            using var stream = new MemoryStream();
            await FrameCodec.WriteFrameAsync(stream, payload, CancellationToken.None);
            stream.Position = 0;

            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);

            Assert.Equal(FrameReadStatus.Ok, result.Status);
            Assert.Equal(payload, result.Payload);
            Assert.Equal(6, result.DeclaredLength);
            Assert.NotEqual(payload.Length, result.DeclaredLength);
        }

        [Fact]
        public async Task DeclaredLength_matches_the_header_for_mixed_scripts()
        {
            // ASCII + CJK + emoji (surrogate pair): chars=?, bytes must match the header.
            const string payload = """{"layer":"图层-A","note":"ok 🚀"}""";
            int expectedBytes = Encoding.UTF8.GetByteCount(payload);

            using var stream = new MemoryStream();
            await FrameCodec.WriteFrameAsync(stream, payload, CancellationToken.None);
            stream.Position = 0;

            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);

            Assert.Equal(expectedBytes, result.DeclaredLength);
            Assert.True(result.DeclaredLength > payload.Length, "byte count must exceed char count here");
            Assert.Equal(payload, result.Payload);
        }

        [Fact]
        public async Task Reads_exactly_one_frame_and_leaves_the_next_intact()
        {
            // Guards against "read JSON until socket close" behaviour.
            using var stream = new MemoryStream();
            await FrameCodec.WriteFrameAsync(stream, "first", CancellationToken.None);
            await FrameCodec.WriteFrameAsync(stream, "second", CancellationToken.None);
            stream.Position = 0;

            FrameReadResult one = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);
            FrameReadResult two = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);

            Assert.Equal("first", one.Payload);
            Assert.Equal("second", two.Payload);
        }

        [Fact]
        public async Task Clean_close_on_boundary_reports_Closed()
        {
            using var empty = new MemoryStream(Array.Empty<byte>());
            FrameReadResult result = await FrameCodec.ReadFrameAsync(empty, CancellationToken.None);
            Assert.Equal(FrameReadStatus.Closed, result.Status);
        }

        [Fact]
        public async Task Oversized_declared_length_is_rejected_without_reading_body()
        {
            // Header claims 100 MB but no body follows; must reject on the header alone.
            byte[] header = new byte[4];
            BinaryPrimitives.WriteUInt32BigEndian(header, 100u * 1024 * 1024);
            using var stream = new MemoryStream(header);

            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);

            Assert.Equal(FrameReadStatus.TooLarge, result.Status);
        }

        [Fact]
        public async Task Zero_length_frame_is_rejected()
        {
            using var stream = new MemoryStream(new byte[] { 0, 0, 0, 0 });
            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);
            Assert.Equal(FrameReadStatus.TooLarge, result.Status);
        }

        [Fact]
        public async Task Truncated_body_is_malformed()
        {
            byte[] header = new byte[4];
            BinaryPrimitives.WriteUInt32BigEndian(header, 10);
            using var stream = new MemoryStream([.. header, .. "abc"u8.ToArray()]);

            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);

            Assert.Equal(FrameReadStatus.Malformed, result.Status);
        }

        [Fact]
        public async Task Truncated_header_is_malformed()
        {
            using var stream = new MemoryStream(new byte[] { 0, 0 });
            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);
            Assert.Equal(FrameReadStatus.Malformed, result.Status);
        }

        [Fact]
        public async Task Invalid_utf8_payload_is_malformed()
        {
            byte[] header = new byte[4];
            BinaryPrimitives.WriteUInt32BigEndian(header, 2);
            // 0xC3 starts a 2-byte sequence; 0x28 is an invalid continuation byte.
            using var stream = new MemoryStream([.. header, 0xC3, 0x28]);

            FrameReadResult result = await FrameCodec.ReadFrameAsync(stream, CancellationToken.None);

            Assert.Equal(FrameReadStatus.Malformed, result.Status);
        }

        [Fact]
        public void Encoding_an_oversized_payload_throws()
        {
            string big = new('x', ProtocolConstants.MaxPayloadBytes + 1);
            Assert.Throws<InvalidOperationException>(() => FrameCodec.Encode(big));
        }
    }
}
