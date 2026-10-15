// Exercise the shared controller through rendered DOM controls and both transports.
// This focused harness verifies state behavior; actual browser layout is reviewed separately.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
const source = await readFile(new URL('../panel/static/app.js', import.meta.url), 'utf8');
const bridge = await readFile(new URL('./bridge.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../panel/static/index.html', import.meta.url), 'utf8');
const copy = value => JSON.parse(JSON.stringify(value));
const selection = {coordinator:{model:'planner',reasoning_effort:'high'},worker:{model:'executor',reasoning_effort:'high'}};
const workflow = {activation:'automatic_project',coordinator_mode:'current_thread',max_worker_turns:3,max_parallel_workers:1};
function snapshot(revision='r1', selected=selection) {
  return {catalog:{models:[{id:'planner',name:'Planner',efforts:['high','ultra'],default_effort:'high'},
    {id:'executor',name:'Executor',efforts:['high','medium'],default_effort:'high'},
    {id:'small',name:'Small',efforts:['low','medium'],default_effort:'medium'}]},
    saved:{revision,document:{selection:copy(selected),workflow:copy(workflow)}},workflow:copy(workflow),default:copy(selection),
    project_opt_in:{enabled:true,error:null},project_root:'/test/tandem',storage_path:'/test/tandem/.codex-duo/selection.json',csrf_token:'fixture-token'};
}
class Element {
  constructor(id='') {this.id=id;this.value='';this.disabled=false;this.hidden=false;this.textContent='';this.children=[];this.attributes={};this.events={};this.style={};this.className='';this.open=false;
    this.classList={toggle:(name,on)=>{const classes=new Set(this.className.split(' ').filter(Boolean));on?classes.add(name):classes.delete(name);this.className=[...classes].join(' ');}};
  }
  setAttribute(key,value){this.attributes[key]=value;}
  replaceChildren(...children){this.children=children;}
  append(...children){this.children.push(...children);}
  add(child){this.children.push(child);}
  addEventListener(type,handler){this.events[type]=handler;}
  focus(){this.focused=true;}
  select(){this.selected=true;}
  showModal(){this.open=true;}
  close(){this.open=false;}
}
async function harness(transport='mcp', first=snapshot()) {
  const elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(match=>[match[1],new Element(match[1])]));
  const doc=new Element();doc.documentElement=new Element();doc.getElementById=id=>{assert.ok(elements.has(id),`Missing control ${id}`);return elements.get(id);};doc.createElement=()=>new Element();
  let latest=copy(first), failRead=false, failSave=null, resetState=null;
  const calls=[];
  const serve=async(path,body)=>{
    calls.push({path,body:copy(body || null)});
    if(path.split('?')[0]==='/api/state'){if(failRead) throw new Error('offline');return {...copy(latest),...(path.includes('?') ? {scope:path.split('=')[1]} : {})};}
    if(failSave) throw Object.assign(new Error(failSave),{code:failSave});
    if(path==='/api/reset'){assert.ok(resetState,'reset fixture required');latest=copy(resetState);return copy(latest);}
    latest.saved={revision:`r${calls.length+1}`,changed:true,document:{selection:copy(body.selection),workflow:copy(body.workflow)}};
    if(body.enable_project) latest.project_opt_in={enabled:true,error:null};
    latest.saved.project_opt_in=copy(latest.project_opt_in);
    latest.workflow=copy(body.workflow);return copy(latest.saved);
  };
  const context=vm.createContext({document:doc,window:{},Option:class{constructor(text,value){this.text=text;this.value=value;}},setTimeout,clearTimeout});
  if(transport==='mcp'){
    // Use the real bridge with a mock SDK host, including structured tool errors.
    context.App=class{
      constructor(){context.host=this;}
      async connect(){}
      getHostContext(){return {theme:"dark"};}
      async callServerTool({name,arguments:args}){
        try {return {structuredContent:await serve(name==='codex_duo_state'?'/api/state'+(args.scope?'?scope='+args.scope:''):name==='codex_duo_reset'?'/api/reset':'/api/selection',args)};}
        catch(error){return {isError:true,structuredContent:{error:{message:error.message,code:error.code}}};}
      }
    };
    vm.runInContext(bridge.replace("import { App } from '@modelcontextprotocol/ext-apps';",''),context);
    context.host.ontoolresult({_meta:{'codex-duo/state':copy(first)}});
  } else {
    context.fetch=async(path,options)=>{
      if(options.method==='POST'){assert.equal(options.headers['X-Codex-Duo-Token'],'fixture-token');assert.equal(options.headers['Content-Type'],'application/json');}
      try {const data=await serve(path,options.body?JSON.parse(options.body):undefined);return {ok:true,json:async()=>data};}
      catch(error){return {ok:false,json:async()=>({error:{message:error.message,code:error.code}})};}
    };
  }
  vm.runInContext(source,context);
  const settle=async()=>{await new Promise(resolve=>setImmediate(resolve));};
  const control=id=>elements.get(id);
  const fire=async(id,type='click',value)=>{const target=id==='document'?doc:control(id);if(value!==undefined)target.value=String(value);await target.events[type]({target,key:'s',metaKey:true,preventDefault(){}});await settle();};
  await settle();
  return {control,fire,calls,settle,root:doc.documentElement,host:context.host,set latest(value){latest=copy(value);},get latest(){return copy(latest);},set resetState(value){resetState=copy(value);},set failRead(value){failRead=value;},set failSave(value){failSave=value;}};
}
for(const transport of ['mcp','http']) {
  const h=await harness(transport);
  assert.equal(h.control('saved-state').textContent,'已保存');
  assert.equal(h.control('activation-description').textContent,'在这个项目里提开发任务时自动启用，不用每次说明。','enabled project keeps concise daily copy');
  if(transport==='mcp'){
    assert.equal(h.root.attributes['data-theme'],'dark','initial host theme overrides system preference');
    h.host.onhostcontextchanged({theme:'light'});
    assert.equal(h.root.attributes['data-theme'],'light','live host theme updates');
    h.host.onhostcontextchanged({locale:'zh-CN'});
    assert.equal(h.root.attributes['data-theme'],'light','partial context update retains theme');
  } else assert.equal(h.root.attributes['data-theme'],undefined,'HTTP retains system appearance fallback');
  assert.equal(h.control('save').disabled,true);
  assert.equal(h.control('coordinator-model').disabled,true);
  assert.equal(h.control('worker-effort').children.find(option=>option.value==='high').text,'高');
  await h.fire('worker-model','change','small');
  assert.equal(h.control('worker-effort').value,'medium','unsupported effort falls back to model default');
  assert.equal(h.control('save').disabled,false);
  await h.fire('activation-manual');
  await h.fire('turns-plus');
  await h.fire('max-parallel-workers','change','3');
  await h.fire('refresh');
  assert.equal(h.control('worker-model').value,'small','same revision refresh keeps draft');
  assert.equal(h.control('max-worker-turns').value,'4');
  assert.equal(h.control('activation-manual').attributes['aria-pressed'],'true');
  await h.fire('save');
  const save=h.calls.find(call=>call.path==='/api/selection');
  assert.equal(save.body.expected_revision,'r1');
  assert.equal(save.body.project_root,'/test/tandem');
  assert.equal(save.body.enable_project,undefined,'manual save never opts project in');
  if(transport==='mcp') assert.ok(h.calls.every(call=>call.body?.project_root==='/test/tandem'),'all MCP calls pinned to opener root');
  assert.deepEqual(save.body.selection.coordinator,selection.coordinator,'inactive planner stays intact');
  assert.equal(save.body.workflow.max_worker_turns,4);
  assert.equal(save.body.workflow.max_parallel_workers,3);
  assert.equal(h.control('max-parallel-workers').value,'3');
  assert.equal(save.body.workflow.activation,'manual');
  assert.equal(h.control('save').disabled,true);
  assert.equal(h.control('saved-state').textContent,'已保存');
  await h.fire('refresh');
  assert.equal(h.control('worker-model').value,'small','saved draft survives reload');

  const conflict=await harness(transport);
  await conflict.fire('worker-effort','change','medium');
  const external=snapshot('external',{...selection,worker:{model:'small',reasoning_effort:'low'}});
  conflict.latest=external;
  await conflict.fire('refresh');
  assert.equal(conflict.control('saved-state').textContent,'有冲突');
  assert.equal(conflict.control('worker-model').value,'executor');
  assert.equal(conflict.control('worker-effort').value,'medium');
  assert.equal(conflict.control('save').disabled,true);
  await conflict.fire('save');await conflict.fire('document','keydown');
  assert.equal(conflict.calls.filter(call=>call.path==='/api/selection').length,0,'stale draft cannot be overwritten through click or shortcut');
  await conflict.fire('worker-effort','change','high');
  await conflict.fire('refresh');
  assert.equal(conflict.control('saved-state').textContent,'有冲突','reverting edits does not silently rebase conflict');
  await conflict.fire('restore');assert.equal(conflict.control('discard-dialog').open,true);
  await conflict.fire('discard-cancel');assert.equal(conflict.control('worker-model').value,'executor');
  await conflict.fire('restore');await conflict.fire('discard-confirm');
  assert.equal(conflict.control('worker-model').value,'small');
  assert.equal(conflict.control('saved-state').textContent,'已保存');
  await conflict.fire('worker-effort','change','medium');await conflict.fire('save');
  assert.equal(conflict.calls.find(call=>call.path==='/api/selection').body.expected_revision,'external','explicit restore adopts latest revision');

  const race=await harness(transport);
  await race.fire('worker-effort','change','medium');race.failSave='revision_conflict';await race.fire('save');
  assert.equal(race.control('saved-state').textContent,'有冲突','server conflict code survives transport');
  assert.equal(race.control('worker-effort').value,'medium');
  assert.equal(race.control('save').disabled,true);
  const offline=await harness(transport);
  await offline.fire('worker-effort','change','medium');offline.failRead=true;await offline.fire('refresh');
  assert.equal(offline.control('save').disabled,true);assert.equal(offline.control('worker-effort').value,'medium');
  offline.failRead=false;await offline.fire('refresh');assert.equal(offline.control('save').disabled,false);
  offline.failSave='storage_unavailable';await offline.fire('save');
  assert.equal(offline.control('worker-effort').value,'medium');assert.equal(offline.control('save').disabled,false,'storage error retains editable draft');
  await offline.fire('max-worker-turns','change',1);assert.equal(offline.control('turns-minus').disabled,true);
  await offline.fire('max-worker-turns','change',10);assert.equal(offline.control('turns-plus').disabled,true);
  await offline.fire('max-worker-turns','change',11);assert.equal(offline.control('save').disabled,true);
  const unavailable=snapshot();unavailable.saved.document.selection.worker={model:'gone',reasoning_effort:'ultra'};
  const invalid=await harness(transport,unavailable);assert.equal(invalid.control('save').disabled,true);
  assert.equal(invalid.control('worker-model').value,'gone');
  const initial=snapshot('none');initial.saved.document=null;initial.project_opt_in.enabled=false;
  const fresh=await harness(transport,initial);assert.equal(fresh.control('save').disabled,false,'first save works without editing');
  assert.equal(fresh.control('activation-manual').attributes['aria-pressed'],'true','new projects start manual');
  await fresh.fire('activation-automatic');
  assert.ok(fresh.control('activation-description').textContent.includes('AGENTS.md'),'first opt-in explains project instruction change');
  await fresh.fire('save');
  assert.equal(fresh.control('activation-description').textContent,'在这个项目里提开发任务时自动启用，不用每次说明。','saved enabled project uses concise copy');assert.equal(fresh.control('saved-state').textContent,'已保存');
  assert.equal(fresh.calls.find(call=>call.path==='/api/selection').body.enable_project,true,'explicit automatic save enables instructions');
  const pinned=await harness(transport);
  await pinned.fire('worker-effort','change','medium');
  pinned.latest={...snapshot('foreign'),project_root:'/foreign/project'};
  await pinned.fire('refresh');
  assert.equal(pinned.control('project-scope').textContent,'/test/tandem','foreign state never publishes another root');
  assert.equal(pinned.control('worker-effort').value,'medium','foreign state preserves draft');
  assert.equal(pinned.control('save').disabled,true,'foreign state blocks write until valid refresh');
  pinned.latest=snapshot();await pinned.fire('refresh');await pinned.fire('save');
  assert.equal(pinned.calls.find(call=>call.path==='/api/selection').body.project_root,'/test/tandem');
  const inherited=snapshot('none'); inherited.saved.document=null;
  inherited.scope='project'; inherited.source='global'; inherited.global_revision='g1';
  inherited.effective={revision:'g1',document:{selection:copy(selection),workflow:copy(workflow)}};
  const globalRace=await harness(transport,inherited);
  assert.equal(globalRace.control('activation-automatic').attributes['aria-pressed'],'true','inherited automatic stays automatic');
  await globalRace.fire('worker-effort','change','medium');
  globalRace.latest={...inherited,global_revision:'g2'};
  await globalRace.fire('refresh');
  assert.equal(globalRace.control('saved-state').textContent,'有冲突','external global edit conflicts with inherited draft');
  assert.equal(globalRace.control('worker-effort').value,'medium');
  assert.equal(globalRace.control('save').disabled,true);
  await globalRace.fire('save');
  assert.equal(globalRace.calls.filter(call=>call.path==='/api/selection').length,0);

  const scopes=await harness(transport,{...snapshot(),scope:'project',source:'project',global_revision:'g1'});
  await scopes.fire('settings-scope','change','global');
  assert.equal(scopes.control('settings-scope').value,'global');
  assert.equal(scopes.control('project-card').hidden,true);
  assert.equal(scopes.control('project-note').hidden,true);
  assert.equal(scopes.control('global-scope-note').hidden,false);
  assert.equal(scopes.calls.filter(call=>call.path==='/api/selection').length,0,'scope switching does not save settings');
  await scopes.fire('worker-effort','change','medium');
  scopes.failRead=true;await scopes.fire('settings-scope','change','project');
  assert.equal(scopes.control('discard-dialog').open,true,'scope switch asks before dropping draft');
  await scopes.fire('discard-confirm');
  assert.equal(scopes.control('settings-scope').value,'global','failed scope switch retains old scope');
  assert.equal(scopes.control('project-card').hidden,true,'failed switch retains global visibility');
  assert.equal(scopes.control('worker-effort').value,'medium','failed scope switch retains draft');
  scopes.failRead=false;await scopes.fire('refresh');
  await scopes.fire('save');
  assert.equal(scopes.calls.find(call=>call.path==='/api/selection').body.scope,'global','global save is explicit');
  assert.equal(scopes.calls.find(call=>call.path==='/api/selection').body.enable_project,undefined,'global save never changes project instructions');
  await scopes.fire('settings-scope','change','project');
  assert.equal(scopes.control('project-card').hidden,false);
  assert.equal(scopes.control('project-note').hidden,false);
  assert.equal(scopes.control('global-scope-note').hidden,true);
  assert.equal(scopes.control('project-name').textContent,'tandem');
  assert.equal(scopes.control('project-scope').textContent,'/test/tandem');
  const recovery=snapshot('corrupt');recovery.saved.document=null;recovery.saved.error={message:'损坏的配置将先备份'};
  const corrupt=await harness(transport,recovery);assert.equal(corrupt.control('save').textContent,'保存并备份');
  console.log(`${transport}: save/reload, effort validation, planner preservation, draft refresh, stale revision, explicit discard, transport errors, host theme, turn bounds, initial and corrupt settings passed`);
}
console.log('Panel behavior checks passed. Browser appearance and native execution are separate acceptance gates.');

