(function(){var API=(typeof window!=="undefined"&&window.API)||"";var mask=null,panel=null;function actsHtml(){return'<span class="img-acts">'
+'<button class="img-act" data-vs="sample" title="视频采样" aria-label="视频采样"><span class="ic ic-spark"></span></button>'
+'<button class="img-act" data-vs="face" title="脸部修复" aria-label="脸部修复"><span class="ic ic-star"></span></button>'
+'<a class="img-act" data-vs="dl" href="#" title="下载这段视频" aria-label="下载这段视频"><span class="ic ic-dl"></span></a>'
+'</span>';}
function bindActs(box,url,meta){var bar=box.querySelector(".img-acts");if(!bar)return;bar.querySelectorAll(".img-act").forEach(function(b){var kind=b.getAttribute("data-vs");if(kind==="dl"){b.href="/api/download?url="+encodeURIComponent(url);b.addEventListener("click",function(e){e.stopPropagation();});return;}
b.addEventListener("click",function(e){e.stopPropagation();open(url,meta||{},kind==="face"?"face":"refine");});});}
function ensurePanel(){if(panel)return panel;mask=document.createElement("div");mask.className="ie-mask";mask.innerHTML='<div class="ie-panel" role="dialog" aria-label="视频采样">'
+'  <div class="ie-head">'
+'    <span class="ie-title"><span class="ic ic-spark"></span><b id="vsTitleTx">视频采样</b></span>'
+'    <button class="ie-x" id="vsX" title="关闭"><span class="ic ic-x"></span></button>'
+'  </div>'
+'  <div class="ie-body">'
+'    <div class="ie-left">'
+'      <div class="ie-prev"><img id="vsPrev" alt="当前视频帧"></div>'
+'      <div class="ie-meta" id="vsMeta"></div>'
+'    </div>'
+'    <div class="ie-right">'
+'      <div class="ie-tabs" id="vsTabs"></div>'
+'      <div class="ie-params" id="vsParams"></div>'
+'    </div>'
+'  </div>'
+'  <div class="ie-foot">'
+'    <span class="ie-hint" id="vsHint">只对这一段已生成的视频做二次加工，不重跑整段</span>'
+'    <button class="ie-btn" id="vsCancel">取消</button>'
+'    <button class="ie-btn primary" id="vsGo">开始采样</button>'
+'  </div>'
+'</div>';document.body.appendChild(mask);panel=mask.querySelector(".ie-panel");mask.addEventListener("click",function(e){if(e.target===mask)close();});panel.querySelector("#vsX").addEventListener("click",close);panel.querySelector("#vsCancel").addEventListener("click",close);panel.querySelector("#vsGo").addEventListener("click",function(){submit();});return panel;}
var ctx={url:"",meta:{},tab:"refine",vals:{}};var ROWS={refine:[{key:"megapixels",label:"放大目标",type:"select",options:["0.5 MP","1.0 MP（768×720）","1.5 MP"],value:"1.0 MP（768×720）"},{key:"denoise",label:"重绘幅度",type:"range",min:0,max:1,step:0.05,value:0.25},{key:"steps",label:"调度步数",type:"range",min:1,max:30,step:1,value:3},{key:"scheduler",label:"调度器",type:"select",options:["beta","simple","karras"],value:"beta"},{key:"upscale_method",label:"上采样方式",type:"select",options:["lanczos","bilinear","nearest"],value:"lanczos"},{key:"upscale_model",label:"上采样模型",type:"select",options:["4x-UltraSharp.pth"],value:"4x-UltraSharp.pth"}],face:[{key:"paste_region",label:"修复范围",type:"select",options:["仅脸部","整幅"],value:"仅脸部"},{key:"denoise",label:"重绘幅度",type:"range",min:0,max:1,step:0.05,value:0.4},{key:"steps",label:"采样步数",type:"range",min:1,max:30,step:1,value:8},{key:"confidence",label:"检测置信度",type:"range",min:0.1,max:0.9,step:0.05,value:0.35},{key:"feather",label:"边缘羽化",type:"range",min:0,max:48,step:2,value:24},{key:"select",label:"脸部选择",type:"select",options:["最大人脸","全部人脸"],value:"最大人脸"}]};var TABS=[{v:"refine",t:"二次采样",ic:"ic-spark"},{v:"face",t:"脸部修复",ic:"ic-star"}];function rowHtml(r){if(r.type==="select"){var opts=r.options.map(function(o){return'<option'+(o===r.value?" selected":"")+'>'+o+'</option>';}).join("");return'<div class="ie-row"><label>'+r.label+'</label><select data-k="'+r.key+'">'
+opts+'</select></div>';}
return'<div class="ie-row"><label>'+r.label+'</label>'
+'<input type="range" data-k="'+r.key+'" min="'+r.min+'" max="'+r.max
+'" step="'+r.step+'" value="'+r.value+'">'
+'<b data-v="'+r.key+'">'+r.value+'</b></div>';}
function renderBody(){var p=ensurePanel();p.querySelector("#vsTitleTx").textContent=ctx.tab==="face"?"脸部修复（节点27）":"二次采样（节点18–24）";p.querySelector("#vsMeta").innerHTML=(ctx.meta&&(ctx.meta.width&&ctx.meta.height))?(ctx.meta.width+" × "+ctx.meta.height+" · "+(ctx.meta.durationSec||"")+" 秒<br>"
+"MiniMax H3 · 只加工这一段"):"MiniMax H3 · 只加工这一段";var img=p.querySelector("#vsPrev");if(ctx.meta&&ctx.meta.poster)img.src=ctx.meta.poster;var tabs=p.querySelector("#vsTabs");tabs.innerHTML="";TABS.forEach(function(t){var b=document.createElement("button");b.className="ie-chip"+(t.v===ctx.tab?" on":"");b.innerHTML='<span class="ic '+t.ic+'"></span>'+t.t;b.addEventListener("click",function(){ctx.tab=t.v;renderBody();});tabs.appendChild(b);});var box=p.querySelector("#vsParams");box.innerHTML="";ROWS[ctx.tab].forEach(function(r){box.insertAdjacentHTML("beforeend",rowHtml(r));ctx.vals[r.key]=r.value;});box.querySelectorAll("input[type=range]").forEach(function(inp){var out=box.querySelector('b[data-v="'+inp.dataset.k+'"]');var sync=function(){ctx.vals[inp.dataset.k]=parseFloat(inp.value);if(out)out.textContent=inp.value;};inp.addEventListener("input",sync);sync();});box.querySelectorAll("select").forEach(function(sel){sel.addEventListener("change",function(){ctx.vals[sel.dataset.k]=sel.value;});});}
function open(url,meta,tab){ctx.url=url||"";ctx.meta=meta||{};ctx.tab=tab||"refine";renderBody();mask.classList.add("show");}
function close(){if(mask)mask.classList.remove("show");}
function submit(){var body={video_url:ctx.url,tab:ctx.tab,params:ctx.vals,meta:ctx.meta};var go=panel.querySelector("#vsGo");go.disabled=true;fetch(API+"/api/runninghub/sample",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(r){return r.json().then(function(d){return{ok:r.ok,d:d};});}).then(function(res){if(res.ok&&res.d&&res.d.video_id){close();if(typeof window.toast==="function")window.toast("采样任务已创建，结果会出现在会话里");return;}
alert((res.d&&res.d.error)||"采样接口未接入。请先完成 P1 验证（确认二次采样/脸部修复在平台侧是否默认执行），再开此接口。");}).catch(function(){alert("采样请求失败：服务端未就绪。");}).finally(function(){go.disabled=false;});}
window.VideoSampler={actsHtml:actsHtml,bindActs:bindActs,open:open,close:close,ROWS:ROWS};})();