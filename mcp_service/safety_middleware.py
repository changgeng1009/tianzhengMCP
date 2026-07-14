"""H0 Safety Middleware."""
import os
FORBIDDEN = ['TSaveAs','tgbatplots','dcsz']
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'
def check(tool): return (tool not in FORBIDDEN, 'Forbidden' if tool in FORBIDDEN else 'OK')
def check_path(p): return (os.path.normpath(p).lower() != os.path.normpath(SOURCE).lower(), 'Source blocked')
