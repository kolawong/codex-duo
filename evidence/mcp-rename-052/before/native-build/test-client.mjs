import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { mkdtemp, rm, readFile, mkdir, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=await realpath(await mkdtemp(path.join(tmpdir(),'fusion-sdk-test-')));
const client=new Client({name:'fusion-conformance-test',version:'0.4.0'});
try {
 const pluginRoot=path.join(root,'plugins/fusion-minimal');
 const config=JSON.parse(await readFile(path.join(pluginRoot,'mcp.json'),'utf8')).mcpServers.fusion;
 const args=config.args.map(x=>x.replaceAll('${PLUGIN_ROOT}',pluginRoot));
 args[args.indexOf('--project-root')+1]=temp;
 await client.connect(new StdioClientTransport({command:config.command,args,cwd:pluginRoot}));
 const tools=await client.listTools();assert.equal(tools.tools.length,9);
 const res=await client.readResource({uri:'ui://fusion-minimal/model-desk-v4'});
 assert.equal(res.contents[0].mimeType,'text/html;profile=mcp-app');
 const settings=await client.callTool({name:'fusion.settings_read',arguments:{}});
 assert.ok(settings.structuredContent.values.coordinator);
 const saved=await client.callTool({name:'fusion.settings_update',arguments:{set:{worker:'gpt-6-luna / high'}}});
 assert.equal(saved.isError,undefined);
 const state=(await client.callTool({name:'fusion.state',arguments:{}})).structuredContent;
 const prepared=(await client.callTool({name:'fusion.prepare',arguments:{task:state.task_template,expected_revision:state.saved.revision}})).structuredContent;
 const plan=(await client.callTool({name:'fusion.execution_plan',arguments:{handoff_id:prepared.id}})).structuredContent;
 assert.equal(plan.execution_started,false);
 const configured=await client.callTool({name:'fusion.settings_update',arguments:{set:{activation:'automatic_project',max_worker_turns:'3'}}});
 assert.equal(configured.isError,undefined);
 const defaults=(await client.callTool({name:'fusion.defaults',arguments:{project_root:temp}})).structuredContent;
 assert.equal(defaults.workflow.activation,'automatic_project');
 const begun=(await client.callTool({name:'fusion.begin',arguments:{project_root:temp,task:state.task_template,invocation:'automatic'}})).structuredContent;
 assert.equal(begun.state,'ready_for_native_worker');
 assert.equal(begun.coordinator.requires_new_task,false);
 assert.equal(begun.execution_started,false);
 const bad=await client.callTool({name:'fusion.settings_update',arguments:{set:{worker:'gpt-6-luna / ultra'}}});
 assert.equal(bad.isError,true);
 const other=path.join(temp,'other project');await mkdir(other);
 const otherState=(await client.callTool({name:'fusion.state',arguments:{project_root:other}})).structuredContent;
 assert.equal(otherState.project_root,other);
 assert.equal(otherState.saved.document,null);
 const otherSaved=await client.callTool({name:'fusion.save',arguments:{project_root:other,selection:state.default,
   workflow:{activation:'automatic_project',coordinator_mode:'current_thread',max_worker_turns:2},expected_revision:'none',enable_project:true}});
 assert.equal(otherSaved.structuredContent.project_opt_in.enabled,true);
 assert.ok((await readFile(path.join(other,'AGENTS.md'),'utf8')).includes('codex-duo:begin'));
 const original=(await client.callTool({name:'fusion.state',arguments:{}})).structuredContent;
 assert.equal(original.project_root,temp,'omitted root never follows most recent explicit project');
 const cross=await client.callTool({name:'fusion.execution_plan',arguments:{project_root:other,handoff_id:prepared.id}});
 assert.equal(cross.isError,true,'handoff lookup cannot cross project roots');
 const stored=JSON.parse(await readFile(path.join(temp,'.fusion/selection.json'),'utf8'));
 assert.equal(stored.selection.worker.reasoning_effort,'high');
 console.log(JSON.stringify({status:'passed',sdk:'@modelcontextprotocol/client 2.3.1',
  checks:['stdio handshake','tool schema discovery','resource read','structured settings read/update',
   'shared saved state','persistent workflow defaults','automatic task adapter','handoff snapshot','execution adapter without execution','invalid effort error','stateless multi-project reads/saves','explicit AGENTS opt-in','cross-project handoff isolation'],model_calls:0}));
} finally {await client.close();await rm(temp,{recursive:true,force:true});}
