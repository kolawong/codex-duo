import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=await mkdtemp(path.join(tmpdir(),'fusion-sdk-test-'));
const client=new Client({name:'fusion-conformance-test',version:'0.3.1'});
try {
 const pluginRoot=path.join(root,'plugins/fusion-minimal');
 const config=JSON.parse(await readFile(path.join(pluginRoot,'mcp.json'),'utf8')).mcpServers.fusion;
 const args=config.args.map(x=>x.replaceAll('${PLUGIN_ROOT}',pluginRoot));
 args[args.indexOf('--project-root')+1]=temp;
 await client.connect(new StdioClientTransport({command:config.command,args,cwd:pluginRoot}));
 const tools=await client.listTools();assert.equal(tools.tools.length,7);
 const res=await client.readResource({uri:'ui://fusion-minimal/model-desk-v3'});
 assert.equal(res.contents[0].mimeType,'text/html;profile=mcp-app');
 const settings=await client.callTool({name:'fusion.settings_read',arguments:{}});
 assert.ok(settings.structuredContent.values.coordinator);
 const saved=await client.callTool({name:'fusion.settings_update',arguments:{set:{worker:'gpt-6-luna / high'}}});
 assert.equal(saved.isError,undefined);
 const state=(await client.callTool({name:'fusion.state',arguments:{}})).structuredContent;
 const prepared=(await client.callTool({name:'fusion.prepare',arguments:{task:state.task_template,expected_revision:state.saved.revision}})).structuredContent;
 const plan=(await client.callTool({name:'fusion.execution_plan',arguments:{handoff_id:prepared.id}})).structuredContent;
 assert.equal(plan.execution_started,false);
 const bad=await client.callTool({name:'fusion.settings_update',arguments:{set:{worker:'gpt-6-luna / ultra'}}});
 assert.equal(bad.isError,true);
 const stored=JSON.parse(await readFile(path.join(temp,'.fusion/selection.json'),'utf8'));
 assert.equal(stored.selection.worker.reasoning_effort,'high');
 console.log(JSON.stringify({status:'passed',sdk:'@modelcontextprotocol/client 2.3.1',
  checks:['stdio handshake','tool schema discovery','resource read','structured settings read/update',
   'shared saved state','handoff snapshot','execution adapter without execution','invalid effort error'],model_calls:0}));
} finally {await client.close();await rm(temp,{recursive:true,force:true});}
