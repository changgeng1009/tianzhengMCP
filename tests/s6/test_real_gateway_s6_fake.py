"""S6 COM gateway 的 Fake 调用契约；不会导入 pywin32 或启动 AutoCAD。"""
from __future__ import annotations

from pathlib import Path

from mcp_nextgen.backends.autocad_com_gateway import Pywin32AutoCadSandboxGateway
from mcp_nextgen.backends.real_autocad_com import DocumentOwnershipRegistry
from mcp_nextgen.s6.contracts import EntitySelector, EntitySpec


class Entity:
    def __init__(self, name, handle, parent=None, **values): self.ObjectName=name; self.Handle=handle; self.Layer="0"; self._parent=parent; self.__dict__.update(values)
    def Move(self, _base, displacement): self.InsertionPoint = tuple(displacement) if hasattr(self, "InsertionPoint") else getattr(self, "Center", (0,0,0))
    def Rotate(self, _base, angle): self.Rotation = float(angle)
    def ScaleEntity(self, _base, factor): self.Height = getattr(self, "Height", 1.0) * factor
    def Copy(self):
        copy = Entity(self.ObjectName, self.Handle + "C", self._parent, **{key:value for key,value in self.__dict__.items() if key not in {"ObjectName", "Handle", "Layer", "_parent"}})
        self._parent.append(copy); return copy
    def Delete(self): self.deleted=True


class Model(list):
    def _add(self, name, **values):
        entity=Entity(name, f"H{len(self)+1}", self, **values); self.append(entity); return entity
    def AddArc(self, center, radius, start, end): return self._add("AcDbArc", Center=tuple(center), Radius=float(radius), StartAngle=float(start), EndAngle=float(end))
    def AddLightWeightPolyline(self, points): return self._add("AcDbPolyline", Coordinates=tuple(points), Closed=False)
    def AddText(self, text, point, height): return self._add("AcDbText", TextString=text, InsertionPoint=tuple(point), Height=float(height), Rotation=0.0)
    def AddMText(self, point, width, content): return self._add("AcDbMText", TextString=content, InsertionPoint=tuple(point), Height=1.0, Width=float(width), Rotation=0.0)
    def AddLine(self, start, end): return self._add("AcDbLine", StartPoint=tuple(start), EndPoint=tuple(end))
    def AddCircle(self, center, radius): return self._add("AcDbCircle", Center=tuple(center), Radius=float(radius))
    def InsertBlock(self, point, name, x, _y, _z, rotation): return self._add("AcDbBlockReference", EffectiveName=name, InsertionPoint=tuple(point), Rotation=float(rotation), XScaleFactor=float(x))


class Collection:
    def __init__(self): self.items={}
    def Item(self, name):
        if name not in self.items: raise RuntimeError("missing")
        return self.items[name]
    def Add(self, name): self.items[name] = Block(name); return self.items[name]


class Block:
    def __init__(self, name): self.Name=name
    def AddLine(self, *_args): return object()


class Blocks(Collection):
    def Add(self, _point, name): self.items[name]=Block(name); return self.items[name]


class Document:
    def __init__(self): self.FullName=""; self.Name="Drawing1.dwg"; self.ReadOnly=False; self.ModelSpace=Model(); self.Layers=Collection(); self.TextStyles=Collection(); self.DimStyles=Collection(); self.Blocks=Blocks(); self.closed=False
    def SaveAs(self, path): self.FullName=str(path); self.Name=Path(str(path)).name
    def Save(self): pass
    def Close(self, _save): self.closed=True
    def HandleToObject(self, handle):
        for item in self.ModelSpace:
            if item.Handle == handle: return item
        raise RuntimeError("missing")


class Documents:
    def __init__(self): self.doc=None
    def Add(self): self.doc=Document(); return self.doc
    def Open(self, path, _read_only): self.doc.closed=False; assert self.doc.FullName == path; return self.doc
    @property
    def Count(self): return int(self.doc is not None and not self.doc.closed)


class App:
    def __init__(self): self.Documents=Documents()
    def Quit(self): pass


def _identity(tmp_path):
    return DocumentOwnershipRegistry(tmp_path).reserve(run_id="s6", job_id="job.1", plan_hash="a"*64, output_path=tmp_path / "sandbox" / "s6.dwg")


