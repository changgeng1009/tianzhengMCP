using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using TianzhengCadPlugin.Protocol;
using Exception = System.Exception;

namespace TianzhengCadPlugin
{
    /// <summary>A previously committed idempotency record read back from the drawing.</summary>
    internal sealed class IdempotencyRecord
    {
        public required string Key { get; init; }
        public required string PlanHash { get; init; }
        public required List<string> Handles { get; init; }
        public required int CreatedCount { get; init; }
    }

    /// <summary>
    /// Persistent idempotency, stored INSIDE the drawing database.
    ///
    /// WHY IN-DOCUMENT: an in-memory dictionary cannot survive save → close → reopen, so it
    /// could never prove real idempotency. Records live in the Named Objects Dictionary under
    /// a plugin-private key, so they are written into the DWG itself and come back on reopen.
    ///
    /// WHY ATOMIC: <see cref="Write"/> is called with the SAME transaction that created the
    /// entities. Entities and the idempotency record therefore commit together or abort
    /// together — it is structurally impossible for a rolled-back batch to leave behind a
    /// record claiming success.
    ///
    /// Layout:
    ///   NamedObjectsDictionary
    ///     └── TIANZHENG_S7_IDEMPOTENCY        (DBDictionary)
    ///           └── &lt;idempotency_key&gt;   (Xrecord)
    ///                 [0] Text  = plan_hash
    ///                 [1] Int32 = created_count
    ///                 [2..] Text = entity handles
    ///
    /// The dictionary uses a plugin-private, namespaced name and never touches user entities
    /// or well-known public keys.
    /// </summary>
    internal static class IdempotencyStore
    {
        /// <summary>Plugin-private NOD key. Namespaced to avoid collision with any other app.</summary>
        public const string DictionaryName = "TIANZHENG_S7_IDEMPOTENCY";

        private const int PlanHashCode = 1;   // DxfCode.Text
        private const int CountCode = 90;     // DxfCode.Int32
        private const int HandleCode = 3;     // DxfCode.Text (secondary)

        /// <summary>
        /// Look up a key. Returns null when this document has never committed it.
        /// Read-only: never creates the dictionary.
        /// </summary>
        public static IdempotencyRecord? TryRead(Transaction transaction, Database database, string key)
        {
            if (string.IsNullOrEmpty(key)) return null;

            try
            {
                var namedObjects = (DBDictionary)transaction.GetObject(
                    database.NamedObjectsDictionaryId, OpenMode.ForRead);

                if (!namedObjects.Contains(DictionaryName)) return null;

                var store = (DBDictionary)transaction.GetObject(
                    namedObjects.GetAt(DictionaryName), OpenMode.ForRead);

                if (!store.Contains(key)) return null;

                var record = (Xrecord)transaction.GetObject(store.GetAt(key), OpenMode.ForRead);
                if (record.Data == null) return null;

                string planHash = "";
                int createdCount = 0;
                var handles = new List<string>();

                foreach (TypedValue value in record.Data)
                {
                    switch (value.TypeCode)
                    {
                        case PlanHashCode:
                            planHash = value.Value?.ToString() ?? "";
                            break;
                        case CountCode:
                            createdCount = Convert.ToInt32(value.Value);
                            break;
                        case HandleCode:
                            string handle = value.Value?.ToString() ?? "";
                            if (handle.Length > 0) handles.Add(handle);
                            break;
                    }
                }

                return new IdempotencyRecord
                {
                    Key = key,
                    PlanHash = planHash,
                    Handles = handles,
                    CreatedCount = createdCount,
                };
            }
            catch (Exception)
            {
                // A malformed or unreadable store must never be treated as "already applied".
                return null;
            }
        }

        /// <summary>
        /// Record a committed batch. MUST be called with the same transaction that created
        /// the entities, so the record and the entities share one commit boundary.
        /// </summary>
        public static void Write(
            Transaction transaction,
            Database database,
            string key,
            string planHash,
            IReadOnlyList<string> handles,
            int createdCount)
        {
            if (string.IsNullOrEmpty(key)) return;

            var namedObjects = (DBDictionary)transaction.GetObject(
                database.NamedObjectsDictionaryId, OpenMode.ForWrite);

            DBDictionary store;
            if (namedObjects.Contains(DictionaryName))
            {
                store = (DBDictionary)transaction.GetObject(
                    namedObjects.GetAt(DictionaryName), OpenMode.ForWrite);
            }
            else
            {
                store = new DBDictionary();
                namedObjects.SetAt(DictionaryName, store);
                transaction.AddNewlyCreatedDBObject(store, true);
            }

            var buffer = new ResultBuffer(
                new TypedValue(PlanHashCode, planHash),
                new TypedValue(CountCode, createdCount));
            foreach (string handle in handles)
            {
                if (!string.IsNullOrEmpty(handle)) buffer.Add(new TypedValue(HandleCode, handle));
            }

            var entry = new Xrecord { Data = buffer };

            // SetAt replaces an existing entry; for a fresh key it adds one.
            store.SetAt(key, entry);
            transaction.AddNewlyCreatedDBObject(entry, true);
        }
    }
}
