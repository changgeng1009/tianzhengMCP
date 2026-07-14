import json, os, datetime
from PyPDF2 import PdfReader

REF_PDF = r'D:\ExampleWorkspace\天正\artifacts\input\reference.pdf'

def extract_pdf_geometry(path=REF_PDF):
    if not os.path.exists(path):
        return {'phase':'D3','errors':['PDF not found: '+path]}

    reader = PdfReader(path)
    pages = []
    total_text = ''
    for i, page in enumerate(reader.pages):
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        text = page.extract_text() or ''
        total_text += text
        pages.append({
            'page_number': i+1,
            'width': w, 'height': h,
            'area': w * h,
            'text_length': len(text),
            'text_preview': text[:200] if text else '(no text)'
        })

    return {
        'phase': 'D3',
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source': path,
        'total_pages': len(pages),
        'total_text_length': len(total_text),
        'pages': pages,
        'summary': f'{len(pages)} pages, {len(total_text)} chars total text'
    }