for (const transport of ['mcp','http']) {
  const presetState = snapshot();
  presetState.presets = [{id:'light',name:'轻任务',worker_only:true,selection:{coordinator:{model:'unused',reasoning_effort:'ultra'},worker:{model:'small',reasoning_effort:'low'}}}];
  const presetUI = await harness(transport,presetState);
  const summaryBefore = presetUI.control('worker-default-summary').textContent;
  await presetUI.fire('worker-preset','change','light');
  assert.equal(presetUI.control('worker-model').value,'small');
  assert.equal(presetUI.control('worker-effort').value,'low');
  assert.equal(presetUI.control('coordinator-model').value,'planner');
  assert.equal(presetUI.control('planner-mode').value,'disabled');
  assert.equal(presetUI.control('max-worker-turns').value,'3');
  assert.equal(presetUI.control('worker-default-summary').textContent,summaryBefore,'unsaved preset is not a new saved default');
  assert.equal(presetUI.calls.filter(call=>call.path==='/api/selection').length,0,'preset does not auto-save');
  assert.ok(summaryBefore.includes('设置不确认运行时身份'));
  await presetUI.fire('restore'); await presetUI.fire('discard-confirm');
  assert.equal(presetUI.control('worker-model').value,'executor');
  const legacy=snapshot(); delete legacy.workflow.max_parallel_workers; delete legacy.saved.document.workflow.max_parallel_workers;
  const h=await harness(transport,legacy);
  assert.equal(h.control('max-parallel-workers').value,'1');
  assert.equal(h.control('save').disabled,true,'legacy reads stay clean');
  await h.fire('max-parallel-workers','change','4');
  assert.equal(h.control('save').disabled,true,'out of range parallel cap blocks save');
  await h.fire('max-parallel-workers','change','2');
  assert.equal(h.control('save').disabled,false);
  await h.fire('restore');
  await h.fire('discard-confirm');
  assert.equal(h.control('max-parallel-workers').value,'1');
}


