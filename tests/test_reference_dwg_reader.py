from __future__ import annotations

from tests.test_cad_reader import FakeDocument, FakeLineEntity, FakeManager


def test_reference_cad_model_can_load_from_reader_output():
    from reference.dwg_reader import ReferenceDWGReader
    from reference.reference_cad_model import ReferenceCADModel

    result = ReferenceDWGReader(FakeManager(FakeDocument([FakeLineEntity()]))).read_reference_document()
    model = ReferenceCADModel.from_dict(result["model"])

    assert result["success"] is True
    assert model.source["kind"] == "reference_dwg"
    assert model.entities[0]["source"] == "reference_dwg"
    assert model.entities[0]["type"] == "line"


def test_reference_reader_can_read_explicit_document_without_switching_autocad():
    from reference.dwg_reader import ReferenceDWGReader

    document = FakeDocument([FakeLineEntity()])
    result = ReferenceDWGReader(FakeManager(document)).read_document(document, source_kind="reference_dwg")

    assert result["model"]["source"]["active_document"] == "reader-test.dwg"
    assert result["model"]["entities"][0]["handle"] == "L1"
