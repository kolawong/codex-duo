const $ = id => document.getElementById(id);
const roles = ['coordinator', 'worker'];
const efforts = {none:'无', minimal:'最低', low:'低', medium:'中', high:'高', xhigh:'很高', max:'最高', ultra:'超高'};
let state = null, draft = null, workflow = null, baseline = null, busy = false, connected = false, conflict = false, enableRequested = false, pendingScope = null;
const clone = value => JSON.parse(JSON.stringify(value));
const model = id => state?.catalog?.models.find(m => m.id === id);
const changes = () => !baseline || !draft ? 0 : roles.reduce((count, role) => count + Number(draft[role].model !== baseline.selection[role].model) + Number(draft[role].reasoning_effort !== baseline.selection[role].reasoning_effort), 0) + ['activation', 'coordinator_mode', 'max_worker_turns', 'max_parallel_workers', 'planner_mode', 'planner_model', 'planner_reasoning_effort', 'max_planner_turns'].reduce((count, key) => count + Number(workflow[key] !== baseline.workflow[key]), 0);
const dirty = () => changes() > 0;
const valid = () => Boolean(draft && workflow && roles.every(role => model(draft[role].model)?.efforts.includes(draft[role].reasoning_effort)) && ['automatic_project','manual'].includes(workflow.activation) && ['current_thread','selected_model'].includes(workflow.coordinator_mode) && Number.isInteger(workflow.max_worker_turns) && workflow.max_worker_turns >= 1 && workflow.max_worker_turns <= 10 && Number.isInteger(workflow.max_parallel_workers) && workflow.max_parallel_workers >= 1 && workflow.max_parallel_workers <= 3 && ['disabled','plan_only'].includes(workflow.planner_mode) && Number.isInteger(workflow.max_planner_turns) && workflow.max_planner_turns >= 1 && workflow.max_planner_turns <= 3 && (workflow.planner_mode === 'disabled' || model(workflow.planner_model)?.efforts.includes(workflow.planner_reasoning_effort)));
const canSave = () => !busy && connected && !conflict && valid() && (dirty() || Boolean(state.saved.error) || (!state.saved.document && (state.scope === 'global' || !state.effective?.document)) || enableRequested);
const conflictMessage = '配置已在别处更新。已保留你的修改；请放弃修改并重新载入最新配置。';

