# Phase R1 - Real AutoCAD Connection Smoke Test
# LIMITED PERMISSION: connect only, no SendCommand, no DWG open, no save

import json, os, sys, traceback
from datetime import datetime, timezone

result = {
    'phase': 'R1',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'autocad_connection_attempted': True,
    'autocad_connected': False,
    'autocad_version': None,
    'autocad_visible': None,
    'documents_count': 0,
    'active_document_name': None,
    'active_document_fullname': None,
    'dwg_opened_by_script': False,
    'source_dwg_opened': False,
    'tianzheng_plumbing_path_exists': False,
    'tianzheng_hvac_path_exists': False,
    'tianzheng_loaded_signal': None,
    'bridge_initialized': False,
    'http_bridge_called': False,
    'sendcommand_used': False,
    'dwg_saved': False,
    'entity_created': False,
    'errors': [],
    'warnings': []
}

PLUMBING_PATH = r'D:\Tangent\TwtT30V1'
HVAC_PATH = r'C:\Tangent\THvacT30V1'

# Step 0: Check paths
result['tianzheng_plumbing_path_exists'] = os.path.isdir(PLUMBING_PATH)
result['tianzheng_hvac_path_exists'] = os.path.isdir(HVAC_PATH)

# Step 1: Check pywin32
try:
    import win32com.client
    result['bridge_initialized'] = True
except ImportError as e:
    result['errors'].append(f'pywin32 not found: {e}')
    result['bridge_initialized'] = False

# Step 2: Connect to AutoCAD via COM
if result['bridge_initialized']:
    try:
        acad = win32com.client.GetActiveObject("AutoCAD.Application")
        result['autocad_connected'] = True
        result['autocad_version'] = str(acad.Version)
        result['autocad_visible'] = bool(acad.Visible) if hasattr(acad, 'Visible') else None
        
        docs = acad.Documents
        result['documents_count'] = docs.Count
        
        if docs.Count > 0:
            adoc = acad.ActiveDocument
            if adoc:
                result['active_document_name'] = str(adoc.Name)
                try:
                    result['active_document_fullname'] = str(adoc.FullName)
                except:
                    result['warnings'].append('Could not read FullName')
        
        # Check Tianzheng signals
        try:
            caption = str(acad.Caption or '')
            if '天正' in caption or 'T30' in caption or 'TWT' in caption.upper():
                result['tianzheng_loaded_signal'] = 'caption_match'
                result['warnings'].append(f'Caption contains Tianzheng: {caption[:80]}')
        except:
            pass

        # Check SupportPath
        try:
            prefs = acad.Preferences
            sp = str(prefs.Files.SupportPath or '')
            if 'tangent' in sp.lower() or 'twt' in sp.lower():
                result['tianzheng_loaded_signal'] = result['tianzheng_loaded_signal'] or 'support_path_match'
        except:
            pass

    except Exception as e:
        result['errors'].append(f'COM connection failed: {e}')
        result['autocad_connected'] = False

print(json.dumps(result, ensure_ascii=False, indent=2))
