using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using TianzhengCadPlugin.Transport;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

namespace TianzhengCadPlugin
{
    /// <summary>
    /// Concrete <see cref="IDocumentHandle"/> wrapping a real AutoCAD Document.
    ///
    /// The ownership registry only ever compares <see cref="DatabaseFingerprint"/> and checks
    /// <see cref="IsAlive"/>; it never dereferences the Document. That separation is what lets
    /// the ownership policy be unit-tested without AutoCAD.
    /// </summary>
    internal sealed class AutoCadDocumentHandle : IDocumentHandle
    {
        private readonly Document _document;
        private readonly string _fingerprint;

        public AutoCadDocumentHandle(Document document, string fingerprint)
        {
            _document = document ?? throw new ArgumentNullException(nameof(document));
            _fingerprint = fingerprint;
        }

        /// <summary>Live fingerprint read back from the database on every access.</summary>
        public string DatabaseFingerprint
        {
            get
            {
                try
                {
                    Database? db = _document.Database;
                    return db == null || db.IsDisposed ? "" : db.FingerprintGuid.ToString();
                }
                catch (Exception) { return ""; }
            }
        }

        /// <summary>Fingerprint captured at registration time.</summary>
        public string RegisteredFingerprint => _fingerprint;

        public bool IsAlive
        {
            get
            {
                try
                {
                    Database? db = _document.Database;
                    return db != null && !db.IsDisposed && !_document.IsDisposed;
                }
                catch (Exception) { return false; }
            }
        }

        /// <summary>Host-internal access. Never exposed over the protocol.</summary>
        internal Document Document => _document;
    }

    /// <summary>
    /// Creates blank, synthetic, job-owned documents.
    ///
    /// MUST be called on the AutoCAD main thread. It never opens a user DWG/DXF, never takes a
    /// caller-supplied path, and never adopts an existing document: the only thing it does is
    /// ask AutoCAD for a NEW blank drawing.
    ///
    /// Template note: AutoCAD's DocumentCollection.Add requires a template NAME, which AutoCAD
    /// resolves from its own configured template folder. We pass only Autodesk's standard
    /// default template names (and prefer the empty/default form), never an arbitrary local
    /// .dwt/.dwg path. The resulting drawing is therefore Autodesk-standard-blank, which the
    /// stage brief explicitly permits provided it is documented — as it is here and in the
    /// `creation_method` field returned to the client.
    /// </summary>
    internal static class AutoCadDocumentFactory
    {
        /// <summary>Tried in order; the first that yields a document wins.</summary>
        private static readonly string[] TemplateCandidates = { "", "acadiso.dwt", "acad.dwt" };

        internal readonly struct CreationOutcome
        {
            public Document? Document { get; init; }
            public string Fingerprint { get; init; }
            public string CreationMethod { get; init; }
            public string FailureDetail { get; init; }
            public bool Success => Document != null;
        }

        /// <summary>Create a new blank drawing. Main thread only.</summary>
        public static CreationOutcome CreateBlankDocument()
        {
            DocumentCollection documents = AcApp.DocumentManager;
            string lastFailure = "no template candidate succeeded";

            foreach (string template in TemplateCandidates)
            {
                try
                {
                    Document document = documents.Add(template);
                    if (document?.Database == null)
                    {
                        lastFailure = "DocumentManager.Add returned no database";
                        continue;
                    }

                    string fingerprint = document.Database.FingerprintGuid.ToString();
                    return new CreationOutcome
                    {
                        Document = document,
                        Fingerprint = fingerprint,
                        CreationMethod = template.Length == 0
                            ? "DocumentManager.Add(default_template)"
                            : $"DocumentManager.Add({template})",
                    };
                }
                catch (Exception ex)
                {
                    // Record only the exception type: no path, no Autodesk stack.
                    lastFailure = ex.GetType().Name;
                }
            }

            return new CreationOutcome { FailureDetail = lastFailure };
        }
    }
}