assert.doesNotMatch(html, /completion-mode|review-inbox|复制验收提示/);
assert.doesNotMatch(bridge, /review-prompt|codex_duo_completion|wake_on_completion/);
for (const transport of ['mcp','http']) {
  for (const mode of ['manual_review','wake_on_completion']) {
    const legacy=snapshot();legacy.workflow.completion_mode=mode;
    legacy.saved.document.workflow.completion_mode=mode;
    const h=await harness(transport,legacy);
    assert.equal(h.control('save').disabled,true,'old mode is ignored on read');
    await h.fire('turns-plus');await h.fire('save');
    assert.equal(h.latest.workflow.completion_mode,undefined,'old mode must not be saved');
    assert.deepEqual(h.latest.saved.document.selection,selection);
    assert.ok(h.calls.every(c=>['/api/state','/api/selection'].includes(c.path.split('?')[0])));
  }
}
console.log('Return-only panel: removed controls/routes and legacy preference reads passed.');

assert.match(html, /<label for="agent-activity">代理积极程度<\/label>/);
assert.match(html, /id="agent-activity" type="range" min="0" max="2" step="1"/);
assert.match(html, /aria-describedby="agent-activity-description"/);
for (const transport of ['mcp','http']) {
  const legacy = await harness(transport);
  assert.equal(legacy.control('agent-activity').value,'1');
  assert.equal(legacy.control('agent-activity-value').textContent,'均衡');
  assert.equal(legacy.control('save').disabled,true,'missing activity stays clean');
  await legacy.fire('save');
  assert.equal(legacy.calls.filter(c=>c.path==='/api/selection').length,0,'legacy read does not write defaults');
  assert.equal(legacy.latest.saved.document.workflow.agent_activity,undefined);
  const values=['conservative','balanced','aggressive'], titles=['保守','均衡','积极'];
  for (const scope of ['global','project']) {
    for (const [index, activity] of values.entries()) {
      const first=snapshot(); first.scope=scope;first.source=scope;first.global_revision='g1';
      first.workflow.agent_activity=values[(index+1)%3];
      first.saved.document.workflow.agent_activity=first.workflow.agent_activity;
      const h=await harness(transport,first);
      await h.fire('agent-activity','input',index);
      assert.equal(h.control('agent-activity-value').textContent,titles[index]);
      assert.equal(h.control('agent-activity').attributes['aria-valuetext'],titles[index]);
      assert.ok(h.control('agent-activity-description').textContent.length>5);
      assert.equal(h.control('draft-state').textContent,'1 项修改未保存');
      await h.fire('refresh');
      assert.equal(h.control('agent-activity').value,String(index),'same revision keeps activity draft');
      await h.fire('save');
      const save=h.calls.find(c=>c.path==='/api/selection');
      assert.equal(save.body.scope,scope);
      assert.equal(save.body.workflow.agent_activity,activity);
      assert.deepEqual(save.body.selection,selection,'activity leaves models and efforts intact');
      assert.deepEqual({...save.body.workflow,agent_activity:undefined},
        {...workflow,worker_strategy:'fixed',worker_profiles:{},planner_mode:'disabled',planner_model:'',planner_reasoning_effort:'',max_planner_turns:1,agent_activity:undefined},
        'activity leaves activation, planner and budgets intact');
      assert.equal(h.control('save').disabled,true);
      await h.fire('refresh');
      assert.equal(h.control('agent-activity-value').textContent,titles[index]);
    }
  }
  const conflict=await harness(transport);
  await conflict.fire('agent-activity','input',2);
  const external=snapshot('external');external.workflow.agent_activity='conservative';external.saved.document.workflow.agent_activity='conservative';
  conflict.latest=external;await conflict.fire('refresh');
  assert.equal(conflict.control('agent-activity-value').textContent,'积极');
  assert.equal(conflict.control('saved-state').textContent,'有冲突');
  assert.equal(conflict.control('save').disabled,true);
  await conflict.fire('restore');await conflict.fire('discard-confirm');
  assert.equal(conflict.control('agent-activity-value').textContent,'保守');
  assert.equal(conflict.control('save').disabled,true);
  const local={...snapshot(),scope:'project',source:'project',global_revision:'g1'};
  const reset=await harness(transport,local);
  await reset.fire('agent-activity','input',2);
  const inherited={...external,scope:'project',source:'global',global_revision:'g2',effective:copy(external.saved)};
  inherited.saved={revision:'none',document:null,error:null};
  reset.resetState=inherited;
  await reset.fire('reset-inherit');await reset.fire('reset-confirm');
  assert.equal(reset.control('agent-activity-value').textContent,'保守','reset uses inherited activity');
  assert.equal(reset.control('save').disabled,true);
  assert.equal(reset.calls.find(c=>c.path==='/api/reset').body.expected_global_revision,'g1');
  for(const value of [null,false,0,'','Balanced','unknown']) {
    const malformed=snapshot();malformed.workflow.agent_activity=value;malformed.saved.document.workflow.agent_activity=value;
    const h=await harness(transport,malformed);
    assert.equal(h.control('save').disabled,true,'invalid present activity cannot save');
    assert.equal(h.control('agent-activity-value').textContent,'不可用');
    await h.fire('save');assert.equal(h.calls.filter(c=>c.path==='/api/selection').length,0);
  }
  const invalidStop=await harness(transport);
  await invalidStop.fire('agent-activity','input','1.5');
  assert.equal(invalidStop.control('save').disabled,true);
  await invalidStop.fire('agent-activity','input',2);
  assert.equal(invalidStop.control('save').disabled,false);
}
console.log('Agent activity: legacy clean reads, all stops, global/project save/reload, isolated values, draft refresh, conflicts, discard, inheritance reset and invalid values passed.');

