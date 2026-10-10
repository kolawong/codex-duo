import { App } from '@modelcontextprotocol/ext-apps';

const app = new App({name: 'Fusion model desk', version: '0.3.0'},
  {availableDisplayModes: ['fullscreen']}, {autoResize: true});
let receiveInitial;
const initial = new Promise(resolve => { receiveInitial = resolve; });
let received = false;
app.ontoolresult = value => {
  if (!received) { received = true; receiveInitial(value); }
};
const ready = app.connect(undefined, {timeout: 15000}).then(async () => {
  const context = app.getHostContext();
  if (context?.displayMode === 'inline' && context.availableDisplayModes?.includes('fullscreen')) {
    await app.requestDisplayMode({mode: 'fullscreen'});
  }
});
// The first render consumes the opener result, never calls the opener again.
function decode(value) {
  if (value.isError) throw new Error(value.structuredContent?.error?.message || value.content?.[0]?.text || 'MCP 请求失败。');
  const data = value._meta?.['fusion/state'] || value.structuredContent;
  if (!data) throw new Error('宿主未返回面板数据，请刷新目录重试。');
  return data;
}
async function boundedInitial() {
  await ready;
  let timer;
  try {
    return decode(await Promise.race([initial, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('等待入口结果超时。请点击刷新目录重试。')), 10000);
    })]));
  } finally {clearTimeout(timer);}
}
window.fusionTransport = {
  initial: boundedInitial,
  async request(path, body) {
    await ready;
    const name = {'/api/state': 'fusion.state', '/api/selection': 'fusion.save', '/api/handoff': 'fusion.prepare'}[path];
    if (!name) throw new Error('未支持的面板操作。');
    return decode(await app.callServerTool({name, arguments: body || {}}, {timeout: 20000}));
  }
};