def test_s6_gateway_creates_queries_and_transforms_only_current_synthetic_document(tmp_path):
    identity=_identity(tmp_path); app=App(); gateway=Pywin32AutoCadSandboxGateway(application=app); gateway.create_synthetic(identity)
    line=gateway.create_s6_entity(identity, EntitySpec("line", {"start":[0,-1],"end":[5,-1]}), "line.1")
    circle=gateway.create_s6_entity(identity, EntitySpec("circle", {"center":[8,-1],"radius":2}), "circle.1")
    polyline=gateway.create_s6_entity(identity, EntitySpec("polyline", {"vertices":[[11,-2],[12,-1],[13,-2]],"closed":False}), "polyline.1")
    arc=gateway.create_s6_entity(identity, EntitySpec("arc", {"center":[0,0],"radius":3,"start_angle":0,"end_angle":1}), "arc.1")
    rectangle=gateway.create_s6_entity(identity, EntitySpec("rectangle", {"corner_a":[10,0],"corner_b":[20,10]}), "rectangle.1")
    text=gateway.create_s6_entity(identity, EntitySpec("text", {"text":"S6","insertion_point":[0,20],"height":2}), "text.1")
    mtext=gateway.create_s6_entity(identity, EntitySpec("mtext", {"content":"S6","insertion_point":[0,30],"height":2,"width":10}), "mtext.1")
    block=gateway.create_s6_entity(identity, EntitySpec("block_definition", {"name":"S6_Block","entities":[{"kind":"line"}]}), "block.def.1")
    reference=gateway.create_s6_entity(identity, EntitySpec("block_reference", {"block_name":"S6_Block","insertion_point":[30,0],"scale":1}), "block.ref.1")
    assert {item["entity_type"] for item in gateway.query_s6_entities(identity)} == {"line","circle","polyline","arc","rectangle","text","mtext","block_definition","block_reference"}
    moved=gateway.transform_s6_entity(identity, EntitySelector(handle=arc["handle"]), "MOVE_ENTITY", {"displacement":{"x":2,"y":0,"z":0}}, "move.1")
    copied=gateway.transform_s6_entity(identity, EntitySelector(handle=text["handle"]), "COPY_ENTITY", {"displacement":{"x":2,"y":0,"z":0}}, "copy.1")
    deleted=gateway.transform_s6_entity(identity, EntitySelector(handle=copied["handle"]), "DELETE_ENTITY", {}, "delete.1")
    assert moved["entity_type"] == "arc" and copied["handle"] != text["handle"] and deleted["deleted"] is True
    assert rectangle["layer"] == reference["layer"] == block["layer"] == "CADAGENT_S6_MVP"
    assert line["layer"] == circle["layer"] == polyline["layer"] == "CADAGENT_S6_MVP"


def test_s6_gateway_keeps_non_com_fake_entity_without_dynamic_import():
    entity = Entity("AcDbArc", "H1", Center=(0, 0, 0), Radius=1, StartAngle=0, EndAngle=1)
    assert Pywin32AutoCadSandboxGateway._dynamic_entity_view(entity) is entity


def test_s6_block_definition_query_requires_document_block_to_exist(tmp_path):
    identity = _identity(tmp_path); app = App(); gateway = Pywin32AutoCadSandboxGateway(application=app)
    gateway.create_synthetic(identity)
    gateway.create_s6_entity(identity, EntitySpec("block_definition", {"name":"S6_Block","entities":[{"kind":"line"}]}), "block.def.1")
    assert len(gateway.query_s6_entities(identity, EntitySelector(operation_id="block.def.1"))) == 1
    app.Documents.doc.Blocks.items.clear()
    assert gateway.query_s6_entities(identity, EntitySelector(operation_id="block.def.1")) == []


def test_s6_gateway_creates_sandbox_scoped_style_resources(tmp_path):
    identity = _identity(tmp_path); app = App(); gateway = Pywin32AutoCadSandboxGateway(application=app)
    gateway.create_synthetic(identity)
    assert gateway.ensure_s6_resource(identity, "ENSURE_LAYER", {"layer": {"name":"CADAGENT_S6_MVP", "color_index":3, "linetype":"Continuous", "lineweight":-1, "visible":True, "locked":False}})["status"] == "CREATED"
    assert gateway.ensure_s6_resource(identity, "ENSURE_TEXT_STYLE", {"text_style": {"name":"CADAGENT_S6_TEXT", "font":"txt.shx"}})["status"] == "CREATED"
    assert gateway.ensure_s6_resource(identity, "ENSURE_DIMENSION_STYLE", {"dimension_style": {"name":"CADAGENT_S6_DIM"}})["status"] == "CREATED"
