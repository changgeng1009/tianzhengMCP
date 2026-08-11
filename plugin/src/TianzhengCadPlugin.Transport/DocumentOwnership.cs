using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using TianzhengCadPlugin.Protocol;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>
    /// Opaque handle to the real AutoCAD Document held by the host assembly.
    ///
    /// The ownership POLICY (this file) never dereferences it — it only compares identity.
    /// That is what keeps the policy free of AutoCAD references and therefore unit-testable
    /// without AutoCAD, while the host supplies the concrete implementation.
    /// </summary>
    public interface IDocumentHandle
    {
        /// <summary>Database fingerprint (AutoCAD assigns a GUID per database).</summary>
        string DatabaseFingerprint { get; }

        /// <summary>False once the underlying Document/Database is gone.</summary>
        bool IsAlive { get; }
    }

    /// <summary>One registered, job-owned synthetic document.</summary>
    public sealed class DocumentRecord
    {
        public required string DocumentToken { get; init; }
        public required string SessionId { get; init; }
        public required string JobId { get; init; }
        public required IDocumentHandle Handle { get; init; }
        public required string DatabaseFingerprint { get; init; }
        public required DateTimeOffset CreatedAt { get; init; }

        /// <summary>Always true: only plugin-created documents are ever registered.</summary>
        public bool Synthetic { get; init; } = true;

        public string CreationMethod { get; init; } = "";

        // ---- S7.4 lifecycle state ----

        /// <summary>Absolute sandbox path once saved. Host-internal; never sent on the wire.</summary>
        public string? SavedPath { get; internal set; }

        /// <summary>True once the document has been closed by the plugin.</summary>
        public bool Closed { get; internal set; }

        /// <summary>Token this record superseded, when produced by a reopen.</summary>
        public string? SupersededToken { get; init; }
    }

    /// <summary>Outcome of resolving a document token.</summary>
    public readonly struct OwnershipResolution
    {
        public DocumentRecord? Record { get; }
        public string ErrorCode { get; }
        public string Message { get; }
        public bool Success => Record != null;

        private OwnershipResolution(DocumentRecord? record, string errorCode, string message)
        {
            Record = record;
            ErrorCode = errorCode;
            Message = message;
        }

        public static OwnershipResolution Ok(DocumentRecord record) => new(record, ErrorCodes.None, "");
        public static OwnershipResolution Fail(string errorCode, string message) => new(null, errorCode, message);
    }

    /// <summary>
    /// Job-owned synthetic document registry and ownership policy.
    ///
    /// SAFETY MODEL — a document becomes writable ONLY by being registered here, and the
    /// only caller that registers is the plugin's own create_synthetic_document path.
    /// Consequently:
    ///   * a document the user already had open is never registered and has no token;
    ///   * MdiActiveDocument confers nothing — "active" is not "owned";
    ///   * a file name or window title confers nothing — ownership is never inferred from them;
    ///   * tokens are unguessable, bound to this plugin session, and die with it.
    ///
    /// Every write must pass <see cref="Resolve"/>, which re-checks session, job, liveness and
    /// database fingerprint. There is deliberately NO fallback to the active document.
    /// </summary>
    public sealed class DocumentOwnershipRegistry
    {
        /// <summary>Token entropy in bytes (256 bits).</summary>
        public const int TokenBytes = 32;

        private readonly object _gate = new();
        private readonly Dictionary<string, DocumentRecord> _records = new(StringComparer.Ordinal);
        private readonly string _sessionId;

        public DocumentOwnershipRegistry(string sessionId)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
                throw new ArgumentException("sessionId is required", nameof(sessionId));
            _sessionId = sessionId;
        }

        public string SessionId => _sessionId;

        public int Count
        {
            get { lock (_gate) { return _records.Count; } }
        }

        /// <summary>Cryptographically random, unguessable token. Never derived from any document property.</summary>
        public static string NewDocumentToken()
        {
            byte[] bytes = new byte[TokenBytes];
            RandomNumberGenerator.Fill(bytes);
            return Convert.ToHexString(bytes).ToLowerInvariant();
        }

        /// <summary>
        /// Register a document THIS plugin just created. There is no API to register a
        /// pre-existing or user-opened document — that is the core safety property.
        /// </summary>
        public DocumentRecord Register(
            IDocumentHandle handle, string jobId, DateTimeOffset createdAt, string creationMethod)
        {
            if (handle == null) throw new ArgumentNullException(nameof(handle));
            if (string.IsNullOrWhiteSpace(jobId)) throw new ArgumentException("jobId is required", nameof(jobId));

            var record = new DocumentRecord
            {
                DocumentToken = NewDocumentToken(),
                SessionId = _sessionId,
                JobId = jobId,
                Handle = handle,
                DatabaseFingerprint = handle.DatabaseFingerprint,
                CreatedAt = createdAt,
                Synthetic = true,
                CreationMethod = creationMethod,
            };

            lock (_gate) { _records[record.DocumentToken] = record; }
            return record;
        }

        /// <summary>
        /// Resolve a token for a write or query. Fails closed on every mismatch and NEVER
        /// falls back to the active document.
        /// </summary>
        public OwnershipResolution Resolve(string? documentToken, string requestSessionId, string requestJobId)
        {
            if (string.IsNullOrEmpty(documentToken))
                return OwnershipResolution.Fail(ErrorCodes.DocumentTokenRequired, "document_token is required");

            DocumentRecord? record;
            lock (_gate) { _records.TryGetValue(documentToken, out record); }

            // Unknown token — includes any random guess and any token from a dead session.
            if (record == null)
                return OwnershipResolution.Fail(ErrorCodes.DocumentTokenInvalid, "document_token is not registered");

            if (!string.Equals(record.SessionId, requestSessionId, StringComparison.Ordinal))
                return OwnershipResolution.Fail(
                    ErrorCodes.DocumentSessionMismatch, "document_token belongs to a different plugin session");

            if (!string.Equals(record.JobId, requestJobId, StringComparison.Ordinal))
                return OwnershipResolution.Fail(
                    ErrorCodes.DocumentJobMismatch, "document_token belongs to a different job");

            if (!record.Synthetic)
                return OwnershipResolution.Fail(
                    ErrorCodes.DocumentNotJobOwned, "target document is not a job-owned synthetic document");

            // A closed document keeps its record for reopen bookkeeping, but is not writable.
            if (record.Closed)
                return OwnershipResolution.Fail(
                    ErrorCodes.DocumentAlreadyClosed, "the owned document has been closed; reopen it first");

            if (!record.Handle.IsAlive)
                return OwnershipResolution.Fail(
                    ErrorCodes.DocumentNotJobOwned, "the owned document is no longer available");

            // Database identity must still match what was registered: guards against the
            // underlying document being swapped out beneath a still-valid token.
            if (!string.Equals(record.Handle.DatabaseFingerprint, record.DatabaseFingerprint, StringComparison.Ordinal))
                return OwnershipResolution.Fail(
                    ErrorCodes.DocumentDatabaseMismatch, "database fingerprint no longer matches the registered document");

            return OwnershipResolution.Ok(record);
        }

        /// <summary>
        /// Look up a record without the writability checks, for lifecycle bookkeeping
        /// (e.g. reading the saved path of an already-closed document before reopening).
        /// </summary>
        public DocumentRecord? Peek(string? documentToken)
        {
            if (string.IsNullOrEmpty(documentToken)) return null;
            lock (_gate) { return _records.TryGetValue(documentToken, out DocumentRecord? record) ? record : null; }
        }

        /// <summary>Record the sandbox path a document was saved to. Host-internal.</summary>
        public void RecordSaved(string documentToken, string fullPath)
        {
            lock (_gate)
            {
                if (_records.TryGetValue(documentToken, out DocumentRecord? record)) record.SavedPath = fullPath;
            }
        }

        /// <summary>
        /// Mark a document closed. The token becomes non-writable immediately but the record
        /// survives so reopen can recover the sandbox path this plugin itself chose.
        /// </summary>
        public void MarkClosed(string documentToken)
        {
            lock (_gate)
            {
                if (_records.TryGetValue(documentToken, out DocumentRecord? record)) record.Closed = true;
            }
        }

        /// <summary>
        /// Register a reopened document under a BRAND NEW token and permanently invalidate the
        /// old one, so a token can never outlive the document instance it was issued for.
        /// </summary>
        public DocumentRecord RegisterReopened(
            IDocumentHandle handle, DocumentRecord previous, DateTimeOffset reopenedAt, string savedPath)
        {
            var record = new DocumentRecord
            {
                DocumentToken = NewDocumentToken(),
                SessionId = _sessionId,
                JobId = previous.JobId,
                Handle = handle,
                DatabaseFingerprint = handle.DatabaseFingerprint,
                CreatedAt = reopenedAt,
                Synthetic = true,
                CreationMethod = "reopen_exact_sandbox_path",
                SavedPath = savedPath,
                SupersededToken = previous.DocumentToken,
            };

            lock (_gate)
            {
                // The superseded token is REMOVED, not merely flagged: a stale token must
                // resolve to DOCUMENT_TOKEN_INVALID, never to the reopened document.
                _records.Remove(previous.DocumentToken);
                _records[record.DocumentToken] = record;
            }
            return record;
        }

        /// <summary>Drop every registration. Called at plugin shutdown so no token outlives the session.</summary>
        public void Clear()
        {
            lock (_gate) { _records.Clear(); }
        }

        public IReadOnlyList<DocumentRecord> Snapshot()
        {
            lock (_gate) { return new List<DocumentRecord>(_records.Values); }
        }
    }
}