function notice(text = '', error = false) {
  $('notice').textContent = text;
  $('notice').classList.toggle('error', error);
  $('notice').setAttribute('role', error ? 'alert' : 'status');
}
async function request(path, body) {
  if (window.fusionTransport) return window.fusionTransport.request(path, body);
  const response = await fetch(path, body === undefined ? {cache:'no-store'} : {
    method:'POST', headers:{'Content-Type':'application/json','X-Fusion-Token':state.csrf_token}, body:JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) {const error = new Error(data.error?.message || '本地请求失败，请重试。'); error.code = data.error?.code; throw error;}
  return data;
}
function restoreDraft() {
  draft = clone(state.saved.document?.selection || state.default);
  workflow = {max_parallel_workers:1, planner_mode:'disabled', planner_model:'', planner_reasoning_effort:'', max_planner_turns:1, ...clone(state.workflow)};
  if (!state.saved.document && !state.effective?.document && !state.saved.error) workflow.activation = 'manual';
  enableRequested = false;
  baseline = {selection:clone(draft), workflow:clone(workflow), revision:state.saved.revision, globalRevision:state.global_revision};
  conflict = false;
}
function render() {
  const available = connected && Boolean(state?.catalog), saved = state?.saved?.document || (state?.scope !== 'global' ? state?.effective?.document : null);
  $('controls').disabled = busy || !available;
  $('settings-scope').disabled = busy || !available;
  const projectScope = (state?.scope || 'project') === 'project';
  $('settings-scope').value = state?.scope || 'project';
  $('project-card').hidden = !projectScope;
  $('project-note').hidden = !projectScope;
  $('global-scope-note').hidden = projectScope;
  $('settings-source').textContent = state?.source === 'project' ? '项目独立设置' : state?.source === 'global' ? (state?.scope === 'project' ? '继承全局默认' : '已保存的全局默认') : '未配置';
  $('reset-inherit').hidden = (state?.scope || 'project') !== 'project' || (!state?.saved?.document && !state?.saved?.error);
  $('reset-inherit').disabled = busy || !available || conflict;
  $('refresh').disabled = busy;
  $('save').disabled = !canSave();
  $('restore').hidden = !dirty() && !conflict;
  $('restore').disabled = busy || !available;
  for (const role of roles) {
    const select = $(`${role}-model`), effort = $(`${role}-effort`);
    select.replaceChildren(); effort.replaceChildren();
    if (state?.catalog && draft) {
      for (const item of state.catalog.models) select.add(new Option(item.name, item.id));
      if (!model(draft[role].model)) select.add(new Option(`不可用：${draft[role].model}`, draft[role].model));
      select.value = draft[role].model;
      const supported = model(draft[role].model)?.efforts || [];
      for (const item of supported) effort.add(new Option(efforts[item] || item, item));
      if (!supported.includes(draft[role].reasoning_effort)) effort.add(new Option(`不可用：${draft[role].reasoning_effort}`, draft[role].reasoning_effort));
      effort.value = draft[role].reasoning_effort;
      $(`${role}-description`).textContent = model(draft[role].model)?.description || '该模型已不在目录中，请重新选择。';
    }
  }
  if (workflow) {
    const automatic = workflow.activation === 'automatic_project', selected = workflow.coordinator_mode === 'selected_model';
    $('activation-automatic').setAttribute('aria-pressed', String(automatic));
    $('activation-manual').setAttribute('aria-pressed', String(!automatic));
    $('activation-description').textContent = (state.scope === 'global') ? (automatic ? '各项目开发任务自动启用；项目独立设置优先。' : '各项目默认手动启用；项目覆盖优先。') : state.source === 'global' ? (automatic ? '继承全局自动模式，开发任务会自动启用。编辑后保存为当前项目独立设置。' : '继承全局手动模式，仅明确要求时启用。') : automatic ? (state.project_opt_in?.enabled ? '在这个项目里提开发任务时自动启用，不用每次说明。' : '选择自动后保存，会在本项目 AGENTS.md 添加 Codex Duo 指令。已有聊天首次可调用 $codex-duo。') : '只在你于聊天中明确要求时启用。';
    $('planner-mode').value = workflow.planner_mode;
    $('max-planner-turns').value = String(workflow.max_planner_turns);
    const plannerSelect = $('planner-model'), plannerEffort = $('planner-effort');
    plannerSelect.replaceChildren(new Option('请选择模型', '')); plannerEffort.replaceChildren(new Option('请选择推理强度', ''));
    for (const item of state.catalog.models) plannerSelect.add(new Option(item.name, item.id));
    if (workflow.planner_model && !model(workflow.planner_model)) plannerSelect.add(new Option(`不可用：${workflow.planner_model}`, workflow.planner_model));
    plannerSelect.value = workflow.planner_model;
    const plannerEfforts = model(workflow.planner_model)?.efforts || [];
    for (const item of plannerEfforts) plannerEffort.add(new Option(efforts[item] || item, item));
    if (workflow.planner_reasoning_effort && !plannerEfforts.includes(workflow.planner_reasoning_effort)) plannerEffort.add(new Option(`不可用：${workflow.planner_reasoning_effort}`, workflow.planner_reasoning_effort));
    plannerEffort.value = workflow.planner_reasoning_effort;
    for (const id of ['planner-model','planner-effort','max-planner-turns']) $(id).disabled = workflow.planner_mode !== 'plan_only';
    $('coordinator-mode').value = workflow.coordinator_mode;
    $('coordinator-summary').textContent = selected ? '指定模型' : '当前聊天';
    $('coordinator-help').textContent = selected ? '只记录你偏好的规划模型。只有你明确要求时才会新建聊天。' : '你正在使用的聊天负责拆解任务和验收结果。Codex Duo 不会更改它的模型。';
    $('coordinator-model').disabled = !selected;
    $('coordinator-effort').disabled = !selected;
    $('max-parallel-workers').value = String(workflow.max_parallel_workers);
    $('max-worker-turns').value = String(workflow.max_worker_turns);
    $('turns-minus').disabled = workflow.max_worker_turns <= 1;
    $('turns-plus').disabled = workflow.max_worker_turns >= 10;
    const level = {none:0,minimal:1,low:1,medium:2,high:3,xhigh:4,max:4,ultra:4}[draft.worker.reasoning_effort] || 0;
    $('worker-meter').replaceChildren();
    for (let i=0; i<4; i++) {const bar=document.createElement('i'); bar.style.height=`${4+i*2.2}px`; bar.className=i<level?'on':''; $('worker-meter').append(bar);}
  }
  const status = conflict ? '有冲突' : !connected && !busy ? '读取失败' : !draft ? '读取中' : !valid() ? '组合无效' : dirty() ? '未保存' : !saved ? '未配置' : '已保存';
  $('saved-state').textContent = status;
  $('saved-state').setAttribute('data-tone', ['有冲突','读取失败','组合无效'].includes(status) ? 'red' : status==='未保存'?'amber':status==='已保存'?'green':status==='未配置'?'accent':'neutral');
  $('draft-state').textContent = conflict ? '配置已在别处更新' : dirty() ? `${changes()} 项修改未保存` : saved ? '备用设置入口' : '保存后用于后续任务';
  $('save').textContent = busy ? '处理中…' : state?.saved?.error ? '保存并备份' : '保存';
  const project = state?.project_root || '';
  $('project-name').textContent = project ? project.replace(/\/$/,'').split('/').pop() : '当前项目';
  $('project-scope').textContent = project;
  $('project-scope').title = project;
  $('storage').textContent = state?.storage_path || '配置存储路径暂不可用';
}
async function load(mode = 'initial', scope = state?.scope) {
  if (busy) return;
  const keepDraft = Boolean(draft && (dirty() || conflict));
  busy = true; render();
  try {
    const latest = mode === 'initial' && window.fusionTransport ? await window.fusionTransport.initial() : await request('/api/state' + (scope ? '?scope=' + scope : ''));
    if (!latest.catalog) {connected=false; notice(latest.error?.message || '模型目录读取失败，请刷新重试。', true); return;}
    if (state?.project_root && latest.project_root !== state.project_root) throw new Error('项目不一致，原项目和修改已保留。');
    state = latest; connected = true;
    if (!draft || mode === 'restore' || mode === 'scope' || !keepDraft) restoreDraft();
    else if (state.saved.revision !== baseline.revision || state.global_revision !== baseline.globalRevision) conflict = true;
    notice(conflict ? conflictMessage : (state.saved.error || (state.scope !== 'global' ? state.effective?.error : null))?.message || (mode === 'restore' ? '已重新载入最新配置。' : mode === 'refresh' && keepDraft ? '已刷新，未保存的修改已保留。' : ''), conflict || Boolean(state.saved.error || (state.scope !== 'global' ? state.effective?.error : null)));
    if (!valid() && !conflict) notice('当前配置包含不再支持的组合，请更新。', true);
  } catch (error) {connected = false; notice(window.fusionTransport ? error.message : '无法连接本地服务，请确认服务运行后刷新。', true);}
  finally {busy = false; render();}
}
function edited() {notice(conflict ? conflictMessage : '', conflict); render();}
for (const role of roles) {
  $(`${role}-model`).addEventListener('change', event => {
    const selected = model(event.target.value);
    if (!selected || busy || !connected) return;
    draft[role].model = selected.id;
    let adjusted = false;
    if (!selected.efforts.includes(draft[role].reasoning_effort)) {draft[role].reasoning_effort = selected.default_effort; adjusted = true;}
    edited();
    if (adjusted && !conflict) notice(`推理强度已调整为该模型支持的“${efforts[selected.default_effort] || selected.default_effort}”，保存后生效。`);
  });
  $(`${role}-effort`).addEventListener('change', event => {draft[role].reasoning_effort=event.target.value; edited();});
}
for (const [id,value] of [['activation-automatic','automatic_project'],['activation-manual','manual']]) $(id).addEventListener('click', () => {workflow.activation=value; enableRequested=(state.scope || 'project')==='project' && value==='automatic_project' && state.source!=='global' && !state.project_opt_in?.enabled; edited();});
$('planner-mode').addEventListener('change', event => {workflow.planner_mode=event.target.value; edited();});
$('planner-model').addEventListener('change', event => {
  workflow.planner_model=event.target.value;
  const option=model(workflow.planner_model);
  if (option && !option.efforts.includes(workflow.planner_reasoning_effort)) workflow.planner_reasoning_effort=option.default_effort;
  edited();
});
$('planner-effort').addEventListener('change', event => {workflow.planner_reasoning_effort=event.target.value; edited();});
$('max-planner-turns').addEventListener('change', event => {workflow.max_planner_turns=Number(event.target.value); edited();});
$('max-parallel-workers').addEventListener('change', event => {workflow.max_parallel_workers=Number(event.target.value); edited();});
$('coordinator-mode').addEventListener('change', event => {workflow.coordinator_mode=event.target.value; edited();});
$('max-worker-turns').addEventListener('change', event => {workflow.max_worker_turns=Number(event.target.value); edited();});
for (const [id,delta] of [['turns-minus',-1],['turns-plus',1]]) $(id).addEventListener('click', () => {workflow.max_worker_turns=Math.min(10,Math.max(1,workflow.max_worker_turns+delta)); edited();});
$('refresh').addEventListener('click', () => load('refresh'));
$('restore').addEventListener('click', () => {if (!busy) $('discard-dialog').showModal();});
$('discard-cancel').addEventListener('click', () => {pendingScope=null; $('discard-dialog').close(); render();});
$('discard-confirm').addEventListener('click', () => {$('discard-dialog').close(); const scope=pendingScope; pendingScope=null; load(scope ? 'scope' : 'restore', scope || state?.scope);});
async function save() {
  if (!canSave()) return;
  busy=true; render();
  try {
    const saved=await request('/api/selection', {selection:clone(draft), workflow:clone(workflow), expected_revision:baseline.revision, project_root:state.project_root, scope:state.scope || 'project', ...(baseline.globalRevision ? {expected_global_revision:baseline.globalRevision} : {}), ...(enableRequested ? {enable_project:true} : {})});
    if (saved.state) state={...saved.state, csrf_token:state.csrf_token};
    state.saved=saved; if (saved.project_opt_in) state.project_opt_in=saved.project_opt_in; state.workflow=clone(saved.document.workflow);
    restoreDraft(); notice('已保存，之后的新任务会使用这套设置。');
  } catch(error) {
    if (error.code==='revision_conflict') conflict=true;
    notice(conflict ? conflictMessage : error.message, true);
  } finally {busy=false; render();}
}
$('save').addEventListener('click', save);
document.addEventListener('keydown', event => {if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase()==='s') {event.preventDefault(); save();}});
$('settings-scope').addEventListener('change', event => {
  if (busy || !connected) return;
  const scope=event.target.value;
  if (scope===(state.scope || 'project')) return;
  if (dirty() || conflict) {pendingScope=scope; $('discard-dialog').showModal(); render();}
  else load('scope',scope);
});
$('reset-inherit').addEventListener('click', () => {if (!busy && connected) $('reset-dialog').showModal();});
$('reset-cancel').addEventListener('click', () => $('reset-dialog').close());
$('reset-confirm').addEventListener('click', async () => {
  $('reset-dialog').close();
  if (busy || !connected || conflict) return;
  busy=true; render();
  try {
    const latest=await request('/api/reset',{project_root:state.project_root,expected_revision:baseline.revision,expected_global_revision:baseline.globalRevision});
    state={...latest,csrf_token:state.csrf_token}; restoreDraft(); notice('已清除项目覆盖，后续任务继承全局默认。');
  } catch(error) {if(error.code==='revision_conflict')conflict=true; notice(conflict ? conflictMessage : error.message,true);}
  finally {busy=false;render();}
});
load();
