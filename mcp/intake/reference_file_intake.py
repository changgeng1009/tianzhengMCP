import json, os, shutil, datetime
from pathlib import Path
from mcp.intake.file_fingerprint import fingerprint

SOURCE_DWG = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'
REF_PDF = r'D:\ExampleWorkspace\天正\artifactsreal.test.001\reference.pdf'
REF_DWG = r'D:\ExampleWorkspace\天正\artifactsreal.test.001\水泵房-模型\target.dwg'
ARTIFACTS_INPUT = r'D:\ExampleWorkspace\天正\artifacts\input'
SANDBOX_DIR = r'D:\ExampleWorkspace\天正\artifacts\sandbox'

def run_intake():
    os.makedirs(ARTIFACTS_INPUT, exist_ok=True)
    os.makedirs(SANDBOX_DIR, exist_ok=True)

    src = fingerprint(SOURCE_DWG)
    rpdf = fingerprint(REF_PDF)
    rdwg = fingerprint(REF_DWG)

    # Copy references to artifacts/input
    refs = []
    if rpdf['exists']:
        dst = os.path.join(ARTIFACTS_INPUT, 'reference.pdf')
        shutil.copy2(REF_PDF, dst)
        refs.append(fingerprint(dst))
    if rdwg['exists']:
        dst = os.path.join(ARTIFACTS_INPUT, 'reference.dwg')
        shutil.copy2(REF_DWG, dst)
        refs.append(fingerprint(dst))

    # Create sandbox copy
    sandbox_name = 'sandbox_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.dwg'
    sandbox_path = os.path.join(SANDBOX_DIR, sandbox_name)
    sandbox = None
    if src['exists']:
        shutil.copy2(SOURCE_DWG, sandbox_path)
        sandbox = fingerprint(sandbox_path)

    report = {
        'phase': 'D2', 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source': src,
        'references': [rpdf, rdwg],
        'artifacts_input': refs,
        'sandbox': sandbox,
        'sandbox_created': sandbox is not None and sandbox.get('exists'),
        'hash_match': src['sha256'] == sandbox['sha256'] if sandbox else None,
        'source_dwg_opened': False, 'source_dwg_saved': False,
        'source_modification_allowed': False, 'd1_allowed': False,
        'production_d1_allowed': False
    }

    json.dump(report, open('reports/phase_d2_reference_file_intake.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    return report

def get_manifest():
    return json.load(open('reports/phase_d2_reference_file_intake.json', encoding='utf-8')) if os.path.exists('reports/phase_d2_reference_file_intake.json') else None
