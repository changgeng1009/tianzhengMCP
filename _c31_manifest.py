import json, os, hashlib, time

FILES = {
    'plumbing': {
        'pgp': r'D:\Tangent\TwtT30V1\sys\acad.pgp',
        'tmn_tch': r'D:\Tangent\TwtT30V1\sys\TCH.TMN',
        'tmn_out': r'D:\Tangent\TwtT30V1\sys\OUT.TMN',
        'cuix': r'D:\Tangent\TwtT30V1\sys\tangent.cuix',
        'cuix13': r'D:\Tangent\TwtT30V1\sys\tangent13.cuix',
    },
    'hvac': {
        'pgp': r'C:\Tangent\THvacT30V1\sys\acad.pgp',
        'tmn_tch': r'C:\Tangent\THvacT30V1\sys\TCH.TMN',
        'cuix': r'C:\Tangent\THvacT30V1\sys\tangent.cuix',
        'cuix13': r'C:\Tangent\THvacT30V1\sys\tangent13.cuix',
    }
}

manifest = []
for domain, paths in FILES.items():
    for source_type, path in paths.items():
        if not os.path.exists(path):
            continue
        st = os.stat(path)
        sha = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk: break
                sha.update(chunk)
        manifest.append({
            'path': path, 'domain': domain, 'source_type': source_type,
            'size': st.st_size,
            'mtime': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(st.st_mtime)),
            'sha256': sha.hexdigest(),
            'read_only': True, 'executed': False, 'loaded': False
        })

for domain, base in [('plumbing', r'D:\Tangent\TwtT30V1\Lisp'), ('hvac', r'C:\Tangent\THvacT30V1\Lisp')]:
    if not os.path.isdir(base): continue
    for fn in sorted(os.listdir(base)):
        if not fn.lower().endswith('.lsp'): continue
        path = os.path.join(base, fn)
        st = os.stat(path)
        sha = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk: break
                sha.update(chunk)
        manifest.append({
            'path': path, 'domain': domain, 'source_type': 'lsp',
            'size': st.st_size,
            'mtime': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(st.st_mtime)),
            'sha256': sha.hexdigest(),
            'read_only': True, 'executed': False, 'loaded': False
        })

pd = sum(1 for m in manifest if m['domain']=='plumbing')
hd = sum(1 for m in manifest if m['domain']=='hvac')
print('Manifest files:', len(manifest), 'P:', pd, 'H:', hd)
for m in manifest:
    print('  [%s] %s: %s sz=%d sha=%s...' % (m['domain'], m['source_type'], os.path.basename(m['path']), m['size'], m['sha256'][:16]))

result = {
    'phase': 'C3.1', 'total_files': len(manifest),
    'by_domain': {'plumbing': pd, 'hvac': hd},
    'all_read_only': True, 'any_executed': False, 'any_loaded': False,
    'files': manifest
}
with open('command_registry/local_discovery_manifest.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print('MANIFEST_SAVED')
