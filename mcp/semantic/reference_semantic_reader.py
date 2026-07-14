import json, datetime

PIPE_DIAMETER_PATTERNS = ['DN','De','D','Φ']

def parse_pipe_labels(text):
    results = []
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        for prefix in PIPE_DIAMETER_PATTERNS:
            if prefix in line:
                results.append({'raw_text': line, 'prefix': prefix, 'source': 'pdf_text'})
                break
    return results

def run_d5_semantic():
    try:
        pdf = json.load(open('reports/phase_d3_pdf_geometry.json', encoding='utf-8'))
        text = pdf['pages'][0]['text_preview']
        labels = parse_pipe_labels(text)
        return {
            'phase': 'D5',
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_text': text,
            'detected_labels': labels,
            'label_count': len(labels),
            'keywords_found': [w for w in ['栓泵','喷泵','水泵房','大样图','1:50'] if w in text],
            'source_dwg_opened': False, 'd1_allowed': False
        }
    except Exception as e:
        return {'phase': 'D5', 'errors': [str(e)]}
