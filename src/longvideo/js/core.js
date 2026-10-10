
(function () {
  "use strict";
  const API = location.origin;

  
  
  
  const _tailThumbsToLoad = [];

  
  function _loadTailThumbs() {
    if (!_tailThumbsToLoad.length) return;
    const queue = _tailThumbsToLoad.splice(0);
    const _io = ("IntersectionObserver" in window) ? new IntersectionObserver((entries, obs) => {
      entries.forEach(en => {
        if (!en.isIntersecting) return;
        const el = en.target;
        obs.unobserve(el);
        _fillOneTail(el);
      });
    }, { rootMargin: "120px 0px" }) : null;
    queue.forEach(el => {
      if (_io) _io.observe(el);
      else _fillOneTail(el);  
    });
  }
  function _fillOneTail(el) {
    if (el._dataLoaded) return;
    const jobId = el.dataset.jobId || (window.LV_JOB_ID || "");
    const shotIdx = el.dataset.shotIdx;
    
    
    
    const segNo = el.dataset.segNo || shotIdx;
    if (!jobId || !segNo) return;
    const url = `${API}/api/jobs/${encodeURIComponent(jobId)}/segment/${parseInt(segNo, 10)}/tail.png`;
    el._dataLoaded = true;
    
    const img = new Image();
    img.className = "lv-thumb lv-thumb-tail-img";
    img.alt = "续接段首图（上一段尾帧）";
    img.loading = "lazy";
    img.onload = () => {
      
      const placeholder = el.querySelector(".lv-thumb-tail");
      if (placeholder) placeholder.style.display = "none";
      el.appendChild(img);
      
      const cap = document.createElement("span");
      cap.className = "lv-thumb-idx";
      cap.textContent = "图1";
      el.appendChild(cap);
    };
    img.onerror = () => {
      
      el._dataLoaded = false;  
    };
    img.src = url;
  }

  
  const style = document.createElement("style");
  style.id = "lvStyle";
  style.textContent = CSS;
  document.head.appendChild(style);

  
  const EXAMPLE = `老城区巷口，橘猫蹲在窗台。三花猫走近，从衣兜掏出一张写有手机号的纸条塞给橘猫："有户人家说家里闷得慌，请你们过去看看。"橘猫接过纸条："谢谢您，我晚点联系。"两只猫说话时嘴唇开合，街边有路人走过，傍晚阳光斑驳。`;

  const overlay = document.createElement("div");
  overlay.id = "lvOverlay";
  overlay.hidden = true;
  overlay.innerHTML = `
  <div class="lv-top">
    <button class="lv-back" id="lvBack" type="button" title="返回（退出长视频）">
      <span class="ic ic-cancel" aria-hidden="true"></span>
      <span>返回</span>
    </button>
    <div class="lv-steps">
      <button data-step="1" class="on">① 素材登记</button>
      <button data-step="2">② 分镜与生成</button>
      <button data-step="4">③ 成片预览</button>
    </div>
    <div class="lv-msg" id="lvMsg"></div>
  </div>
  <div class="lv-main">
    <aside class="lv-side" id="lvSide">
      <button class="lv-jobs-new" id="lvNewTask" type="button"><span class="ic ic-plus" aria-hidden="true"></span>新建任务</button>
      <div class="lv-jobs-h">最近任务</div>
      <div class="lv-side-bulk" id="lvSideBulk" hidden>
        <label><input type="checkbox" id="lvSelAllJobs"> 全选</label>
        <button class="lv-bdel cancel" id="lvDelJobs" type="button"><span class="lv-bdel-cancel">取消</span><span class="lv-bdel-del">删除（<span id="lvSelJobsCnt">0</span>）</span></button>
      </div>
      <div class="lv-side-list" id="lvJobsList"></div>
    </aside>
    <div class="lv-body">
    <section class="lv-pane" data-pane="1">
      <div class="lv-h">素材登记<span class="lv-sub">上传后给每张图填准确的角色 / 场景 / 道具名（<b>须与脚本中的称呼完全一致</b>），并标注</span></div>
      <div class="lv-drop" id="lvDrop"><span class="lv-drop-ic"><span class="ic ic-upload" aria-hidden="true"></span></span>点击或拖拽上传（图片 / 音频，数量不限）</div>
      <input type="file" id="lvFile" accept="image/*,audio/*" multiple hidden>
      
      <div class="lv-bulkrow">
        <div class="lv-bulkbar" id="lvBulk" hidden>
          <label><input type="checkbox" id="lvSelAll"> 全选</label>
          <button class="lv-bdel" id="lvBulkDel" disabled>移除选中（<span id="lvSelCnt">0</span>）</button>
          <span class="cc" id="lvBulkHint"></span>
        </div>
        <button class="lv-btn ghost" id="lvPickFromLib" type="button" title="从资产库选择已有素材加入当前任务"><span class="ic ic-library" aria-hidden="true" style="margin-right:5px"></span>从资产库选</button>
      </div>
      <div class="lv-afilter" id="lvAFilter" hidden></div>
      <div class="lv-assets" id="lvAssets"></div>
      <div class="lv-actions">
        <button class="lv-btn primary" id="lvTo2">下一步：分镜预览</button>
      </div>
    </section>
    <section class="lv-pane" data-pane="2" hidden>
      
      <div class="lv-progsum" id="lvProgSum" hidden>
        <span class="ps-n" id="lvPsN">0/0</span>
        <span class="ps-k">已用</span><span class="ps-v" id="lvPsElapsed">—</span>
        <span class="ps-k">预计还需</span><span class="ps-v" id="lvPsEta">—</span>
        <span class="ps-k">状态</span><span class="ps-v amber" id="lvPsSt">—</span>
        <div class="ps-bar"><i id="lvPsBar"></i></div>
        <div class="ps-acts">
          <button class="mini" id="lvTo4" type="button" hidden>查看成片</button>
          <button class="mini" id="lvRetry" type="button" hidden>补齐失败段</button>
          <button class="mini" id="lvResume" type="button" hidden>继续生成</button>
        </div>
        <span class="ps-hint" id="lvPsHint"></span>
      </div>
      
      <div class="lv-shots" id="lvShots"></div>
      
      <div class="lv-input-bar">
        <div class="lv-ro-hint" id="lvShotsRoHint" hidden><span class="ic ic-lock" aria-hidden="true"></span>分镜卡已锁定（生成后为只读存档）。单段修改 → 到「分镜与生成」屏逐段改提示词重提；整体重编 → <button class="mini" id="lvUnlockEdit" type="button" style="color:var(--vio);font-weight:700;text-decoration:underline">解锁编辑</button>（旧成片保留对照，改完再生成）</div>
        <textarea id="lvScript" class="lv-script" placeholder="在这里粘贴你的脚本（对话、动作、场景都可以），点「智能分镜」自动拆成分镜；脚本不能为空。"></textarea>
        
        <div class="lv-opts" id="lvOpts">
          <button class="lv-btn ghost" id="lvBack1">上一步</button>
          <div class="seg" id="lvSegLlm">
            <button type="button" class="seg-cur" title="分镜 LLM 引擎：2.5 稳，3.0 实验"><span class="seg-tx"></span><span class="seg-ar ic ic-chevron-down"></span></button>
            <select id="lvLlmModel" style="display:none">
              <option value="agnes-2.5-flash" selected>agnes-2.5-flash</option>
              <option value="agnes-3.0-flash">agnes-3.0-flash（实验）</option>
            </select>
            <div class="seg-pop"></div>
          </div>
          <button class="lv-btn primary" id="lvOptimize"><span class="ic ic-spark" aria-hidden="true"></span>智能分镜</button>
          <button class="mini" id="lvShotsHist" type="button" hidden title="历次分镜稿归档：可恢复/删除">分镜历史</button>
          <span class="lv-opts-sep" aria-hidden="true"></span>
          <div class="seg" id="lvSegModel">
            <button type="button" class="seg-cur"><span class="seg-tx"></span><span class="seg-ar ic ic-chevron-down"></span></button>
            <select id="lvOptModel" style="display:none">
              <option value="agnes-video-2.5-flash">agnes-video-2.5-flash</option>
            </select>
            <div class="seg-pop"></div>
          </div>
          <div class="seg" id="lvSegArRes">
            <button type="button" class="seg-cur" id="lvArResCur" title="画幅与分辨率（合并面板）"><span class="seg-tx" id="lvArResTx">16:9 · 720P</span><span class="seg-ar ic ic-chevron-down"></span></button>
            <select id="lvOptAspect" style="display:none">
              <option value="16:9">16:9</option>
              <option value="9:16">9:16</option>
              <option value="1:1">1:1</option>
              <option value="4:3">4:3</option>
              <option value="3:4">3:4</option>
              <option value="21:9">21:9</option>
            </select>
            <select id="lvOptRes" style="display:none" disabled>
              <option value="720P">720P</option>
            </select>
            
            <div class="seg-pop arsec-panel">
              <div class="arsec-sec">
                <div class="arsec-h">画幅比例</div>
                <div class="seg-ar-grid"></div>
              </div>
              <div class="arsec-sec">
                <div class="arsec-h">视频分辨率</div>
                <div class="arsec-sizes"></div>
              </div>
              <div class="arsec-foot"><button type="button" class="arsec-done">完成</button></div>
            </div>
          </div>
          <div class="lv-actions" id="lvStep2Act" hidden>
            <button class="lv-btn primary" id="lvTo3">开始生成</button>
          </div>
        </div>
      </div>
    </section>
    <section class="lv-pane lv-pane4" data-pane="4" hidden>
      
      <div class="lv-edit">
        <div class="lv-edit-h">提示词可重新编辑提交</div>
        <div class="lv-seg-cap">
          <div class="cap-l">
            <span class="segbadge" id="lvCapSeg">镜头 1</span>
          </div>
        </div>
        <div class="lv-matrow" id="lvMatRow">
          <span class="chip" id="lvChip1">图1 尾帧</span>
          <span class="chip" id="lvChip2">图2 角色</span>
          <span class="chip" id="lvChip3"><span class="ic ic-audio" aria-hidden="true"></span>音频</span>
        </div>
        <div class="lv-prompt-wrap">
          <div id="lvSegPrompt" class="lv-prompt-big"></div>
          <span class="cc" id="lvCC">0 字符</span>
        </div>
        <div class="lv-actionbar">
          <button class="nav" id="lvPrev" type="button"><span class="ic ic-chevron-left" aria-hidden="true"></span>上一段</button>
          <button class="nav" id="lvNext" type="button">下一段<span class="ic ic-chevron-right" aria-hidden="true"></span></button>
          <span class="lv-sec-edit" id="lvSecEdit" title="调整本段时长（界随所选视频模型），改动会随「重新生成本段」一起生效">
            <button class="lv-sec-btn" id="lvSecDown" type="button" aria-label="减少秒数"><span class="ic ic-minus" aria-hidden="true"></span></button>
            <span class="lv-sec-val" id="lvCapSec">5s</span>
            <button class="lv-sec-btn" id="lvSecUp" type="button" aria-label="增加秒数"><span class="ic ic-plus" aria-hidden="true"></span></button>
          </span>
          <button class="nav" id="lvHistory" type="button" title="查看本段提示词历史版本">历史</button>
          <span class="sp"></span>
          <button class="regen" id="lvRegen" type="button">重新生成本段</button>
        </div>
      </div>
      
      <div class="lv-prev">
        <div class="lv-prev-h">片段预览</div>
        <div class="lv-video-wrap">
          <video id="lvVideo" controls></video>
          <div class="play-ic" id="lvPlayIc"><span class="ic ic-resume" aria-hidden="true"></span></div>
        </div>
        <div class="lv-prev-ctrls">
          <button class="lv-prev-jump" id="lvJump" type="button">从该段开始播放<span class="ic ic-jump" aria-hidden="true"></span></button>
          <button class="lv-cont on" id="lvCont" type="button" aria-pressed="true" title="切换单段 / 全片播放模式"><span class="lv-cont-lbl">全片播放</span><span class="lv-toggle" aria-hidden="true"><span class="lv-toggle-knob"></span></span></button>
        </div>
        <div class="lv-prev-line">
          <span class="pl-seg" id="lvPrevCap"></span>
          <span class="lv-prev-status" id="lvPrevStatus">状态：—</span>
          <span class="lv-prev-meta" id="lvPrevMeta"></span>
          <span class="pl-sec" id="lvPrevSec">本段时长：5s</span>
        </div>
      </div>
      
      <div class="lv-strip-wrap">
        <div class="lv-strip" id="lvStrip"></div>
      </div>
    </section>

    </div>
  </div>`;
  
  document.querySelector(".main-area").appendChild(overlay);

  
  document.addEventListener("provider:changed", (e) => {
    const prov = (e.detail) || {};
    const vidSel = document.getElementById("lvOptModel");
    try {
      
      
      if (typeof window.lvApplyLlmModels === "function") window.lvApplyLlmModels(prov);
      if (vidSel && Array.isArray(prov.videoModels) && prov.videoModels.length) {
        const keep = vidSel.value;
        vidSel.innerHTML = prov.videoModels.map(m => `<option value="${m}">${m}</option>`).join("");
        if (prov.videoModels.includes(keep)) vidSel.value = keep;
      }
      
      if (Array.isArray(prov.videoModels) && prov.videoModels.length && !prov.videoModels.includes(lv.opts.model)) {
        lv.opts.model = prov.videoModels[0];
      }
      
      _segRefresh("lvSegLlm");
      _segRefresh("lvSegModel");
    } catch (err) {}
  });

  
  const $ = (id) => document.getElementById(id);
  const mediaSel = $("media");
  const msg = $("lvMsg");
  
  
  
  
  function setMsg(t, ico) {
    msg.innerHTML = t ? ((ico ? '<span class="ic ic-' + ico + '" aria-hidden="true"></span>' : "") + _esc(t)) : "";
    msg.classList.remove("error");
    clearTimeout(msg._timeout);
    if (!t) return;
    
    if (/[!✗❌]/.test(t)) msg._timeout = setTimeout(() => { msg.textContent = ""; }, 10000);
    else if (!/✓/.test(t)) msg._timeout = setTimeout(() => { msg.textContent = ""; }, 8000);
  }
  function err(t) {
    
    setMsg(t);
    msg.classList.add("error");
    clearTimeout(msg._timeout);
    msg._timeout = setTimeout(() => { msg.textContent = ""; msg.classList.remove("error"); }, 10000);
  }

  
  let _confirmEl = null;
  function lvConfirm(opts) {
    const o = typeof opts === "string" ? { message: opts } : (opts || {});
    return new Promise((resolve) => {
      if (_confirmEl) _confirmEl.remove();
      const wrap = document.createElement("div");
      wrap.className = "lv-cf";
      wrap.innerHTML = `
        <div class="lv-cf-mask"></div>
        <div class="lv-cf-box${o.danger ? " danger" : ""}">
          <div class="lv-cf-t"></div>
          <div class="lv-cf-m"></div>
          <div class="lv-cf-btns"><button type="button" class="lv-cf-cancel">取消</button><button type="button" class="lv-cf-ok"></button></div>
        </div>`;
      wrap.querySelector(".lv-cf-t").textContent = o.title || (o.danger ? "危险操作" : "确认操作");
      wrap.querySelector(".lv-cf-m").textContent = o.message || "";
      wrap.querySelector(".lv-cf-ok").textContent = o.okText || "确定";
      const done = (v) => { wrap.remove(); _confirmEl = null; document.removeEventListener("keydown", onKey, true); resolve(v); };
      const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); done(false); } };
      wrap.querySelector(".lv-cf-mask").addEventListener("click", () => done(false));
      wrap.querySelector(".lv-cf-cancel").addEventListener("click", () => done(false));
      wrap.querySelector(".lv-cf-ok").addEventListener("click", () => done(true));
      document.addEventListener("keydown", onKey, true);
      document.body.appendChild(wrap);
      _confirmEl = wrap;
      wrap.querySelector(".lv-cf-ok").focus();
    });
  }

  
  function lvPick(opts) {
    const items = (opts && opts.items) || [];
    return new Promise((resolve) => {
      const wrap = document.createElement("div");
      wrap.className = "lv-pk";
      const rows = items.map((it, i) => {
        const thumb = it.type === "audio"
          ? `<span class="lv-pk-th audio"><span class="ic ic-audio" aria-hidden="true"></span></span>`
          : (it.url ? `<img src="${_thumb(it.url, 128)}" alt="">` : `<span class="lv-pk-th"><span class="ic ic-image" aria-hidden="true"></span></span>`);
        return `<div class="lv-pk-it" data-i="${i}">${thumb}<span class="nm">${esc(it.label || it.name || "")}<small>${esc(it.name || "")}</small></span></div>`;
      }).join("");
      wrap.innerHTML = `
        <div class="lv-pk-mask"></div>
        <div class="lv-pk-box">
          <div class="lv-pk-t"></div>
          <div class="lv-pk-list">${rows || '<div class="lv-pk-empty">没有可选素材</div>'}</div>
        </div>`;
      wrap.querySelector(".lv-pk-t").textContent = (opts && opts.title) || "选择素材";
      const done = (v) => { wrap.remove(); document.removeEventListener("keydown", onKey, true); resolve(v); };
      const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); done(null); } };
      wrap.querySelector(".lv-pk-mask").addEventListener("click", () => done(null));
      wrap.querySelector(".lv-pk-list").addEventListener("click", (e) => {
        const it = e.target.closest(".lv-pk-it");
        if (it) done(items[parseInt(it.dataset.i, 10)] || null);
      });
      document.addEventListener("keydown", onKey, true);
      document.body.appendChild(wrap);
    });
  }

  

  
  const lv = {
    assets: [],   
    shots: [],    
    jobId: null,
    segs: [],     
    selSeg: 1,
    step: 1,
    jobStatus: null,  
    shotsHist: [],    
    curShotVer: -1,    
    genStartTs: 0,     
    poll: null,
    opts: { llmModel: "agnes-2.5-flash", model: "agnes-video-2.5-flash", aspect_ratio: "16:9", resolution: "720P" },  
  };

  
  const LS_KEY = "lv_state_v1";
  function saveState() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        media: mediaSel.value,
        step: lv.step || 1,
        assets: lv.assets,
        shots: lv.shots,
        jobId: lv.jobId,
        selSeg: lv.selSeg,
        jobStatus: lv.jobStatus,
        genStartTs: lv.genStartTs || 0,
        script: lvScript ? lvScript.value : "",
        opts: lv.opts || {},
        storyboardBasis: lv.storyboardBasis || null,   
      }));
    } catch (e) {}
  }
  function loadState() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || "null"); }
    catch (e) { return null; }
  }
  function clearState() { try { localStorage.removeItem(LS_KEY); } catch (e) {} }

  
  (async function syncOptsFromConfig() {
    try {
      const r = await fetch("/api/config");
      if (!r.ok) return;
      const d = await r.json();
      
      window.__lvProvider = d.provider || {};
      document.dispatchEvent(new CustomEvent("provider:changed", { detail: d.provider || {} }));
    } catch (e) {}
  })();

  
  
  
  
  
  let _resumed = false;
  function resumeFromState() {
    const st = loadState();
    if (_resumed) {
      
      _syncOptsToUI();
      goStep(lv.step || 1);
      return;
    }
    if (st) {
      lv.assets = st.assets || [];
      lv.shots = st.shots || [];
      lv.jobId = st.jobId || null;
      lv.selSeg = st.selSeg || 1;
      lv.step = st.step || 1;
      lv.jobStatus = st.jobStatus || null;
      lv.genStartTs = st.genStartTs || 0;
      lv.storyboardBasis = st.storyboardBasis || null;   
      if (st.opts) lv.opts = Object.assign(lv.opts, st.opts);   
      
      
      
      
      if (lvScript) {
        if (st.script && st.script !== EXAMPLE) lvScript.value = st.script;
        else lvScript.value = "";   
      }
      _resumed = true;
      _syncOptsToUI();
      renderAssets();
      renderShots();
      lvStep2Act.hidden = lv.shots.length === 0;
      
      lv.step = _normStep(lv.step || 1);
      if (lv.jobId) openJob(lv.jobId, lv.step, true);
      else goStep(lv.step || 1);
    } else {
      _resumed = true;
      goStep(1);   
    }
    
  }

  
  
  
  let _openSeq = 0;
  async function openJob(jobId, preferredStep, fromRestore) {
    const seq = ++_openSeq;   
    stopPoll();   
    setMsg("加载任务中…");
    try {
      
      await fetch(API + "/api/jobs/" + jobId + "/resume", { method: "POST" }).catch(() => {});
      if (seq !== _openSeq) return;   
      const r = await fetch(API + "/api/jobs/" + jobId);
      const j = await r.json();
      if (seq !== _openSeq) return;   
        if (!r.ok) {
        
        err("任务不存在，已重置");
        lv.jobId = null; lv.jobStatus = null; lv.segs = []; lv.shots = []; lv.assets = [];
        renderAssets();   
        clearState();
        goStep(1);
        return;
      }
      lv.jobId = jobId;
      const st = (j.job && j.job.status) || "draft";
      lv.jobStatus = st;
      
      if (j.gen_params) { lv.opts = Object.assign(lv.opts, j.gen_params); _syncOptsToUI(); }
      
      
      lv.assets = Array.isArray(j.assets) ? j.assets : [];
      lv.shots  = Array.isArray(j.shots)  ? j.shots  : [];
      lv.segs = [];   
                      
      lv.shotsHist = Array.isArray(j.shots_history) ? j.shots_history : [];   
      
      const _csv = (typeof j.current_shot_ver === "number") ? j.current_shot_ver : -1;
      lv.curShotVer = (_csv >= 0 && _csv < lv.shotsHist.length) ? _csv : (lv.shotsHist.length ? lv.shotsHist.length - 1 : -1);
      const _shb = $("lvShotsHist"); if (_shb) _shb.hidden = lv.shotsHist.length === 0;
      if (lvScript) lvScript.value = j.script || "";
      await loadLibrary().catch(() => {});   
      renderAssets();
      renderShots();
      lvStep2Act.hidden = lv.shots.length === 0;
      _syncStartBtn();          
      
      
      
      const _preferRaw = (typeof preferredStep === "number" && preferredStep >= 1) ? preferredStep : (lv.step || 1);
      const _prefer = _normStep(_preferRaw);
      const _pick = (fallback) => (_prefer && canGoStep(_prefer)) ? _prefer : fallback;
      if (st === "draft") {
        
        const step = _pick(lv.shots.length ? 2 : 1);
        goStep(step);
        if (lv.shots.length && step === 2) {
          
          
          
          
          
          
          const _v3Marker = /\u56fe\d+\u7684[\u4e00-\u9fa5]{2,}/;
          const hasV3Engine = lv.shots.some((s) => _v3Marker.test(s.prompt || ""));
          if (!hasV3Engine) {
            setMsg("当前分镜为较早版本，画面细节可能不全，建议重新点「智能分镜」生成一版新的");
          } else {
            setMsg(fromRestore ? "已回到分镜步骤" : "已进入分镜步骤");
          }
        } else {
          
          
          setMsg(fromRestore ? `已恢复到${lv.shots.length ? "分镜步骤" : "素材上传"}` : `已打开${lv.shots.length ? "分镜步骤" : "素材上传"}`);
        }
      } else if (st === "completed") {
        lv.segs = j.segments || [];
        lv.finalUrl = j.final_url || (j.job && j.job.final_url) || null;
        
        if (!lv.genStartTs) {
          const _fs = lv.segs.filter((s) => s.started_at).sort((a, b) => a.started_at - b.started_at)[0];
          lv.genStartTs = (_fs && _fs.started_at) || (Date.now() / 1000);
        }
        const step = _pick(4);
        goStep(step);
        if (step === 4) buildStrip();
        renderShots();   
        
        
        if (lv.segs.some((s) => s.status === "processing")) {
          startPoll();
          setMsg("有分镜正在后台重新生成，完成后自动刷新视频…");
        } else {
          setMsg("成片已生成");
        }
      } else if (st === "failed") {
        lv.segs = j.segments || [];
        
        if (!lv.genStartTs) {
          const _fs = lv.segs.filter((s) => s.started_at).sort((a, b) => a.started_at - b.started_at)[0];
          lv.genStartTs = (_fs && _fs.started_at) || (Date.now() / 1000);
        }
        const step = _pick(2);   
        goStep(step);
        renderShots();
        
        if (lv.segs.some((s) => s.status === "processing")) startPoll();
        if (step === 2) err("该任务上次失败：" + ((j.job && j.job.error) || ""));
      } else if (st === "cancelled") {
        
        
        lv.segs = j.segments || [];
        const step = _pick(2);
        goStep(step);
        renderShots();
        
        
        const _flying = lv.segs.some((s) => s.status === "processing");
        if (_flying) startPoll();
        setMsg(_flying ? "任务已停止；在飞的一段会跑完保留（不再发新提交），点「继续生成」可续跑剩余段"
                       : "任务已停止；点「继续生成」可续跑剩余段");
      } else {
        lv.segs = j.segments || [];
        const step = _pick(2);   
        
        
        if (!lv.genStartTs) {
          const _fs = lv.segs.filter((s) => s.started_at).sort((a, b) => a.started_at - b.started_at)[0];
          lv.genStartTs = (_fs && _fs.started_at) || (Date.now() / 1000);
        }
        
        
        
        startPoll();
        goStep(step);
        renderShots();
        setMsg("生成中，已接着上次进度继续");
      }
      saveState();
    } catch (e) {
      err("加载任务异常：" + e.message);
      
      
      const _fb = lv.jobStatus === "processing" ? 3
                : lv.jobStatus === "completed"  ? 4
                : 1;
      goStep(canGoStep(_fb) ? _fb : 1);
    }
    loadJobs();
  }

  
  let _draftPending = false;
  
  function _cleanAssets(list) {
    return (list || []).map((a) => {
      const c = Object.assign({}, a);
      Object.keys(c).forEach((k) => { if (k.charAt(0) === "_") delete c[k]; });
      return c;
    });
  }
  async function saveDraftNow() {
    
    
    
    
    
    
    if (!lv.jobId) return null;
    
    
    const _hasScript = lvScript && lvScript.value && lvScript.value.trim() !== "";
    if (!lv.assets.length && !lv.shots.length && !_hasScript) return lv.jobId;
    const stage = lv.shots.length ? "分镜预览" : "素材登记";
    
    
    
    
    _draftPending = true;
    try {
      const r = await fetch(API + "/api/jobs/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: lv.jobId || null,
          stage,
          script: lvScript ? lvScript.value : "",
          assets: _cleanAssets(lv.assets),
          shots: lv.shots,
          gen_params: lv.opts || {},
        }),
      });
      const j = await r.json();
      if (r.ok && j.job_id) {
        if (!lv.jobId) lv.jobId = j.job_id;
        saveState();
      }
    } catch (e) {}
    finally { _draftPending = false; }
    return lv.jobId;
  }
  
  
  async function ensureJob() {
    if (lv.jobId) return lv.jobId;
    
    
    
    const _d = new Date();
    const _defaultName = "任务 " + (_d.getMonth() + 1) + "/" + _d.getDate() + " " +
      _d.getHours().toString().padStart(2, "0") + ":" + _d.getMinutes().toString().padStart(2, "0");
    try {
      const r = await fetch(API + "/api/jobs/draft", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: null, name: _defaultName, stage: "素材登记", script: "", assets: [], shots: [], gen_params: lv.opts || {} }),
      });
      const j = await r.json();
      if (r.ok && j.job_id) { lv.jobId = j.job_id; saveState(); loadJobs(); }
    } catch (e) {}
    return lv.jobId;
  }
  let _draftTimer = null;
  function saveDraft() {
    
    
    
    if (!lv.jobId) { clearTimeout(_draftTimer); _draftTimer = null; return; }
    clearTimeout(_draftTimer);
    _draftTimer = setTimeout(() => { _draftTimer = null; saveDraftNow().then(loadJobs); }, 500);
  }

  
  
  
  
  const _optimisticName = new Map();  
  const _lastJobsById = new Map();    

  
  let _jobsToken = 0;
  async function loadJobs() {
    const box = $("lvJobsList");
    if (!box) return;
    
    
    try {
      const pending = JSON.parse(localStorage.getItem("_lv_pending_name") || "{}");
      const ids = Object.keys(pending);
      if (ids.length) {
        for (const jid of ids) {
          const nm = pending[jid];
          const blob = new Blob([JSON.stringify({ name: nm })], { type: "application/json" });
          
          let sent = false;
          if (navigator.sendBeacon) {
            try { sent = navigator.sendBeacon(API + "/api/jobs/" + jid, blob); } catch (_) {}
          }
          if (!sent) {
            fetch(API + "/api/jobs/" + jid, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: nm }), keepalive: true })
              .catch(() => {});
          }
        }
        
      }
    } catch (_) {}
    
    if (box.querySelector(".lv-job-title.editing")) {
      return;
    }
    const my = ++_jobsToken;
    let jobs = [];
    try {
      const r = await fetch(API + "/api/jobs");
      const j = await r.json();
      jobs = j.jobs || [];
    } catch (e) {
      if (my === _jobsToken) box.innerHTML = '<div class="lv-jobs-empty">任务列表加载失败</div>';
      return;
    }
    if (my !== _jobsToken) return; 

    box.innerHTML = "";
    
    if (!lv.jobId && (lv.assets.length || lv.shots.length) && !_draftPending) {
      const stg = lv.shots.length ? "分镜预览" : "素材登记";
      const card = document.createElement("div");
      card.className = "lv-job local";
      card.innerHTML = `
        <div class="lv-job-row1">
          <span class="lv-job-title placeholder">未命名任务</span>
        </div>
        <div class="lv-job-row2">
          <span class="lv-job-stage stage-${stg}">${stg}</span>
          <span class="lv-job-cnt">未保存</span>
          <span class="lv-job-meta">本机草稿</span>
        </div>`;
      card.addEventListener("click", () => goStep(lv.shots.length ? 2 : 1));
      box.appendChild(card);
    }

    if (!jobs.length && !box.children.length) {
      box.innerHTML = '<div class="lv-jobs-empty">暂无任务，先从「素材登记」开始</div>';
      return;
    }

    
    _lastJobsById.clear();
    jobs.forEach((jb) => { _lastJobsById.set(jb.job_id, jb); });

    jobs.forEach((jb) => {
      const isCur = jb.job_id === lv.jobId;
      
      const opt = _optimisticName.get(jb.job_id);
      if (opt) jb.name = opt.name;
      const el = document.createElement("div");
      el.className = "lv-job" + (isCur ? " on" : "");
      const created = jb.created_at ? new Date(jb.created_at * 1000).toLocaleString() : "";
      
      
      const stage = jb.status === "completed" ? "成片预览"
        : jb.status === "failed" ? "失败"
        : jb.status === "cancelled" ? "已停止"
        : (jb.stage || (jb.status === "processing" ? "生成中" : "草稿"));
      const total = jb.segment_count || 0;
      const done  = jb.done_count || 0;
      const pct   = total ? Math.round(done / total * 100) : 0;
      const doneAll = total > 0 && done >= total;
      const shortDate = created ? created.replace(/^.*?\d{4}\/(\d+\/\d+).*?(\d+:\d+).*$/, "$1 $2") : "";
      el.innerHTML = `
        <input type="checkbox" class="lv-job-sel" data-id="${jb.job_id}">
        <div class="lv-job-row1">
          <span class="lv-job-title${_esc(jb.name||"") ? "" : " placeholder"}" data-id="${jb.job_id}" data-ph="未命名任务">${_esc(jb.name||"") || "未命名任务"}</span>
          ${isCur ? `<span class="lv-job-cur">编辑中</span>` : ""}
          ${jb.status === "processing" || jb.status === "pending" ? `<button class="lv-job-stop" type="button" data-id="${jb.job_id}" title="停止生成（保留已完成段）">停止</button>` : ""}
          ${jb.status === "cancelled" ? `<span class="lv-job-stopped">已停止</span>` : ""}
          <button class="sess-dots lv-job-dots" type="button" title="更多操作" aria-label="更多">⋮</button>
        </div>
        <div class="sess-menu">
          <div class="sess-menu-item" data-act="batch"><span class="ic ic-check"></span>批量管理</div>
          <div class="sess-menu-item" data-act="rename"><span class="ic ic-pencil"></span>重命名</div>
          <div class="sess-menu-item" data-act="delete"><span class="ic ic-del"></span>删除</div>
        </div>
        <div class="lv-job-row2">
          <span class="lv-job-stage stage-${_esc(stage)}">${_esc(stage)}</span>
          <span class="lv-job-cnt">${total > 0 ? `${done}/${total} 段` : "待分镜"}</span>
          <span class="lv-job-meta">${_esc(shortDate)}</span>
        </div>
        ${jb.error ? `<div class="lv-job-err" title="${_esc(jb.error)}"><span class="ic ic-warn" aria-hidden="true"></span>${_esc(jb.error)}</div>` : ""}
        <div class="lv-job-bar"><div class="lv-job-bar-fill${doneAll ? " done" : ""}" style="width:${pct}%"></div></div>`;
      
      el.addEventListener("click", () => {
        if (_jobManage) {
          const cb = el.querySelector(".lv-job-sel");
          cb.checked = !cb.checked;
          syncJobSel();
          return;
        }
        openJob(jb.job_id, null, false);
      });
      
      const dots = el.querySelector(".lv-job-dots");
      const menu = el.querySelector(".sess-menu");
      dots.addEventListener("click", (e) => {
        e.stopPropagation();
        const wasOpen = menu.classList.contains("open");
        closeLvJobMenus();
        if (!wasOpen) menu.classList.add("open");
      });
      menu.querySelector('[data-act="batch"]').addEventListener("click", (e) => { e.stopPropagation(); closeLvJobMenus(); setJobManage(true); });
      menu.querySelector('[data-act="rename"]').addEventListener("click", (e) => { e.stopPropagation(); closeLvJobMenus(); if (startTitleEdit) startTitleEdit(); });
      menu.querySelector('[data-act="delete"]').addEventListener("click", (e) => { e.stopPropagation(); closeLvJobMenus(); deleteJob(jb.job_id, jb.name || jb.stage || jb.status); });
      const stopBtn = el.querySelector(".lv-job-stop");
      if (stopBtn) {
        stopBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (!(await lvConfirm({ title: "停止生成", message: `将停止「${jb.name || "此任务"}」的生成，已完成段保留。`, okText: "停止", danger: true }))) return;
          try {
            const r = await fetch(API + `/api/jobs/${jb.job_id}/cancel`, { method: "POST" });
            if (!r.ok) { const j2 = await r.json().catch(() => ({})); err("停止失败：" + (j2.error || "")); return; }
            
            if (Array.isArray(lv.segs) && lv.jobId === jb.job_id) {
              lv.segs = lv.segs.map((s) => s.status === "processing" || s.status === "pending" ? { ...s, status: "cancelled" } : s);
              renderShots();
              _updateProgSum();
            }
            setMsg("已停止生成");
            loadJobs();
          } catch (ex) { err("停止异常：" + ex.message); }
        });
      }
      const cbx = el.querySelector(".lv-job-sel");
      cbx.addEventListener("click", (e) => e.stopPropagation());
      cbx.addEventListener("change", syncJobSel);
      
      const titleEl = el.querySelector(".lv-job-title");
      const startTitleEdit = titleEl ? attachTitleEdit(titleEl, jb) : null;
      box.appendChild(el);
    });

    
    const hasJobs = jobs.length > 0;
    if (!hasJobs && _jobManage) setJobManage(false);
    syncJobSel();
    _syncStepLocks();   
  }

  
  
  
  
  
  
  function attachTitleEdit(el, jb) {
    if (el.dataset.editBound) return;
    el.dataset.editBound = "1";
    const PH = el.dataset.ph || "未命名任务";
    const startEdit = () => {
      if (el.dataset.editing === "1") return;
      el.dataset.editing = "1";
      el.classList.add("editing");   
      el.dataset.orig = el.textContent.trim();
      const cur = el.dataset.orig;
      
      el.innerHTML = "";
      const input = document.createElement("input");
      input.type = "text";
      input.value = (cur === PH) ? "" : cur;     
      input.placeholder = PH;
      input.maxLength = 60;
      input.style.cssText = "width:100%;border:none;outline:none;font:inherit;color:inherit;background:transparent;padding:0;margin:0;";
      el.appendChild(input);
      input.focus();
      input.select();
      const finish = (save) => {
        if (el.dataset.editing !== "1") return;
        el.dataset.editing = "0";
        el.classList.remove("editing");
        const newName = (input.value || "").trim().slice(0, 60);
        const orig = el.dataset.orig || "";
        el.removeChild(input);
        el.classList.toggle("placeholder", !newName);
        
        
        if (save && !newName) {
          el.textContent = orig || PH;
          el.classList.toggle("placeholder", !orig);
          return;
        }
        el.textContent = newName || PH;
        if (save && newName !== orig) {
          
          _optimisticName.set(jb.job_id, { name: newName, ts: Date.now() });
          
          
          
          
          const url = API + "/api/jobs/" + jb.job_id;
          const body = JSON.stringify({ name: newName });
          const doPatch = (retries) => {
            if (retries <= 0) {
              
              try {
                if (navigator.sendBeacon) {
                  
                  const blob = new Blob([body], { type: "application/json" });
                  navigator.sendBeacon(url, blob);
                  setMsg("已发送改名请求「" + newName + "」，结果可能稍晚生效");
                  return;
                }
              } catch (_) {}
              
              try {
                const pending = JSON.parse(localStorage.getItem("_lv_pending_name") || "{}");
                pending[jb.job_id] = newName;
                localStorage.setItem("_lv_pending_name", JSON.stringify(pending));
                err("网络异常，改名暂存 localStorage，下次页面加载会自动重发");
              } catch (_) {}
              el.textContent = orig || PH;
              el.classList.toggle("placeholder", !orig);
              _optimisticName.delete(jb.job_id);
              return;
            }
            fetch(url, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body,
              keepalive: true,
            }).then(r => r.json()).then(j2 => {
              if (j2.ok) {
                jb.name = j2.name || "";
                
                _optimisticName.set(jb.job_id, { name: j2.name || "", ts: Date.now() });
                
                try {
                  const pending = JSON.parse(localStorage.getItem("_lv_pending_name") || "{}");
                  if (pending[jb.job_id]) { delete pending[jb.job_id]; localStorage.setItem("_lv_pending_name", JSON.stringify(pending)); }
                } catch (_) {}
                setMsg("✓ 任务已重命名：「" + (j2.name || "未命名任务") + "」");
                loadJobs();
                setTimeout(() => {
                  const v = _optimisticName.get(jb.job_id);
                  if (v && v.name === (j2.name || "")) _optimisticName.delete(jb.job_id);
                }, 3000);
              } else {
                _optimisticName.delete(jb.job_id);
                el.textContent = orig || PH;
                el.classList.toggle("placeholder", !orig);
                err("重命名失败：" + (j2.error || "服务端拒绝"));
                loadJobs();
              }
            }).catch(() => {
              
              doPatch(retries - 1);
            });
          };
          doPatch(3);
        } else if (!save) {
          
        } else {
          
        }
      };
      input.addEventListener("keydown", (e) => {
        
        
        if (e.isComposing || e.keyCode === 229) return;
        if (e.key === "Enter") { e.preventDefault(); finish(true); el.blur(); }
        else if (e.key === "Escape") { e.preventDefault(); finish(false); el.blur(); }
      });
      
      input.addEventListener("blur", () => {
        setTimeout(() => { finish(true); }, 0);
      });
    };
    
    
    
    el.addEventListener("click", (e) => { e.stopPropagation(); startEdit(); });
    el.addEventListener("dblclick", (e) => { e.stopPropagation(); startEdit(); });
    return startEdit;
  }

  
  function closeLvJobMenus() {
    document.querySelectorAll("#lvJobsList .sess-menu.open").forEach((m) => m.classList.remove("open"));
  }
  if (!window.__lvJobMenuWired) {
    window.__lvJobMenuWired = true;
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".sess-menu")) closeLvJobMenus();
    });
  }

  function syncJobSel() {
    const box = $("lvJobsList");
    if (!box) return;
    const all = [...box.querySelectorAll(".lv-job-sel")];
    const checked = all.filter((c) => c.checked);
    const cnt = checked.length;
    $("lvSelJobsCnt").textContent = cnt;
    
    const del = $("lvDelJobs");
    del.classList.toggle("cancel", cnt === 0);
    del.disabled = false;
    $("lvSelAllJobs").checked = all.length > 0 && checked.length === all.length;
    $("lvSelAllJobs").indeterminate = cnt > 0 && cnt < all.length;
  }

  async function deleteJob(jobId, label) {
    if (!(await lvConfirm({ title: "删除任务", message: "确定删除任务「" + (label || jobId) + "」？成片与分段可在资产库中查看。", danger: true, okText: "删除" }))) return;
    setMsg("删除中…");
    try {
      const r = await fetch(API + "/api/jobs/" + encodeURIComponent(jobId), { method: "DELETE" });
      const j = await r.json();
      if (!r.ok) { err(j.error || "删除失败"); return; }
      
      if (lv.jobId === jobId) {
        lv.jobId = null; lv.jobStatus = null; lv.segs = []; lv.shots = []; lv.assets = [];
        renderAssets();   
        lvShots.innerHTML = "";
        if ($("lvScript")) $("lvScript").value = "";   
        clearState();
        _syncStartBtn();   
        goStep(1);
      }
      setMsg("已删除任务");
      loadJobs();
    } catch (e) { err("删除异常：" + e.message); }
  }

  async function deleteJobs() {
    const box = $("lvJobsList");
    if (!box) return;
    const ids = [...box.querySelectorAll(".lv-job-sel:checked")].map((c) => c.getAttribute("data-id"));
    if (!ids.length) return;
    if (!(await lvConfirm({ title: "删除任务", message: "确定删除选中的 " + ids.length + " 个任务？成片与分段可在资产库中查看。", danger: true, okText: "删除" }))) return;
    setMsg("批量删除中…");
    try {
      const r = await fetch(API + "/api/jobs/delete_batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const j = await r.json();
      if (!r.ok) { err(j.error || "批量删除失败"); return; }
      
      if (lv.jobId && ids.includes(lv.jobId)) {
        lv.jobId = null; lv.jobStatus = null; lv.segs = []; lv.shots = []; lv.assets = [];
        renderAssets();   
        lvShots.innerHTML = "";
        if ($("lvScript")) $("lvScript").value = "";   
        clearState();
        _syncStartBtn();   
        goStep(1);
      }
      setMsg(`已删除 ${j.ok || 0}/${j.total || ids.length} 个任务` + ((j.total || 0) > (j.ok || 0) ? "，部分失败" : ""));
      loadJobs();
    } catch (e) { err("批量删除异常：" + e.message); }
  }

  async function continueJob(jobId) {
    setMsg("继续任务中…");
    try { await openJob(jobId, null, false); }
    catch (e) { err("继续任务异常：" + e.message); }
    setMsg("");
  }

  async function newTask() {
    
    const isGenerated = lv.jobId && lv.jobStatus && lv.jobStatus !== "draft";
    if (isGenerated && !(await lvConfirm({ title: "新建任务", message: "当前任务已生成/进行中，确定新建一个任务？当前任务会保留在「最近任务」中，可随时回来继续。" }))) return;
    
    
    clearTimeout(_draftTimer); _draftTimer = null;
    
    await saveDraftNow();   
    lv.assets = []; lv.shots = []; lv.jobId = null; lv.jobStatus = null; lv.segs = []; lv.selSeg = 1; lv.step = 1;
    lv.shotsHist = [];   
    const _shb2 = $("lvShotsHist"); if (_shb2) _shb2.hidden = true;
    if (lvScript) lvScript.value = "";   
    clearState();
    renderAssets();
    lvShots.innerHTML = "";
    const _rh = $("lvShotsRoHint"); if (_rh) _rh.hidden = true;
    const _ps = $("lvProgSum"); if (_ps) _ps.hidden = true;   
    lvStep2Act.hidden = true;
    _syncStartBtn();   
    goStep(1);
    loadJobs();
    setMsg("已新建任务（原草稿已保留在「最近任务」），从第 1 步开始");
  }

  
  async function withBtn(btn, loadingText, fn) {
    if (!btn || btn.disabled) return;
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="lv-spin"></span>${loadingText}`;
    try { await fn(); }
    catch (e) { err(e && e.message ? e.message : String(e)); }
    finally {
      btn.disabled = false;
      btn.innerHTML = orig;
    }
  }
