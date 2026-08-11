using System;
using System.Buffers.Binary;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>Outcome of a framed read.</summary>
    public enum FrameReadStatus
    {
        Ok,
        /// <summary>Peer closed cleanly on a frame boundary (no partial frame).</summary>
        Closed,
        /// <summary>Declared length exceeded <see cref="ProtocolConstants.MaxPayloadBytes"/> or was zero.</summary>
        TooLarge,
        /// <summary>Stream ended mid-frame, or the payload was not valid UTF-8.</summary>
        Malformed,
    }

    public readonly struct FrameReadResult
    {
        public FrameReadStatus Status { get; }
        public string? Payload { get; }

        /// <summary>
        /// The payload length in UTF-8 BYTES, exactly as declared by the frame header.
        /// This is never a character count: for non-ASCII payloads the byte count is
        /// larger than <c>Payload.Length</c>.
        /// </summary>
        public int DeclaredLength { get; }

        private FrameReadResult(FrameReadStatus status, string? payload, int declaredLength)
        {
            Status = status;
            Payload = payload;
            DeclaredLength = declaredLength;
        }

        public static FrameReadResult Ok(string payload, int declaredByteLength) =>
            new(FrameReadStatus.Ok, payload, declaredByteLength);

        public static FrameReadResult Closed() => new(FrameReadStatus.Closed, null, 0);
        public static FrameReadResult TooLarge(int declared) => new(FrameReadStatus.TooLarge, null, declared);
        public static FrameReadResult Malformed() => new(FrameReadStatus.Malformed, null, 0);
    }

    /// <summary>
    /// Length-prefixed framing: [4-byte unsigned big-endian payload length][UTF-8 JSON payload].
    ///
    /// The declared length is validated against <see cref="ProtocolConstants.MaxPayloadBytes"/>
    /// BEFORE any payload byte is read, so an oversized or hostile declaration cannot force an
    /// unbounded allocation. Reading JSON "until the socket closes" is never used.
    /// </summary>
    public static class FrameCodec
    {
        /// <summary>Encode a payload into a complete frame (header + body).</summary>
        public static byte[] Encode(string payload)
        {
            if (payload is null) throw new ArgumentNullException(nameof(payload));

            byte[] body = Encoding.UTF8.GetBytes(payload);
            if (body.Length > ProtocolConstants.MaxPayloadBytes)
            {
                throw new InvalidOperationException(
                    $"payload {body.Length} exceeds max {ProtocolConstants.MaxPayloadBytes}");
            }

            byte[] frame = new byte[ProtocolConstants.FrameHeaderBytes + body.Length];
            BinaryPrimitives.WriteUInt32BigEndian(frame.AsSpan(0, ProtocolConstants.FrameHeaderBytes), (uint)body.Length);
            Buffer.BlockCopy(body, 0, frame, ProtocolConstants.FrameHeaderBytes, body.Length);
            return frame;
        }

        public static async Task WriteFrameAsync(Stream stream, string payload, CancellationToken ct)
        {
            byte[] frame = Encode(payload);
            await stream.WriteAsync(frame, ct).ConfigureAwait(false);
            await stream.FlushAsync(ct).ConfigureAwait(false);
        }

        /// <summary>
        /// Read exactly one frame. Returns a status instead of throwing on protocol-level
        /// problems so the caller can emit a structured error response.
        /// </summary>
        public static async Task<FrameReadResult> ReadFrameAsync(Stream stream, CancellationToken ct)
        {
            byte[] header = new byte[ProtocolConstants.FrameHeaderBytes];

            int read = await ReadUpToAsync(stream, header, ct).ConfigureAwait(false);
            if (read == 0) return FrameReadResult.Closed();              // clean close on boundary
            if (read < header.Length) return FrameReadResult.Malformed(); // truncated header

            uint declared = BinaryPrimitives.ReadUInt32BigEndian(header);
            if (declared == 0 || declared > ProtocolConstants.MaxPayloadBytes)
            {
                // Reject BEFORE allocating/reading the body.
                return FrameReadResult.TooLarge(declared > int.MaxValue ? int.MaxValue : (int)declared);
            }

            byte[] body = new byte[declared];
            int bodyRead = await ReadUpToAsync(stream, body, ct).ConfigureAwait(false);
            if (bodyRead < body.Length) return FrameReadResult.Malformed();

            try
            {
                // Strict UTF-8: invalid byte sequences are a protocol error, not silent U+FFFD.
                string payload = new UTF8Encoding(false, throwOnInvalidBytes: true).GetString(body);
                // body.Length is the declared UTF-8 byte count, not the character count.
                return FrameReadResult.Ok(payload, body.Length);
            }
            catch (DecoderFallbackException)
            {
                return FrameReadResult.Malformed();
            }
        }

        /// <summary>Fill <paramref name="buffer"/>; returns bytes actually read (0 = clean EOF).</summary>
        private static async Task<int> ReadUpToAsync(Stream stream, byte[] buffer, CancellationToken ct)
        {
            int total = 0;
            while (total < buffer.Length)
            {
                int n = await stream.ReadAsync(buffer.AsMemory(total, buffer.Length - total), ct).ConfigureAwait(false);
                if (n == 0) break;
                total += n;
            }
            return total;
        }
    }
}
