using System;
using System.Collections.Concurrent;
using System.Collections.Generic;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>Log categories required by the S7 logging contract.</summary>
    public static class LogCategory
    {
        public const string Transport = "transport";
        public const string Authentication = "authentication";
        public const string Validation = "validation";
        public const string Scheduling = "scheduling";
        public const string Document = "document";
        public const string Transaction = "transaction";
        public const string Entity = "entity";
        public const string Save = "save";
        public const string Persistence = "persistence";
        public const string Idempotency = "idempotency";
        public const string Shutdown = "shutdown";
    }

    public readonly struct LogEntry
    {
        public DateTimeOffset Timestamp { get; init; }
        public string Category { get; init; }
        public string Level { get; init; }
        public string Message { get; init; }
        public override string ToString() =>
            $"{Timestamp:O} [{Level}] [{Category}] {Message}";
    }

    /// <summary>
    /// Minimal in-memory, category-tagged log. Callers must pass already-sanitized text:
    /// tokens are redacted via <see cref="TokenAuthenticator.Redact"/> and full user file
    /// paths / drawing content are never written here.
    /// </summary>
    public sealed class PluginLog
    {
        private readonly ConcurrentQueue<LogEntry> _entries = new();
        private readonly int _maxEntries;

        public PluginLog(int maxEntries = 2000) => _maxEntries = maxEntries;

        public void Write(string category, string level, string message)
        {
            _entries.Enqueue(new LogEntry
            {
                Timestamp = DateTimeOffset.UtcNow,
                Category = category,
                Level = level,
                Message = message,
            });
            while (_entries.Count > _maxEntries && _entries.TryDequeue(out _)) { }
        }

        public void Info(string category, string message) => Write(category, "INFO", message);
        public void Warn(string category, string message) => Write(category, "WARN", message);
        public void Error(string category, string message) => Write(category, "ERROR", message);

        public IReadOnlyList<LogEntry> Snapshot() => new List<LogEntry>(_entries);
    }
}
