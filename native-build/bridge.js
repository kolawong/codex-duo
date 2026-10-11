import { App } from '@modelcontextprotocol/ext-apps';

const app = new App({name: 'Codex Duo settings', version: '0.9.7'},
  {availableDisplayModes: ['fullscreen']}, {autoResize: true});
let receiveInitial;
const initial = new Promise(resolve => { receiveInitial = resolve; });
let received = false;
let projectRoot;
app.ontoolresult = value => {
  if (!received) { received = true; receiveInitial(value); }
};
function applyTheme(context) {
  if (context?.theme === 'light' || context?.theme === 'dark') {
    document.documentElement.setAttribute('data-theme', context.theme);
  }
}
app.onhostcontextchanged = applyTheme;
const ready = app.connect(undefined, {timeout: 15000}).then(async () => {
  const context = app.getHostContext();
  applyTheme(context);
  if (context?.displayMode === 'inline' && context.availableDisplayModes?.includes('fullscreen')) {
    await app.requestDisplayMode({mode: 'fullscreen'});
  }
});
// The first render consumes the opener result, never calls the opener again.
function decode(value) {
  if (value.isError) {
    const error = new Error(value.structuredContent?.error?.message || value.content?.[0]?.text || 'MCP 请求失败。');
    error.code = value.structuredContent?.error?.code;
    throw error;
  }
  const data = value._meta?.['codex-duo/state'] || value.structuredContent;
  if (!data) throw new Error('宿主未返回面板数据，请刷新目录重试。');
  return data;
}
async function boundedInitial() {
  await ready;
  let timer;
  try {
    const data = decode(await Promise.race([initial, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('等待入口结果超时。请点击刷新目录重试。')), 10000);
    })]));
    if (typeof data.project_root !== 'string' || !data.project_root.startsWith('/')) throw new Error('入口缺少明确项目路径，请从当前聊天调用设置工具。');
    if (projectRoot && projectRoot !== data.project_root) throw new Error('面板项目不一致，已停止读取。');
    projectRoot = data.project_root;
    return data;
  } finally {clearTimeout(timer);}
}
window.codexDuoTransport = {
  initial: boundedInitial,
  async request(path, body) {
    await ready;
    if (!projectRoot) await boundedInitial();
    const route = path.split('?')[0];
    const scope = path.includes('?scope=global') ? 'global' : path.includes('?scope=project') ? 'project' : undefined;
    const name = {'/api/state': 'codex_duo_state', '/api/selection': 'codex_duo_save', '/api/reset': 'codex_duo_reset'}[route];
    if (!name) throw new Error('未支持的面板操作。');
    if (body?.project_root && body.project_root !== projectRoot) throw new Error('面板不能切换到其他项目。');
    const data = decode(await app.callServerTool({name, arguments: {...body, ...(scope ? {scope} : {}), project_root: projectRoot}}, {timeout: 20000}));
    if (data.project_root && data.project_root !== projectRoot) throw new Error('面板项目不一致，已停止读取。');
    return data;
  }
};
