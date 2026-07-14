import hashlib, os, time, json
from pathlib import Path

def fingerprint(path):
    if not os.path.exists(path):
        return {'path': path, 'exists': False, 'error': 'not_found'}
    st = os.stat(path)
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk: break
            sha.update(chunk)
    return {
        'path': str(path), 'exists': True,
        'size': st.st_size,
        'mtime': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(st.st_mtime)),
        'sha256': sha.hexdigest(),
        'extension': os.path.splitext(path)[1].lower()
    }

def verify(source_hash, target_path):
    if not os.path.exists(target_path): return False
    return fingerprint(target_path)['sha256'] == source_hash
