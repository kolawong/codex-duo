from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path('/Users/kola/codex-fusion')
EVIDENCE=ROOT/'evidence/update-031'
CACHE=Path('/Users/kola/.codex/plugins/cache/fusion-local/fusion-minimal/0.3.1')
CLI='/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data): (EVIDENCE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def inventory(p): return {str(x.relative_to(p)):sha(x) for x in p.rglob('*') if x.is_file() and '__pycache__' not in x.parts}
source=inventory(ROOT/'plugins/fusion-minimal'); cached=inventory(CACHE)
assert source==cached
save('installed-cache.json',{'path':str(CACHE),'matches_source':True,'files':cached})
for action in ['plugin','mcp']:
    run=subprocess.run([CLI,action,'list','--json'],cwd=ROOT,capture_output=True,text=True,timeout=20)
    data=json.loads(run.stdout)
    if action=='plugin': data=data['installed']
    save(action+'-list.json',{'exit_code':run.returncode,'fusion':[x for x in data if 'fusion' in x.get('name','')],
         'other_identities':[{k:x.get(k) for k in ['name','version','enabled']} for x in data if 'fusion' not in x.get('name','')],
         'stderr':run.stderr})
before=json.loads((EVIDENCE/'before.json').read_text())
global_before=before['protected']['/Users/kola/.codex/config.toml']
check=subprocess.run(['python3','-B','tools/validate_static.py','--installed','--global-config-sha256',global_before],
    cwd=ROOT,capture_output=True,text=True,timeout=20)
(EVIDENCE/'canonical-static.log').write_text(check.stdout+check.stderr)
assert check.returncode==0
server=json.loads((CACHE/'mcp.json').read_text())['mcpServers']['fusion']
args=[x.replace('${PLUGIN_ROOT}',str(CACHE)) for x in server['args']]
requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
          {'jsonrpc':'2.0','method':'notifications/initialized'},
          {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},
          {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'fusion.settings_read','arguments':{}}}]
result=subprocess.run([server['command'],*args],cwd=CACHE,capture_output=True,text=True,
    input=''.join(json.dumps(x)+'\n' for x in requests),timeout=20)
responses=[json.loads(line) for line in result.stdout.splitlines()]
assert result.returncode==0 and responses[0]['result']['serverInfo']['version']=='0.3.1'
assert len(responses[1]['result']['tools'])==7
assert not responses[2]['result'].get('isError')
save('installed-handshake.json',{'exit_code':result.returncode,'responses':responses,
     'model_calls':0,'settings_writes':0,'note':'Independent process; not desktop host discovery.'})
protected={p:sha(Path(p))==h for p,h in before['protected'].items()}
assert all(protected.values())
allowed=set(json.loads((EVIDENCE/'deploy-plan.json').read_text())['files'])
unexpected=[p for p,h in before['source'].items() if p not in allowed and sha(ROOT/p)!=h]
assert not unexpected
save('preservation.json',{'protected_hashes_match':protected,'unexpected_source_changes':unexpected,
    'global_config_sha256':sha(Path('/Users/kola/.codex/config.toml'))})
save('runtime-observation.json',{'fusion_tools':[],'mcp_apps_backend_available':True,'mcp_app_tabs':[],
    'native_ui_verified':False,'host_discovery_verified':False})
print(json.dumps({'version':'0.3.1','cache_matches':True,'independent_tools':7,'settings_read':True,
    'protected_unchanged':all(protected.values()),'host_discovery_verified':False}))
