using System.Text.Json;
using TianzhengCadPlugin.Protocol;
using Xunit;

namespace TianzhengCadPlugin.Tests
{
    public class GeometryValidationTests
    {
        private static JsonElement Json(string raw)
        {
            using JsonDocument document = JsonDocument.Parse(raw);
            return document.RootElement.Clone();
        }

        // ---------- points ----------

        [Fact]
        public void Parses_object_and_array_point_forms_identically()
        {
            Point3 fromObject = Geometry.ParsePoint(Json("""{"p":{"x":1,"y":2,"z":3}}"""), "p");
            Point3 fromArray = Geometry.ParsePoint(Json("""{"p":[1,2,3]}"""), "p");

            Assert.Equal(fromObject.X, fromArray.X);
            Assert.Equal(fromObject.Y, fromArray.Y);
            Assert.Equal(fromObject.Z, fromArray.Z);
        }

        [Fact]
        public void Point_z_defaults_to_zero()
        {
            Assert.Equal(0.0, Geometry.ParsePoint(Json("""{"p":{"x":1,"y":2}}"""), "p").Z);
            Assert.Equal(0.0, Geometry.ParsePoint(Json("""{"p":[1,2]}"""), "p").Z);
        }

        [Theory]
        [InlineData("""{"p":{"x":"a","y":2}}""")]
        [InlineData("""{"p":{"y":2}}""")]
        [InlineData("""{"p":[1]}""")]
        [InlineData("""{"p":[1,2,3,4]}""")]
        [InlineData("""{"p":"nope"}""")]
        [InlineData("""{"p":{"x":1e400,"y":2}}""")]
        public void Rejects_malformed_points(string raw)
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ParsePoint(Json(raw), "p"));
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        [Fact]
        public void Rejects_coordinates_beyond_the_synthetic_limit()
        {
            var ex = Assert.Throws<GeometryValidationException>(
                () => Geometry.ParsePoint(Json("""{"p":{"x":200000,"y":0}}"""), "p"));
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        // ---------- layer ----------

        [Theory]
        [InlineData("S7_ENTITY_MVP")]
        [InlineData("CADAGENT_S6_MVP")]
        [InlineData("_private.layer-1$")]
        public void Accepts_valid_layer_names(string name)
            => Assert.Equal(name, Geometry.ValidateLayerName(name));

        [Theory]
        [InlineData("")]
        [InlineData("  ")]
        [InlineData("1leading-digit")]
        [InlineData("has space")]
        [InlineData("C:\\path\\layer")]
        [InlineData("../traversal")]
        [InlineData("layer/with/slash")]
        public void Rejects_invalid_layer_names(string name)
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidateLayerName(name));
            Assert.Equal(ErrorCodes.InvalidLayer, ex.ErrorCode);
        }

        [Theory]
        [InlineData("0")]
        [InlineData("Defpoints")]
        [InlineData("defpoints")]
        public void Rejects_reserved_layers(string name)
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidateLayerName(name));
            Assert.Equal(ErrorCodes.InvalidLayer, ex.ErrorCode);
        }

        [Theory]
        [InlineData("""{"layer":"L","color_index":0}""")]
        [InlineData("""{"layer":"L","color_index":256}""")]
        [InlineData("""{"layer":"L","color_index":"red"}""")]
        public void Rejects_invalid_color_index(string raw)
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidateColorIndex(Json(raw)));
            Assert.Equal(ErrorCodes.InvalidLayer, ex.ErrorCode);
        }

        [Fact]
        public void Color_index_defaults_to_7()
            => Assert.Equal(7, Geometry.ValidateColorIndex(Json("""{"layer":"L"}""")));

        // ---------- line ----------

        [Fact]
        public void Accepts_a_valid_line()
        {
            (Point3 start, Point3 end) = Geometry.ValidateLine(
                Json("""{"start":{"x":0,"y":0},"end":{"x":100,"y":50}}"""));

            Assert.Equal(0.0, start.X);
            Assert.Equal(100.0, end.X);
            Assert.Equal(50.0, end.Y);
        }

        [Fact]
        public void Rejects_a_degenerate_line()
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidateLine(
                Json("""{"start":{"x":5,"y":5},"end":{"x":5,"y":5}}""")));
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        // ---------- circle ----------

        [Fact]
        public void Accepts_a_valid_circle()
        {
            (Point3 center, double radius) = Geometry.ValidateCircle(
                Json("""{"center":{"x":10,"y":20},"radius":42.5}"""));

            Assert.Equal(10.0, center.X);
            Assert.Equal(42.5, radius);
        }

        [Theory]
        [InlineData(-1.0)]
        [InlineData(-0.000001)]
        [InlineData(0.0)]
        public void Rejects_non_positive_radius(double radius)
        {
            string raw = $$"""{"center":{"x":0,"y":0},"radius":{{radius}}}""";
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidateCircle(Json(raw)));
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        [Fact]
        public void Rejects_radius_at_or_below_tolerance()
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidateCircle(
                Json("""{"center":{"x":0,"y":0},"radius":1e-12}""")));
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        // ---------- polyline ----------

        [Fact]
        public void Accepts_a_valid_polyline()
        {
            (var vertices, bool closed) = Geometry.ValidatePolyline(
                Json("""{"vertices":[[0,0],[10,0],[10,10]],"closed":true}"""));

            Assert.Equal(3, vertices.Count);
            Assert.True(closed);
            Assert.Equal(10.0, vertices[2].Y);
        }

        [Fact]
        public void Polyline_closed_defaults_to_false()
        {
            (_, bool closed) = Geometry.ValidatePolyline(Json("""{"vertices":[[0,0],[1,1]]}"""));
            Assert.False(closed);
        }

        [Theory]
        [InlineData("""{"vertices":[]}""")]
        [InlineData("""{"vertices":[[0,0]]}""")]
        [InlineData("""{"vertices":"nope"}""")]
        [InlineData("""{}""")]
        public void Rejects_polyline_with_too_few_vertices(string raw)
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidatePolyline(Json(raw)));
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }

        [Fact]
        public void Rejects_polyline_vertex_with_bad_coordinate()
        {
            var ex = Assert.Throws<GeometryValidationException>(() => Geometry.ValidatePolyline(
                Json("""{"vertices":[[0,0],[999999,0]]}""")));
            Assert.Equal(ErrorCodes.InvalidGeometry, ex.ErrorCode);
        }
    }
}
