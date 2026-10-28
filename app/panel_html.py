PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zotero MCP</title>
<style>
:root{--bg:#f6f6f4;--card:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#e3e3e0;--brand:#cc2936;--ok:#2ea043;--warn:#e6a21e;--bad:#da3633;--idle:#8c8c8c;--btn:#f0f0ee}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1e;--card:#262628;--fg:#ececec;--muted:#9a9a9f;--line:#3a3a3c;--btn:#333336}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,"Segoe UI","Microsoft YaHei UI","PingFang SC",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:24px 16px 48px}
header{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.logo{width:40px;height:40px;border-radius:10px;background:var(--brand);color:#fff;font-weight:700;font-size:24px;display:grid;place-items:center;position:relative}
.logo i{position:absolute;right:-4px;bottom:-4px;width:16px;height:16px;border-radius:50%;border:3px solid var(--bg);background:var(--idle)}
h1{font-size:20px;margin:0}.sub{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}
.card h2{font-size:13px;color:var(--muted);font-weight:600;margin:0 0 10px;text-transform:none}
.rows div{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line)}.rows div:last-child{border:0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;background:var(--idle)}
.v{color:var(--muted)}
.url{display:flex;gap:8px}.url input{flex:1;min-width:0;font:12.5px ui-monospace,Consolas,monospace;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--btn);color:var(--fg);cursor:pointer}
button.primary{background:var(--brand);border-color:var(--brand);color:#fff}button:disabled{opacity:.5;cursor:default}
.btns{display:flex;flex-wrap:wrap;gap:8px}
table{width:100%;border-collapse:collapse;font:12px ui-monospace,Consolas,monospace}td{padding:4px 6px;border-bottom:1px solid var(--line);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px}
.events{font:12px ui-monospace,Consolas,monospace;color:var(--muted);white-space:pre-wrap;max-height:140px;overflow:auto}
label{display:block;margin:10px 0 4px;font-weight:600}label small{font-weight:400;color:var(--muted)}
input[type=text],input[type=password]{width:100%;padding:9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
.note{font-size:12.5px;color:var(--muted);margin-top:8px}.hide{display:none}
.banner{padding:10px 12px;border-radius:8px;background:color-mix(in srgb,var(--warn) 18%,transparent);margin-bottom:12px}
.cred{font:12.5px ui-monospace,Consolas,monospace;display:grid;grid-template-columns:auto 1fr auto;gap:6px 10px;align-items:center}
details summary{cursor:pointer;color:var(--muted)}
</style></head><body><div class="wrap">
<header><div class="logo">Z<i id="logoDot"></i></div><div><h1>Zotero MCP</h1><div class="sub" id="summary">检查中…</div></div></header>

<div id="setup" class="card hide">
  <h2>首次设置</h2>
  <label>ngrok Authtoken <small>dashboard.ngrok.com → Your Authtoken</small></label>
  <input type="password" id="tok" autocomplete="off">
  <label>固定域名 <small>dashboard.ngrok.com → Domains，例如 xxx.ngrok-free.dev</small></label>
  <input type="text" id="dom" placeholder="xxxx.ngrok-free.dev">
  <div class="btns" style="margin-top:12px"><button class="primary" id="btnSetup">保存并启动</button></div>
  <details style="margin-top:12px"><summary>从旧版脚本迁移（E:\zotero_mcp）</summary>
    <label>旧版文件夹</label><input type="text" id="legacy" value="E:\zotero_mcp">
    <div class="note">会读取旧的管理员密码和第一道用户名密码，沿用后 claude.ai 连接器无需改 URL。迁移前请先停止旧版（运行 stop.ps1 和 remove-autostart.cmd）。</div>
    <div class="btns" style="margin-top:8px"><button id="btnLegacy">读取旧版配置</button></div>
  </details>
  <details style="margin-top:8px"><summary>从配置包导入（换电脑）</summary>
    <label>配置包 (.zmcp)</label><input type="file" id="impFile" accept=".zmcp">
    <label>口令</label><input type="password" id="impPw">
    <div class="btns" style="margin-top:8px"><button id="btnImport">导入并启动</button></div>
  </details>
</div>

<div id="main" class="hide">
  <div class="card"><h2>状态</h2><div class="rows">
    <div><span><span class="dot" id="d_zotero"></span>Zotero 本地 API</span><span class="v" id="v_zotero">…</span></div>
    <div><span><span class="dot" id="d_server"></span>MCP 服务器（仅本机）</span><span class="v" id="v_server">…</span></div>
    <div><span><span class="dot" id="d_tunnel"></span>ngrok 隧道</span><span class="v" id="v_tunnel">…</span></div>
    <div><span><span class="dot" id="d_auth"></span>白名单</span><span class="v" id="v_auth">…</span></div>
  </div></div>

  <div class="card"><h2>连接器 URL（claude.ai → 设置 → 连接器 → 添加自定义连接器）</h2>
    <div class="url"><input id="url" readonly><button id="btnCopy">复制</button></div></div>

  <div class="card"><h2>操作</h2><div class="btns">
    <button class="primary" id="btnStart">启动 / 重启</button><button id="btnStop">停止</button>
    <button id="btnAuth">进入授权模式 15 分钟</button><button id="btnAuthEnd" class="hide">结束授权模式</button>
  </div><div class="note">授权模式：临时放行本机公网 IP，用于在 claude.ai 首次连接或重新授权；到时自动恢复，只留 Anthropic 的 IP。</div></div>

  <div class="card"><h2>最近请求</h2><table id="reqs"></table></div>
  <div class="card"><h2>事件</h2><div class="events" id="events"></div></div>

  <div class="card"><h2>设置</h2>
    <label><input type="checkbox" id="auto"> 开机自动启动（同时会打开 Zotero）</label>
    <details style="margin-top:10px"><summary>查看登录凭证（授权时使用）</summary><div class="cred" id="cred" style="margin-top:8px"></div></details>
    <details style="margin-top:10px"><summary>导出配置包（换电脑用）</summary>
      <label>设置口令 <small>至少 8 位，导入时需要</small></label><input type="password" id="expPw">
      <div class="btns" style="margin-top:8px"><button id="btnExport">导出 .zmcp</button></div>
      <div class="note">配置包包含 ngrok 令牌、所有密码和 claude.ai 授权记录，已用口令加密。新电脑导入后无需重新授权。</div></details>
    <div class="btns" style="margin-top:12px"><button id="btnLogs">打开日志文件夹</button><button id="btnNgrok">更新 ngrok</button></div>
    <div class="note" id="ver"></div>
  </div>
</div>
</div>
<script>
const T="__TOKEN__";const H={"X-Token":T,"Content-Type":"application/json"};
const $=id=>document.getElementById(id);
const C={ok:"var(--ok)",warn:"var(--warn)",bad:"var(--bad)",idle:"var(--idle)"};
async function api(p,b){const r=await fetch(p,{method:b===undefined?"GET":"POST",headers:H,body:b===undefined?undefined:JSON.stringify(b)});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j}
function row(k,lv,txt){$("d_"+k).style.background=C[lv];$("v_"+k).textContent=txt}
let authOn=false;
async function refresh(){try{const s=await api("/api/status");
 $("setup").classList.toggle("hide",s.configured);$("main").classList.toggle("hide",!s.configured);
 $("logoDot").style.background=C[s.level];
 $("summary").textContent=!s.configured?"尚未设置":s.paused?"已停止（自动守护已暂停）":s.level=="ok"?"在线：claude.ai / 手机 / Office 均可访问":s.zotero!=200?"等待 Zotero 启动…":"部分异常，可点「启动 / 重启」";
 row("zotero",s.zotero==200?"ok":"bad",s.zotero==200?"正常":s.zotero==0?"未运行":"HTTP "+s.zotero);
 row("server",s.server?"ok":"bad",s.server?"运行中，要求认证":"未运行");
 row("tunnel",s.tunnel?"ok":"bad",s.tunnel?"在线":"未连接");
 authOn=s.auth_mode_left>0;
 row("auth",authOn?"warn":"ok",authOn?`授权模式：放行 ${s.auth_mode_ip}，剩 ${Math.ceil(s.auth_mode_left/60)} 分钟`:"仅 Anthropic");
 $("btnAuth").classList.toggle("hide",authOn);$("btnAuthEnd").classList.toggle("hide",!authOn);
 if(document.activeElement!==$("url"))$("url").value=s.url;
 $("reqs").innerHTML=(s.requests.length?s.requests:[{time:"",method:"",path:"（暂无）",status:"",from:""}]).map(q=>`<tr><td>${q.time}</td><td>${q.method}</td><td>${q.path}</td><td>${q.status}</td><td>${q.from}</td></tr>`).join("");
 $("events").textContent=s.events.join("\n")||"（暂无）";
 $("auto").checked=s.autostart;$("ver").textContent="版本 __VERSION__ · "+(s.ngrok_version||"ngrok 未安装");
}catch(e){$("summary").textContent="面板连接中断："+e.message}}
async function act(btn,fn){btn.disabled=true;try{await fn()}catch(e){alert(e.message)}finally{btn.disabled=false;refresh()}}
$("btnSetup").onclick=e=>act(e.target,()=>api("/api/setup",{ngrok_authtoken:$("tok").value,domain:$("dom").value}));
$("btnLegacy").onclick=e=>act(e.target,async()=>{const r=await api("/api/import-legacy",{folder:$("legacy").value});if(r.domain&&!$("dom").value)$("dom").value=r.domain;alert(`已读取：域名 ${r.domain||"无"}；管理员密码 ${r.found_password?"有":"无"}；第一道凭证 ${r.found_basic?"有":"无"}。\n请填写 ngrok Authtoken 后点「保存并启动」。`)});
$("btnImport").onclick=e=>act(e.target,async()=>{const f=$("impFile").files[0];if(!f)throw new Error("请选择配置包");const r=await fetch("/api/import",{method:"POST",headers:{"X-Token":T,"X-Passphrase":$("impPw").value},body:await f.arrayBuffer()});if(!r.ok)throw new Error((await r.json()).error)});
$("btnStart").onclick=e=>act(e.target,()=>api("/api/start",{}));
$("btnStop").onclick=e=>act(e.target,()=>api("/api/stop",{}));
$("btnAuth").onclick=e=>act(e.target,()=>api("/api/auth-mode",{minutes:15}));
$("btnAuthEnd").onclick=e=>act(e.target,()=>api("/api/auth-mode-end",{}));
$("btnCopy").onclick=()=>{navigator.clipboard.writeText($("url").value);$("btnCopy").textContent="已复制";setTimeout(()=>$("btnCopy").textContent="复制",1500)};
$("auto").onchange=e=>api("/api/autostart",{enabled:e.target.checked}).then(refresh);
$("btnLogs").onclick=()=>api("/api/open-logs",{});
$("btnNgrok").onclick=e=>act(e.target,async()=>{const r=await api("/api/ngrok-update",{});alert(r.output||"完成")});
$("btnExport").onclick=e=>act(e.target,async()=>{const r=await fetch("/api/export",{method:"POST",headers:H,body:JSON.stringify({passphrase:$("expPw").value})});if(!r.ok)throw new Error((await r.json()).error);const b=await r.blob();const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="zotero-mcp-backup.zmcp";a.click()});
document.querySelector("details summary").parentElement;
document.querySelectorAll("#main details")[0].addEventListener("toggle",async ev=>{if(!ev.target.open)return;const c=await api("/api/credentials");
 const items=[["第一道 用户名",c.basic_user],["第一道 密码",c.basic_password],["管理员密码",c.admin_password]];
 $("cred").innerHTML="";items.forEach(([k,v])=>{const a=document.createElement("span");a.textContent=k;const b=document.createElement("code");b.textContent=v;const btn=document.createElement("button");btn.textContent="复制";btn.onclick=()=>navigator.clipboard.writeText(v);$("cred").append(a,b,btn)})});
refresh();setInterval(refresh,5000);
</script></body></html>"""
