"""Exercise PDF extraction using an original, generated PDF, never private CAD exports."""
import json
from pathlib import Path

import pytest
from PyPDF2 import PdfWriter
from PyPDF2.generic import DictionaryObject, NameObject, DecodedStreamObject

from mcp.extraction.pdf_geometry_extractor import extract_pdf_geometry

SYNTHETIC_TEXT = "Synthetic geometry fixture - rectangle and test label"


@pytest.fixture
def synthetic_pdf(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=2100, height=3100)
    page = writer.pages[0]
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data((f'10 10 200 100 re S\nBT /F1 12 Tf 20 150 Td ({SYNTHETIC_TEXT}) Tj ET\n').encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    path = tmp_path / 'synthetic_geometry.pdf'
    with path.open('wb') as handle:
        writer.write(handle)
    return str(path)


class TestD3PDF:
    def test_extract(self, synthetic_pdf):
        result = extract_pdf_geometry(synthetic_pdf)
        assert result['total_pages'] == 1
        assert 'errors' not in result

    def test_page_dimensions(self, synthetic_pdf):
        page = extract_pdf_geometry(synthetic_pdf)['pages'][0]
        assert page['width'] == 2100
        assert page['height'] == 3100
        assert page['area'] == 6510000

    def test_text_contains_keywords(self, synthetic_pdf):
        result = extract_pdf_geometry(synthetic_pdf)
        text = result['pages'][0]['text_preview']
        assert SYNTHETIC_TEXT in text
        assert result['total_text_length'] == len(text)

    def test_report_saved(self):
        path = Path(__file__).resolve().parents[2] / 'reports/phase_d3_pdf_geometry.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        assert report['fixture_kind'] == 'original_synthetic'
        assert report['pages'][0]['text_preview'] == SYNTHETIC_TEXT
        assert report['total_text_length'] == len(SYNTHETIC_TEXT)
