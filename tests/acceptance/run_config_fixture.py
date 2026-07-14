"""Original synthetic run configuration helpers; never real-CAD evidence."""
import json
import os


def set_parameter(monkeypatch, tmp_path, key, value):
    path = tmp_path / 'synthetic_run_config.json'
    payload = json.loads(path.read_text()) if path.exists() else {'schema_version': 1, 'parameters': {}}
    payload['parameters'][key] = value
    path.write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.setenv('TIANZHENG_RUN_CONFIG', str(path))
