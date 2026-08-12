using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    /// <summary>
    /// Guards the S8.2 operation boundary.
    ///
    /// The whole point of the Tianzheng surface is that a caller sends structured pipe
    /// parameters and can never send a command. These tests pin that contract at the protocol
    /// layer, where it is cheap to check and expensive to violate by accident.
    ///
    /// The pipe query/signature logic itself lives in the AutoCAD-linked assembly and is
    /// covered by the Python decision tests plus the opt-in integration run.
    /// </summary>
    public class TianzhengOperationSurfaceTests
    {
        private static readonly string[] TianzhengOperations =
        {
            OperationType.TianzhengCreatePipe,
            OperationType.TianzhengQueryPipe,
            OperationType.TianzhengValidatePipeIdentity,
            OperationType.TianzhengPipeInventory,
        };

        [Fact]
        public void TianzhengOperationsAreOnTheAcceptedWhitelist()
        {
            foreach (string operation in TianzhengOperations)
                Assert.True(OperationType.IsKnown(operation), operation);
        }

        [Fact]
        public void UnknownTianzhengLookingOperationsAreStillRejected()
        {
            // A near-miss name must not slip through just because it starts with "tianzheng_".
            Assert.False(OperationType.IsKnown("tianzheng_run_command"));
            Assert.False(OperationType.IsKnown("tianzheng_send_command"));
            Assert.False(OperationType.IsKnown("tianzheng_execute_lisp"));
            Assert.False(OperationType.IsKnown("tianzheng_create_valve"));
        }

        [Fact]
        public void NoOperationNameExposesACommandExecutionSurface()
        {
            string[] forbidden = { "run_command", "send_command", "sendcommand", "lisp", "keystroke", "hzgx" };

            foreach (string operation in OperationType.All)
            {
                foreach (string bad in forbidden)
                    Assert.False(operation.ToLowerInvariant().Contains(bad),
                        $"operation '{operation}' exposes '{bad}'");
            }
        }

        [Fact]
        public void TianzhengOperationsAreNotClaimedAsImplementedInTheS71AStage()
        {
            // The S7.1-A read-only stage predates all of this; nothing here belongs to it.
            foreach (string operation in TianzhengOperations)
                Assert.False(OperationType.IsImplementedInStage(operation), operation);
        }

        [Fact]
        public void EveryTianzhengErrorCodeIsDistinctAndNamespaced()
        {
            List<string> codes = typeof(TianzhengErrorCodes)
                .GetFields(BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy)
                .Where(f => f.IsLiteral && f.FieldType == typeof(string))
                .Select(f => (string)f.GetRawConstantValue()!)
                .ToList();

            Assert.NotEmpty(codes);
            Assert.Equal(codes.Count, codes.Distinct().Count());
            foreach (string code in codes)
                Assert.StartsWith("TIANZHENG_", code);
        }

        [Fact]
        public void FailureModesAreDistinguishableRatherThanOneGenericFailure()
        {
            // Callers must be able to tell "not found" from "not native" from "save broke".
            Assert.NotEqual(TianzhengErrorCodes.PipeNotFound, TianzhengErrorCodes.NativeIdentityMismatch);
            Assert.NotEqual(TianzhengErrorCodes.SaveFailed, TianzhengErrorCodes.ReopenFailed);
            Assert.NotEqual(TianzhengErrorCodes.PersistenceFailed, TianzhengErrorCodes.IdempotencyConflict);
            Assert.NotEqual(TianzhengErrorCodes.PropertyUnavailable, TianzhengErrorCodes.PipeNotFound);
        }
    }
}