for (const transport of ['mcp','http']) {
  const profiles = {light:{model:'small',reasoning_effort:'low'},standard:copy(selection.worker),complex:copy(selection.worker)};
  const first=snapshot();first.suggested_worker_profiles=copy(profiles);
  const h=await harness(transport,first);
  assert.equal(h.control('worker-strategy').value,'fixed');
  assert.equal(h.control('worker-profiles').hidden,true);
  assert.equal(h.control('save').disabled,true,'old settings read clean');
  assert.ok(h.control('execution-status-lines').children[0].textContent.includes('派发时确认/未知'));
  await h.fire('worker-strategy','change','adaptive');
  assert.equal(h.control('profile-light-model').value,'small');
  assert.equal(h.control('profile-light-effort').value,'low');
  assert.deepEqual(h.control('profile-light-effort').children.map(item=>item.value),['low','medium']);
  assert.equal(h.control('worker-profiles').hidden,false);
  assert.equal(h.control('max-parallel-workers').value,'1');
  await h.fire('profile-standard-model','change','small');
  assert.equal(h.control('profile-standard-effort').value,'medium');
  await h.fire('worker-strategy','change','fixed');
  await h.fire('worker-strategy','change','adaptive');
  assert.equal(h.control('profile-standard-model').value,'small','toggle keeps edited profiles');
  await h.fire('refresh');
  assert.equal(h.control('profile-standard-model').value,'small','refresh preserves profile draft');
  await h.fire('save');
  const saved=h.calls.find(item=>item.path==='/api/selection').body;
  assert.equal(saved.workflow.worker_strategy,'adaptive');
  assert.equal(saved.workflow.worker_profiles.standard.model,'small');
  assert.deepEqual(saved.selection,selection,'profiles do not change fallback or coordinator');
  assert.equal(saved.workflow.agent_activity,'balanced');
  await h.fire('worker-strategy','change','fixed');await h.fire('save');
  assert.equal(h.latest.workflow.worker_profiles.standard.model,'small','fixed save retains profiles');
  const active=snapshot();active.workflow.worker_strategy='adaptive';active.workflow.worker_profiles=copy(profiles);
  active.saved.document.workflow=copy(active.workflow);
  active.execution_status={handoff_id:'h1',task_id:'recent-task',goal:'最近的目标',updated_at:'2026-10-15T12:00:00Z',configured_max_parallel_workers:3,reported_host_capacity:2,effective_max_parallel_workers:2,occupied_workers:1,queued_workstreams:2,ready_workstreams:['ready'],waiting_workstreams:[{id:'later',reason:'等待依赖 first'}],remaining_worker_turns:4};
  const reported=await harness(transport,active);
  const statusText=reported.control('execution-status-lines').children.map(item=>item.textContent).join('\n');
  assert.match(statusText,/recent-task · 更新：2026-10-15T12:00:00Z/);
  assert.match(statusText,/已报告容量：2/);assert.match(statusText,/占用（已预留\/执行中）：1/);
  assert.match(statusText,/等待 later：等待依赖 first/);assert.match(statusText,/非实时宿主遥测/);
  assert.equal(reported.control('max-parallel-workers').value,'1','reported status never changes cap');
  const global=copy(active);global.scope='global';global.source='global';
  const globalUI=await harness(transport,global);
  assert.ok(globalUI.control('execution-status-lines').children[0].textContent.includes('未知'));
  for(const scope of ['global','project']) {
    const scoped=copy(first);scoped.scope=scope;scoped.source=scope;scoped.global_revision='g1';
    const scopedUI=await harness(transport,scoped);
    await scopedUI.fire('worker-strategy','change','adaptive');await scopedUI.fire('save');
    assert.equal(scopedUI.calls.find(item=>item.path==='/api/selection').body.scope,scope);
  }
  const conflict=await harness(transport,active);
  await conflict.fire('profile-light-effort','change','medium');
  const external=copy(active);external.saved.revision='external';
  conflict.latest=external;await conflict.fire('refresh');
  assert.equal(conflict.control('profile-light-effort').value,'medium');assert.equal(conflict.control('save').disabled,true);
  await conflict.fire('restore');await conflict.fire('discard-confirm');
  assert.equal(conflict.control('profile-light-effort').value,'low');
  const reset=await harness(transport,active);
  await reset.fire('profile-light-effort','change','medium');
  const inherited=copy(active);inherited.scope='project';inherited.source='global';inherited.global_revision='g2';inherited.effective=copy(active.saved);inherited.saved={revision:'none',document:null,error:null};
  reset.resetState=inherited;await reset.fire('reset-inherit');await reset.fire('reset-confirm');
  assert.equal(reset.control('profile-light-effort').value,'low');assert.equal(reset.control('save').disabled,true);
  for(const badProfiles of [{}, {light:profiles.light}, {...profiles,extra:profiles.light}, {...profiles,light:{model:'small',reasoning_effort:'ultra'}},null]) {
    const malformed=copy(active);malformed.workflow.worker_profiles=badProfiles;malformed.saved.document.workflow=copy(malformed.workflow);
    const invalid=await harness(transport,malformed);
    assert.equal(invalid.control('save').disabled,true);assert.equal(invalid.control('worker-profile-error').hidden,false);
    await invalid.fire('save');assert.equal(invalid.calls.filter(item=>item.path==='/api/selection').length,0);
  }
}
console.log('Adaptive workers: clean legacy defaults, draft-only starter profiles, catalog validation, fixed retention, scoped saves, conflicts/inheritance and unknown/reported capacity passed.');
