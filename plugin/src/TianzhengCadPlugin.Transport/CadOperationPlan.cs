using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TianzhengCadPlugin.Protocol;

namespace TianzhengCadPlugin.Transport
{
    /// <summary>
    /// One structurally-parsed operation ready for main-thread execution.
    ///
    /// TWO-PHASE VALIDATION.
    ///  * Plan time (transport thread): structure only — field presence, JSON types, finite
    ///    numbers, coordinate range, layer-name syntax. Malformed input is rejected before a
    ///    lock or transaction is ever taken.
    ///  * Execution time (main thread, INSIDE the transaction): <see cref="ValidateSemantics"/>
    ///    — degenerate line, non-positive radius, too-few vertices.
    ///
    /// Semantic checks deliberately run inside the transaction so that a failing operation
    /// aborts a real AutoCAD transaction and discards entities created by earlier operations
    /// in the same batch. That is what makes all_or_nothing demonstrable rather than merely
    /// asserted: a pre-pass that rejected the batch before opening a transaction could never
    /// prove rollback. The CAD API is still never handed a bad value, because the check runs
    /// immediately before the entity is constructed.
    /// </summary>
    public sealed class PlannedOperation
    {
        public required int Index { get; init; }
        public required string OperationId { get; init; }
        public required string OperationType { get; init; }
        public required string Layer { get; init; }

        public int ColorIndex { get; init; } = 7;
        public Point3 Start { get; init; }
        public Point3 End { get; init; }
        public Point3 Center { get; init; }
        public double Radius { get; init; }
        public IReadOnlyList<Point3> Vertices { get; init; } = Array.Empty<Point3>();
        public bool Closed { get; init; }

        /// <summary>
        /// Execution-time semantic validation. Throws <see cref="GeometryValidationException"/>,
        /// which the executor turns into an operation failure and therefore a batch abort.
        /// </summary>
        public void ValidateSemantics()
        {
            switch (OperationType)
            {
                case Protocol.OperationType.CreateLine:
                {
                    double dx = End.X - Start.X, dy = End.Y - Start.Y, dz = End.Z - Start.Z;
                    if (Math.Sqrt((dx * dx) + (dy * dy) + (dz * dz)) <= Geometry.Tolerance)
                        throw new GeometryValidationException(
                            ErrorCodes.InvalidGeometry, "line start and end are coincident");
                    break;
                }

                case Protocol.OperationType.CreateCircle:
                    if (Radius <= Geometry.Tolerance)
                        throw new GeometryValidationException(
                            ErrorCodes.InvalidGeometry, "circle radius must be greater than the geometry tolerance");
                    break;

                case Protocol.OperationType.CreatePolyline:
                    if (Vertices.Count < 2)
                        throw new GeometryValidationException(
                            ErrorCodes.InvalidGeometry, "polyline requires at least 2 vertices");
                    if (Vertices.Count > Geometry.MaxPolylineVertices)
                        throw new GeometryValidationException(
                            ErrorCodes.InvalidGeometry, $"polyline exceeds {Geometry.MaxPolylineVertices} vertices");
                    break;
            }
        }
    }

    /// <summary>A validated batch, bound to exactly one owned document.</summary>
    public sealed class CadOperationPlan
    {
        public required string BatchId { get; init; }
        public required string DocumentToken { get; init; }
        public required IReadOnlyList<PlannedOperation> Operations { get; init; }

        /// <summary>
        /// Deterministic hash of the batch PAYLOAD (operation types, layers, geometry) —
        /// deliberately excluding batch id and document token, which vary between otherwise
        /// identical replays.
        ///
        /// Computed by the plugin from the parsed operations rather than trusted from the
        /// wire, so a caller cannot present the same idempotency key with a different payload
        /// and have it accepted: the recomputed hash will differ and the batch is refused
        /// with IDEMPOTENCY_CONFLICT.
        /// </summary>
        public string ComputePlanHash()
        {
            var builder = new StringBuilder();
            foreach (PlannedOperation op in Operations)
            {
                builder.Append(op.OperationType).Append('|')
                       .Append(op.Layer).Append('|')
                       .Append(op.ColorIndex).Append('|')
                       .Append(Fmt(op.Start)).Append('|')
                       .Append(Fmt(op.End)).Append('|')
                       .Append(Fmt(op.Center)).Append('|')
                       .Append(op.Radius.ToString("G17", CultureInfo.InvariantCulture)).Append('|')
                       .Append(op.Closed ? '1' : '0').Append('|');
                foreach (Point3 vertex in op.Vertices) builder.Append(Fmt(vertex)).Append(',');
                builder.Append(';');
            }

            byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(builder.ToString()));
            return Convert.ToHexString(digest).ToLowerInvariant();
        }

