const $ = id => document.getElementById(id);
const roles = ['coordinator', 'worker'];
let state = null, draft = null, busy = false;
const clone = value => JSON.parse(JSON.stringify(value));
const same = (a, b) => roles.every(role => a?.[role]?.model === b?.[role]?.model && a?.[role]?.reasoning_effort === b?.[role]?.reasoning_effort);
const model = id => state?.catalog?.models.find(m => m.id === id);
const valid = () => draft && roles.every(role => model(draft[role].model)?.efforts.includes(draft[role].reasoning_effort));
const dirty = () => !same(draft, state?.saved?.document?.selection);
const label = role => `${model(role.model)?.name || role.model} / ${role.reasoning_effort}`;

function notice(text = '', error = false) {
  $('notice').textContent = text;
  $('notice').classList.toggle('error', error);
  $('notice').setAttribute('role', error ? 'alert' : 'status');
}

async function request(path, body) {
  if (window.fusionTransport) return window.fusionTransport.request(path, body);
  const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Fusion-Token': state.csrf_token},
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || '本地请求失败，请重试。');
  return data;
}

function render() {
  const available = Boolean(state?.catalog);
  $('controls').disabled = busy || !available;
  $('refresh').disabled = busy;
  $('save').disabled = busy || !available || !valid() || !dirty();
  $('restore').disabled = busy || !available || !state?.saved?.document;
  $('prepare').disabled = busy || !available || !state?.saved?.document || dirty() || !valid();
  $('task-json').disabled = busy;
  $('presets').replaceChildren();
  for (const preset of state?.presets || []) {
    const button = document.createElement('button');
    button.className = 'preset'; button.type = 'button'; button.disabled = busy || !available;
    button.setAttribute('aria-pressed', String(same(draft, preset.selection)));
    const title = document.createElement('strong'); title.textContent = preset.name;
    const description = document.createElement('p'); description.textContent = preset.description;
    button.append(title, description);
    button.addEventListener('click', () => {draft = clone(preset.selection); notice('预设已载入草稿。保存后可用于新交接包。'); render();});
    $('presets').append(button);
  }
  for (const role of roles) {
    const select = $(`${role}-model`), effort = $(`${role}-effort`);
    select.replaceChildren(); effort.replaceChildren();
    if (available && draft) {
      for (const item of state.catalog.models) select.add(new Option(item.name, item.id));
      if (!model(draft[role].model)) select.add(new Option(`不可用：${draft[role].model}`, draft[role].model));
      select.value = draft[role].model;
      for (const item of model(draft[role].model)?.efforts || []) effort.add(new Option(item[0].toUpperCase() + item.slice(1), item));
      if (!(model(draft[role].model)?.efforts || []).includes(draft[role].reasoning_effort)) effort.add(new Option(`不可用：${draft[role].reasoning_effort}`, draft[role].reasoning_effort));
      effort.value = draft[role].reasoning_effort;
      $(`${role}-description`).textContent = model(draft[role].model)?.description || '该模型已不在本机目录中，请重新选择。';
    }
  }
  $('catalog-count').textContent = available ? `${state.catalog.models.length} 个本机可见模型` : '目录暂不可用';
  $('catalog-source').textContent = available ? state.catalog.source.version : '可点击“刷新目录”重试';
  const saved = state?.saved?.document;
  $('draft-state').textContent = !available ? '等待目录' : !valid() ? '组合无效' : dirty() ? '有未保存更改' : '已保存';
  $('save-description').textContent = dirty() ? '草稿尚未用于任务交接。' : '已保存 · 仅适用于之后生成的新交接包。';
  $('save').textContent = busy ? '处理中…' : state?.saved?.error ? '保存并备份原配置' : '保存配置 ↗';
  $('saved-state').textContent = saved ? '已保存 · 未启动' : state?.saved?.error ? '保存文件无效' : '尚未保存';
  $('saved-pair').textContent = saved ? `主控  ${label(saved.selection.coordinator)}    →    执行  ${label(saved.selection.worker)}` : '保存后，这里会显示用于新交接包的模型组合。';
  $('storage').textContent = state?.storage_path ? `保存在本项目：${state.storage_path}` : '';
}

async function load(mode = 'initial') {
  busy = true; render();
  try {
    const loaded = mode === 'initial' && window.fusionTransport ? await window.fusionTransport.initial() : await request('/api/state');
    state = loaded;
    if (!loaded.catalog) {notice(loaded.error?.message || '模型目录读取失败。', true); return;}
    if (!draft || mode === 'restore') draft = clone(loaded.saved.document?.selection || loaded.default);
    if (!$('task-json').value) $('task-json').value = JSON.stringify(loaded.task_template, null, 2);
    notice(loaded.saved.error?.message || (mode === 'restore' ? '已恢复磁盘上的保存版本。' : ''), Boolean(loaded.saved.error));
    if (draft && !valid()) notice('当前草稿包含目录不再支持的组合，请重新选择。', true);
  } catch (error) {
    state = {...(state || {}), catalog: null};
    notice(window.fusionTransport ? error.message : '无法连接本地服务。请确认服务正在运行，再刷新目录。', true);
  } finally {busy = false; render();}
}

for (const role of roles) {
  $(`${role}-model`).addEventListener('change', event => {
    draft[role].model = event.target.value;
    const selected = model(event.target.value);
    if (!selected.efforts.includes(draft[role].reasoning_effort)) {
      draft[role].reasoning_effort = selected.default_effort;
      notice(`该模型不支持原强度，草稿已调整为 ${selected.default_effort}。请确认后保存。`);
    } else notice();
    render();
  });
  $(`${role}-effort`).addEventListener('change', event => {
    draft[role].reasoning_effort = event.target.value; notice(); render();
  });
}
$('refresh').addEventListener('click', () => load('refresh'));
$('restore').addEventListener('click', () => load('restore'));
$('save').addEventListener('click', async () => {
  if (busy || !valid()) return;
  busy = true; render();
  try {
    const saved = await request('/api/selection', {selection: draft, expected_revision: state.saved.revision});
    state.saved = saved;
    $('handoff-result').hidden = true;
    notice(saved.changed ? '配置已保存。仅影响之后生成的新交接包，当前会话未改变。' : '配置已经保存，无需重复写入。');
  } catch (error) {notice(error.message, true);}
  finally {busy = false; render();}
});
$('prepare').addEventListener('click', async () => {
  if (busy || dirty()) return;
  let task;
  try {task = JSON.parse($('task-json').value);} catch {notice('任务规范不是有效的 JSON。请修正后重试。', true); $('task-details').open = true; return;}
  busy = true; render();
  try {
    const result = await request('/api/handoff', {task, expected_revision: state.saved.revision});
    $('handoff-result').hidden = false;
    $('handoff-path').textContent = result.path;
    $('handoff-preview').textContent = JSON.stringify({selection: result.manifest.selection,
      state: result.manifest.state, execution_started: result.manifest.execution_started,
      applies_to_current_thread: result.manifest.applies_to_current_thread,
      launch_approval_required: result.manifest.launch_approval_required}, null, 2);
    notice(result.created ? '交接包已生成。任务尚未启动，需另行批准。' : '已复用相同交接包，没有重复生成或启动任务。');
  } catch (error) {notice(error.message, true);}
  finally {busy = false; render();}
});
load();
