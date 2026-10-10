#!/usr/bin/env python3
"""Development host simulator. Not Codex installation or native-host verification."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fusion_mcp', ROOT / 'plugins/fusion-minimal/mcp/server.py')
mcp = importlib.util.module_from_spec(spec); spec.loader.exec_module(mcp)
TOKEN = secrets.token_urlsafe(24)
HTML = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Fusion · MCP 测试宿主</title>
<style>body{margin:0;background:#151916;color:#e5eddf;font:14px system-ui}header{padding:14px 22px;border-bottom:1px solid #465042}label{margin-right:16px}select,button{margin:8px;padding:8px;background:#263022;color:inherit;border:1px solid #667659;border-radius:5px}iframe{display:block;width:100%;height:1000px;border:0}#log{color:#c7e788}</style></head><body>
<header><strong>MCP 开发测试宿主 · 不是 Codex 原生安装验证</strong><p>原生设置协议模拟：与下方 MCP App 共用临时状态，不写正式配置。</p><div id="settings"></div><button id="reload">读取设置</button><button id="update">保存设置</button><span id="log">读取中</span></header>
<iframe title="Fusion MCP App" sandbox="allow-scripts" src="/app"></iframe><script>
const frame=document.querySelector('iframe'); let initialCount=0;
async function rpc(method,params){const res=await fetch('/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Fusion-Token':'__TOKEN__'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})});const data=await res.json();if(data.error)throw Error(data.error.message);return data.result;}
async function call(name,args={}){const result=await rpc('tools/call',{name,arguments:args});if(result.isError)throw Error(result.content[0].text);return result;}
function send(data){frame.contentWindow.postMessage({jsonrpc:'2.0',...data},'*');}
window.addEventListener('message',async event=>{if(event.source!==frame.contentWindow||event.data?.jsonrpc!=='2.0')return;const data=event.data;try{
 if(data.method==='ui/initialize'){send({id:data.id,result:{protocolVersion:data.params.protocolVersion,hostInfo:{name:'Fusion local test host',version:'0.3.1'},hostCapabilities:{serverTools:{}},hostContext:{displayMode:'fullscreen',availableDisplayModes:['fullscreen'],platform:'desktop',theme:'dark'}}});}
 else if(data.method==='ui/notifications/initialized'){if(initialCount++===0)send({method:'ui/notifications/tool-result',params:await call('fusion.open')});}
 else if(data.method==='tools/call'){send({id:data.id,result:await rpc('tools/call',data.params)});}
 else if(data.id!==undefined){send({id:data.id,error:{code:-32601,message:'Unsupported in test host'}});}
}catch(error){if(data.id!==undefined)send({id:data.id,error:{code:-32603,message:error.message}});document.querySelector('#log').textContent=error.message;}});
async function read(){try{const data=(await call('fusion.settings_read')).structuredContent;const box=document.querySelector('#settings');box.replaceChildren();for(const [key,schema]of Object.entries(data.schema.properties)){const label=document.createElement('label');label.textContent=schema.title;const select=document.createElement('select');select.id='setting-'+key;for(const v of schema.enum)select.add(new Option(v,v));select.value=data.values[key];label.append(select);box.append(label);}document.querySelector('#log').textContent='设置读取成功';}catch(error){document.querySelector('#log').textContent=error.message;}}
document.querySelector('#reload').onclick=read;document.querySelector('#update').onclick=async()=>{try{const set={};for(const e of document.querySelectorAll('#settings select'))set[e.id.slice(8)]=e.value;await call('fusion.settings_update',{set});document.querySelector('#log').textContent='设置已保存 · 未启动任务';}catch(error){document.querySelector('#log').textContent=error.message;}};read();
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, status, body, kind='application/json'):
        data = body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type', kind+'; charset=utf-8')
        self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(data)))
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-src 'self'; connect-src " + ("'none'" if self.path == '/app' else "'self'") + "; img-src data:; base-uri 'none'; form-action 'none'")
        self.end_headers(); self.wfile.write(data)
    def valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        if not self.valid_host(): return self.reply(403, {})
        if self.path == '/': return self.reply(200, HTML.replace('__TOKEN__',TOKEN),'text/html')
        if self.path == '/app': return self.reply(200, (mcp.PLUGIN/'ui/model-desk.html').read_text(),'text/html')
        return self.reply(404,{})
    def do_POST(self):
        if not self.valid_host() or self.path != '/rpc' or not secrets.compare_digest(self.headers.get('X-Fusion-Token',''),TOKEN):
            return self.reply(403,{})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=65536: return self.reply(400,{})
            data=json.loads(self.rfile.read(n)); result=self.server.mcp.dispatch(data)
            return self.reply(200,result)
        except (ValueError,OSError): return self.reply(400,{})


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='fusion-native-qa-') as root:
        os.environ['CODEX_HOME'] = str(Path(root)/'codex-home')
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
        server.mcp=mcp.MCPServer(mcp.FusionService(Path(root)/'.fusion'))
        print(f'TEST HOST ONLY http://127.0.0.1:{server.server_port} | temporary state {root}',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
