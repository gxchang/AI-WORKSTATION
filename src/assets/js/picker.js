(function(){"use strict";const API=location.origin;const _esc=(s)=>String(s==null?"":s).replace(/[&<>"]/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));const _thumb=(u,w)=>(typeof thumbUrl==="function"?thumbUrl(u,w):u);const TABS=[["created","创作资产"],["uploaded","主体资产"]];const AXIS={created:{param:"type",list:[["","全部类型"],["image","图片"],["audio","音频"],["video","视频"],["doc","文档"]]},uploaded:{param:"kind",list:[["","全部"],["character","角色"],["scene","场景"],["prop","道具"],["voice","声线"]]}};const PICKER_CSS=`

.ap-root{position:fixed;inset:0;z-index:2500;display:none;align-items:center;justify-content:center}
.ap-root.open{display:flex}
.ap-mask{position:absolute;inset:0;background:rgba(0,0,0,.45);backdrop-filter:blur(1px)}
.ap-modal{position:relative;display:flex;flex-direction:column;width:min(880px,92vw);max-height:84vh;background:var(--card,#fff);border:1px solid var(--line,#e3e3e8);border-radius:14px;box-shadow:0 16px 48px rgba(0,0,0,.28);overflow:hidden}
.ap-hd{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line,#e3e3e8)}
.ap-title{margin:0;font-size:15px;font-weight:600;color:var(--txt,#1d1d1f)}
.ap-x{margin-left:auto;width:30px;height:30px;border:0;border-radius:8px;background:var(--card-2,#f2f2f5);color:var(--txt,#1d1d1f);font-size:20px;line-height:1;cursor:pointer}
.ap-x:hover{background:var(--vio-soft,#ece9ff)}
.ap-filters{display:flex;flex-direction:column;gap:10px;padding:12px 18px;border-bottom:1px solid var(--line,#e3e3e8)}
.ap-tabs{display:flex;gap:6px}
.ap-tab{padding:6px 14px;border:1px solid var(--line,#e3e3e8);border-radius:9px;background:var(--card,#fff);color:var(--mut,#6b6b70);font-size:13px;font-weight:600;cursor:pointer}
.ap-tab.on{background:var(--vio,#6b4bff);border-color:var(--vio,#6b4bff);color:#fff}
.ap-chips{display:flex;gap:6px;flex-wrap:wrap}
.ap-chip{padding:5px 12px;border:1px solid var(--line,#e3e3e8);border-radius:999px;background:var(--card,#fff);color:var(--mut,#6b6b70);font-size:13px;cursor:pointer}
.ap-chip.on{background:var(--vio-soft,#ece9ff);border-color:var(--vio,#6b4bff);color:var(--vio,#6b4bff)}
.ap-grid{flex:1;overflow:auto;display:flex;flex-wrap:wrap;gap:12px;align-content:flex-start;padding:16px 18px;background:var(--card-2,#fafafb)}
.ap-empty{padding:40px;text-align:center;color:var(--mut,#6b6b70)}
.ap-loading{padding:40px;color:var(--mut,#6b6b70)}

.ap-day{flex:0 0 100%;font-size:13px;font-weight:600;color:var(--txt,#1d1d1f);padding:2px 2px 0}
.ap-card{position:relative;display:flex;flex-direction:column;align-items:center;gap:6px;width:110px;cursor:pointer}
.ap-card .src-chip{width:110px;height:110px;margin:0;border-radius:12px;box-shadow:0 0 0 2px transparent;transition:box-shadow .12s;cursor:pointer}
.ap-card:hover .src-chip{box-shadow:0 0 0 2px var(--vio-soft,#ece9ff)}
.ap-card.sel .src-chip{box-shadow:0 0 0 2px var(--vio,#6b4bff)}
.ap-card .al-audio-cover{width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#eef0ff,#e6ecff);border-radius:12px}
.ap-card .al-audio-cover .ic{width:30px;height:30px;font-size:30px;color:var(--vio,#6b4bff)}

.ap-card .al-video-cover{width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#2b2b3a,#3a3a4f);border-radius:12px}
.ap-card .al-video-cover .ic{width:34px;height:34px;font-size:34px;color:#fff}
.ap-card .ap-name{font-size:12px;color:var(--mut,#6b6b70);max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center}
.ap-ck{position:absolute;top:6px;left:6px;width:18px;height:18px;border-radius:5px;background:rgba(255,255,255,.92);border:1px solid var(--vio,#6b4bff);display:none}
.ap-card.sel .ap-ck{display:block;background:var(--vio,#6b4bff)}
.ap-card.sel .ap-ck::after{content:"";position:absolute;left:5px;top:1px;width:5px;height:10px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
.ap-foot{display:flex;align-items:center;gap:10px;padding:12px 18px;border-top:1px solid var(--line,#e3e3e8)}
.ap-selinfo{font-size:13px;color:var(--mut,#6b6b70)}
.ap-sp{flex:1}
.ap-cancel,.ap-ok{padding:7px 16px;border-radius:9px;font-size:13px;cursor:pointer;border:1px solid var(--line,#e3e3e8)}
.ap-cancel{background:var(--card,#fff);color:var(--txt,#1d1d1f)}
.ap-ok{background:var(--vio,#6b4bff);border-color:var(--vio,#6b4bff);color:#fff}
.ap-ok:disabled{opacity:.45;cursor:not-allowed}
`;let root=null,gridEl=null,emptyEl=null,selInfo=null,okBtn=null,titleEl=null;const S={source:"library",tab:"uploaded",sub:"",multi:true,items:[],sel:new Map(),onPick:null,onCancel:null};function ensureDom(){if(root)return;if(!document.getElementById("ap-style")){const st=document.createElement("style");st.id="ap-style";st.textContent=PICKER_CSS;document.head.appendChild(st);}
root=document.createElement("div");root.className="ap-root";root.id="apRoot";root.innerHTML=`
      <div class="ap-mask" data-close></div>
      <div class="ap-modal" role="dialog" aria-modal="true">
        <div class="ap-hd">
          <h4 class="ap-title">选择素材</h4>
          <button class="ap-x" type="button" title="关闭" aria-label="关闭">×</button>
        </div>
        <div class="ap-filters">
          <div class="ap-tabs" id="apTabs"></div>
          <div class="ap-chips" id="apSubChips"></div>
        </div>
        <div class="ap-grid" id="apGrid"></div>
        <div class="ap-empty" id="apEmpty" hidden>没有匹配的素材</div>
        <div class="ap-foot">
          <span class="ap-selinfo" id="apSelInfo">未选择</span>
          <span class="ap-sp"></span>
          <button class="ap-cancel" id="apCancel" type="button">取消</button>
          <button class="ap-ok" id="apOk" type="button" disabled>确定</button>
        </div>
      </div>`;document.body.appendChild(root);gridEl=root.querySelector("#apGrid");emptyEl=root.querySelector("#apEmpty");selInfo=root.querySelector("#apSelInfo");okBtn=root.querySelector("#apOk");titleEl=root.querySelector(".ap-title");root.querySelector(".ap-x").addEventListener("click",cancel);root.querySelector(".ap-mask").addEventListener("click",cancel);root.querySelector("#apCancel").addEventListener("click",cancel);okBtn.addEventListener("click",confirmPick);document.addEventListener("keydown",onKey);}
function onKey(e){if(e.key==="Escape"&&root&&root.classList.contains("open"))cancel();}
function renderFilters(){const tabs=root.querySelector("#apTabs");tabs.innerHTML=TABS.map(([v,t])=>`<button class="ap-tab${v === S.tab ? " on" : ""}" data-v="${v}">${t}</button>`).join("");tabs.querySelectorAll(".ap-tab").forEach((b)=>b.addEventListener("click",()=>{S.tab=b.dataset.v;S.sub="";renderFilters();renderGrid();}));const axis=AXIS[S.tab];const sc=root.querySelector("#apSubChips");sc.innerHTML=axis.list.map(([v,t])=>`<button class="ap-chip${v === S.sub ? " on" : ""}" data-v="${v}">${t}</button>`).join("");sc.querySelectorAll(".ap-chip").forEach((b)=>b.addEventListener("click",()=>{S.sub=b.dataset.v;renderFilters();renderGrid();}));}
function pickChipInner(a){const nm=a.label||a.name;if(a.type==="image")return`<img src="${_esc(_thumb(a.url))}" alt="${_esc(nm)}" loading="lazy" decoding="async">`;if(a.type==="audio")return`<div class="al-audio-cover"><span class="ic ic-resume"></span></div>`;if(a.type==="video")return`<div class="al-video-cover"><span class="ic ic-resume"></span></div>`;return`<div class="src-ic ic al-doc"></div>`;}
function _dateKey(ts){const d=new Date((ts||0)*1000);return`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;}
function _fmtDay(ts){const d=new Date((ts||0)*1000),now=new Date();const same=(a,b)=>a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()&&a.getDate()===b.getDate();if(same(d,now))return"今天";const y=new Date(now);y.setDate(y.getDate()-1);if(same(d,y))return"昨天";if(d.getFullYear()===now.getFullYear())return`${d.getMonth() + 1}月${d.getDate()}日`;return`${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;}
function renderGrid(){const origin=S.tab;const param=AXIS[origin].param;const list=S.items.filter((a)=>{if((a.origin||"uploaded")!==origin)return false;if(S.sub&&(a[param]||"")!==S.sub)return false;return true;});emptyEl.hidden=list.length>0;gridEl.innerHTML="";if(!list.length)return;const sorted=list.slice().sort((a,b)=>(b.created_at||0)-(a.created_at||0));const groups=new Map();sorted.forEach((a)=>{const k=_dateKey(a.created_at);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(a);});groups.forEach((items)=>{const hd=document.createElement("div");hd.className="ap-day";hd.textContent=_fmtDay(items[0].created_at);gridEl.appendChild(hd);items.forEach((a)=>{const card=document.createElement("div");const picked=S.sel.has(a.name);card.className="ap-card"+(picked?" sel":"");card.dataset.name=a.name;card.innerHTML=`<div class="src-chip src-chip-${_esc(a.type)}">${pickChipInner(a)}</div>
          <span class="ap-name">${_esc(a.label || a.name)}</span>
          <span class="ap-ck"></span>`;card.addEventListener("click",()=>toggle(a,card));gridEl.appendChild(card);});});}
function toggle(a,card){if(S.multi){if(S.sel.has(a.name)){S.sel.delete(a.name);card.classList.remove("sel");}
else{S.sel.set(a.name,a);card.classList.add("sel");}
updateSel();}else{S.sel.clear();S.sel.set(a.name,a);gridEl.querySelectorAll(".ap-card").forEach((c)=>c.classList.remove("sel"));card.classList.add("sel");confirmPick();}}
function updateSel(){const n=S.sel.size;selInfo.textContent=n?`已选 ${n} 个`:"未选择";okBtn.disabled=n===0;}
async function load(){gridEl.innerHTML='<div class="ap-loading">加载中…</div>';emptyEl.hidden=true;try{let url;if(S.source==="library")url=API+"/api/assets/registry";else{const q=new URLSearchParams({tab:S.tab||"uploaded",page:"1",size:"500"});url=API+"/api/assets/list?"+q.toString();}
const r=await fetch(url);const j=await r.json();S.items=j.items||[];renderGrid();}catch(e){gridEl.innerHTML=`<div class="ap-loading">加载失败：${_esc(e.message || e)}</div>`;}}
function open(opts){ensureDom();S.source=opts.source||"library";S.tab=opts.tab||"uploaded";S.sub=opts.sub||"";S.multi=opts.multi!==false;S.items=[];S.sel.clear();S.onPick=opts.onPick||null;S.onCancel=opts.onCancel||null;titleEl.textContent=opts.title||"选择素材";selInfo.textContent="未选择";okBtn.disabled=true;root.classList.add("open");renderFilters();load();}
function cancel(){if(!root||!root.classList.contains("open"))return;root.classList.remove("open");const c=S.onCancel;S.onCancel=null;S.onPick=null;if(typeof c==="function")c();}
function confirmPick(){const items=[...S.sel.values()];if(!items.length)return;root.classList.remove("open");const p=S.onPick;S.onPick=null;S.onCancel=null;if(typeof p==="function")p(items);}
window.AssetPicker={open,close:cancel};})();