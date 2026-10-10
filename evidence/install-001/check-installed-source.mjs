import { Client } from './native-stage/native-build/node_modules/@modelcontextprotocol/client/dist/index.mjs';
import { StdioClientTransport } from './native-stage/native-build/node_modules/@modelcontextprotocol/client/dist/stdio.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
const root='/Users/kola/codex-fusion';
const cache='/Users/kola/.codex/plugins/cache/fusion-local/fusion-minimal/0.3.0';
const evidence=root+'/evidence/install-001';
const config=JSON.parse(await readFile(cache+'/mcp.json','utf8')).mcpServers.fusion;
const expand=value=>value.replaceAll('${PLUGIN_ROOT}',cache);
const before=await readFile(root+'/.fusion/selection.json');
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const client=new Client({name:'fusion-installed-package-check',version:'0.3.0'});
const transport=new StdioClientTransport({command:config.command,args:config.args.map(expand),cwd:expand(config.cwd),stderr:'pipe'});
let original, changed=false, expectedRevision, outcome={installed_cache:cache,model_calls:0,thread_starts:0,
  native_ui_verified:false,desktop_daemon_connection_verified:false};
async function call(name,args={}) {
 const data=await client.callTool({name,arguments:args});
 if(data.isError)throw Error(data.content[0].text);
 return data;
}
try {
 await client.connect(transport,{timeout:15000});
 outcome.process_pid=transport.pid;
 outcome.startup='Installed command expanded and stdio handshake completed';
 const tools=await client.listTools();
 outcome.tools=tools.tools.map(x=>x.name);assert.equal(outcome.tools.length,7);
 outcome.capabilities=client.getServerCapabilities();
 const settings=(await call('fusion.settings_read')).structuredContent;
 original=settings.values;
 await writeFile(evidence+'/settings-read.json',JSON.stringify(settings,null,2)+'\n');
 const resource=await client.readResource({uri:'ui://fusion-minimal/model-desk-v3'});
 outcome.resource={uri:resource.contents[0].uri,mimeType:resource.contents[0].mimeType,
   metadata:resource.contents[0]._meta,html_sha256:digest(resource.contents[0].text)};
 const opening=await call('fusion.open');
 assert.equal(opening._meta['fusion/state'].saved.document.selection.worker.model,JSON.parse(before).selection.worker.model);
 outcome.opener_returns_shared_state=true;
 const alternative=settings.schema.properties.worker.enum.find(x=>x!==original.worker && x.startsWith(original.worker.split(' / ')[0]+' / '));
 assert.ok(alternative);
 await call('fusion.settings_update',{set:{worker:alternative}});changed=true;
 const updated=(await call('fusion.state')).structuredContent;
 assert.equal(updated.saved.document.selection.worker.model+' / '+updated.saved.document.selection.worker.reasoning_effort,alternative);
 outcome.save_and_readback=true;
 outcome.temporary_test_value=alternative;
 await call('fusion.settings_update',{set:original});changed=false;
 const restored=(await call('fusion.state')).structuredContent;
 expectedRevision=restored.saved.revision;
 assert.deepEqual((await call('fusion.settings_read')).structuredContent.values,original);
 outcome.logical_restore=true;
 outcome.status='passed';
} catch(error) {outcome.status='failed';outcome.error=String(error);}
finally {
 if(changed && original){await call('fusion.settings_update',{set:original});expectedRevision=(await call('fusion.state')).structuredContent.saved.revision;}
 await client.close();
 outcome.process_closed_after_verification=true;
 // Restore exact pre-test bytes, guarded by the same cross-process lock and revision.
 if(expectedRevision) {
  const restore=`import sys,hashlib,os,tempfile\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom fusion_selection import StorageLock\np=Path(sys.argv[2]); backup=Path(sys.argv[3])\nwith StorageLock(p.parent):\n assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[4], 'Concurrent change; refusing restore'\n fd,name=tempfile.mkstemp(prefix='.restore-',dir=p.parent)\n with os.fdopen(fd,'wb') as f:f.write(backup.read_bytes());f.flush();os.fsync(f.fileno())\n os.replace(name,p)\n`;
  execFileSync(config.command,['-B','-c',restore,cache+'/skills/fusion/scripts',root+'/.fusion/selection.json',
     evidence+'/selection-before.json',expectedRevision]);
 }
 outcome.selection_bytes_restored=digest(await readFile(root+'/.fusion/selection.json'))===digest(before);
 await writeFile(evidence+'/installed-mcp-check.json',JSON.stringify(outcome,null,2)+'\n');
 console.log(JSON.stringify(outcome));
}
