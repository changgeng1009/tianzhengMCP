using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace TianzhengCadPlugin.Protocol
{
    /// <summary>Raised when an operation payload fails geometry/layer validation.</summary>
    public sealed class GeometryValidationException : Exception
    {
        public string ErrorCode { get; }

        public GeometryValidationException(string errorCode, string message) : base(message)
            => ErrorCode = errorCode;
    }

    /// <summary>Backend-neutral 3D point. Mirrors the S6 Point3 shape (x, y, z).</summary>
    public readonly struct Point3
    {
        [JsonPropertyName("x")] public double X { get; }
        [JsonPropertyName("y")] public double Y { get; }
        [JsonPropertyName("z")] public double Z { get; }

        public Point3(double x, double y, double z)
        {
            X = x;
            Y = y;
            Z = z;
        }

        public Dictionary<string, double> ToDictionary() =>
            new() { ["x"] = X, ["y"] = Y, ["z"] = Z };

        public override string ToString() => FormattableString.Invariant($"({X},{Y},{Z})");
    }

    /// <summary>
    /// Geometry validation shared by single operations and batch operations.
    ///
    /// Deliberately strict and fail-closed: NaN, Infinity, out-of-range coordinates,
    /// degenerate lines, non-positive radii and short polylines are all rejected BEFORE any
    /// AutoCAD transaction is opened, so an invalid request can never reach the CAD API.
    /// </summary>
    public static class Geometry
    {
        /// <summary>Synthetic coordinate bound, matching the S6 contract's limit.</summary>
        public const double CoordinateLimit = 100_000.0;

        /// <summary>Absolute tolerance below which a length/radius counts as degenerate.</summary>
        public const double Tolerance = 1e-9;

        /// <summary>Maximum vertices accepted for one polyline.</summary>
        public const int MaxPolylineVertices = 10_000;

        private static readonly Regex LayerNameRegex =
            new(@"^[A-Za-z_][A-Za-z0-9_.$-]{0,63}$", RegexOptions.Compiled);

        /// <summary>Layer names AutoCAD reserves or that must never be targeted.</summary>
        private static readonly HashSet<string> ForbiddenLayers =
            new(StringComparer.OrdinalIgnoreCase) { "0", "Defpoints" };

        /// <summary>Read a required numeric property from <paramref name="parent"/> and validate it.</summary>
        public static double FiniteProperty(JsonElement parent, string name)
        {
            if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out JsonElement element))
                throw new GeometryValidationException(ErrorCodes.InvalidGeometry, $"missing '{name}'");
            return Finite(element, name);
        }

        /// <summary>Validate a numeric element: finite, in range, not NaN/Infinity.</summary>
        public static double Finite(JsonElement element, string name)
        {
            if (element.ValueKind != JsonValueKind.Number || !element.TryGetDouble(out double value))
                throw new GeometryValidationException(ErrorCodes.InvalidGeometry, $"'{name}' must be a number");
            if (double.IsNaN(value) || double.IsInfinity(value))
                throw new GeometryValidationException(ErrorCodes.InvalidGeometry, $"'{name}' must be finite");
            if (Math.Abs(value) > CoordinateLimit)
                throw new GeometryValidationException(
                    ErrorCodes.InvalidGeometry,
                    $"'{name}' exceeds the synthetic coordinate limit {CoordinateLimit}");
            return value;
        }

        /// <summary>Parse a point from {"x":..,"y":..,"z":..} (z optional) or [x,y] / [x,y,z].</summary>
        public static Point3 ParsePoint(JsonElement parent, string name)
        {
            if (!parent.TryGetProperty(name, out JsonElement element))
                throw new GeometryValidationException(ErrorCodes.InvalidGeometry, $"missing '{name}'");
            return ParsePointElement(element, name);
        }

        public static Point3 ParsePointElement(JsonElement element, string name)
        {
            if (element.ValueKind == JsonValueKind.Object)
            {
                double x = FiniteProperty(element, "x");
                double y = FiniteProperty(element, "y");
                double z = element.TryGetProperty("z", out JsonElement zEl) && zEl.ValueKind != JsonValueKind.Null
                    ? Finite(zEl, "z")
                    : 0.0;
                return new Point3(x, y, z);
            }

            if (element.ValueKind == JsonValueKind.Array)
            {
                int length = element.GetArrayLength();
                if (length is not (2 or 3))
                    throw new GeometryValidationException(
                        ErrorCodes.InvalidGeometry, $"'{name}' array must hold 2 or 3 numbers");

                var values = new double[3];
                int index = 0;
                foreach (JsonElement item in element.EnumerateArray())
                {
                    values[index] = Finite(item, $"{name}[{index}]");
                    index++;
                }
                return new Point3(values[0], values[1], length == 3 ? values[2] : 0.0);
            }

            throw new GeometryValidationException(
                ErrorCodes.InvalidGeometry, $"'{name}' must be an object or array");
        }

        /// <summary>Validate a layer name. Rejects reserved layers and path-like input.</summary>
        public static string ValidateLayerName(string? layer)
        {
            if (string.IsNullOrWhiteSpace(layer))
                throw new GeometryValidationException(ErrorCodes.InvalidLayer, "layer name is required");

            string trimmed = layer.Trim();
            if (!LayerNameRegex.IsMatch(trimmed))
                throw new GeometryValidationException(
                    ErrorCodes.InvalidLayer, "layer name contains unsupported characters");
            if (ForbiddenLayers.Contains(trimmed))
                throw new GeometryValidationException(
                    ErrorCodes.InvalidLayer, $"layer '{trimmed}' is reserved and must not be targeted");

            return trimmed;
        }

        public static string RequireLayer(JsonElement parameters)
        {
            if (!parameters.TryGetProperty("layer", out JsonElement element) ||
                element.ValueKind != JsonValueKind.String)
            {
                throw new GeometryValidationException(ErrorCodes.InvalidLayer, "'layer' must be a string");
            }
            return ValidateLayerName(element.GetString());
        }

        public static int ValidateColorIndex(JsonElement parameters)
        {
            if (!parameters.TryGetProperty("color_index", out JsonElement element) ||
                element.ValueKind == JsonValueKind.Null)
            {
                return 7; // AutoCAD default (white/black)
            }
            if (element.ValueKind != JsonValueKind.Number || !element.TryGetInt32(out int color))
                throw new GeometryValidationException(ErrorCodes.InvalidLayer, "'color_index' must be an integer");
            if (color is < 1 or > 255)
                throw new GeometryValidationException(ErrorCodes.InvalidLayer, "'color_index' must be 1-255");
            return color;
        }

        // ---- Structural parsing (plan time). Shape/type/range only, no semantics. ----

        /// <summary>Parse line endpoints. Does NOT check for degeneracy.</summary>
        public static (Point3 Start, Point3 End) ParseLine(JsonElement parameters) =>
            (ParsePoint(parameters, "start"), ParsePoint(parameters, "end"));

        /// <summary>Parse circle centre/radius. Does NOT check that the radius is positive.</summary>
        public static (Point3 Center, double Radius) ParseCircle(JsonElement parameters) =>
            (ParsePoint(parameters, "center"), FiniteProperty(parameters, "radius"));

        /// <summary>Parse polyline vertices. Does NOT check the vertex count.</summary>
        public static (List<Point3> Vertices, bool Closed) ParsePolyline(JsonElement parameters)
        {
            if (!parameters.TryGetProperty("vertices", out JsonElement vertices) ||
                vertices.ValueKind != JsonValueKind.Array)
            {
                throw new GeometryValidationException(ErrorCodes.InvalidGeometry, "'vertices' must be an array");
            }

            if (vertices.GetArrayLength() > MaxPolylineVertices)
                throw new GeometryValidationException(
                    ErrorCodes.InvalidGeometry, $"polyline exceeds {MaxPolylineVertices} vertices");

            var points = new List<Point3>(vertices.GetArrayLength());
            int index = 0;
            foreach (JsonElement item in vertices.EnumerateArray())
            {
                points.Add(ParsePointElement(item, $"vertices[{index}]"));
                index++;
            }

            bool closed = parameters.TryGetProperty("closed", out JsonElement closedEl)
                          && closedEl.ValueKind == JsonValueKind.True;

            return (points, closed);
        }

        // ---- Combined parse + semantic validation (used directly by tests). ----

        /// <summary>Line: start and end must differ by more than the tolerance.</summary>
        public static (Point3 Start, Point3 End) ValidateLine(JsonElement parameters)
        {
            Point3 start = ParsePoint(parameters, "start");
            Point3 end = ParsePoint(parameters, "end");

            double dx = end.X - start.X, dy = end.Y - start.Y, dz = end.Z - start.Z;
            if (Math.Sqrt((dx * dx) + (dy * dy) + (dz * dz)) <= Tolerance)
                throw new GeometryValidationException(
                    ErrorCodes.InvalidGeometry, "line start and end are coincident");

            return (start, end);
        }

        /// <summary>Circle: radius must exceed the geometry tolerance (rejects 0 and negatives).</summary>
        public static (Point3 Center, double Radius) ValidateCircle(JsonElement parameters)
        {
            Point3 center = ParsePoint(parameters, "center");
            double radius = FiniteProperty(parameters, "radius");

            if (radius <= Tolerance)
                throw new GeometryValidationException(
                    ErrorCodes.InvalidGeometry, "circle radius must be greater than the geometry tolerance");

            return (center, radius);
        }

        /// <summary>Polyline: at least 2 vertices, each finite and in range.</summary>
        public static (List<Point3> Vertices, bool Closed) ValidatePolyline(JsonElement parameters)
        {
            if (!parameters.TryGetProperty("vertices", out JsonElement vertices) ||
                vertices.ValueKind != JsonValueKind.Array)
            {
                throw new GeometryValidationException(ErrorCodes.InvalidGeometry, "'vertices' must be an array");
            }

            int count = vertices.GetArrayLength();
            if (count < 2)
                throw new GeometryValidationException(
                    ErrorCodes.InvalidGeometry, "polyline requires at least 2 vertices");
            if (count > MaxPolylineVertices)
                throw new GeometryValidationException(
                    ErrorCodes.InvalidGeometry, $"polyline exceeds {MaxPolylineVertices} vertices");

            var points = new List<Point3>(count);
            int index = 0;
            foreach (JsonElement item in vertices.EnumerateArray())
            {
                points.Add(ParsePointElement(item, $"vertices[{index}]"));
                index++;
            }

            bool closed = parameters.TryGetProperty("closed", out JsonElement closedEl)
                          && closedEl.ValueKind == JsonValueKind.True;

            return (points, closed);
        }

        /// <summary>Stable, culture-invariant rendering used in evidence output.</summary>
        public static string Format(double value) =>
            value.ToString("G17", CultureInfo.InvariantCulture);
    }
}
