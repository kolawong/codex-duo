"""Apply only reviewed files after checking for concurrent source edits."""
from pathlib import Path
import hashlib
import json
import shutil

STAGE = Path(__file__).resolve().parent
ROOT = Path('/Users/kola/codex-fusion')
plan = json.loads((STAGE/'evidence/deploy-plan.json').read_text())
for name in plan['files']:
    target = ROOT/name
    actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
    if actual != plan['expected_source'][name]:
        raise RuntimeError('Concurrent source change: '+name)
evidence = ROOT/'evidence/update-031'
evidence.mkdir(exist_ok=False)
for name in plan['files']:
    target = ROOT/name
    if target.exists():
        backup = evidence/'before-source'/name
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(target,backup)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(STAGE/name,target)
for name in ['before.json','deploy-plan.json','package.json','sdk-client.json','tests-031.log','static-031.log']:
    shutil.copy2(STAGE/'evidence'/name,evidence/name)
shutil.copy2(STAGE/'evidence/current/static-validation.json',evidence/'static-validation.json')
shutil.copy2(STAGE/'fusion-minimal-0.3.1.zip',ROOT/'fusion-minimal-0.3.1.zip')
print(json.dumps({'updated_files':plan['files'],'evidence':str(evidence),'version':'0.3.1'}))
