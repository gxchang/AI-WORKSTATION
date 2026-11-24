
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
    <button class="lv-back" id="lvBack" type="button" title="返回（退出长视频）" aria-label="返回（退出长视频）">
      <span class="ic ic-arrow-left" aria-hidden="true"></span>
    </button>
    
    <div class="lv-steps">
      <button data-step="1" class="on" type="button">
        <span class="lv-step-dot"><span class="lv-step-no">1</span><span class="ic ic-check lv-step-tick" aria-hidden="true"></span></span>
        <span class="lv-step-tx">素材登记</span>
      </button>
      <span class="lv-step-line" aria-hidden="true"><i></i></span>
      <button data-step="2" type="button">
        <span class="lv-step-dot"><span class="lv-step-no">2</span><span class="ic ic-check lv-step-tick" aria-hidden="true"></span></span>
        <span class="lv-step-tx">分镜生成</span>
      </button>
    </div>
    <div class="lv-msg" id="lvMsg"></div>
  </div>
  <div class="lv-main">
    <aside class="lv-side" id="lvSide">
      
      <button class="lv-side-expand" id="lvSideExpand" type="button" title="展开任务列表" aria-label="展开任务列表">
        <span class="ic ic-panel-right" aria-hidden="true"></span>
      </button>
      <div class="lv-side-top">
        <button class="lv-jobs-new" id="lvNewTask" type="button"><span class="ic ic-plus" aria-hidden="true"></span><span class="lv-jobs-new-tx">新建任务</span></button>
        <button class="lv-side-collapse" id="lvSideCollapse" type="button" title="收起任务列表" aria-label="收起任务列表">
          <span class="ic ic-panel-left" aria-hidden="true"></span>
        </button>
      </div>
      <div class="lv-jobs-h">最近任务</div>
      <div class="lv-side-bulk" id="lvSideBulk" hidden>
        <label><input type="checkbox" id="lvSelAllJobs"> 全选</label>
        <button class="lv-bdel cancel" id="lvDelJobs" type="button"><span class="lv-bdel-cancel">取消</span><span class="lv-bdel-del">删除（<span id="lvSelJobsCnt">0</span>）</span></button>
      </div>
      <div class="lv-side-list" id="lvJobsList"></div>
    </aside>
    <div class="lv-body">
    <section class="lv-pane" data-pane="1">
      
      <div class="lv-scroll1" id="lvScroll1">
        <div class="lv-drop" id="lvDrop"><span class="lv-drop-ic"><span class="ic ic-upload" aria-hidden="true"></span></span><span class="lv-drop-tx">点击或拖拽上传（图片 / 音频，数量不限）</span><span class="lv-drop-sub">上传后给每张图填入脚本中的角色 / 场景 / 道具名</span></div>
        <input type="file" id="lvFile" accept="image/*,audio/*" multiple hidden>
        <div class="lv-afilter" id="lvAFilter" hidden></div>
        <div class="lv-assets" id="lvAssets"></div>
      </div>
      
      <div class="lv-dock" id="lvDock">
        <div class="lv-bulkbar" id="lvBulk" hidden>
          <label><input type="checkbox" id="lvSelAll"> 全选</label>
          <button class="lv-bdel" id="lvBulkDel" disabled>移除选中（<span id="lvSelCnt">0</span>）</button>
        </div>
        <span class="lv-dock-gap"></span>
        <button class="lv-btn ghost" id="lvPickFromLib" type="button" title="从资产库选择已有素材加入当前任务"><span class="ic ic-library" aria-hidden="true"></span>从资产库选</button>
        <button class="lv-btn ghost" id="lvToUp" type="button" hidden title="上传素材（图片 / 音频）"><span class="ic ic-upload" aria-hidden="true"></span>上传</button>
        <button class="lv-btn primary" id="lvTo2">下一步</button>
      </div>
    </section>
    <section class="lv-pane lv-pane2" data-pane="2" hidden>
      
      <div class="lv-progsum" id="lvProgSum" hidden>
        <span class="ps-n" id="lvPsN">0/0</span>
        <span class="ps-k">已用</span><span class="ps-v" id="lvPsElapsed">—</span>
        <span class="ps-k">预计还需</span><span class="ps-v" id="lvPsEta">—</span>
        <span class="ps-k">状态</span><span class="ps-v amber" id="lvPsSt">—</span>
        
        <span class="ps-k" id="lvPsCostK" hidden>累计资费</span><span class="ps-v" id="lvPsCost" hidden>—</span>
        <div class="ps-bar"><i id="lvPsBar"></i></div>
        <div class="ps-acts">
          <button class="mini" id="lvRetry" type="button" hidden>补齐失败段</button>
          <button class="mini" id="lvResume" type="button" hidden>继续生成</button>
        </div>
        <span class="ps-hint" id="lvPsHint"></span>
      </div>
      
      <div class="lv-workbench">
        
        <div class="lv-col lv-col-script">
          <div class="lv-col-h">剧本</div>
          <textarea id="lvScript" class="lv-script" placeholder="在这里粘贴你的剧本，点「智能分镜」自动拆成分镜；没有剧本可以使用悬浮助手帮你更好创作，创作后的剧本会提交到此处。"></textarea>
          <div class="lv-opt-hint" id="lvOptHint"></div>
          <div class="lv-script-acts">
            <button class="lv-btn primary" id="lvOptimize"><span class="ic ic-spark" aria-hidden="true"></span>智能分镜</button>
          </div>
        </div>
        
        <div class="lv-col lv-col-shots">
          <div class="lv-shots" id="lvShots"></div>
          <div class="lv-opts" id="lvOpts">
            <div class="seg" id="lvSegModel">
              <button type="button" class="seg-cur"><span class="seg-tx"></span><span class="seg-ar ic ic-chevron-down"></span></button>
              <select id="lvOptModel" style="display:none">
                <option value="agnes-video-2.5-flash"></option>
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
                <div class="arsec-sec">
                  <div class="arsec-h">种子（可选）</div>
                  <div class="arsec-seed">
                    <input type="number" id="lvSeedInput" class="seed-input" min="0" step="1" placeholder="不了解用法可不填">
                    <button type="button" id="lvSeedRand" class="seed-rand">随机</button>
                  </div>
                </div>
                <div class="arsec-foot"><button type="button" class="arsec-done">完成</button></div>
              </div>
            </div>
            <div class="lv-actions" id="lvStep2Act" hidden>
              <button class="lv-btn primary" id="lvTo3">批量生成</button>
            </div>
          </div>
        </div>
        
        <div class="lv-col lv-col-prev">
          <div class="lv-col-h">成片预览</div>
          <div class="lv-video-wrap">
            <video id="lvVideo" controls></video>
            <div class="play-ic" id="lvPlayIc"><span class="ic ic-resume" aria-hidden="true"></span></div>
          </div>
          <div class="lv-prev-ctrls">
            <button class="lv-prev-jump" id="lvJump" type="button">从该段开始播放<span class="ic ic-jump" aria-hidden="true"></span></button>
            <button class="lv-btn ghost" id="lvPlayAll" type="button">播放全片</button>
          </div>
          <div class="lv-prev-line">
            <span class="pl-seg" id="lvPrevCap"></span>
            <span class="lv-prev-status" id="lvPrevStatus">状态：—</span>
            <span class="lv-prev-meta" id="lvPrevMeta"></span>
            <span class="pl-sec" id="lvPrevSec">本段时长：5s</span>
          </div>
        </div>
      </div>
    </section>
    </div>
  </div>
  
  <div class="lv-toast" id="lvToast" role="status" aria-live="polite" hidden></div>`;
  
  document.querySelector(".main-area").appendChild(overlay);

  
  let _modelMismatch = "";        
  let _modelMismatchShown = "";   
  function _warnModelMismatch(m) {
    if (_modelMismatchShown === m) return;
    _modelMismatchShown = m;
    
    const label = window.__lvVideoLabel || "当前服务商";
    setMsg(`该任务用的是 ${m}，不属于当前生效的视频服务商「${label}」；模型下拉只列本家模型，生成前请到「服务商设置」切换到对应服务商`, "warn");
  }

  
  document.addEventListener("provider:changed", (e) => {
    const prov = (e.detail) || {};
    
    
    
    
    
    if (prov.videoProvider && prov.videoProvider.winner) {
      window.__lvVideoProvider = prov.videoProvider.winner;
      
      if (prov.videoProvider.label) window.__lvVideoLabel = prov.videoProvider.label;
    }
    const vidSel = document.getElementById("lvOptModel");
    try {
      
      
      
      const pool = Array.isArray(prov.videoModels) ? prov.videoModels : [];
      if (vidSel && pool.length) {
        const keep = vidSel.value;
        const _lim = (prov.modelLimits && typeof prov.modelLimits === "object") ? prov.modelLimits : {};
        const _optTx = (m) => {
          const c = _lim[m] || {};
          return c.label ? `${c.label} · 自助` : m;
        };
        const _optEsc = (s) => String(s).replace(/[&<>"']/g,
          (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
        vidSel.innerHTML = pool.map(m => `<option value="${_optEsc(m)}">${_optEsc(_optTx(m))}</option>`).join("");
        vidSel.value = pool.includes(keep) ? keep : pool[0];
        
        
        window.__lvModelPoolReady = true;
      }
      _modelMismatchShown = "";   
      
      
      
      if (typeof _syncOptsToUI === "function") _syncOptsToUI();
      else _segRefresh("lvSegModel");
    } catch (err) {}
  });

  
  const $ = (id) => document.getElementById(id);
  const mediaSel = $("media");
  const msg = $("lvMsg");
  
  const toastEl = $("lvToast");
  
  
  
  function _polish(t) {
    let s = String(t == null ? "" : t).trim();
    s = s.replace(/[；;，,、\s]+$/, "");
    s = s.replace(/[（(]\s*未写入(?:历史)?\s*[)）]/g, "");
    s = s.replace(/[：:]\s*(?:undefined|null|\[object Object\]|NaN)\s*$/i, "，请稍后重试");
    s = s.replace(/[：:]\s*HTTP\s*\d{3}\S*\s*$/i, "，服务暂时没响应，请稍后重试");
    s = s.replace(/[：:]\s*[A-Za-z][A-Za-z0-9_.:/\- ]*(?:Error|Exception|failed|timeout)[A-Za-z0-9_.:/\- ]*$/i,
                  "，服务暂时没响应，请稍后重试");
    return s;
  }
  
  function _toast(t) {
    if (!toastEl) return;
    clearTimeout(toastEl._t1);
    clearTimeout(toastEl._t2);
    if (!t) { toastEl.classList.remove("on"); toastEl._t2 = setTimeout(() => { toastEl.hidden = true; }, 220); return; }
    toastEl.textContent = _polish(t);
    toastEl.hidden = false;
    toastEl.classList.remove("on");
    void toastEl.offsetWidth;          
    toastEl.classList.add("on");
    toastEl._t1 = setTimeout(() => {
      toastEl.classList.remove("on");
      toastEl._t2 = setTimeout(() => { if (!toastEl.classList.contains("on")) toastEl.hidden = true; }, 220);
    }, 1800);
  }
  
  function _pill(t, ico, kind) {
    msg.innerHTML = t ? ((ico ? '<span class="ic ic-' + ico + '" aria-hidden="true"></span>' : "") + _esc(_polish(t))) : "";
    msg.classList.toggle("warn", kind === "warn");
    msg.classList.toggle("error", kind === "error");
    clearTimeout(msg._timeout);
    if (!t) return;
    msg._timeout = setTimeout(() => {
      msg.textContent = "";
      msg.classList.remove("warn", "error");
    }, kind === "error" ? 10000 : 8000);
  }
  
  function _banner(t, kind) {
    if (typeof window.toast === "function") { window.toast(_polish(t), kind); return; }
    
    _pill(t, "", kind === "warn" ? "warn" : "error");
  }
  function setMsg(t, ico) {
    if (!t) { _pill(""); _toast(""); return; }
    
    if (ico === "lock" || ico === "warn") {
      _toast("");
      _banner(t, "warn");
    } else _toast(t);
  }
  function err(t) {
    _toast("");                        
    _banner(t, "err");
  }
  
  function errFold(summary, detail) {
    if (!detail) return err(summary);
    _toast("");
    _banner(summary, "err");
    if (typeof window.toast === "function") window.toast(String(detail), "err");
    else _pill(summary + "：" + String(detail), "", "error");   
  }

  
  const optHint = $("lvOptHint");
  function setOptHint(html) { if (optHint) optHint.innerHTML = html || ""; }
  function clearOptHint() { if (optHint) optHint.innerHTML = ""; }
  
  
  
  const _OPT_STAGE_TEXT = {
    prepare:    { hint: "正在准备…",         btn: "准备中…" },
    recognize:  { hint: "正在识别图片素材",   btn: "识别图中…" },
    storyboard: { hint: "AI 正在分镜…",      btn: "分镜中…" },
    done:       { hint: "正在整理分镜结果…", btn: "分镜中…" },
    error:      { hint: "分镜请求失败",       btn: "分镜中…" },
  };
  function _optPhaseHint(stage, sec, tail) {
    const s = _OPT_STAGE_TEXT[stage] || _OPT_STAGE_TEXT.prepare;
    
    
    
    setOptHint('<span class="lv-spin"></span>' + s.hint + `（已等待 ${sec} 秒）` +
               (tail === undefined ? "，请耐心等候" : tail));
    const b = $("lvOptimize");
    if (b && b.disabled) b.innerHTML = '<span class="lv-spin"></span>' + s.btn;
  }
  
  function _optWaitHint(sec, tail) { _optPhaseHint("storyboard", sec, tail); }
  function _stopOptPhasePoller() {
    if (_optTipTimer) { clearInterval(_optTipTimer); _optTipTimer = null; }
  }
  
  function _startOptPhasePoller(owner) {
    _stopOptPhasePoller();
    if (!owner) return;
    const tick = async () => {
      if (owner.done || _optActive !== owner || owner.view !== "owner") {
        _stopOptPhasePoller(); return;
      }
      const sec = Math.round((Date.now() - owner.t0) / 1000);
      let stage = owner.lastStage || "prepare";
      if (owner.reqId) {
        try {
          const r = await fetch(API + "/api/optimizer/progress?req_id=" + encodeURIComponent(owner.reqId));
          if (r.ok) {
            const d = await r.json();
            if (d && d.stage) {
              stage = d.stage;
              owner.lastStage = stage;
            }
          }
        } catch (_) {  }
      }
      if (owner.done || _optActive !== owner || owner.view !== "owner") return;
      _optPhaseHint(stage, sec);
    };
    _optTipTimer = setInterval(tick, 1500);
    tick();   
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
    shotsBudgetError: "",   
    jobId: null,
    segs: [],     
    selSeg: 1,
    
    
    
    segVer: {},
    step: 1,
    jobStatus: null,  
    
    state: null,
    _jobLabelSeen: null,   
    
    poll: null,
    opts: { model: "agnes-video-2.5-flash", aspect_ratio: "16:9", resolution: "720P" },  
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
      const d = window.fetchConfig ? await window.fetchConfig()
                                   : await (await fetch("/api/config")).json();
      
      window.__lvProvider = d.provider || {};
      
      window.__lvVideoProvider = (d.videoProvider && d.videoProvider.winner) || window.__lvVideoProvider || "agnes";
      
      if (d.videoProvider && d.videoProvider.label) window.__lvVideoLabel = d.videoProvider.label;
      document.dispatchEvent(new CustomEvent("provider:changed", {
        detail: Object.assign({}, d.provider || {}, { videoProvider: d.videoProvider || {} }),
      }));
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
      
      lv.jobStatus = null;
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
    
    loadJobs();
  }

  
  
  
  let _openSeq = 0;
  
  
  
  
  
  let _optGen = 0;
  let _optTipTimer = null;
  let _optActive = null;
  function _restoreOptimizeLoading() {
    const b = $("lvOptimize");
    
    if (b) { b.disabled = true; b.innerHTML = '<span class="lv-spin"></span>分镜中…'; }
    const owner = _optActive;
    
    if (owner) _startOptPhasePoller(owner);
  }
  function _cancelInFlightOptimize(nextJobId) {
    
    const back = _optActive && !_optActive.done && nextJobId &&
                 _optActive.jobId === nextJobId && _optActive.gen === _optGen;
    
    
    if (_optActive && !_optActive.done) _optActive.view = back ? "owner" : "away";
    if (back) { _restoreOptimizeLoading(); return; }
    _stopOptPhasePoller();
    
    
    
    const b = $("lvOptimize");
    if (b) { b.disabled = false; b.innerHTML = '<span class="ic ic-spark" aria-hidden="true"></span>智能分镜'; }
    
    
    clearOptHint();
  }
  async function openJob(jobId, preferredStep, fromRestore) {
    const seq = ++_openSeq;   
    _cancelInFlightOptimize(jobId);   
    stopPoll();   
    
    if (typeof _resetJobContext === "function") _resetJobContext();
    else if (typeof _resetPrevInfo === "function") _resetPrevInfo();
    setMsg("加载任务中…");
    try {
      
      await fetch(API + "/api/jobs/" + jobId + "/resume", { method: "POST" }).catch(() => {});
      if (seq !== _openSeq) return;   
      const r = await fetch(API + "/api/jobs/" + jobId);
      const j = await r.json();
      if (seq !== _openSeq) return;   
      if (!r.ok) {
        
        err("任务不存在，已重置");
        lv.jobId = null; lv.shots = []; lv.assets = [];
        if (typeof _resetJobContext === "function") _resetJobContext();
        else { lv.jobStatus = null; lv.segs = []; lv.state = null; }
        renderAssets();   
        clearState();
        _resetModelToProvider();
        _cancelInFlightOptimize();   
        goStep(1);
        return;
      }
      lv.jobId = jobId;
      
      _adoptJobState(j, { claim: true });
      lv._jobLabelSeen = (lv.state && lv.state.label) || null;
      
      const st = lv.jobStatus || "draft";
      
      if (j.gen_params) { lv.opts = Object.assign(lv.opts, j.gen_params); _syncOptsToUI(); }
      
      
      lv.assets = Array.isArray(j.assets) ? j.assets : [];
      lv.shotsBudgetError = j.shots_budget_error || "";
      
      
      
      lv.shots  = Array.isArray(j.shots) ? j.shots : [];
      lv.segs = [];   
                      
      if (lvScript) lvScript.value = j.script || "";
      await loadLibrary().catch(() => {});   
      renderAssets();
      renderShots();
      if (lv.shotsBudgetError) errFold("历史分镜超出模型上限，未阻止载入；该稿不能直接开始生成", lv.shotsBudgetError);
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
            setMsg("当前分镜为较早版本，画面细节可能不全，建议重新点「智能分镜」生成一版新的", "warn");
          } else {
            setMsg(fromRestore ? "已回到分镜步骤" : "已进入分镜步骤");
          }
        } else {
          
          
          setMsg(fromRestore ? `已恢复到${lv.shots.length ? "分镜步骤" : "素材上传"}` : `已打开${lv.shots.length ? "分镜步骤" : "素材上传"}`);
        }
      } else if (st === "completed") {
        lv.segs = j.segments || [];
        lv.finalUrl = j.final_url || (j.job && j.job.final_url) || null;
        const step = _pick(2);   
        goStep(step);
        renderShots();   
        
        
        if (lv.segs.some((s) => s.status === "processing")) {
          startPoll();
          setMsg("有分镜正在后台重新生成，完成后自动刷新视频…");
        } else {
          setMsg("成片已生成");
        }
      } else if (st === "failed") {
        lv.segs = j.segments || [];
        const step = _pick(2);   
        goStep(step);
        renderShots();
        
        if (lv.segs.some((s) => s.status === "processing")) startPoll();
        
        if (step === 2) err("该任务上次：" + ((lv.state && (lv.state.detail || lv.state.label)) || "失败"));
      } else if (st === "cancelled") {
        
        
        lv.segs = j.segments || [];
        const step = _pick(2);
        goStep(step);
        renderShots();
        
        
        const _flying = lv.segs.some((s) => s.status === "processing");
        if (_flying) startPoll();
        
        if (_flying) {
          setMsg("任务已停止；在飞的一段会跑完保留（不再发新提交），点「继续生成」可续跑剩余段", "warn");
        } else {
          setMsg("任务已停止；点「继续生成」可续跑剩余段");
        }
      } else {
        lv.segs = j.segments || [];
        const step = _pick(2);   
        
        
        
        startPoll();
        goStep(step);
        renderShots();
        setMsg("生成中，已接着上次进度继续");
      }
      
      _pinOptsToSnapshot();
      
      if (lv.segs.length) { try { _syncSegUI(lv.selSeg || 1); } catch (e) {} }
      _updateProgSum();
      _updateShotStatusLines();
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

  
  function _pinOptsToSnapshot() {
    if (!lv.jobId || !lv.jobStatus || lv.jobStatus === "draft") return;
    const s0 = (lv.segs || [])[0];
    if (!s0 || !lv.opts) return;
    
    const _sameModel = !s0.model || !lv.opts.model || String(s0.model) === String(lv.opts.model);
    if (!_sameModel) return;
    let changed = false;
    if (s0.aspect_ratio) { lv.opts.aspect_ratio = s0.aspect_ratio; changed = true; }
    if (s0.resolution)   { lv.opts.resolution   = s0.resolution;   changed = true; }
    if (changed && typeof _syncOptsToUI === "function") _syncOptsToUI();
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
    const _sentJobId = lv.jobId || null;   
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
      if (!r.ok) { err("分镜未写入：" + (j.error || ("HTTP " + r.status))); return lv.jobId; }
      
      if (j.job_id && (lv.jobId || null) === _sentJobId) {
        if (j.state) _adoptJobState(j, { claim: true });   
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
      if (r.ok && j.job_id) {
        lv.jobId = j.job_id;
        
        if (j.state) _adoptJobState(j, { claim: true });   
        saveState(); loadJobs();
      }
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
      el.dataset.status = (jb.state && jb.state.status) || "draft";   
      const created = jb.created_at ? new Date(jb.created_at * 1000).toLocaleString() : "";
      
      
      
      const st = jb.state || {};
      const stage = st.label || "—";
      const phCls = st.phase || (jb.status === "draft" ? "draft" : "");
      const total = (st.total != null) ? st.total : (jb.segment_count || 0);
      const done  = (st.done != null) ? st.done : (jb.done_count || 0);
      const detail = st.detail || "";
      const pct   = total ? Math.round(done / total * 100) : 0;
      const doneAll = total > 0 && done >= total;
      const shortDate = created ? created.replace(/^.*?\d{4}\/(\d+\/\d+).*?(\d+:\d+).*$/, "$1 $2") : "";
      el.innerHTML = `
        <input type="checkbox" class="lv-job-sel" data-id="${jb.job_id}">
        <span class="lv-job-avatar" title="${_esc(jb.name||"未命名任务")}" data-st="${_esc(jb.status||"draft")}">${_esc((jb.name||"未命名任务").trim().charAt(0) || "任")}</span>
        <div class="lv-job-row1">
          <span class="lv-job-title${_esc(jb.name||"") ? "" : " placeholder"}" data-id="${jb.job_id}" data-ph="未命名任务">${_esc(jb.name||"") || "未命名任务"}</span>
          ${isCur ? `<span class="lv-job-cur">编辑中</span>` : ""}
          ${st.status === "processing" || st.status === "pending" ? `<button class="lv-job-stop" type="button" data-id="${jb.job_id}" title="停止生成（保留已完成段）">停止</button>` : ""}
          <button class="sess-dots lv-job-dots" type="button" title="更多操作" aria-label="更多">⋮</button>
        </div>
        <div class="sess-menu">
          <div class="sess-menu-item" data-act="batch"><span class="ic ic-check"></span>批量管理</div>
          <div class="sess-menu-item" data-act="rename"><span class="ic ic-pencil"></span>重命名</div>
          <div class="sess-menu-item" data-act="delete"><span class="ic ic-del"></span>删除</div>
        </div>
        <div class="lv-job-row2">
          <span class="lv-job-stage ph-${_esc(phCls)}">${_esc(stage)}</span>
          <span class="lv-job-cnt">${total > 0 ? `${done}/${total} 段` : "待分镜"}</span>
          <span class="lv-job-meta">${_esc(shortDate)}</span>
        </div>
        ${detail ? `<div class="lv-job-err" title="${_esc(st.error || detail)}"><span class="ic ic-warn" aria-hidden="true"></span>${_esc(detail)}</div>` : ""}
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
          
          if (!(await lvConfirm({ title: "停止生成", message: `将停止「${jb.name || "此任务"}」的生成：后续段不再发射，已完成段保留。\n正在生成的这一段无法撤回（上游不支持），会跑完。`, okText: "停止", danger: true }))) return;
          try {
            const r = await fetch(API + `/api/jobs/${jb.job_id}/cancel`, { method: "POST" });
            if (!r.ok) { const j2 = await r.json().catch(() => ({})); err("停止失败：" + (j2.error || "")); return; }
            const jc = await r.json().catch(() => ({}));
            
            if (Array.isArray(lv.segs) && lv.jobId === jb.job_id) {
              lv.segs = lv.segs.map((s) => s.status === "processing" || s.status === "pending" ? { ...s, status: "cancelled" } : s);
              renderShots();
              _updateProgSum();
            }
            
            const _rc = jc && jc.remote_cancelled ? Number(jc.remote_cancelled) : 0;
            const _rf = (jc && Array.isArray(jc.remote_failed)) ? jc.remote_failed : [];
            const _ru = jc && jc.remote_unsupported ? Number(jc.remote_unsupported) : 0;
            const _inf = jc && jc.inflight ? Number(jc.inflight) : 0;
            
            if (_rc > 0) {
              setMsg(_inf ? `已停止：远端 ${_rc} 个任务已取消（本地 ${_inf} 段在收尾）` : `已停止：远端 ${_rc} 个任务已取消`);
            } else if (_rf.length) {
              err("已停止本地任务，但远端取消未成功：" + (_rf[0].error || "未知原因")
                  + (_inf ? `（仍有 ${_inf} 段在远端跑，可能继续扣费）` : ""));
            } else if (_ru > 0 || _inf > 0) {
              setMsg(`已停止：该上游无取消接口，仍有 ${_inf || _ru} 段会跑完（可能继续计费）`, "warn");
            } else {
              setMsg("已停止生成");
            }
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
        lv.jobId = null; lv.shots = []; lv.assets = [];
        
        if (typeof _resetJobContext === "function") _resetJobContext();
        else if (typeof _resetPrevInfo === "function") _resetPrevInfo();
        renderAssets();   
        renderShots();    
        if ($("lvScript")) $("lvScript").value = "";   
        clearState();
        _resetModelToProvider();
        _cancelInFlightOptimize();   
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
      const partial = (j.total || 0) > (j.ok || 0);
      
      if (lv.jobId && ids.includes(lv.jobId)) {
        lv.jobId = null; lv.shots = []; lv.assets = [];
        
        if (typeof _resetJobContext === "function") _resetJobContext();
        else if (typeof _resetPrevInfo === "function") _resetPrevInfo();
        renderAssets();   
        renderShots();    
        if ($("lvScript")) $("lvScript").value = "";   
        clearState();
        _resetModelToProvider();
        _cancelInFlightOptimize();   
        _syncStartBtn();   
        goStep(1);
      }
      
      setMsg(`已删除 ${j.ok || 0}/${j.total || ids.length} 个任务` + (partial ? "，部分失败" : ""),
             partial ? "warn" : "");
      
      if (!partial) setJobManage(false);
      loadJobs();
    } catch (e) { err("批量删除异常：" + e.message); }
  }

  async function continueJob(jobId) {
    setMsg("继续任务中…");
    try { await openJob(jobId, null, false); }
    catch (e) { err("继续任务异常：" + e.message); }
    setMsg("");
  }

  
  function _resetModelToProvider() {
    const pool = (window.__lvProvider && Array.isArray(window.__lvProvider.videoModels))
      ? window.__lvProvider.videoModels : [];
    if (!pool.length) return;
    lv.opts.model = pool[0];
    if (typeof _syncOptsToUI === "function") _syncOptsToUI();
  }
  async function newTask() {
    _cancelInFlightOptimize();
    
    const isGenerated = lv.jobId && lv.jobStatus && lv.jobStatus !== "draft";
    if (isGenerated && !(await lvConfirm({ title: "新建任务", message: "当前任务已生成/进行中，确定新建一个任务？当前任务会保留在「最近任务」中，可随时回来继续。" }))) return;
    
    
    clearTimeout(_draftTimer); _draftTimer = null;
    
    await saveDraftNow();   
    lv.assets = []; lv.shots = []; lv.jobId = null; lv.selSeg = 1; lv.step = 1;
    
    if (typeof _resetJobContext === "function") _resetJobContext();
    else if (typeof _resetPrevInfo === "function") _resetPrevInfo();
    if (lvScript) lvScript.value = "";   
    clearState();
    _resetModelToProvider();
    renderAssets();
    
    renderShots();
    const _ps = $("lvProgSum"); if (_ps) _ps.hidden = true;   
    lvStep2Act.hidden = true;
    _syncStartBtn();   
    goStep(1);
    loadJobs();
    setMsg("已新建任务（原草稿已保留在「最近任务」），从第 1 步开始");
  }

  
  async function withBtn(btn, loadingText, fn, isStale, onDone) {
    if (!btn || btn.disabled) return;
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="lv-spin"></span>${loadingText}`;
    try { await fn(); }
    catch (e) { err(e && e.message ? e.message : String(e)); }
    finally {
      
      if (onDone) { try { onDone(); } catch (_) {} }
      
      
      if (!(isStale && isStale())) {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    }
  }
