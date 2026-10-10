import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const bundled = await build({entryPoints:[path.join(root,'native-build/bridge.js')], bundle:true,
  write:false, format:'iife', target:'es2022', minify:true, legalComments:'inline'});
let html = await readFile(path.join(root,'panel/static/index.html'),'utf8');
const css = await readFile(path.join(root,'panel/static/style.css'),'utf8');
const js = await readFile(path.join(root,'panel/static/app.js'),'utf8');
// Catch damaged HTML substitution before packaging (replacement strings interpret $&).
const code = bundled.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')+'\n'+js;
new vm.Script(code);
html = html.replace('<link rel="stylesheet" href="/style.css">',()=>'<style>'+css+'</style>')
 .replace('<script src="/app.js" defer></script>','')
 .replace('href="/" aria-label="Fusion 首页"','href="#" aria-label="Fusion 模型面板"')
 .replace(' 本地面板',' MCP App')
 .replace('独立本地页面 · 未接入 Codex 原生模型开关','通过宿主 MCP 桥接 · 仅配置后续任务')
 .replace('</body>', ()=>'<script>'+code+'</script></body>');
const extracted = html.match(/<script>([\s\S]*)<\/script>/)?.[1];
if (extracted !== code) throw new Error('Embedded script changed during HTML assembly');
new vm.Script(extracted);
await mkdir(path.join(root,'plugins/fusion-minimal/ui'),{recursive:true});
await writeFile(path.join(root,'plugins/fusion-minimal/ui/model-desk.html'),html);
console.log('Built self-contained MCP App from shared panel source.');
