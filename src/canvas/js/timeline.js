window.Timeline=(function(){"use strict";var API=location.origin;var TL_MIN=0.05;var FRAME=0.04;var IMG_LEN=3;var PPS_COMFORT=28;var SNAP_PX=7;var ORIGIN_PAD=0.5;var GUT=26;var PAD_R=8;var NULL_HOST={save:function(){},render:function(){},renderPanels:function(){},snapshot:function(){return{nodes:[],edges:[]};},push:function(){},undo:function(){},redo:function(){},canUndo:function(){return false;},canRedo:function(){return false;},nodeById:function(){return null;},selected:function(){return null;},canvasAssets:function(){return[];},toast:function(){}};var HOST=NULL_HOST;var SPR={};var WAV={};var PRB={};var MEDIA={};var FS=null;var DRAG=null;function tlData(n){if(!n.data)n.data={};var d=n.data.tl;if(!d||typeof d!=="object")d=n.data.tl={};if(!d.segs||typeof d.segs!=="object")d.segs={};if(!Array.isArray(d.segs.video))d.segs.video=[];if(!Array.isArray(d.segs.audio))d.segs.audio=[];var u=d.ui;if(!u||typeof u!=="object")u=d.ui={};if(typeof u.T!=="number")u.T=null;if(typeof u.pps!=="number")u.pps=PPS_COMFORT;if(typeof u.snap!=="boolean")u.snap=true;if(typeof u.playing!=="boolean")u.playing=false;if(!u.muted||typeof u.muted!=="object")u.muted={video:false,audio:false};if(!u.sel||typeof u.sel!=="object")u.sel={track:"",id:""};if(typeof u.ar!=="number")u.ar=0;["video","audio"].forEach(function(t){d.segs[t].forEach(function(s){if(!s)return;if(s.dur!=null&&s.len==null){s.len=s.dur;delete s.dur;}
if(s.start!=null&&s.in==null){s.in=s.start;delete s.start;}
if(typeof s.in!=="number")s.in=0;if(typeof s.at!=="number")s.at=0;if(typeof s.len!=="number")s.len=IMG_LEN;if(typeof s.total!=="number")s.total=0;if(!s.id)s.id="s"+Math.random().toString(36).slice(2,8);});});return d;}
function uiOf(n){return tlData(n).ui;}
function segs(n,t){return tlData(n).segs[t];}
function segById(n,t,id){var a=segs(n,t);for(var i=0;i<a.length;i++)if(a[i]&&a[i].id===id)return a[i];return null;}
function idxOf(a,id){for(var i=0;i<a.length;i++)if(a[i]&&a[i].id===id)return i;return-1;}
function computeOrigin(n){var d=tlData(n),mn=null;function scan(t){(d.segs[t]||[]).forEach(function(s){var at=s.at||0;if(mn===null||at<mn)mn=at;});}
scan("video");if(mn===null)scan("audio");if(mn===null)return 0;return Math.max(0,mn-ORIGIN_PAD);}
function originOf(n){var ui=tlData(n).ui;if(typeof ui.origin!=="number")ui.origin=computeOrigin(n);return ui.origin;}
function resetOrigin(n){tlData(n).ui.origin=null;}
function contentPx(n,t,pps){var mx=0;segs(n,t).forEach(function(s){mx=Math.max(mx,pxOf(n,(s.at||0)+(s.len||0),pps));});return mx;}
function zoomOf(n){if(FS&&FS.id&&(!n||FS.id===n.id))return 1;return(HOST.zoom&&HOST.zoom())||1;}
function pxOf(n,t,pps){return Math.round(((t||0)-originOf(n))*(pps||tlData(n).ui.pps||PPS_COMFORT));}
function spanOf(n){var d=tlData(n),mx=0,o=originOf(n);["video","audio"].forEach(function(t){var a=d.segs[t];if(a.length){var last=a[a.length-1];mx=Math.max(mx,(last.at||0)+(last.len||0)-o);}});var el=document.querySelector('.tl-fs[data-tl-node="'+n.id+'"] .tl-scroll')||document.querySelector('.cs-node[data-node="'+n.id+'"] .tl-scroll');var cw=el?el.clientWidth:0;if(cw<GUT+40)cw=420+GUT+PAD_R;var vis=cw-GUT-PAD_R;return Math.max(mx,Math.max(vis,1)/(d.ui.pps||PPS_COMFORT),1);}
function availW(n){var el=document.querySelector('.tl-fs[data-tl-node="'+n.id+'"] .tl-scroll')||document.querySelector('.cs-node[data-node="'+n.id+'"] .tl-scroll');var cw=el?el.clientWidth:0;if(cw<GUT+40)cw=420+GUT+PAD_R;return Math.floor(Math.max(120,cw-GUT-PAD_R));}
function trackW(n,t){var w=availW(n),pps=uiOf(n).pps;var c=t?contentPx(n,t,pps):Math.max(contentPx(n,"video",pps),contentPx(n,"audio",pps));return Math.max(120,c>w?Math.ceil(c):w);}
function endOf(n){var d=tlData(n),mx=0;["video","audio"].forEach(function(t){(d.segs[t]||[]).forEach(function(s){mx=Math.max(mx,(s.at||0)+(s.len||0));});});return mx;}
function filmLen(n){return Math.max(0,endOf(n)-filmStart(n));}
function filmStart(n){var a=segs(n,"video");if(a.length)return a[0].at||0;var b=segs(n,"audio");if(b.length)return b[0].at||0;return 0;}
function filmCur(n){return clamp((uiOf(n).T||0)-filmStart(n),0,filmLen(n));}
function reflow(a,from){if(!a||!a.length)return;for(var i=Math.max(0,from||0);i<a.length;i++){a[i].at=(i===0)?0:(a[i-1].at+a[i-1].len);}}
function clamp(v,lo,hi){return v<lo?lo:(v>hi?hi:v);}
function fmt(t,total){t=Math.max(0,Math.round((t||0)*1000)/1000);total=total||0;var hh=Math.floor(t/3600),mm=Math.floor((t%3600)/60),ss=t%60;var sec=(ss<10?"0":"")+ss.toFixed(3);if(total>=3600)return hh+":"+pad(mm)+":"+sec;return mm+":"+sec;}
function fmtCur(t,total){return fmt(t,total);}
function fmtBrief(t){t=Math.max(0,t||0);var hh=Math.floor(t/3600),mm=Math.floor((t%3600)/60),ss=Math.floor(t%60);return hh?(hh+":"+pad(mm)+":"+pad(ss)):(mm+":"+pad(ss));}
function pad(v){v=Math.round(v);return v<10?"0"+v:""+v;}
function probe(url){if(PRB[url])return Promise.resolve(PRB[url]);return fetch(API+"/api/media/probe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:url})}).then(function(r){return r.json();}).then(function(j){if(j&&j.error)throw new Error(j.error);PRB[url]=j;return j;});}
function wave(url){if(WAV[url])return Promise.resolve(WAV[url]);return fetch(API+"/api/media/waveform",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:url,buckets:600})}).then(function(r){return r.json();}).then(function(j){if(j&&j.error)throw new Error(j.error);WAV[url]=j;return j;});}
function sprite(seg,H,pps){var key=seg.url+"|"+(seg.in||0).toFixed(2)+"|"+(seg.len||0).toFixed(2)+"|"+H+"|"+Math.round(pps);if(SPR[key])return Promise.resolve(SPR[key]);var ar=(seg.vw&&seg.vh)?(seg.vw/seg.vh):(16/9);var fw=Math.max(8,H*ar);var W=Math.max(2,(seg.len||0)*pps);var cnt=clamp(Math.ceil(W/fw),2,24);return new Promise(function(res){var v=document.createElement("video");v.preload="auto";v.muted=true;v.style.cssText="position:absolute;left:-9999px;width:1px;height:1px";document.body.appendChild(v);var cv=document.createElement("canvas");cv.width=Math.max(2,Math.round(cnt*fw));cv.height=H;var ctx=cv.getContext("2d");var i=0,done=false;ctx.fillStyle="#ece9f6";ctx.fillRect(0,0,cv.width,cv.height);function fin(){if(done)return;done=true;var url2=null;try{url2=cv.toDataURL("image/jpeg",0.72);}catch(e){url2=null;}
try{v.remove();}catch(e){}
if(url2)SPR[key]=url2;res(url2);}
v.onerror=fin;v.onloadeddata=function(){if(!v.videoWidth){fin();return;}
ar=v.videoWidth/v.videoHeight;fw=Math.max(8,H*ar);step();};function draw(){try{ctx.drawImage(v,i*fw,0,fw,H);}catch(e){}
i++;if(i>=cnt){fin();return;}
step();}
function step(){var t=(seg.in||0)+(seg.len||0)*(i+0.5)/cnt;v.onseeked=draw;try{v.currentTime=t;}catch(e){draw();}}
v.src=seg.url;setTimeout(fin,8000);});}
var _queue=Promise.resolve();function acceptAsset(nid,item){_queue=_queue.then(function(){return acceptOne(nid,item);}).catch(function(){return false;});return _queue;}
function acceptOne(nid,item){var n=HOST.nodeById(nid);if(!n)return Promise.resolve(false);var kind=item.kind||"image";var track=(kind==="audio")?"audio":"video";var url=localUrl(item.url);var p=(kind==="image")?Promise.resolve({kind:"image",duration:0,width:item.vw||0,height:item.vh||0}):probe(url);return p.then(function(j){if(j&&j.error){alert("该视频源有问题，无法读取时长");return false;}
var d=tlData(n);var a=d.segs[track];var idx=a.length;var T=d.ui.T;if(typeof T==="number"){for(var i=0;i<a.length;i++){if(T>=a[i].at-1e-6&&T<=a[i].at+a[i].len+1e-6){idx=i+1;break;}}}
var seg={id:"s"+Math.random().toString(36).slice(2,8),url:url,kind:kind,name:item.name||"",at:0,len:(kind==="image")?IMG_LEN:(j.duration||IMG_LEN),in:0,total:(kind==="image")?0:(j.duration||0),vw:j.width||0,vh:j.height||0};if(kind!=="image"){seg.total=j.duration||0;seg.len=seg.total>0?seg.total:IMG_LEN;}
HOST.push(HOST.snapshot());a.splice(idx,0,seg);reflow(a,idx);var landed="";if(item.land&&HOST.addAssetNode){landed=HOST.addAssetNode(nid,{url:seg.url,kind:kind,name:seg.name},!FS)||"";}
if(HOST.linkEdge){var ef=landed||item.edgeFrom||item.nodeId;if(ef)HOST.linkEdge(ef,nid);}
d.ui.sel={track:track,id:seg.id};if(d.ui.T==null)d.ui.T=0;if(!d.ui.ar&&seg.vw&&seg.vh)d.ui.ar=seg.vw/seg.vh;resetOrigin(n);HOST.save();render(nid);if(HOST.renderEdges)HOST.renderEdges();if(FS&&FS.id===nid)fillLib(n);if(HOST.toast){HOST.toast("已加入"+(track==="audio"?"音频轨":"画面轨")+"："+(seg.name||"素材"));}
return true;}).catch(function(e){alert("该视频源有问题，无法读取时长");return false;});}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function thumb(u,w){return(typeof thumbUrl==="function")?thumbUrl(u,w):u;}
function ico(name){return'<span class="ic '+name+'"></span>';}
function laneVW(n){var sc=document.querySelector('.tl-fs[data-tl-node="'+n.id+'"] .tl-scroll')||document.querySelector('.cs-node[data-node="'+n.id+'"] .tl-scroll');var vw=sc?sc.clientWidth:0;return vw>GUT+40?(vw-GUT-PAD_R):600;}
var COMFORT_TOL=0.06;function comfortSliderPct(n){var vis=laneVW(n)/PPS_COMFORT;return+(clamp((150-vis)/135,0,1)*100).toFixed(2);}
function zoomSizeText(n){return(laneVW(n)/(uiOf(n).pps||PPS_COMFORT)).toFixed(1)+"s";}
function syncZoomSize(n){Array.prototype.forEach.call(document.querySelectorAll('.tl-fs[data-tl-node="'+n.id+'"] .tl-zoom-size'),function(el){el.textContent=zoomSizeText(n);});}
function paintTicks(root,n){var ruler=root.querySelector(".tl-ruler");if(!ruler)return;Array.prototype.forEach.call(ruler.querySelectorAll(".tl-tick"),function(x){x.remove();});ruler.insertAdjacentHTML("afterbegin",ticksHtml(n));}
var zoomRaf=0;function applyZoomLive(n){if(zoomRaf)return;zoomRaf=requestAnimationFrame(function(){zoomRaf=0;if(!HOST.nodeById(n.id))return;Array.prototype.forEach.call(document.querySelectorAll('.tl-panel[data-tl-node="'+n.id+'"], .tl-fs[data-tl-node="'+n.id+'"]'),function(root){paintTicks(root,n);});paint(n);syncZoomSize(n);});}
function setZoomFromSlider(n,raw,commit){var u=uiOf(n),vw=laneVW(n);var p=clamp((+raw||0)/1000,0,1);var cP=clamp((150-vw/PPS_COMFORT)/135,0,1);var vis=(Math.abs(p-cP)<=COMFORT_TOL)?(vw/PPS_COMFORT):snapZoomLevel(150-p*135);u.pps=clamp(vw/vis,4,1000);if(commit){HOST.save();render(n);}}
function onZoomInput(e){var inp=e.target;if(!inp||!inp.getAttribute||inp.getAttribute("data-tl-ctrl")!=="zoom")return;var panel=inp.closest(".tl-fs, .tl-panel");var n=panel&&HOST.nodeById(panel.getAttribute("data-tl-node")||(FS&&FS.id));if(!n)return;var raw=+inp.value||0;inp.style.setProperty("--fill",(raw/10).toFixed(2)+"%");setZoomFromSlider(n,raw,false);applyZoomLive(n);}
function onZoomChange(e){var inp=e.target;if(!inp||!inp.getAttribute||inp.getAttribute("data-tl-ctrl")!=="zoom")return;var panel=inp.closest(".tl-fs, .tl-panel");var n=panel&&HOST.nodeById(panel.getAttribute("data-tl-node")||(FS&&FS.id));if(!n)return;setZoomFromSlider(n,+inp.value||0,true);}
function zoomStep(n,k){var u=uiOf(n);u.pps=clamp((u.pps||PPS_COMFORT)*k,4,1000);HOST.save();render(n);}
function zoomSliderVal(n){var u=tlData(n).ui;var vw=laneVW(n);var vis=vw/(u.pps||PPS_COMFORT);return Math.round(clamp((150-vis)/135,0,1)*1000);}
function barHtml(n,isFS){var d=tlData(n),u=d.ui,has=!!(d.segs.video.length||d.segs.audio.length);var sel=!!u.sel.id,dis=function(ok){return ok?"":" dis";};return'<div class="tl-bar-l">'
+'<button data-tl-ctrl="undo" title="撤销"'+dis(HOST.canUndo())+'>'+ico("ic-undo")+'</button>'
+'<button data-tl-ctrl="redo" title="重做"'+dis(HOST.canRedo())+'>'+ico("ic-redo")+'</button>'
+'<button data-tl-ctrl="split" title="分隔"'+dis(has)+'>'+ico("ic-tl-split")+'</button>'
+'<button data-tl-ctrl="trim-in" title="向左剪裁"'+dis(has&&sel)+'>'+ico("ic-tl-left")+'</button>'
+'<button data-tl-ctrl="trim-out" title="向右剪裁"'+dis(has&&sel)+'>'+ico("ic-tl-right")+'</button>'
+'<button data-tl-ctrl="del" title="删除选中段"'+dis(has&&sel)+'>'+ico("ic-trash")+'</button>'
+'</div>'
+(isFS?"":'<div class="tl-bar-c">'
+'<button data-tl-ctrl="play" title="播放 / 暂停"'+dis(has)+'>'+ico(u.playing?"ic-pause":"ic-play")+'</button>'
+'<span class="tl-tc">'+fmtCur(filmCur(n),filmLen(n))+' / '+fmt(filmLen(n),filmLen(n))+'</span>'
+'</div>')
+'<div class="tl-bar-r">'+(isFS?('<span class="tl-fs-zoom">'
+'<button data-tl-ctrl="zoom-out" title="缩小时间轴">－</button>'
+'<span class="tl-zoom-wrap">'
+'<input type="range" min="0" max="1000" value="'+zoomSliderVal(n)+'" data-tl-ctrl="zoom"'
+' style="--fill:'+(zoomSliderVal(n)/10).toFixed(2)+'%;--cmf:'
+comfortSliderPct(n)+'%">'
+'</span>'
+'<button data-tl-ctrl="zoom-in" title="放大时间轴">＋</button>'
+'<span class="tl-zoom-size" title="当前时间轴每屏可见时长">'+zoomSizeText(n)+'</span>'
+'</span>'
+'<button data-tl-ctrl="snap" class="tl-fs-snap'+(u.snap?" on":"")+'" title="素材首尾吸附">'
+ico("ic-tl-snap")+'</button>'):'<button data-tl-ctrl="export" title="导出成片"'+dis(has)+'>'+ico("ic-download")+'</button>'
+'<button data-tl-ctrl="full" title="全屏编辑">'+ico("ic-fit")+'</button>')
+'</div>';}
function tickStepOf(pps){var cands=[0.1,0.2,0.5,1,2,5,10,15,30,60,120,300];for(var i=0;i<cands.length;i++){if(cands[i]*pps>=64)return cands[i];}
return 600;}
function fmtTick(t,step){t=Math.max(0,t||0);var d=(step>=1)?0:((step>=0.5)?1:2);if(d===0)return fmt(t,0);var hh=Math.floor(t/3600),mm=Math.floor((t%3600)/60),ss=t%60;var sr=ss.toFixed(d);if(parseFloat(sr)<10)sr="0"+sr;return(hh?(hh+":"+pad(mm)):mm)+":"+sr;}
function ticksHtml(n){var d=tlData(n),pps=d.ui.pps,span=spanOf(n),o=originOf(n);if(!(pps>0))return"";var total=span*pps,step=tickStepOf(pps),sub=(step>=1)?step/5:step/2;if(!(step>0)||!(sub>0))return"";var out="";var i0=Math.ceil(o/step-1e-9);for(var k=0,j;;k++){var t=(i0+k)*step;if(t-o>span+1e-6)break;var x=Math.round((t-o)*pps);out+='<span class="tl-tick m" style="left:'+x+'px">'
+(x+30>total?"":fmtTick(t,step))+'</span>';for(j=1;j*sub<step-1e-6;j++){var xs=Math.round((t-o+sub*j)*pps);if(xs>total)break;out+='<span class="tl-tick s" style="left:'+xs+'px"></span>';}}
return out;}
function segHtml(n,t,s){var u=tlData(n).ui,pps=u.pps;var w=Math.max(6,(s.len||0)*pps);var sel=(u.sel.track===t&&u.sel.id===s.id)?" sel":"";var inner=(t==="audio")?'<canvas class="tl-wave"></canvas>':'<div class="tl-film"></div>';return'<div class="tl-seg'+sel+'" data-tl-seg="'+s.id+'" data-track="'+t+'"'
+' style="left:'+pxOf(n,s.at,pps)+'px;width:'+Math.round(w)+'px">'
+'<span class="tl-grip tl-grip-l" data-tl-ctrl="trim-in"></span>'
+inner
+'<span class="tl-dur">'+(s.len||0).toFixed(1)+'s</span>'
+'<span class="tl-grip tl-grip-r" data-tl-ctrl="trim-out"></span>'
+'</div>';}
function laneBodyHtml(n,t){var a=tlData(n).segs[t];return a.length?a.map(function(s){return segHtml(n,t,s);}).join(""):'<button class="tl-empty" data-tl-ctrl="add" data-track="'+t+'">＋ 添加素材到时间线</button>';}
function trackHtml(n,t){var d=tlData(n),pps=d.ui.pps,span=spanOf(n);var body=laneBodyHtml(n,t);var base=trackW(n,t);return'<div class="tl-trow">'
+'<button class="tl-mute'+(d.ui.muted[t]?" off":"")+'" data-tl-ctrl="mute" data-track="'+t+'" title="音量">'
+ico(d.ui.muted[t]?"ic-volume-off":"ic-volume")+'</button>'
+'<div class="tl-lane" data-track="'+t+'" style="width:'+base+'px">'
+body
+'</div></div>';}
function addColHtml(n){var d=tlData(n);var btns=["video","audio"].map(function(t){return d.segs[t].length?('<button class="tl-add" data-tl-ctrl="add" data-track="'+t+'" title="添加素材">＋</button>'):"";}).join("");return btns?'<div class="tl-addcol">'+btns+'</div>':"";}
function syncAddCol(root,n){var col=root.querySelector(".tl-addcol");var html=addColHtml(n);if(col){if(html)col.innerHTML=html.replace(/^<div class="tl-addcol">|<\/div>$/g,"");else col.remove();}else if(html){var tracks=root.querySelector(".tl-tracks");if(tracks)tracks.insertAdjacentHTML("beforeend",html);}}
function prevInner(n){var u=tlData(n).ui;var noFrame=u.T==null||!curSeg(n,"video",u.T);return'<div class="tl-prev-slot"></div>'
+'<canvas class="tl-prev-w"></canvas>'
+(noFrame?'<div class="tl-prev-ph">'+ico("ic-film")+'<span>暂无画面</span></div>':"");}
function ensurePool(st){if(!st.vA){st.vA=document.createElement("video");st.vA.className="tl-prev-v";st.vA.setAttribute("playsinline","");}
if(!st.vB){st.vB=document.createElement("video");st.vB.className="tl-prev-v idle";st.vB.setAttribute("playsinline","");st.vB.muted=true;}
if(!st.img){st.img=document.createElement("img");st.img.className="tl-prev-i";st.img.setAttribute("alt","");}
if(st.act!=="A"&&st.act!=="B")st.act="A";if(!st.video)st.video=(st.act==="B")?st.vB:st.vA;return st;}
function poolOf(n){return ensurePool(media(n));}
function actV(n){var st=ensurePool(media(n));return st.act==="B"?st.vB:st.vA;}
function idleV(n){var st=ensurePool(media(n));return st.act==="B"?st.vA:st.vB;}
function swapV(n){var st=poolOf(n);st.act=(st.act==="B")?"A":"B";markV(n);st.video=actV(n);}
function markV(n){var st=ensurePool(media(n));if(st.vA)st.vA.classList.toggle("idle",st.act!=="A");if(st.vB)st.vB.classList.toggle("idle",st.act!=="B");}
function mountPrev(n){var st=poolOf(n);markV(n);var host=(FS&&FS.id===n.id&&FS.el)?FS.el:document.querySelector('.cs-node[data-node="'+n.id+'"]');var pv=host?host.querySelector(".tl-prev"):null;if(pv){var slot=pv.querySelector(".tl-prev-slot")||pv;[st.img,st.vA,st.vB].forEach(function(v){if(v&&v.parentNode!==slot)slot.appendChild(v);});}
Array.prototype.forEach.call(document.querySelectorAll("img.tl-prev-i"),function(el){if(el!==st.img)el.remove();});Array.prototype.forEach.call(document.querySelectorAll("video.tl-prev-v"),function(el){if(el!==st.vA&&el!==st.vB){try{el.pause();}catch(e){}el.remove();}});}
function prevHost(n){var host=(FS&&FS.id===n.id&&FS.el)?FS.el:document.querySelector('.cs-node[data-node="'+n.id+'"]');return host?host.querySelector(".tl-prev"):null;}
function markPrev(n,mode){var pv=prevHost(n);if(!pv)return null;pv.classList.toggle("img-on",mode==="img");pv.classList.toggle("wave-on",mode==="wave");return pv;}
function drawPrevWave(n,s){var pv=prevHost(n);if(!pv||!s)return;var cv=pv.querySelector(".tl-prev-w");if(!cv)return;var key=s.url+"|"+(s.in||0)+"|"+(s.len||0);if(cv.getAttribute("data-key")===key)return;cv.setAttribute("data-key",key);wave(s.url).then(function(j){if(j){cv._j=j;drawWave(cv,j,s,true);}}).catch(function(){});}
function scrubStep(n,v,want,mode){var st=ensurePool(media(n));var idle=idleV(n);if(!idle)return false;idle.muted=true;if(idle.getAttribute("data-url")!==v.url){idle.setAttribute("data-url",v.url);idle.src=v.url;st.pend=want;st.pendSrc=v.url;return false;}
var ref=(mode==="tail")?want:st.pend;var tol=(mode==="tail")?0.04:0.06;var ok=(typeof ref==="number")&&st.pendSrc===v.url&&Math.abs((idle.currentTime||0)-ref)<=tol;if(ok&&idle.readyState>=2&&!idle.seeking){try{idle.pause();}catch(e){}
swapV(n);st.video=actV(n);st.video.muted=!!tlData(n).ui.muted.video;var oldV=idleV(n);if(oldV){oldV.muted=true;try{oldV.pause();}catch(e2){}}
st.pend=null;st.pendSrc=null;return true;}
if(idle.readyState>=1&&!idle.seeking&&!ok){try{idle.currentTime=want;st.pend=want;st.pendSrc=v.url;}catch(e3){}}
return false;}
var PRELOAD_LEAD=0.6;function sealContinuous(v,nx){return!!(nx&&nx.url===v.url&&Math.abs((nx.in||0)-((v.in||0)+v.len))<1e-3);}
function maybePreload(n){var u=uiOf(n),st=poolOf(n);if(!u.playing||u.T==null)return;var v=curSeg(n,"video",u.T);if(!v)return;var nx=nextSeg(n,"video",v);if(!nx||sealContinuous(v,nx))return;if((v.at+v.len)-u.T>PRELOAD_LEAD)return;var idle=idleV(n);idle.muted=true;if(idle.getAttribute("data-url")!==nx.url){idle.setAttribute("data-url",nx.url);idle.src=nx.url;}
if(idle.readyState<1)return;if(Math.abs((idle.currentTime||0)-(nx.in||0))>0.08){try{idle.currentTime=nx.in||0;}catch(e){}}
if(!idle.paused){try{idle.pause();}catch(e){}}}
function bodyHtml(n){var d=tlData(n),u=d.ui;var has=!!(d.segs.video.length||d.segs.audio.length);var showPrev=has&&u.T!=null;var span=spanOf(n),pps=u.pps;var phPos=pxOf(n,u.T,pps);return'<div class="tl-panel" data-tl-node="'+n.id+'">'
+(showPrev?'<div class="tl-prev" data-tl-ctrl="prev" style="aspect-ratio:'
+((tlData(n).ui.ar||(16/9)).toFixed(4))+'">'+prevInner(n)+'</div>':"")
+'<div class="tl-bar">'+barHtml(n)+'</div>'
+'<div class="tl-tracks">'
+'<div class="tl-scroll">'
+'  <div class="tl-inner" style="width:'+trackW(n)+'px">'
+'    <div class="tl-ruler" data-tl-ctrl="ruler">'+ticksHtml(n)+'</div>'
+trackHtml(n,"video")+trackHtml(n,"audio")
+'    <span class="tl-play" data-tl-ctrl="playhead" style="left:'+phPos+'px"><i></i></span>'
+'  </div>'
+'</div>'
+addColHtml(n)
+'</div>'
+'<span class="tl-resize" data-tl-ctrl="resize"></span>'
+'</div>';}
function mount(root){var nid=root.getAttribute("data-tl-node");var n=HOST.nodeById(nid);if(!n)return;var d=tlData(n);var H=46;Array.prototype.forEach.call(root.querySelectorAll(".tl-seg"),function(el){var t=el.getAttribute("data-track"),sid=el.getAttribute("data-tl-seg");var s=segById(n,t,sid);if(!s)return;if(t==="video"){if(s.kind==="image"){var u=thumb(s.url,320);el.querySelector(".tl-film").style.backgroundImage="url('"+u.replace(/'/g,"\\'")+"')";}else{sprite(s,H,d.ui.pps).then(function(du){var f=el.querySelector(".tl-film");if(f&&du)f.style.backgroundImage="url("+du+")";});}}else{wave(s.url).then(function(j){var cv=el.querySelector(".tl-wave");if(!cv||!j||!j.peaks)return;cv._j=j;drawWave(cv,j,s);}).catch(function(){});}});var pv=root.querySelector(".tl-prev");if(pv){mountPrev(n);syncMedia(n,true);}
syncBarDis(n,root);}
function drawWave(cv,j,s,big,progress){var w=cv.clientWidth||120,h=cv.clientHeight||46;if(cv.width!==w||cv.height!==h){cv.width=Math.max(2,w);cv.height=Math.max(2,h);}
var ctx=cv.getContext("2d");ctx.clearRect(0,0,w,h);var peaks=j.peaks||[],dur=j.duration||1;var total=j.duration||s.total||dur;if(!total)total=dur;var i0=Math.floor((s.in||0)/total*peaks.length);var i1=Math.ceil(((s.in||0)+(s.len||0))/total*peaks.length);i0=clamp(i0,0,peaks.length-1);i1=clamp(i1,i0+1,peaks.length);var slice=peaks.slice(i0,i1);if(!slice.length){ctx.strokeStyle="#c4b5fd";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();return;}
var cols=Math.max(1,Math.round(w));var cache=cv._wv;var vals,gain;if(!cache||cache.cols!==cols){var n2=slice.length;vals=new Array(cols);for(var c=0;c<cols;c++){var a0=Math.floor(c*n2/cols),a1=Math.max(a0+1,Math.floor((c+1)*n2/cols));var m2=0;for(var q=a0;q<a1&&q<n2;q++)if(slice[q]>m2)m2=slice[q];vals[c]=m2;}
var peak=0;for(var k2=0;k2<vals.length;k2++)if(vals[k2]>peak)peak=vals[k2];gain=Math.max(0.25,peak||1);cv._wv={cols:cols,vals:vals,gain:gain};}else{vals=cache.vals;gain=cache.gain;}
var bw=w/cols;var cUn=big?"#a78bfa":"#8b5cf6",cOn="#c4b5fd";var paintOn=(progress!=null&&progress>=0&&progress<=1);for(var i=0;i<cols;i++){ctx.fillStyle=(paintOn&&(i/cols)<=progress)?cOn:cUn;var bh=Math.max(1,Math.min(1,vals[i]/gain)*(h-4));ctx.fillRect(i*bw,(h-bh)/2,Math.max(1,bw-0.25),bh);}}
function media(n){return MEDIA[n.id]||(MEDIA[n.id]={});}
var SEG_EPS=1e-3;function curSeg(n,t,T){var a=segs(n,t);for(var i=0;i<a.length;i++){if(T>=a[i].at-SEG_EPS&&T<a[i].at+a[i].len-SEG_EPS)return a[i];}
for(var j=0;j<a.length;j++){if(Math.abs(T-(a[j].at+a[j].len))<=SEG_EPS)return a[j+1]||a[j];if(Math.abs(T-a[j].at)<=SEG_EPS)return a[j];}
return null;}
var _prevSeekAt=0;var _scrubAt=-1e9;function frameSnap(t){return Math.round((t||0)/FRAME)*FRAME;}
function playWhenReady(n,el){var p=el.play();if(!p||!p.catch)return;p.catch(function(){setTimeout(function(){if(!uiOf(n).playing||!el.paused)return;var q2=el.play();if(q2&&q2.catch)q2.catch(function(){});},120);});}
function syncMedia(n,force){var d=tlData(n),u=d.ui,st=poolOf(n);if(u.T==null)return;if(st.video&&!st.video.isConnected)mountPrev(n);var idle=idleV(n);if(idle){if(!idle.paused){try{idle.pause();}catch(e){}}
idle.muted=true;}
st.video=actV(n);var dragging=!!(DRAG&&(DRAG.kind==="seek"));var nowMs=(window.performance&&performance.now)?performance.now():Date.now();if(dragging)_scrubAt=nowMs;if(dragging&&!force){if(nowMs-_prevSeekAt<110)return;_prevSeekAt=nowMs;}
var scrubTail=force&&!u.playing&&(nowMs-_scrubAt<500);if(!dragging&&!scrubTail){var pst=media(n);pst.pend=null;pst.pendSrc=null;}
var T=u.T,v=curSeg(n,"video",T);var sp=spanOf(n);if(T>sp)T=u.T=sp;var auT=curSeg(n,"audio",T);var isImg=!!(v&&v.kind==="image");var mode=isImg?"img":(v?"vid":(auT?"wave":"vid"));var pvEl=markPrev(n,mode);if(mode==="wave")drawPrevWave(n,auT);if(isImg){var stI=poolOf(n);if(stI.img&&stI.img.getAttribute("data-url")!==v.url){stI.img.setAttribute("data-url",v.url);stI.img.src=v.url;}
if(st.video&&!st.video.paused){try{st.video.pause();}catch(e0){}}
if(st.vA)st.vA.muted=true;if(st.vB)st.vB.muted=true;v=null;}else if(v){if(st.vA)st.vA.muted=(st.act==="A")?!!u.muted.video:true;if(st.vB)st.vB.muted=(st.act==="B")?!!u.muted.video:true;}
if(v){var wantV=frameSnap((v.in||0)+(T-v.at));if(dragging&&!u.playing&&!force){scrubStep(n,v,wantV,"drag");st.video=actV(n);st.video.muted=!!u.muted.video;v=null;}else if(scrubTail){if(scrubStep(n,v,wantV,"tail")){st.video=actV(n);st.video.muted=!!u.muted.video;v=null;}}
if(v&&st.video){if(st.video.getAttribute("data-url")!==v.url){st.video.setAttribute("data-url",v.url);st.video.src=v.url;}
var want=frameSnap((v.in||0)+(T-v.at));var tol=u.playing?FRAME:(dragging?0.1:0.25);var dV=Math.abs((st.video.currentTime||0)-want);var atTarget=!st.video.seeking&&dV<=FRAME;if(!atTarget&&(force||dV>tol)){var busy=dragging&&!force&&(st.video.seeking||st.video.readyState<2);if(!busy){try{st.video.currentTime=want;}catch(e){}}}
st.video.muted=!!u.muted.video;if(u.playing&&st.video.paused)playWhenReady(n,st.video);if(!u.playing&&!st.video.paused)st.video.pause();}}else{if(st.video){st.video.muted=!!u.muted.video;if(!u.playing&&!st.video.paused)st.video.pause();}}
var au=curSeg(n,"audio",T);if(!st.audio&&au){st.audio=new Audio();st.audio.preload="auto";}
if(st.audio){if(au){if(st.audio.getAttribute("data-url")!==au.url){st.audio.setAttribute("data-url",au.url);st.audio.src=au.url;}
var w2=(au.in||0)+(T-au.at);var tol2=0.25;var aBusy=st.audio.seeking;var dA=Math.abs((st.audio.currentTime||0)-w2);var aTarget=!aBusy&&dA<=0.05;if(!aTarget&&(force||dA>tol2)){try{st.audio.currentTime=w2;}catch(e){}}
st.audio.muted=!!u.muted.audio;if(u.playing&&st.audio.paused){var q=st.audio.play();if(q&&q.catch)q.catch(function(){});}
if(!u.playing&&!st.audio.paused)st.audio.pause();}else if(!st.audio.paused){st.audio.pause();}}}
var _raf=null;var DRAG_KIND_LAST="";function loop(n){if(_raf)cancelAnimationFrame(_raf);var last=performance.now();function tick(now){var nn=HOST.nodeById(n.id);if(!nn){_raf=null;return;}
var d=tlData(nn),u=d.ui;if(!u.playing){_raf=null;return;}
var dt=(now-last)/1000;last=now;var sp=endOf(nn);var st=poolOf(nn);var vEl=actV(nn);st.video=vEl;var v=curSeg(nn,"video",u.T||0);maybePreload(nn);var vClock=!!(v&&vEl&&!vEl.paused&&!vEl.seeking&&vEl.readyState>=2);if(vClock){var raw=v.at+(vEl.currentTime-(v.in||0));var trusted=(u.T==null)||Math.abs(raw-u.T)<=0.5;if(!trusted)raw=u.T;if(trusted&&vEl.currentTime>=(v.in+v.len)-0.05){var nx=nextSeg(nn,"video",v);if(!nx){u.T=sp;pause(nn);return;}
u.T=nx.at;if(!sealContinuous(v,nx)){var nv=idleV(nn);var ready=nv&&nv.getAttribute("data-url")===nx.url&&nv.readyState>=2&&Math.abs((nv.currentTime||0)-(nx.in||0))<0.12;if(ready){try{nv.currentTime=nx.in||0;}catch(e){}
nv.muted=!!u.muted.video;var pp=nv.play();if(pp&&pp.catch)pp.catch(function(){});try{vEl.pause();}catch(e2){}
vEl.muted=true;swapV(nn);vEl=actV(nn);v=nx;}else{try{vEl.currentTime=nx.in||0;}catch(e3){}}}}
u.T=clamp(raw,v.at,v.at+v.len);}else if(st.audio&&!st.audio.paused&&!st.audio.seeking&&curSeg(nn,"audio",u.T||0)){var a2=curSeg(nn,"audio",u.T||0);var rawA=a2.at+(st.audio.currentTime-(a2.in||0));if(u.T!=null&&Math.abs(rawA-u.T)>0.5)rawA=u.T;u.T=rawA;if(st.audio.currentTime>=(a2.in+a2.len)-0.05){var nx2=nextSeg(nn,"audio",a2);if(nx2)u.T=nx2.at;else if((u.T=(u.T||0)+dt)>=sp){u.T=sp;pause(nn);return;}}}else{u.T=(u.T||0)+dt;if(u.T>=sp){u.T=sp;pause(nn);return;}}
syncMedia(nn,false);updateTimeCode(nn);movePlayhead(nn);_raf=requestAnimationFrame(tick);}
_raf=requestAnimationFrame(tick);}
function nextSeg(n,t,s){var a=segs(n,t),i=idxOf(a,s.id);return(i>=0&&i+1<a.length)?a[i+1]:null;}
function play(n){var u=uiOf(n);if(!u.playing){var sp=endOf(n);if(u.T!=null&&sp>0&&u.T>=sp-0.05)u.T=Math.max(0,filmStart(n));u.playing=true;syncMedia(n,true);loop(n);}
repaint(n);}
function pause(n){var u=uiOf(n),st=media(n);u.playing=false;if(st.video)st.video.pause();if(st.vA){try{st.vA.pause();}catch(e){}}
if(st.vB){try{st.vB.pause();}catch(e){}}
if(st.audio)st.audio.pause();if(_raf){cancelAnimationFrame(_raf);_raf=null;}
repaint(n);}
function updateTimeCode(n){var u=uiOf(n),el=document.querySelector('.tl-panel[data-tl-node="'+n.id+'"] .tl-tc');if(el)el.textContent=fmtCur(filmCur(n),filmLen(n))+" / "+fmt(filmLen(n),filmLen(n));if(FS&&FS.id===n.id){var e2=document.querySelector(".tl-fs-tc");if(e2)e2.textContent=fmtCur(filmCur(n),filmLen(n))+" / "+fmt(filmLen(n),filmLen(n));}}
function movePlayhead(n,dragSeek){var u=uiOf(n),pps=u.pps;Array.prototype.forEach.call(document.querySelectorAll('.tl-panel[data-tl-node="'+n.id+'"] .tl-play, .tl-fs[data-tl-node="'+n.id+'"] .tl-play'),function(el){el.style.left=pxOf(n,u.T,pps)+"px";});Array.prototype.forEach.call(document.querySelectorAll('.tl-panel[data-tl-node="'+n.id+'"] .tl-seg[data-track="audio"], .tl-fs[data-tl-node="'+n.id+'"] .tl-seg[data-track="audio"]'),function(el){var s=segById(n,"audio",el.getAttribute("data-tl-seg"));var cv=el.querySelector(".tl-wave");if(!cv||!s||!(s.len>0)||!cv._j)return;var p=((u.T||0)-s.at)/s.len;drawWave(cv,cv._j,s,false,(p>0&&p<=1)?p:null);});var pv=prevHost(n);if(pv){var pcv=pv.querySelector(".tl-prev-w");var ps=curSeg(n,"audio",u.T||0);if(pcv&&pcv._j&&ps){var pp=((u.T||0)-ps.at)/ps.len;drawWave(pcv,pcv._j,ps,true,(pp>0&&pp<=1)?pp:null);}}
Array.prototype.forEach.call(document.querySelectorAll('.tl-panel[data-tl-node="'+n.id+'"] .tl-scroll, .tl-fs[data-tl-node="'+n.id+'"] .tl-scroll'),function(sc){var x=pxOf(n,u.T,pps),left=sc.scrollLeft,w=sc.clientWidth;if(w<=0)return;if(dragSeek){var vis=x-left;if(vis>w-16)sc.scrollLeft=x-(w-16);else if(vis<16)sc.scrollLeft=Math.max(0,x-16);return;}
if(x-left>w*0.65||x-left<0)sc.scrollLeft=Math.max(0,x-w*0.35);});}
function onWheel(e){var sc=e.target&&e.target.closest?e.target.closest(".tl-scroll"):null;if(!sc)return;var panel=e.target.closest(".tl-panel, .tl-fs");if(!panel)return;var n=HOST.nodeById(panel.getAttribute("data-tl-node"));if(!n)return;var u=uiOf(n);if(e.ctrlKey){e.preventDefault();var k=e.deltaY<0?1.12:(1/1.12);u.pps=clamp(u.pps*k,4,1000);HOST.save();render(n);return;}
var d=(Math.abs(e.deltaX)>Math.abs(e.deltaY))?e.deltaX:e.deltaY;if(d){sc.scrollLeft+=d;e.preventDefault();}}
function snapZoomLevel(vis){var gs=[15,30,60,150],best=null,bd=0.08*135;gs.forEach(function(g){var d=Math.abs(vis-g);if(d<=bd){bd=d;best=g;}});return best==null?vis:best;}
function capture(e){if(!e.target||!e.target.closest)return false;return!!e.target.closest(".tl-panel, .tl-fs");}
function onDown(e){if(e.button!==0)return;var panel=e.target.closest(".tl-panel, .tl-fs");if(!panel)return;var nid=panel.getAttribute("data-tl-node")||(FS&&FS.id);var n=HOST.nodeById(nid);if(!n)return;var d=tlData(n),u=d.ui;var ctrl=e.target.closest("[data-tl-ctrl]");var act=ctrl?ctrl.getAttribute("data-tl-ctrl"):"";if(act==="playhead"||act==="ruler"||(!act&&e.target.closest(".tl-lane"))){var box=e.target.closest(".tl-inner")||panel.querySelector(".tl-inner");var rect=box?box.getBoundingClientRect():{left:0};var T=originOf(n)+(e.clientX-rect.left)/(u.pps*zoomOf(n));if(!e.target.closest("[data-tl-seg]")){beginSeek(n,T);e.preventDefault();return;}}
if(act==="trim-in"||act==="trim-out"){var segEl=e.target.closest("[data-tl-seg]");if(!segEl)return;var t=segEl.getAttribute("data-track"),sid=segEl.getAttribute("data-tl-seg");var s=segById(n,t,sid);if(s){u.sel={track:t,id:sid};HOST.save();repaint(n);syncHead(n);beginTrim(n,t,s,act==="trim-in"?"in":"out",e.clientX);e.preventDefault();return;}}
if(!act&&e.target.closest("[data-tl-seg]")){var segEl2=e.target.closest("[data-tl-seg]");var t2=segEl2.getAttribute("data-track"),sid2=segEl2.getAttribute("data-tl-seg");var s2=segById(n,t2,sid2);if(s2){u.sel={track:t2,id:sid2};HOST.save();repaint(n);syncHead(n);beginMove(n,t2,s2,e.clientX);e.preventDefault();return;}}
if(act==="resize"){beginResize(n,e.clientX);e.preventDefault();return;}}
function beginDrag(kind,n,ctx){DRAG={kind:kind,id:n.id,x0:ctx.x0,snap:ctx.snap||null,onDone:ctx.onDone,deadPx:ctx.deadPx||0,snapShot:HOST.snapshot(),unit:ctx.unit||"sec",moved:false};document.addEventListener("mousemove",onMove);document.addEventListener("mouseup",onUp);}
function onMove(e){if(!DRAG)return;var n=HOST.nodeById(DRAG.id);if(!n||!DRAG.snap)return;var dxRaw=(e.clientX-DRAG.x0)/zoomOf(n);if(DRAG.deadPx&&Math.abs(dxRaw)<DRAG.deadPx)return;DRAG.moved=true;var dx=dxRaw;if(DRAG.unit!=="px")dx=dx/uiOf(n).pps;DRAG.snap(dx,e);}
function onUp(){document.removeEventListener("mousemove",onMove);document.removeEventListener("mouseup",onUp);if(!DRAG)return;var n=HOST.nodeById(DRAG.id);var done=DRAG.onDone,shot=DRAG.snapShot,moved=DRAG.moved;DRAG_KIND_LAST=DRAG.kind;DRAG=null;if(n&&done)done(n);if(n&&moved&&shot)HOST.push(shot);if(n){HOST.save();if(DRAG_KIND_LAST==="seek"){repaint(n);syncMedia(n,true);}
else if(!moved){repaint(n);}
else render(n);}}
function pinTrimHead(n,sid,on){eachSegEl(n,sid,function(el){el.classList.toggle("tl-trim-head",!!on);var f=el.querySelector(".tl-film");if(f&&!on)f.style.backgroundPositionX="";});}
function dragFilmHead(n,s,din,pps){var dx=-Math.max(0,din)*pps;eachSegEl(n,s.id,function(el){var f=el.querySelector(".tl-film");if(f)f.style.backgroundPositionX=dx.toFixed(1)+"px";});}
function eachSegEl(n,sid,fn){var roots=document.querySelectorAll('.tl-panel[data-tl-node="'+n.id+'"], .tl-fs[data-tl-node="'+n.id+'"]');Array.prototype.forEach.call(roots,function(root){Array.prototype.forEach.call(root.querySelectorAll(".tl-seg"),function(el){if(el.getAttribute("data-tl-seg")===sid)fn(el);});});}
function paint(n){var d=tlData(n),pps=d.ui.pps;var roots=document.querySelectorAll('.tl-panel[data-tl-node="'+n.id+'"], .tl-fs[data-tl-node="'+n.id+'"]');Array.prototype.forEach.call(roots,function(root){Array.prototype.forEach.call(root.querySelectorAll(".tl-seg"),function(el){var t=el.getAttribute("data-track"),s=segById(n,t,el.getAttribute("data-tl-seg"));if(!s)return;el.style.left=pxOf(n,s.at,pps)+"px";el.style.width=Math.max(6,Math.round((s.len||0)*pps))+"px";var du=el.querySelector(".tl-dur");if(du)du.textContent=(s.len||0).toFixed(1)+"s";});Array.prototype.forEach.call(root.querySelectorAll(".tl-lane"),function(lane){var t=lane.getAttribute("data-track");lane.style.width=trackW(n,t)+"px";});var inner=root.querySelector(".tl-inner");if(inner){inner.style.width=trackW(n)+"px";}});updateTimeCode(n);movePlayhead(n);}
function beginTrim(n,t,s,side,x0){var d=tlData(n),a=d.segs[t];var idx=idxOf(a,s.id);if(idx<0)return;var in0=s.in,out0=s.out==null?(s.in+s.len):s.out,len0=s.len;var img=(s.kind==="image");var draft={in:in0,out:out0,len:len0};function apply(){s.in=draft.in;s.out=draft.out;s.len=draft.out-draft.in;reflow(a,idx+1);}
if(side==="in")pinTrimHead(n,s.id,true);beginDrag("trim",n,{x0:x0,deadPx:3,snap:function(dx){if(side==="in"){var v=in0+dx;if(!img)v=clamp(v,0,out0-TL_MIN);else v=Math.min(v,out0-TL_MIN);v=snapVal(n,t,s,v,side);draft.in=v;draft.out=out0;draft.len=out0-v;}else{var v2=out0+dx;if(!img)v2=clamp(v2,in0+TL_MIN,s.total||out0);else v2=Math.max(v2,in0+TL_MIN);v2=snapVal(n,t,s,v2,side);draft.out=v2;draft.len=v2-in0;}
apply();paint(n);if(side==="in")dragFilmHead(n,s,draft.in-in0,d.ui.pps);},onDone:function(){pinTrimHead(n,s.id,false);}});}
function beginMove(n,t,s,x0){var a=segs(n,t);if(idxOf(a,s.id)<0)return;var at0=s.at;var lifted=false;function liftOn(){if(lifted)return;lifted=true;eachSegEl(n,s.id,function(el){el.classList.add("tl-lift");});}
return beginDrag("move",n,{x0:x0,snap:function(dx){var u=uiOf(n);var desired=Math.max(0,at0+dx);desired=Math.max(0,snapVal(n,t,s,desired,"move"));var rest=a.filter(function(x){return x!==s;});var acc=0,k=0;for(var i=0;i<rest.length;i++){if(desired>acc+(rest[i].len||0)*0.5){k=i+1;acc+=rest[i].len||0;}
else break;}
var cur=idxOf(a,s.id);if(cur!==k){a.splice(cur,1);a.splice(k,0,s);reflow(a,0);}
var offPx=(desired-s.at)*u.pps;var handPx=(desired-at0)*u.pps;if(Math.abs(handPx)>=4){liftOn();eachSegEl(n,s.id,function(el){el.style.transform="translateX("+Math.round(offPx)+"px)";});}
paint(n);},onDone:function(){eachSegEl(n,s.id,function(el){el.classList.remove("tl-lift");el.style.transform="";});}});}
function beginSeek(n,T){var u=uiOf(n);var sp=endOf(n);u.T=clamp(Math.round(T*1000)/1000,0,sp);HOST.save();repaint(n);beginDrag("seek",n,{x0:0,snap:function(){},onDone:function(){HOST.save();}});document.removeEventListener("mousemove",onMove);document.addEventListener("mousemove",function mv(e){if(!DRAG){document.removeEventListener("mousemove",mv);return;}
var nn=HOST.nodeById(n.id);if(!nn)return;var host=(FS&&FS.id===n.id&&FS.el)?FS.el:document.querySelector('.cs-node[data-node="'+n.id+'"]');var inner=host?host.querySelector('.tl-inner'):null;if(!inner)return;var rect=inner.getBoundingClientRect();uiOf(nn).T=clamp(originOf(nn)+(e.clientX-rect.left)/(uiOf(nn).pps*zoomOf(nn)),0,endOf(nn));updateTimeCode(nn);movePlayhead(nn,true);syncMedia(nn);});}
function beginResize(n,x0){var w0=n.w||520;beginDrag("resize",n,{x0:x0,unit:"px",snap:function(dx){var maxW=Math.min(1400,window.innerWidth-80);n.w=clamp(Math.round(w0+dx),360,maxW);var el=document.querySelector('.cs-node[data-node="'+n.id+'"]');if(el)el.style.width=n.w+"px";paint(n);},onDone:function(){}});}
function snapVal(n,t,s,v,side){var u=uiOf(n),d=tlData(n);if(!u.snap)return v;var tol=SNAP_PX/u.pps;var cands=[0];if(typeof u.T==="number")cands.push(u.T);d.segs[t].forEach(function(o){if(o.id===s.id)return;cands.push(o.at);cands.push(o.at+o.len);});var best=v,bd=tol;cands.forEach(function(c){var dd=Math.abs(c-v);if(dd<=bd){bd=dd;best=c;}});return best;}
function split(n){var d=tlData(n),u=d.ui;if(u.T==null){HOST.toast("先在刻度尺上点一下定位播放头");return;}
var t=u.sel.track||"video";var a=d.segs[t],s=curSeg(n,t,u.T);if(!s){HOST.toast("播放头不在任何素材段内");return;}
var T=u.T;var left=T-s.at;if(s.len<TL_MIN*2||left<TL_MIN||(s.len-left)<TL_MIN){HOST.toast("播放头太靠近段边界，切不出两段");return;}
var idx=idxOf(a,s.id);HOST.push(HOST.snapshot());var right={id:"s"+Math.random().toString(36).slice(2,8),url:s.url,kind:s.kind,name:s.name,at:T,in:(s.in||0)+left,len:s.len-left,total:s.total,vw:s.vw,vh:s.vh};s.len=left;s.out=(s.in||0)+left;a.splice(idx+1,0,right);reflow(a,idx+1);u.sel={track:t,id:right.id};HOST.save();render(n);}
function pruneEdges(n){if(!HOST.incomingEdges||!HOST.removeEdge||!HOST.canvasAssets)return 0;var ins=HOST.incomingEdges(n.id);if(!ins.length)return 0;var used=usedUrls(n);var byNode={};HOST.canvasAssets().forEach(function(a){if(!a||!a.nodeId)return;(byNode[a.nodeId]=byNode[a.nodeId]||[]).push(uKey(a.url));});var k2=0;ins.forEach(function(e){var urls=byNode[e.from];if(!urls){if(HOST.removeEdge(e.id))k2++;return;}
var still=urls.some(function(key){return!!used[key];});if(!still&&HOST.removeEdge(e.id))k2++;});return k2;}
function delSeg(n){var d=tlData(n),u=d.ui;if(!u.sel.id)return;var a=d.segs[u.sel.track],idx=idxOf(a,u.sel.id);if(idx<0)return;HOST.push(HOST.snapshot());var T=u.T;a.splice(idx,1);reflow(a,Math.max(0,idx));if(typeof T==="number"){if(idx===0)T=0;else T=a[idx-1]?(a[idx-1].at+a[idx-1].len):0;u.T=clamp(T,0,endOf(n));}
u.sel={track:"",id:""};resetOrigin(n);var pruned=pruneEdges(n);if(pruned&&HOST.renderEdges)HOST.renderEdges();HOST.save();render(n);}
function cutAtPlayhead(n,side){var d=tlData(n),u=d.ui;if(!u.sel.id)return;var t=u.sel.track,a=d.segs[t],s=segById(n,t,u.sel.id);if(!s)return;if(u.T==null){HOST.toast("先在刻度尺上点一下定位播放头");return;}
var at=s.at||0,in0=s.in||0;var out0=(s.out==null?(in0+s.len):s.out);var EPS=1e-3;if(u.T<at-EPS||u.T>at+(out0-in0)+EPS){HOST.toast("播放头不在选中的素材段内");return;}
var cut=in0+(u.T-at);var idx=idxOf(a,s.id);var nIn=in0,nOut=out0;if(side==="in"){nIn=clamp(cut,in0,out0-TL_MIN);if(nIn-in0<EPS){HOST.toast("播放头左侧已到素材开头");return;}}else{nOut=clamp(cut,in0+TL_MIN,out0);if(out0-nOut<EPS){HOST.toast("播放头右侧已到素材末尾");return;}}
HOST.push(HOST.snapshot());s.in=nIn;s.out=nOut;s.len=nOut-nIn;reflow(a,idx+1);HOST.save();render(n);}
var MENU_AT=null;function menuAt(ev,anchor){if(ev&&typeof ev.clientX==="number"&&(ev.clientX||ev.clientY)){return{x:ev.clientX,y:ev.clientY+6};}
var r=anchor.getBoundingClientRect();return{x:r.left,y:r.bottom+4};}
function clampMenuAt(p,h){var W=200;return{x:Math.max(8,Math.min(p.x,window.innerWidth-W)),y:Math.max(8,Math.min(p.y,window.innerHeight-(h||150)))};}
function openAddMenu(n,track,anchor,ev,opts){closeMenu();var impOnly=!!(opts&&opts.importOnly);var m=document.createElement("div");m.className="tl-menu";m.innerHTML='<button data-act="upload">'+ico("ic-upload")+'本地上传</button>'
+'<button data-act="library">'+ico("ic-library")+'从资产库添加</button>'
+(impOnly?"":'<button data-act="canvas">'+ico("ic-image")+'从画布选择</button>');MENU_AT=menuAt(ev,anchor);var at=clampMenuAt(MENU_AT,150);document.body.appendChild(m);m.style.left=at.x+"px";m.style.top=at.y+"px";m.addEventListener("click",function(e){var b=e.target.closest("button");if(!b)return;var act=b.getAttribute("data-act");closeMenu();if(act==="upload")pickUpload(n,impOnly);else if(act==="library")pickLibrary(n,impOnly);else pickCanvas(n);});setTimeout(function(){document.addEventListener("mousedown",_outside);},0);}
function _outside(e){if(e.target.closest&&e.target.closest(".tl-menu"))return;closeMenu();}
function closeMenu(){var m=document.querySelector(".tl-menu");if(m)m.remove();document.removeEventListener("mousedown",_outside);}
function landImport(n,item){if(!HOST.addAssetNode){if(HOST.toast)HOST.toast("当前版本不支持导入到画布");return false;}
var st=HOST.snapshot?HOST.snapshot():null;var aid=HOST.addAssetNode(n.id,{url:localUrl(item.url),kind:item.kind||"image",name:item.name||"素材"},!FS);if(!aid)return false;if(HOST.linkEdge)HOST.linkEdge(aid,n.id);if(st&&HOST.push)HOST.push(st);HOST.save();if(HOST.renderEdges)HOST.renderEdges();if(FS)fillLib(n);if(HOST.toast)HOST.toast("已导入画布："+(item.name||"素材"));return true;}
function pickUpload(n,importOnly){var inp=document.createElement("input");inp.type="file";inp.accept="image/*,audio/*,video/*";inp.onchange=function(){var f=inp.files&&inp.files[0];if(!f)return;var fd=new FormData();fd.append("file",f);fetch(API+"/api/upload",{method:"POST",body:fd}).then(function(r){return r.json();}).then(function(j){if(!j.url){alert("上传失败："+(j.error||""));return;}
var it={url:j.url.replace(/^https?:\/\/[^/]+/,""),kind:j.kind,name:j.name};if(importOnly){landImport(n,it);return;}
it.land=true;acceptAsset(n.id,it);}).catch(function(e){alert("上传失败："+e.message);});};inp.click();}
function panelTabs(){return(FS&&FS.el?FS.el.querySelectorAll("[data-tab]"):[])||[];}
function pickLibrary(n,importOnly){if(window.AssetPicker&&window.AssetPicker.open){window.AssetPicker.open({source:"library",multi:false,title:importOnly?"从资产库导入到画布":"添加到时间线",onPick:function(items){(items||[]).forEach(function(it){var o={url:it.url,kind:it.type||it.kind,name:it.name||it.label};if(importOnly){landImport(n,o);return;}
o.land=true;acceptAsset(n.id,o);});}});return;}
alert("资产库组件未加载");}
function pickCanvas(n){var list=HOST.canvasAssets();if(!list.length){alert("当前画布还没有素材（先上传或生成）");return;}
var m=document.createElement("div");m.className="tl-menu tl-menu-list";var used2=usedUrls(n);m.innerHTML=list.map(function(it,i){var on=!!used2[uKey(it.url)];return'<button data-i="'+i+'" class="'+(on?"on":"")+'">'
+ico(it.kind==="audio"?"ic-audio":(it.kind==="video"?"ic-video":"ic-image"))
+'<span class="tl-menu-n">'+esc(it.name||"素材")+'</span>'
+(on?'<i class="tl-menu-on">已入线</i>':'')+'</button>';}).join("");document.body.appendChild(m);var at2=clampMenuAt(MENU_AT||{x:window.innerWidth/2-100,y:120},150);m.style.left=at2.x+"px";m.style.top=at2.y+"px";m.style.maxHeight=Math.max(140,window.innerHeight-at2.y-12)+"px";m.addEventListener("click",function(e){var b=e.target.closest("button");if(!b)return;var it=list[+b.getAttribute("data-i")];m.remove();if(it)acceptAsset(n.id,it);});setTimeout(function(){document.addEventListener("mousedown",_outside);},0);}
function exportFilm(n){var d=tlData(n);var v=d.segs.video.map(function(s){return{url:s.url,kind:s.kind,start:s.in||0,dur:s.len||0};}).filter(function(x){return x.dur>0;});var a=d.segs.audio.map(function(s){return{url:s.url,kind:s.kind,start:s.in||0,dur:s.len||0};}).filter(function(x){return x.dur>0;});if(!v.length&&!a.length){alert("时间线为空");return;}
var btn=document.querySelector('.tl-panel[data-tl-node="'+n.id+'"] [data-tl-ctrl="export"]');if(btn)btn.disabled=true;fetch(API+"/api/media/concat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({video:v,audio:a})}).then(function(r){return r.json();}).then(function(j){if(!j||j.error){alert("导出失败："+((j&&j.error)||"未知错误"));return;}
HOST.toast("成片已导出并存入资产库："+j.name);var a2=document.createElement("a");a2.href=j.url;a2.download=j.name;a2.click();}).catch(function(e){alert("导出失败："+e.message);}).then(function(){if(btn)btn.disabled=false;});}
function openFull(n){if(FS)return;var d=tlData(n);var el=document.createElement("div");el.className="tl-fs";el.setAttribute("data-tl-node",n.id);el.innerHTML='<div class="tl-fs-top">'
+'<button data-tl-ctrl="back">'+ico("ic-undo")+'返回画布</button>'
+'<span class="tl-fs-t">视频合成</span>'
+'<span class="tl-fs-sp"></span>'
+'<button data-tl-ctrl="exportfs">'+ico("ic-download")+'导出</button>'
+'<button data-tl-ctrl="closefs" class="tl-fs-x">✕</button>'
+'</div>'
+'<div class="tl-fs-main">'
+'  <div class="tl-fs-lib">'
+'    <div class="tl-fs-tabs"><button class="on" data-tab="lib">已导入素材</button>'
+'      <button data-tab="canvas">画布素材</button></div>'
+'    <div class="tl-fs-chips"><button class="on" data-k="">全部</button><button data-k="image">图片</button>'
+'      <button data-k="video">视频</button><button data-k="audio">音频</button>'
+'      <button class="tl-fs-imp" data-tl-ctrl="importfs" hidden>'+ico("ic-upload")+'导入</button></div>'
+'    <div class="tl-fs-grid"></div>'
+'  </div>'
+'  <div class="tl-fs-stage"><div class="tl-prev" data-tl-ctrl="prev">'+prevInner(n)+'</div>'
+'    <div class="tl-fs-play"><button data-tl-ctrl="play">'+ico("ic-play")+'</button>'
+'      <span class="tl-fs-tc">0:00 / 0:00</span>'
+'      <button data-tl-ctrl="prev-fs" title="播放器全屏">'+ico("ic-maximize")+'</button>'
+'    </div></div>'
+'</div>'
+'<div class="tl-fs-bottom"><div class="tl-bar">'+barHtml(n,true)+'</div>'
+'<div class="tl-tracks"><div class="tl-scroll"><div class="tl-inner">'
+'    <div class="tl-ruler" data-tl-ctrl="ruler">'+ticksHtml(n)+'</div>'
+trackHtml(n,"video")+trackHtml(n,"audio")
+'    <span class="tl-play" data-tl-ctrl="playhead" style="left:'+pxOf(n,d.ui.T)+'px"><i></i></span>'
+'</div></div>'
+addColHtml(n)
+'</div>'
+'</div>';document.body.appendChild(el);FS={id:n.id,el:el,tab:"lib",k:"",libSig:null};syncLibChrome();fillLib(n);syncHead(n);render();mount(el);}
function closeFull(){if(!FS)return;var n=HOST.nodeById(FS.id);if(n)pause(n);if(FS.el)FS.el.remove();FS=null;HOST.render();}
function libItems(all){return(all||[]).filter(function(x){return x&&!x.gen;});}
function usedSig(n){var ks=Object.keys(usedUrls(n));ks.sort();return ks.join("|")+"#"+(FS?FS.tab:"")+"#"+(FS?FS.k:"");}
function syncLibIfStale(n){if(!FS||FS.id!==n.id)return;if(FS.libSig===usedSig(n))return;fillLib(n);}
function paintGrid(n,grid,list){var k=FS?FS.k:"";var arr=k?list.filter(function(x){return(x.kind||"image")===k;}):list;grid.innerHTML=arr.length?cardsHtml(arr,usedUrls(n)):'<div class="tl-fs-load">'+(k?"该类型下暂无素材":"暂无素材")+'</div>';bindCards(n,grid);if(FS)FS.libSig=usedSig(n);}
function fillLib(n){if(!FS)return;var grid=FS.el.querySelector(".tl-fs-grid");if(!grid)return;var all=HOST.canvasAssets();paintGrid(n,grid,(FS.tab==="lib")?libItems(all):all);}
function syncLibChrome(){if(!FS||!FS.el)return;var imp=FS.el.querySelector(".tl-fs-imp");if(imp)imp.hidden=(FS.tab!=="lib");}
function localUrl(u){var x=String(u==null?"":u).trim();var m=x.match(/^https?:\/\/([^/]+)(\/.*)?$/i);if(m){var host=m[1].toLowerCase(),here=(location.host||"").toLowerCase();var isHere=(host===here)||/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host);if(isHere)x=m[2]||"/";}
if(x&&x.charAt(0)!=="/"&&x.indexOf("://")<0)x="/"+x;return x;}
function uKey(u){var x=String(u==null?"":u).split("?")[0].split("#")[0];x=x.replace(/^https?:\/\/[^/]+/i,"");x=x.replace(/^\/+/,"");try{x=decodeURIComponent(x);}catch(e){}
return x;}
function usedUrls(n){var d=tlData(n),m={};["video","audio"].forEach(function(t){(d.segs[t]||[]).forEach(function(x){if(x.url)m[uKey(x.url)]=1;});});return m;}
function cardsHtml(list,used){if(!list.length)return'<div class="tl-fs-load">暂无素材</div>';return list.map(function(it){var lu=localUrl(it.url);var k=it.kind||"image";var th;if(k==="image"){th="<div class=\"tl-fs-th\" data-url=\""+esc(lu)+"\" style=\"background-image:url('"
+thumb(lu,320).replace(/'/g,"\\'")+"')\"></div>";}else if(k==="video"){th='<div class="tl-fs-th" data-url="'+esc(lu)+'">'
+'<video class="tl-fs-v" preload="metadata" muted playsinline src="'+esc(lu)+'#t=0.1"></video>'
+'<span class="tl-fs-dur">--:--</span></div>';}else{th='<div class="tl-fs-th" data-url="'+esc(lu)+'">'
+'<canvas class="tl-fs-w"></canvas>'
+'<span class="tl-fs-dur">--:--</span></div>';}
var on=!!(used&&used[uKey(it.url)]);return'<div class="tl-fs-card'+(on?" on":"")+'" data-url="'+esc(it.url)+'" data-kind="'+esc(k)
+'" data-node="'+esc(it.nodeId||"")+'" data-name="'+esc(it.name||"")+'" title="'+esc(it.name||"")+'">'
+th
+(on?'<i class="tl-fs-on">已入线</i>':"")
+'<span>'+esc(it.name||"素材")+'</span></div>';}).join("");}
function hydrateCards(n,grid){Array.prototype.forEach.call(grid.querySelectorAll("video.tl-fs-v"),function(v){var box=v.parentNode,lbl=box?box.querySelector(".tl-fs-dur"):null;var setDur=function(){if(lbl&&isFinite(v.duration)&&v.duration>0)lbl.textContent=fmtBrief(v.duration);};v.addEventListener("loadedmetadata",function(){setDur();try{if(v.readyState<2)v.currentTime=0.1;}catch(e){}});v.addEventListener("loadeddata",setDur);v.addEventListener("error",function(){if(lbl){lbl.textContent="--:--";lbl.classList.add("bad");}
if(box)box.classList.add("noprev");});if(v.readyState>=1)setDur();});Array.prototype.forEach.call(grid.querySelectorAll("canvas.tl-fs-w"),function(cv){var box=cv.parentNode;var url=box?box.getAttribute("data-url"):"";if(!url)return;wave(url).then(function(j){if(!j||!FS||!cv.isConnected)return;drawWave(cv,j,{url:url,in:0,len:j.duration||0,total:j.duration||0},false);var lbl=box.querySelector(".tl-fs-dur");if(lbl&&j.duration)lbl.textContent=fmtBrief(j.duration);}).catch(function(){});});}
function bindCards(n,grid){Array.prototype.forEach.call(grid.querySelectorAll(".tl-fs-card"),function(c){c.addEventListener("click",function(){if(c.classList.contains("busy"))return;c.classList.add("busy");var clear=function(){c.classList.remove("busy");};setTimeout(clear,8000);var pr=acceptAsset(n.id,{url:c.getAttribute("data-url"),kind:c.getAttribute("data-kind"),name:c.getAttribute("data-name"),edgeFrom:c.getAttribute("data-node")||""});if(pr&&pr.then){pr.then(clear,clear);}else{clear();}});});hydrateCards(n,grid);}
function onClick(e){var panel=e.target.closest(".tl-panel, .tl-fs");if(!panel)return;var nid=panel.getAttribute("data-tl-node");var n=HOST.nodeById(nid);if(!n)return;var d=tlData(n),u=d.ui;var b=e.target.closest("[data-tl-ctrl]");var act=b?b.getAttribute("data-tl-ctrl"):"";var tab=e.target.closest("[data-tab]");var chip=e.target.closest("[data-k]");if(tab){FS.tab=tab.getAttribute("data-tab");Array.prototype.forEach.call(panel.querySelectorAll("[data-tab]"),function(x){x.classList.toggle("on",x===tab);});syncLibChrome();fillLib(n);return;}
if(chip){FS.k=chip.getAttribute("data-k");Array.prototype.forEach.call(panel.querySelectorAll("[data-k]"),function(x){x.classList.toggle("on",x===chip);});fillLib(n);return;}
if(!act)return;if(act==="undo"){HOST.undo();return;}
if(act==="redo"){HOST.redo();return;}
if(act==="split"){split(n);return;}
if(act==="del"){delSeg(n);return;}
if(act==="trim-in"||act==="trim-out"){if(!e.target.closest("[data-tl-seg]")){cutAtPlayhead(n,act==="trim-in"?"in":"out");}
return;}
if(act==="play"){u.playing?pause(n):play(n);return;}
if(act==="export"||act==="exportfs"){exportFilm(n);return;}
if(act==="full"){openFull(n);return;}
if(act==="closefs"||act==="back"){closeFull();return;}
if(act==="mute"){var t=b.getAttribute("data-track");u.muted[t]=!u.muted[t];HOST.save();repaint(n);syncMuted(n);return;}
if(act==="add"){openAddMenu(n,b.getAttribute("data-track"),b,e);return;}
if(act==="importfs"){openAddMenu(n,null,b,e,{importOnly:true});return;}
if(act==="prev-fs"){var pv2=(panel.querySelector(".tl-prev")||{});if(pv2&&pv2.requestFullscreen){try{pv2.requestFullscreen();}catch(e){}}
return;}
if(act==="snap"){u.snap=!u.snap;HOST.save();repaint(n);return;}
if(act==="zoom-in"){zoomStep(n,1.25);return;}
if(act==="zoom-out"){zoomStep(n,1/1.25);return;}
if(act==="prev"){var T2=u.T;if(T2==null){u.T=0;HOST.save();render(n);}
return;}}
function syncBarDis(n,root){var bar=root.querySelector(".tl-bar");if(!bar)return;var d=tlData(n),u=d.ui;var has=!!(d.segs.video.length||d.segs.audio.length);var sel=!!(u.sel&&u.sel.id);[["undo",!HOST.canUndo()],["redo",!HOST.canRedo()],["split",!has],["trim-in",!(has&&sel)],["trim-out",!(has&&sel)],["del",!(has&&sel)],["play",!has],["export",!has]].forEach(function(kv){var b=bar.querySelector('[data-tl-ctrl="'+kv[0]+'"]');if(b)b.classList.toggle("dis",!!kv[1]);});}
function syncAllBars(){Array.prototype.forEach.call(document.querySelectorAll('.tl-panel[data-tl-node], .tl-fs[data-tl-node]'),function(root){var n=HOST.nodeById(root.getAttribute("data-tl-node"));if(n)syncBarDis(n,root);});}
function urlName(u){var s=String(u||"").split("?")[0].split("/").pop();try{s=decodeURIComponent(s);}catch(e){}
return s||"";}
function segTitle(n){if(!n||!n.data)return"";var d=tlData(n),u=d.ui;var s=(u.sel&&u.sel.id)?segById(n,u.sel.track,u.sel.id):null;if(!s)s=d.segs.video[0]||d.segs.audio[0];return s?(s.name||urlName(s.url)):"";}
function syncHead(n){if(!n||n.type!=="timeline")return;if(HOST.syncTitle)HOST.syncTitle(n.id);if(FS&&FS.id===n.id&&FS.el){var t=FS.el.querySelector(".tl-fs-t");if(t){var want=segTitle(n)||"视频合成";if(t.textContent!==want)t.textContent=want;t.setAttribute("title",want);}}}
function syncAllHeads(){Array.prototype.forEach.call(document.querySelectorAll("#csNodes .cs-node[data-node]"),function(el){var n=HOST.nodeById(el.getAttribute("data-node"));if(n&&n.type==="timeline")syncHead(n);});}
function syncFBar(n){if(!FS||FS.id!==n.id)return;var bar=FS.el.querySelector(".tl-bar");if(!bar)return;syncBarDis(n,FS.el);var u=uiOf(n);Array.prototype.forEach.call(FS.el.querySelectorAll(".tl-trow > .tl-mute"),function(mb){var t=mb.getAttribute("data-track");mb.classList.toggle("off",!!u.muted[t]);mb.innerHTML=ico(u.muted[t]?"ic-volume-off":"ic-volume");});var zs=bar.querySelector('[data-tl-ctrl="zoom"]');if(zs){var zv=zoomSliderVal(n);zs.value=zv;zs.style.setProperty("--fill",(zv/10).toFixed(2)+"%");zs.style.setProperty("--cmf",comfortSliderPct(n)+"%");}
syncZoomSize(n);var sb=bar.querySelector('[data-tl-ctrl="snap"]');if(sb)sb.classList.toggle("on",!!u.snap);var pb=FS.el.querySelector('.tl-fs-play [data-tl-ctrl="play"]');if(pb)pb.innerHTML=ico(u.playing?"ic-pause":"ic-play");}
function syncMuted(n){var u=uiOf(n),st=media(n);if(st.vA)st.vA.muted=(st.act==="A")?!!u.muted.video:true;if(st.vB)st.vB.muted=(st.act==="B")?!!u.muted.video:true;if(st.video)st.video.muted=!!u.muted.video;if(st.audio)st.audio.muted=!!u.muted.audio;}
function repaint(n){var d=tlData(n),u=d.ui;var roots=document.querySelectorAll('.tl-panel[data-tl-node="'+n.id+'"], .tl-fs[data-tl-node="'+n.id+'"]');Array.prototype.forEach.call(roots,function(root){var isFS=root.classList.contains("tl-fs");var tc=root.querySelector(isFS?".tl-fs-tc":".tl-tc");if(tc)tc.textContent=fmtCur(filmCur(n),filmLen(n))+" / "+fmt(filmLen(n),filmLen(n));Array.prototype.forEach.call(root.querySelectorAll('[data-tl-ctrl="play"]'),function(pb){pb.innerHTML=ico(u.playing?"ic-pause":"ic-play");});Array.prototype.forEach.call(root.querySelectorAll(".tl-mute"),function(mb){var t=mb.getAttribute("data-track");mb.classList.toggle("off",!!u.muted[t]);mb.innerHTML=ico(u.muted[t]?"ic-volume-off":"ic-volume");});var sb=root.querySelector(".tl-fs-snap");if(sb)sb.classList.toggle("on",!!u.snap);Array.prototype.forEach.call(root.querySelectorAll(".tl-seg"),function(sg){var on=!!(u.sel&&u.sel.id)&&sg.getAttribute("data-tl-seg")===u.sel.id&&sg.getAttribute("data-track")===u.sel.track;sg.classList.toggle("sel",on);});var ph=root.querySelector(".tl-play");if(ph)ph.style.left=pxOf(n,u.T,u.pps)+"px";syncBarDis(n,root);});syncFBar(n);}
function panelRoot(n){return document.querySelector('.cs-node[data-node="'+n.id+'"] .tl-panel[data-tl-node="'+n.id+'"]');}
function paintPanel(n){var root=panelRoot(n);if(!root)return false;var d=tlData(n),u=d.ui;var wantPrev=!!(d.segs.video.length||d.segs.audio.length)&&u.T!=null;if(wantPrev!==!!root.querySelector(".tl-prev"))return false;var span=spanOf(n),o=originOf(n),pps=u.pps;var ruler=root.querySelector(".tl-ruler");if(ruler){Array.prototype.forEach.call(ruler.querySelectorAll(".tl-tick"),function(x){x.remove();});ruler.insertAdjacentHTML("afterbegin",ticksHtml(n));}
Array.prototype.forEach.call(root.querySelectorAll(".tl-lane"),function(lane){var t=lane.getAttribute("data-track");lane.style.width=trackW(n,t)+"px";lane.innerHTML=laneBodyHtml(n,t);});var inner=root.querySelector(".tl-inner");if(inner)inner.style.width=trackW(n)+"px";syncAddCol(root,n);var pv=root.querySelector(".tl-prev");if(pv)pv.style.aspectRatio=(u.ar||(16/9)).toFixed(4);mount(root);paint(n);updateTimeCode(n);syncBarDis(n,root);repaint(n);return true;}
function render(ctx){var n=FS?HOST.nodeById(FS.id):null;if(n&&FS&&FS.el){var d=tlData(n),u=d.ui,span=spanOf(n),o=originOf(n);var inner=FS.el.querySelector(".tl-inner");if(inner)inner.style.width=trackW(n)+"px";var ruler=FS.el.querySelector(".tl-ruler");if(ruler){Array.prototype.forEach.call(ruler.querySelectorAll(".tl-tick"),function(x){x.remove();});ruler.insertAdjacentHTML("afterbegin",ticksHtml(n));}
var ph=FS.el.querySelector(".tl-play");if(ph)ph.style.left=pxOf(n,u.T,u.pps)+"px";Array.prototype.forEach.call(FS.el.querySelectorAll(".tl-lane"),function(lane){var t=lane.getAttribute("data-track");lane.style.width=trackW(n,t)+"px";lane.innerHTML=laneBodyHtml(n,t);});syncAddCol(FS.el,n);mount(FS.el);paint(n);updateTimeCode(n);syncFBar(n);syncLibIfStale(n);}
var done=(ctx&&!FS)?paintPanel(ctx):false;var skipForFs=!!(FS&&ctx&&ctx.id===FS.id);if(!done&&!skipForFs&&HOST.renderPanels)keepScrollAround(function(){HOST.renderPanels();});syncPlayheads();syncAllBars();syncAllHeads();}
function keepScrollAround(rebuild){var q=".tl-panel[data-tl-node], .tl-fs[data-tl-node]";var m={};Array.prototype.forEach.call(document.querySelectorAll(q),function(el){var id=el.getAttribute("data-tl-node"),sc=el.querySelector(".tl-scroll");if(id&&sc)m[id]=sc.scrollLeft;});try{if(rebuild)rebuild();}catch(e){}
Array.prototype.forEach.call(document.querySelectorAll(q),function(el){var id=el.getAttribute("data-tl-node"),sc=el.querySelector(".tl-scroll");if(id&&sc&&m[id]){try{sc.scrollLeft=m[id];}catch(e2){}}});}
function syncPlayheads(){Array.prototype.forEach.call(document.querySelectorAll(".tl-panel[data-tl-node], .tl-fs[data-tl-node]"),function(el){var n=HOST.nodeById(el.getAttribute("data-tl-node"));if(n)movePlayhead(n);});}
function init(host){HOST=host;document.addEventListener("mousedown",onDown,true);document.addEventListener("click",onClick,true);document.addEventListener("input",onZoomInput,true);document.addEventListener("change",onZoomChange,true);document.addEventListener("wheel",onWheel,{passive:false});window.addEventListener("keydown",onKey);}
function onKey(e){var n=FS?HOST.nodeById(FS.id):(HOST.selected&&HOST.selected());if(!n||n.type!=="timeline")return;var u=uiOf(n);if(e.key==="ArrowLeft"||e.key==="ArrowRight"){if(u.T==null)u.T=0;var step=e.shiftKey?1:FRAME;u.T=clamp(u.T+(e.key==="ArrowRight"?step:-step),0,endOf(n));HOST.save();updateTimeCode(n);movePlayhead(n);syncMedia(n,true);e.preventDefault();}}
function stripUi(nodes){var saved={};(nodes||[]).forEach(function(n){if(n&&n.data&&n.data.tl&&n.data.tl.ui){saved[n.id]=n.data.tl.ui;delete n.data.tl.ui;}});return saved;}
function restoreUi(nodes,saved){(nodes||[]).forEach(function(n){if(!n)return;if(saved&&saved[n.id]){if(!n.data)n.data={};if(!n.data.tl)n.data.tl={};n.data.tl.ui=saved[n.id];}else if(n&&n.data&&n.data.tl){tlData(n);}});}
function dispose(n){var st=MEDIA[n.id];if(st){[st.video,st.vA,st.vB].forEach(function(v){if(v){try{v.pause();}catch(e){}try{v.removeAttribute("src");v.load();}catch(e2){}}});if(st.audio)st.audio.pause();delete MEDIA[n.id];}
if(_raf){cancelAnimationFrame(_raf);_raf=null;}
if(FS&&FS.id===n.id)closeFull();}
function stopAll(){Object.keys(MEDIA).forEach(function(k){var st=MEDIA[k];if(st.video)st.video.pause();if(st.vA){try{st.vA.pause();}catch(e){}}
if(st.vB){try{st.vB.pause();}catch(e){}}
if(st.audio)st.audio.pause();var n=HOST.nodeById(k);if(n)uiOf(n).playing=false;});if(_raf){cancelAnimationFrame(_raf);_raf=null;}
if(FS)closeFull();}
function label(nodes,id){var k=0;(nodes||[]).forEach(function(x){if(x.type!=="timeline")return;k++;if(x.id===id)throw{__tlSeq:k};});return"视频合成";}
function seqOf(nodes,id){var k=0,hit=0;(nodes||[]).forEach(function(x){if(x.type!=="timeline")return;k++;if(x.id===id)hit=k;});return hit||k;}
return{init:init,bodyHtml:bodyHtml,mount:mount,render:render,capture:capture,acceptAsset:acceptAsset,stripUi:stripUi,restoreUi:restoreUi,dispose:dispose,stopAll:stopAll,syncBars:syncAllBars,selName:segTitle,seqOf:seqOf,tlData:tlData};})();