import os, time, hashlib

SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

def verify_not_source(path):
    return os.path.normpath(path).lower() != os.path.normpath(SOURCE).lower()

def hash_file(path):
    if not os.path.exists(path): return None
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk: break
            sha.update(chunk)
    return sha.hexdigest()

def safe_save(doc, sandbox_path, max_retries=3):
    if not verify_not_source(sandbox_path):
        return {'save_success':False,'error':'REJECTED_SOURCE_PATH'}

    fstat_before = {'mtime':os.path.getmtime(sandbox_path),'size':os.path.getsize(sandbox_path)} if os.path.exists(sandbox_path) else None

    for attempt in range(1, max_retries+1):
        try:
            time.sleep(0.5)
            doc.Save()
            time.sleep(1.0)
            if os.path.exists(sandbox_path):
                ns = os.path.getsize(sandbox_path)
                nm = os.path.getmtime(sandbox_path)
                return {
                    'save_success':True,
                    'retry_count':attempt,
                    'file_mtime_before':fstat_before['mtime'] if fstat_before else None,
                    'file_mtime_after':nm,
                    'file_size_before':fstat_before['size'] if fstat_before else None,
                    'file_size_after':ns,
                    'save_called_on_sandbox':True,
                    'save_called_on_source':False
                }
        except Exception as e:
            if attempt == max_retries:
                return {
                    'save_success':False,
                    'save_retry_count':attempt,
                    'save_errors':[str(e)[:100]],
                    'save_called_on_sandbox':False,
                    'save_called_on_source':False,
                    'needs_manual_save':True
                }
    return {'save_success':False,'needs_manual_save':True}
