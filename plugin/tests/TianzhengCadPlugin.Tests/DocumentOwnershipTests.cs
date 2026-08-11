using System;
using System.Text.RegularExpressions;
using TianzhengCadPlugin.Protocol;
using TianzhengCadPlugin.Transport;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// Ownership POLICY tests. These run without AutoCAD because the policy only ever
    /// compares an opaque IDocumentHandle's identity — it never dereferences a Document.
    ///
    /// These prove the ownership RULES. They do NOT prove that a real DocumentLock or
    /// Transaction works; that requires the real-AutoCAD stage and is never claimed here.
    /// </summary>
    public class DocumentOwnershipTests
    {
        private sealed class FakeHandle : IDocumentHandle
        {
            public string DatabaseFingerprint { get; set; } = "fingerprint-A";
            public bool IsAlive { get; set; } = true;
        }

        private const string Session = "session-1";
        private const string Job = "job-1";

        private static (DocumentOwnershipRegistry registry, DocumentRecord record, FakeHandle handle) NewRegistry()
        {
            var registry = new DocumentOwnershipRegistry(Session);
            var handle = new FakeHandle();
            DocumentRecord record = registry.Register(handle, Job, DateTimeOffset.UtcNow, "test");
            return (registry, record, handle);
        }

        // ---------- token format ----------

        [Fact]
        public void Token_is_256_bit_lowercase_hex()
        {
            string token = DocumentOwnershipRegistry.NewDocumentToken();

            Assert.Equal(64, token.Length); // 32 bytes -> 64 hex chars
            Assert.Matches(new Regex("^[0-9a-f]{64}$"), token);
        }

        [Fact]
        public void Tokens_are_unique_and_unguessable_across_registrations()
        {
            var seen = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < 200; i++)
                Assert.True(seen.Add(DocumentOwnershipRegistry.NewDocumentToken()), "token collision");
        }

        [Fact]
        public void Token_is_not_derived_from_any_document_property()
        {
            // Two registrations of handles with the SAME fingerprint must still get
            // different tokens — proving the token is random, not derived.
            var registry = new DocumentOwnershipRegistry(Session);
            DocumentRecord first = registry.Register(new FakeHandle(), Job, DateTimeOffset.UtcNow, "test");
            DocumentRecord second = registry.Register(new FakeHandle(), Job, DateTimeOffset.UtcNow, "test");

            Assert.NotEqual(first.DocumentToken, second.DocumentToken);
        }

        // ---------- registry state ----------

        [Fact]
        public void Registration_records_full_ownership_state()
        {
            (_, DocumentRecord record, _) = NewRegistry();

            Assert.Equal(Session, record.SessionId);
            Assert.Equal(Job, record.JobId);
            Assert.Equal("fingerprint-A", record.DatabaseFingerprint);
            Assert.True(record.Synthetic);
            Assert.NotEqual(default, record.CreatedAt);
            Assert.Equal("test", record.CreationMethod);
        }

        [Fact]
        public void Registry_starts_empty_so_no_preexisting_document_is_owned()
        {
            // The decisive safety property: a user's already-open drawing is never
            // registered, because registration only happens via plugin creation.
            var registry = new DocumentOwnershipRegistry(Session);

            Assert.Equal(0, registry.Count);
            Assert.False(registry.Resolve("any-token", Session, Job).Success);
        }

        [Fact]
        public void Resolve_succeeds_for_a_correctly_owned_document()
        {
            (DocumentOwnershipRegistry registry, DocumentRecord record, _) = NewRegistry();

            OwnershipResolution resolution = registry.Resolve(record.DocumentToken, Session, Job);

            Assert.True(resolution.Success);
            Assert.Equal(record.DocumentToken, resolution.Record!.DocumentToken);
        }

        // ---------- rejection paths ----------

        [Fact]
        public void Missing_token_is_rejected()
        {
            (DocumentOwnershipRegistry registry, _, _) = NewRegistry();

            Assert.Equal(ErrorCodes.DocumentTokenRequired, registry.Resolve(null, Session, Job).ErrorCode);
            Assert.Equal(ErrorCodes.DocumentTokenRequired, registry.Resolve("", Session, Job).ErrorCode);
        }

        [Fact]
        public void Unknown_random_token_is_rejected()
        {
            (DocumentOwnershipRegistry registry, _, _) = NewRegistry();

            OwnershipResolution resolution = registry.Resolve(
                DocumentOwnershipRegistry.NewDocumentToken(), Session, Job);

            Assert.False(resolution.Success);
            Assert.Equal(ErrorCodes.DocumentTokenInvalid, resolution.ErrorCode);
        }

        [Fact]
        public void Session_mismatch_is_rejected()
        {
            (DocumentOwnershipRegistry registry, DocumentRecord record, _) = NewRegistry();

            OwnershipResolution resolution = registry.Resolve(record.DocumentToken, "other-session", Job);

            Assert.False(resolution.Success);
            Assert.Equal(ErrorCodes.DocumentSessionMismatch, resolution.ErrorCode);
        }

        [Fact]
        public void Job_mismatch_is_rejected()
        {
            (DocumentOwnershipRegistry registry, DocumentRecord record, _) = NewRegistry();

            OwnershipResolution resolution = registry.Resolve(record.DocumentToken, Session, "other-job");

            Assert.False(resolution.Success);
            Assert.Equal(ErrorCodes.DocumentJobMismatch, resolution.ErrorCode);
        }

        [Fact]
        public void Stale_token_from_a_previous_plugin_session_is_rejected()
        {
            // Session 1 issues a token, then the plugin restarts: a fresh registry has no
            // record of it, so the old token cannot drive the new session.
            (_, DocumentRecord oldRecord, _) = NewRegistry();
            var restarted = new DocumentOwnershipRegistry("session-2");

            OwnershipResolution resolution = restarted.Resolve(oldRecord.DocumentToken, "session-2", Job);

            Assert.False(resolution.Success);
            Assert.Equal(ErrorCodes.DocumentTokenInvalid, resolution.ErrorCode);
        }

        [Fact]
        public void Dead_document_is_rejected()
        {
            (DocumentOwnershipRegistry registry, DocumentRecord record, FakeHandle handle) = NewRegistry();
            handle.IsAlive = false;

            OwnershipResolution resolution = registry.Resolve(record.DocumentToken, Session, Job);

            Assert.False(resolution.Success);
            Assert.Equal(ErrorCodes.DocumentNotJobOwned, resolution.ErrorCode);
        }

        [Fact]
        public void Database_fingerprint_change_is_rejected()
        {
            // Guards against the document being swapped beneath a still-valid token.
            (DocumentOwnershipRegistry registry, DocumentRecord record, FakeHandle handle) = NewRegistry();
            handle.DatabaseFingerprint = "fingerprint-B";

            OwnershipResolution resolution = registry.Resolve(record.DocumentToken, Session, Job);

            Assert.False(resolution.Success);
            Assert.Equal(ErrorCodes.DocumentDatabaseMismatch, resolution.ErrorCode);
        }

        [Fact]
        public void Clear_invalidates_every_token()
        {
            (DocumentOwnershipRegistry registry, DocumentRecord record, _) = NewRegistry();
            registry.Clear();

            Assert.Equal(0, registry.Count);
            Assert.Equal(ErrorCodes.DocumentTokenInvalid,
                registry.Resolve(record.DocumentToken, Session, Job).ErrorCode);
        }

        [Fact]
        public void Registry_exposes_no_api_to_adopt_an_existing_document()
        {
            // Compile-time-ish guarantee expressed as a test: the only mutator that adds a
            // record is Register(IDocumentHandle,...), which the host calls exclusively from
            // its create-synthetic-document path. There is no AdoptActive/RegisterExisting.
            var methods = typeof(DocumentOwnershipRegistry).GetMethods();
            foreach (var method in methods)
            {
                Assert.DoesNotContain("Adopt", method.Name, StringComparison.OrdinalIgnoreCase);
                Assert.DoesNotContain("Active", method.Name, StringComparison.OrdinalIgnoreCase);
                Assert.DoesNotContain("Existing", method.Name, StringComparison.OrdinalIgnoreCase);
            }
        }
    }
}