        private static string Fmt(Point3 point) => string.Create(
            CultureInfo.InvariantCulture,
            $"{point.X:G17}/{point.Y:G17}/{point.Z:G17}");
    }

    /// <summary>Parse failure carrying the offending operation index.</summary>
    public sealed class PlanParseException : Exception
    {
        public string ErrorCode { get; }
        public int OperationIndex { get; }
        public string OperationId { get; }

        public PlanParseException(string errorCode, string message, int operationIndex, string operationId)
            : base(message)
        {
            ErrorCode = errorCode;
            OperationIndex = operationIndex;
            OperationId = operationId;
        }
    }

    /// <summary>
    /// Turns request JSON into a validated <see cref="CadOperationPlan"/>.
    ///
    /// Runs entirely on the transport thread and touches no AutoCAD API. Because every
    /// operation is fully validated here, the main-thread executor can open its transaction
    /// knowing the payload is already well-formed — invalid input never reaches the CAD API.
    /// </summary>
    public static class CadOperationPlanner
    {
        /// <summary>Operations that create geometry or resources inside a batch.</summary>
        public static readonly IReadOnlySet<string> BatchableOperations = new HashSet<string>
        {
            OperationType.CreateLayer,
            OperationType.CreateLine,
            OperationType.CreateCircle,
            OperationType.CreatePolyline,
        };

        public const int MaxBatchOperations = 256;

        /// <summary>Build a single-operation plan (create_layer / create_line / ...).</summary>
        public static CadOperationPlan PlanSingle(PluginRequest request, string documentToken)
        {
            PlannedOperation operation = ParseOperation(
                request.OperationType, request.Parameters, index: 0, operationId: request.OperationId);

            return new CadOperationPlan
            {
                BatchId = request.RequestId,
                DocumentToken = documentToken,
                Operations = new List<PlannedOperation> { operation },
            };
        }

        /// <summary>Build a multi-operation plan from batch_execute parameters.</summary>
        public static CadOperationPlan PlanBatch(PluginRequest request, string documentToken)
        {
            JsonElement parameters = request.Parameters;

            if (!parameters.TryGetProperty("operations", out JsonElement operations) ||
                operations.ValueKind != JsonValueKind.Array)
            {
                throw new PlanParseException(
                    ErrorCodes.MissingField, "'operations' must be an array", -1, request.OperationId);
            }

            int count = operations.GetArrayLength();
            if (count == 0)
                throw new PlanParseException(
                    ErrorCodes.MissingField, "batch must contain at least one operation", -1, request.OperationId);
            if (count > MaxBatchOperations)
                throw new PlanParseException(
                    ErrorCodes.InvalidFieldType, $"batch exceeds {MaxBatchOperations} operations", -1, request.OperationId);

            // A batch declaring a mode other than all_or_nothing is refused rather than
            // silently downgraded — S7.2 offers exactly one transaction semantic.
            if (parameters.TryGetProperty("transaction_mode", out JsonElement modeEl) &&
                modeEl.ValueKind == JsonValueKind.String &&
                !string.Equals(modeEl.GetString(), "all_or_nothing", StringComparison.Ordinal))
            {
                throw new PlanParseException(
                    ErrorCodes.InvalidFieldType,
                    "only transaction_mode 'all_or_nothing' is supported", -1, request.OperationId);
            }

            var planned = new List<PlannedOperation>(count);
            int index = 0;
            var seenIds = new HashSet<string>(StringComparer.Ordinal);

            foreach (JsonElement item in operations.EnumerateArray())
            {
                string operationId = $"{request.OperationId}.{index}";

                if (item.ValueKind != JsonValueKind.Object)
                    throw new PlanParseException(
                        ErrorCodes.InvalidFieldType, "each operation must be an object", index, operationId);

                if (item.TryGetProperty("operation_id", out JsonElement idEl) &&
                    idEl.ValueKind == JsonValueKind.String)
                {
                    operationId = idEl.GetString() ?? operationId;
                }

                if (!seenIds.Add(operationId))
                    throw new PlanParseException(
                        ErrorCodes.InvalidFieldType, "duplicate operation_id in batch", index, operationId);

                if (!item.TryGetProperty("operation_type", out JsonElement typeEl) ||
                    typeEl.ValueKind != JsonValueKind.String)
                {
                    throw new PlanParseException(
                        ErrorCodes.MissingField, "operation_type is required", index, operationId);
                }

                string operationType = typeEl.GetString() ?? "";
                if (!BatchableOperations.Contains(operationType))
                    throw new PlanParseException(
                        ErrorCodes.UnknownOperation,
                        $"operation_type '{Truncate(operationType)}' cannot appear in a batch", index, operationId);

                JsonElement opParameters = item.TryGetProperty("parameters", out JsonElement p) &&
                                           p.ValueKind == JsonValueKind.Object
                    ? p
                    : default;

                if (opParameters.ValueKind != JsonValueKind.Object)
                    throw new PlanParseException(
                        ErrorCodes.MissingField, "operation parameters are required", index, operationId);

                planned.Add(ParseOperation(operationType, opParameters, index, operationId));
                index++;
            }

            return new CadOperationPlan
            {
                BatchId = request.RequestId,
                DocumentToken = documentToken,
                Operations = planned,
            };
        }

        private static PlannedOperation ParseOperation(
            string operationType, JsonElement parameters, int index, string operationId)
        {
            try
            {
                string layer = Geometry.RequireLayer(parameters);

                switch (operationType)
                {
                    case OperationType.CreateLayer:
                        return new PlannedOperation
                        {
                            Index = index,
                            OperationId = operationId,
                            OperationType = operationType,
                            Layer = layer,
                            ColorIndex = Geometry.ValidateColorIndex(parameters),
                        };

                    // Structural parsing only. Semantic checks (degenerate line, non-positive
                    // radius, vertex count) run in PlannedOperation.ValidateSemantics() inside
                    // the transaction, so a failure aborts a real transaction.
                    case OperationType.CreateLine:
                    {
                        (Point3 start, Point3 end) = Geometry.ParseLine(parameters);
                        return new PlannedOperation
                        {
                            Index = index,
                            OperationId = operationId,
                            OperationType = operationType,
                            Layer = layer,
                            Start = start,
                            End = end,
                        };
                    }

                    case OperationType.CreateCircle:
                    {
                        (Point3 center, double radius) = Geometry.ParseCircle(parameters);
                        return new PlannedOperation
                        {
                            Index = index,
                            OperationId = operationId,
                            OperationType = operationType,
                            Layer = layer,
                            Center = center,
                            Radius = radius,
                        };
                    }

                    case OperationType.CreatePolyline:
                    {
                        (List<Point3> vertices, bool closed) = Geometry.ParsePolyline(parameters);
                        return new PlannedOperation
                        {
                            Index = index,
                            OperationId = operationId,
                            OperationType = operationType,
                            Layer = layer,
                            Vertices = vertices,
                            Closed = closed,
                        };
                    }

                    default:
                        throw new PlanParseException(
                            ErrorCodes.UnknownOperation,
                            $"operation_type '{Truncate(operationType)}' is not an entity operation",
                            index, operationId);
                }
            }
            catch (GeometryValidationException ex)
            {
                throw new PlanParseException(ex.ErrorCode, ex.Message, index, operationId);
            }
        }

        private static string Truncate(string value) =>
            value.Length > 40 ? value[..40] + "..." : value;
    }
}
