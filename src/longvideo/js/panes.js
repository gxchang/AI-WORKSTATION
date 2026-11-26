  
  function lvStoryboardModel() {
    return (typeof lvOptModel !== "undefined" && lvOptModel.value) ||
           (lv.opts && lv.opts.model) || "";
  }
  
  let LV_SEC = { min: 4, max: 12 };
  (async () => {
    try {
      const d = window.fetchConfig ? await window.fetchConfig()
                                   : await (await fetch("/api/config")).json();
      if (Array.isArray(d.lvSecBounds)) { LV_SEC.min = d.lvSecBounds[0]; LV_SEC.max = d.lvSecBounds[1]; }
    } catch (_e) {}
  })();
  function lvSecBounds() {
    const m = lvStoryboardModel();
    const lim = (typeof MODEL_LIMITS !== "undefined" && MODEL_LIMITS[m]) || {};
    return { min: lim.min_seconds || LV_SEC.min, max: lim.max_seconds || LV_SEC.max };
  }

  
  function showLV() {
    if (window.Views) Views.show("longvideo"); else overlay.hidden = false;
    resumeFromState();
  }
  
  
  function hideLV() {
    if (window.Views) Views.show("session"); else overlay.hidden = true;
    stopPoll();
    if (typeof closeAllSeg === "function") closeAllSeg();
    
  }

  
  let _preLVMedia = "video";
  mediaSel.addEventListener("change", () => {
    if (mediaSel.value === "longvideo") { showLV(); }
    else { _preLVMedia = mediaSel.value; hideLV(); }
  });

  
  
  overlay.querySelector("#lvBack")?.addEventListener("click", () => {
    mediaSel.value = _preLVMedia || "video";
    const tx = document.querySelector("#mediaSel .seg-tx");
    if (tx) tx.textContent = { video: "视频生成", image: "图片生成" }[mediaSel.value] || "视频生成";
    mediaSel.dispatchEvent(new Event("change"));
  });
  
  
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || e.defaultPrevented) return;
    if (window.Views && Views.cur === "longvideo") { e.preventDefault(); hideLV(); }
  });

  
  
  
  function _normStep(n) { return (n === 3 || n === 4) ? 2 : n; }
  function canGoStep(n) { return _normStep(n) <= 2; }
  function goStep(n) {
    n = _normStep(n);   
    overlay.querySelectorAll(".lv-steps button").forEach((b) =>
      b.classList.toggle("on", +b.getAttribute("data-step") === n)
    );
    overlay.querySelectorAll(".lv-pane").forEach((p) =>
      (p.hidden = +p.getAttribute("data-pane") !== n)
    );
    overlay.querySelector(".lv-body").scrollTop = 0;
    lv.step = n;
    _syncStepLocks();
    
    
    if (n === 2) {
      _updateProgSum();   
      if (lv.segs.length) _updateShotStatusLines();
      buildStrip();
    }
    _syncStartBtn();
    saveState();
    loadJobs();
  }
  
  
  
  function _syncStepLocks() {
    overlay.querySelectorAll(".lv-steps button").forEach((b) => {
      const n = +b.getAttribute("data-step");
      b.classList.toggle("locked", n !== lv.step && !canGoStep(n));
      b.classList.toggle("done", n !== lv.step && n < lv.step);
    });
  }
  overlay.querySelectorAll(".lv-steps button").forEach((b) =>
    b.addEventListener("click", () => {
      const n = +b.getAttribute("data-step");
      if (!canGoStep(n)) {
        err("请先完成「素材上传」与「智能分镜」");
        return;
      }
      goStep(n);
    })
  );

  
  const lvFile = $("lvFile");
  const lvDrop = $("lvDrop");
  const lvAssets = $("lvAssets");

  lvDrop.addEventListener("click", () => lvFile.click());
  
  ["dragenter", "dragover"].forEach((ev) => lvDrop.addEventListener(ev, (e) => { e.preventDefault(); lvDrop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => lvDrop.addEventListener(ev, () => lvDrop.classList.remove("drag")));
  lvDrop.addEventListener("dragover", (e) => { e.preventDefault(); });
  lvDrop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });
  
  const lvUpBtn = $("lvToUp");
  const lvScroll1 = $("lvScroll1");
  if (lvUpBtn) {
    lvUpBtn.addEventListener("click", () => lvFile.click());
    if ("IntersectionObserver" in window && lvScroll1) {
      new IntersectionObserver(
        (es) => { lvUpBtn.hidden = es[0].isIntersecting; },
        { root: lvScroll1, threshold: 0 }
      ).observe(lvDrop);
    } else {
      lvUpBtn.hidden = false;   
    }
  }
  lvFile.addEventListener("change", () => {
    if (lvFile.files.length) uploadFiles(lvFile.files);
    lvFile.value = "";
  });

  async function uploadFiles(fileList) {
    const fd = new FormData();
    for (const f of fileList) fd.append("files", f);
    setMsg("上传中…");
    try {
      
      if (!lv.jobId) await ensureJob();
      const r = await fetch(API + "/api/assets/batch_upload", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) { err(j.error || "上传失败"); return; }
      
      const prev = {};
      lv.assets.forEach((a) => (prev[a.name] = a));
      j.uploaded.forEach((u) => {
        const ex = prev[u.name];
        lv.assets.push(ex ? { ...u, label: ex.label, kind: ex.kind, owner: ex.owner, posture: ex.posture, job_id: null } : { ...u, posture: "", job_id: null, kind: u.type === "audio" ? "voice" : "" });
      });
      renderAssets();
      setMsg(`已上传 ${j.uploaded.length} 个素材`);
      
      
      
      
      await saveDraftNow().then(loadJobs);
    } catch (e) { err("上传异常：" + e.message); }
  }

  
  let currentLibraryItems = [];
  
  
  
  
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  
  
  
  
  function summarizeStillReferenced(map) {
    const lines = [];
    Object.keys(map || {}).forEach((name) => {
      const refs = (map[name] || []).filter(Boolean);
      if (!refs.length) return;
      const by = refs.map((r) => (r.label ? `${r.source}「${r.label}」` : r.source)).join("、");
      lines.push(`「${name}」已从资产库移除，文件仍被 ${by} 使用，暂留（那些引用也删掉后自动清理）`);
    });
    return lines.join("\n");
  }
  
  function _characterLabels() {
    const seen = new Set(), out = [];
    (lv.assets || []).forEach((a) => {
      if (a.kind === "character" && a.label && !seen.has(a.label)) { seen.add(a.label); out.push(a.label); }
    });
    return out;
  }
  
  function _audioAssets() {
    const out = [], seen = new Set();
    (lv.assets || []).forEach((a) => {
      if (a.type === "audio" && !seen.has(a.name)) { seen.add(a.name); out.push(a); }
    });
    return out;
  }
  function _findAudio(name) {
    return (lv.assets || []).find((a) => a.name === name) || null;
  }
  
  function _refreshGrids() {
    renderAssets();
  }

  
  function _assetCardInner(a) {
    const isAudio = a.type === "audio";
    const isChar = !isAudio && a.kind === "character";
    
    const typeField = isAudio
      ? `<span class="lv-i-type fixed" title="音频素材（声线）">声线 / 音频</span>`
      : _segField(a, "kind", '<option value="">类型</option>'
          + '<option value="character">角色</option><option value="scene">场景</option>'
          + '<option value="prop">道具</option>');
    
    const ownerLabels = _characterLabels();
    if (a.owner && ownerLabels.indexOf(a.owner) < 0) ownerLabels.push(a.owner);   
    const ownerOpts = ownerLabels.map((c) => `<option value="${esc(c)}" ${a.owner === c ? "selected" : ""}>${esc(c)}</option>`).join("");
    const ownerField = isAudio ? _segField(a, "owner", `<option value="">归属角色…</option>${ownerOpts}`) : "";
    
    const voiceOpts = _audioAssets().map((au) => `<option value="${esc(au.name)}" ${au.owner === a.label ? "selected" : ""}>${esc(au.label || au.name)}</option>`).join("");
    const voiceField = isChar ? _segField(a, "voice", `<option value="">声线（音频）…</option>${voiceOpts}`) : "";
    
    const postureField = isChar ? _segField(a, "posture", '<option value="">姿态</option>'
        + '<option value="拟人直立">拟人直立</option><option value="四足">四足</option>') : "";
    
    let labelTitle;
    if (isAudio) {
      labelTitle = "声线绑定靠素材卡里的『归属角色』下拉（选到对应角色，如橘猫）——系统自动把这条声线配给该角色，原始脚本无需标注声线。本标签名仅作显示，不影响绑定";
    } else if (a.kind === "character") {
      labelTitle = "角色名须与脚本里写的称呼完全一致（如脚本写『橘猫』就填『橘猫』），否则图加文无法把这图绑进分镜";
    } else if (a.kind === "scene") {
      labelTitle = "场景名须与脚本里写的场景完全一致（如脚本写『客厅』就填『客厅』），否则图加文无法把这图绑进分镜";
    } else if (a.kind === "prop") {
      labelTitle = "道具名须与脚本里写的道具完全一致（如脚本写『毛线球』就填『毛线球』），否则图加文无法把这图绑进分镜";
    } else {
      labelTitle = "标签名须与脚本中写的对应称呼一致（先在上方选类型：角色 / 场景 / 道具），否则图加文无法绑定";
    }
    return { isAudio, isChar, typeField, ownerField, voiceField, postureField, labelTitle };
  }

  
  function _appearanceDisplay(ap) {
    if (!ap) return "";
    const s = (ap || "").trim();
    if (s.startsWith("{")) {
      try {
        const o = JSON.parse(s);
        if (o.raw) return o.raw;
        return JSON.stringify(o.concrete || {});
      } catch (e) {}
    }
    return ap;
  }
  function _appearanceBlockHtml(a) {
    if (a.type !== "image") return "";
    const ap = _appearanceDisplay(a.appearance);
    const body = ap
      ? `<textarea class="lv-i-ap" rows="4" placeholder="AI 已识别，可在此修正视觉描述">${esc(ap)}</textarea>`
      : `<div class="lv-ap-empty">（尚未识别：运行「智能分镜」后会自动生成 AI 视觉描述；也可手动填写后保存）</div>`;
    return `<div class="lv-ap-wrap"><div class="lv-ap-h">AI 识别外观</div>${body}</div>`;
  }

  
  
  function _wireAppearance(card, a) {
    const apEl = card.querySelector(".lv-i-ap");
    if (!apEl) return;
    apEl.addEventListener("blur", () => {
      const val = apEl.value;
      a.appearance = val;
      fetch(API + "/api/assets/register", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify([{ name: a.name, appearance: val }]),
      }).catch(() => {});
      saveDraft();
      setMsg(val.trim() ? "已保存 AI 提取的形象描述" : "已清空 AI 提取的形象描述");
    });
  }

  
  let _audEl = null;
  function _toggleAudition(btn) {
    const url = btn.getAttribute("data-url");
    if (!_audEl) {
      _audEl = new Audio(); _audEl.preload = "none";
      
      if (window.MediaStop) {
        window.MediaStop.register(function (reason) {
          if (!_audEl) return;
          try { _audEl.pause(); } catch (e) { }
          const _r = () => document.querySelectorAll(".lv-play").forEach((b) => (b.innerHTML = '<span class="ic ic-resume" aria-hidden="true"></span>试听'));
          _r();   
        });
      }
    }
    const _reset = () => document.querySelectorAll(".lv-play").forEach((b) => (b.innerHTML = '<span class="ic ic-resume" aria-hidden="true"></span>试听'));
    if (_audEl.getAttribute("data-cur") === url && !_audEl.paused) { _audEl.pause(); _reset(); return; }
    _reset();
    _audEl.setAttribute("data-cur", url);
    _audEl.src = url;
    _audEl.currentTime = 0;
    _audEl.onended = _reset;
    _audEl.onerror = () => { _reset(); alert("这条声线无法播放（文件缺失或格式不支持）"); };
    _audEl.play().then(() => (btn.innerHTML = '<span class="ic ic-pause" aria-hidden="true"></span>暂停'))
      .catch(() => { _reset(); alert("播放被浏览器拦截，请再点一次"); });
  }

  
  let _filterTask = "";
  
  
  let _selNames = new Set();
  const _FILTER_DEFS = [
    { key: "", label: "全部" },
    { key: "character", label: "角色" },
    { key: "scene", label: "场景" },
    { key: "prop", label: "道具" },
    { key: "audio", label: "音频" },
    { key: "none", label: "未分类" },
  ];
  function _assetMatch(a, f) {
    if (!f) return true;
    if (f === "audio") return a.type === "audio";
    if (f === "none") return a.type !== "audio" && !a.kind;
    return a.type !== "audio" && a.kind === f;
  }
  function _filterCounts(list) {
    const c = { character: 0, scene: 0, prop: 0, audio: 0, none: 0 };
    list.forEach((a) => {
      if (a.type === "audio") c.audio++;
      else if (!a.kind) c.none++;
      else if (c[a.kind] !== undefined) c[a.kind]++;
      else c.none++;
    });
    return c;
  }
    
    
    function _renderFilterRow(box, list, cur, onPick) {
      if (!box) return;
      if (!list.length) { box.hidden = true; box.innerHTML = ""; return; }
      const cnt = _filterCounts(list);
      box.innerHTML = _FILTER_DEFS
      .filter((d) => d.key === "" || cnt[d.key] > 0)
      .map((d) => `<button type="button" data-k="${d.key}" class="${cur === d.key ? "on" : ""}">${d.label} ${d.key === "" ? list.length : cnt[d.key]}</button>`)
      .join("");
    box.hidden = false;
    box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => onPick(b.getAttribute("data-k"))));
  }

  
  
  function _segHash(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36);
  }
  function _segId(a, field) {
    return "lvK_" + _segHash(String(a.name || "")) + "_" + field;
  }
  function _segField(a, field, optsHtml) {
    if (!window.UISeg) return '<select class="lv-i-' + field + '">' + optsHtml + '</select>';
    
    const tmp = document.createElement("select");
    tmp.innerHTML = optsHtml;
    const cur = tmp.options[tmp.selectedIndex];
    
    return window.UISeg.html(_segId(a, field), cur ? cur.textContent : "", optsHtml,
                             "lv-i-" + field, "lv-segpop");
  }
  
  function _segSync(a, field) {
    if (!window.UISeg) return;
    const wrap = document.getElementById(_segId(a, field));
    const inner = wrap ? wrap.querySelector("select") : null;
    const opt = inner ? inner.options[inner.selectedIndex] : null;
    window.UISeg.sync(_segId(a, field), opt ? opt.textContent : "");
  }
  
  function _segInitCard(card, a) {
    if (!window.UISeg) return;
    ["kind", "owner", "voice", "posture"].forEach((f) => {
      if (!card.querySelector(".lv-i-" + f)) return;   
      window.UISeg.init(_segId(a, f));                 
      _segSync(a, f);                                  
    });
  }

  
  
  function _isH3() { return window.__lvVideoProvider === "runninghub"; }
  
  document.addEventListener("provider:changed", () => {
    _syncH3JobVis();
    if (_isH3()) _syncH3JobValues();
    
    if (Array.isArray(lv.shots) && lv.shots.length) { try { renderShots(); } catch (e) {} }
    
    if (Array.isArray(lv.segs) && lv.segs.length) {
      try { _syncSegUI(lv.selSeg || 1); } catch (e) {}
    }
  });
  
  
  const _RH_POP = "lv-arres-panel";
  
  function _rhTriggerHtml(id, label) {
    return '<div class="seg" id="' + id + '">'
      + '<button type="button" class="seg-cur"><span class="seg-tx">' + label + '</span>'
      + '<span class="seg-ar ic ic-chevron-down"></span></button></div>';
  }

  
  function _h3JobState() {
    return {
      tier: lv.opts.quality_tier || "hq",
      instance: lv.opts.instance_tier || "plus",
      accel: lv.opts.accel === "1",
      
      
      selflift: lv.opts.selflift || {},
    };
  }
  function _h3JobApply(patch) {
    if (patch.instance != null) lv.opts.instance_tier = patch.instance;
    if (patch.tier != null) {
      lv.opts.quality_tier = patch.tier;
      lv.opts.accel = (patch.tier === "fast") ? "1" : "";
    } else if (patch.accel != null) {
      lv.opts.accel = patch.accel ? "1" : "";
    }
    
    if (patch.selflift != null) lv.opts.selflift = patch.selflift;
    saveDraft();
  }

  
  let _paintTier = null, _paintInst = null;
  function _initH3JobParams() {
    const bar = $("lvOpts");
    if (!bar || !window.RhControls || $("lvRhTierSel")) return;
    const act = $("lvStep2Act");
    const put = (id, label) => {
      const box = document.createElement("div");
      box.innerHTML = _rhTriggerHtml(id, label);
      const el = box.firstElementChild;
      bar.insertBefore(el, act || null);
      return el;
    };
    const elTier = put("lvRhTierSel", "质量档");
    const elInst = put("lvRhInstSel", "运行设备");
    
    
    if (elInst) elInst.classList.add("lv-seg-inst");
    window.RhControls.setCap(lv.opts.model);
    
    _paintTier = window.RhControls.mountTier(elTier, _h3JobState, _h3JobApply,
                                             { panelId: "lvRhTierPanel", popClass: _RH_POP });
    _paintInst = window.RhControls.mountInstance(elInst, _h3JobState, _h3JobApply,
                                                 { popClass: _RH_POP });
    _syncH3JobVis();
    if (_isH3()) _syncH3JobValues();
  }
  function _syncH3JobVis() {
    ["lvRhTierSel", "lvRhInstSel"].forEach((id) => {
      const el = $(id);
      if (el) el.style.display = _isH3() ? "" : "none";
    });
    
  }
  function _syncH3JobValues() {
    if (!_isH3()) return;
    if (window.RhControls) window.RhControls.setCap(lv.opts.model);   
    if (_paintTier) _paintTier();
    if (_paintInst) _paintInst();
  }

  
  function _h3SegParamsHtml(s, idx) {
    if (s.is_continuation) return { html: "" };
    
    let h = _rhTriggerHtml("lvRhRefineSel_" + idx, "二次采样");
    h += _rhTriggerHtml("lvRhFaceSel_" + idx, "脸部修复");
    return { html: h };
  }
  const _paintRefine = {}, _paintFace = {};
  
  
  function _wireH3SegParams(div, s, idx) {
    if (s.is_continuation || !window.RhControls) return;
    const RC = window.RhControls;
    s.post_refine = s.post_refine || {};
    s.post_face = s.post_face || {};
    const get = () => ({ refine: s.post_refine || {}, face: s.post_face || {} });
    const set = (patch) => {
      if (patch.refine) s.post_refine = patch.refine;
      if (patch.face) s.post_face = patch.face;
      saveDraft();
    };
    
    _paintRefine[idx] = RC.mountRefine(div.querySelector("#lvRhRefineSel_" + idx), get, set,
                                       { panelId: "lvRhRefinePanel_" + idx, popClass: _RH_POP });
    _paintFace[idx] = RC.mountFace(div.querySelector("#lvRhFaceSel_" + idx), get, set,
                                   { panelId: "lvRhFacePanel_" + idx, popClass: _RH_POP });
    if (_paintRefine[idx]) _paintRefine[idx]();
    if (_paintFace[idx]) _paintFace[idx]();
  }

  function renderAssets() {
    
    if (window.UISeg) window.UISeg.purge("lvK_");
    lvAssets.innerHTML = "";
    
    const _live = new Set(lv.assets.map((a) => a.name));
    [..._selNames].forEach((n) => { if (!_live.has(n)) _selNames.delete(n); });
    const _list = lv.assets.filter((a) => _assetMatch(a, _filterTask));
    if (!_list.length && lv.assets.length) {
      lvAssets.innerHTML = '<div class="lv-jobs-empty">该筛选下暂无素材，试试其他类型</div>';
    }
    _list.forEach((a) => {
      const card = document.createElement("div");
      card.className = "lv-ac" + (_selNames.has(a.name) ? " sel" : "");
      
      const th = a.type === "image"
        ? `<div class="lv-th"><img src="${_esc(_thumb(a.url))}" alt="" loading="lazy" decoding="async"></div>`
        : `<div class="lv-th"><canvas class="lv-th-wave" data-wave-url="${a.url}"></canvas><button type="button" class="lv-play" data-url="${a.url}" title="试听这条声线"><span class="ic ic-resume" aria-hidden="true"></span>试听</button></div>`;
      const f = _assetCardInner(a);
      card.innerHTML = `
        <input type="checkbox" class="lv-i-sel" data-name="${a.name}"${_selNames.has(a.name) ? " checked" : ""}>
        ${th}
        <input class="lv-i-label" placeholder="${f.isAudio ? "标签＝声线名（如 橘猫声线）" : (a.kind === "scene" ? "标签＝场景名（如 客厅）" : a.kind === "prop" ? "标签＝道具名（如 毛线球）" : "标签＝角色名（如 橘猫）")}" value="${esc(a.label)}">
        ${f.typeField}
        ${f.ownerField}
        ${f.voiceField}
        ${f.postureField}
        ${_appearanceBlockHtml(a)}
        <button class="lv-del" type="button" data-name="${a.name}" title="从本任务移除；文件保留在资产库，可随时重新引用">移除</button>`;
      card.querySelector(".lv-i-label").addEventListener("input", (e) => { a.label = e.target.value; saveDraft(); });
      
      const _tw = card.querySelector(".lv-th-wave");
      if (_tw && window.Wave) window.Wave.mountStatic(_tw, a.url, {
        unplayedColor: "rgba(99,91,255,.20)",
        playedColor: "rgba(99,91,255,.30)",
      });
      const kindEl = card.querySelector(".lv-i-kind");
      if (kindEl) kindEl.addEventListener("change", (e) => { a.kind = e.target.value; saveDraft(); renderAssets(); });
      const postEl = card.querySelector(".lv-i-posture");
      if (postEl) postEl.addEventListener("change", (e) => { a.posture = e.target.value; saveDraft(); });
      const ownerEl = card.querySelector(".lv-i-owner");
      if (ownerEl) ownerEl.addEventListener("change", (e) => { a.owner = e.target.value; saveDraft(); _refreshGrids(); });
      const voiceEl = card.querySelector(".lv-i-voice");
      if (voiceEl) voiceEl.addEventListener("change", (e) => {
        const au = _findAudio(e.target.value);
        if (au) { au.owner = a.label; saveDraft(); }
        _refreshGrids();
      });
      if (kindEl) kindEl.value = a.kind || "";
      if (postEl) postEl.value = a.posture || "";
      const playBtn = card.querySelector(".lv-play");
      if (playBtn) playBtn.addEventListener("click", () => _toggleAudition(playBtn));
      card.querySelector(".lv-del").addEventListener("click", () => deleteAsset(a.name));
      card.querySelector(".lv-i-sel").addEventListener("change", (e) => {
        const n = e.target.getAttribute("data-name");
        if (e.target.checked) _selNames.add(n); else _selNames.delete(n);
        card.classList.toggle("sel", e.target.checked);
        syncSel();
      });
      _wireAppearance(card, a);
      lvAssets.appendChild(card);
      
      _segInitCard(card, a);
    });
    $("lvBulk").hidden = lv.assets.length === 0;
    _renderFilterRow($("lvAFilter"), lv.assets, _filterTask, (k) => { _filterTask = k; renderAssets(); });
    syncSel();
    saveDraft();   
  }

  function syncSel() {
    const all = [...lvAssets.querySelectorAll(".lv-i-sel")];
    const checked = all.filter((c) => c.checked);                    
    const picked = lv.assets.filter((a) => _selNames.has(a.name));   
    $("lvSelCnt").textContent = picked.length;
    $("lvBulkDel").disabled = picked.length === 0;
    $("lvSelAll").checked = all.length > 0 && checked.length === all.length;
    $("lvSelAll").indeterminate = checked.length > 0 && checked.length < all.length;
  }

  async function deleteSelected() {
    
    const names = lv.assets.filter((a) => _selNames.has(a.name)).map((a) => a.name);
    if (!names.length) return;
    
    const msg = `确定将选中的 ${names.length} 个素材从本任务移除？文件仍保留在资产库，可随时重新引用。`;
    if (!(await lvConfirm({ title: "从本任务移除", message: msg, okText: "移除" }))) return;
    lv.assets = lv.assets.filter((a) => !names.includes(a.name));
    renderAssets();   
    setMsg(`已从本任务移除 ${names.length} 个素材（文件保留在资产库）`);
  }

  $("lvBulkDel").addEventListener("click", deleteSelected);
  $("lvSelAll").addEventListener("change", (e) => {
    
    lvAssets.querySelectorAll(".lv-i-sel").forEach((c) => {
      c.checked = e.target.checked;
      const n = c.getAttribute("data-name");
      if (e.target.checked) _selNames.add(n); else _selNames.delete(n);
      c.closest(".lv-ac").classList.toggle("sel", e.target.checked);
    });
    syncSel();
  });

  
  let _lvMarquee = null;
  const _lvScroll = $("lvScroll1");
  function _lvMarqueeDown(e) {
    if (e.button !== 0) return;
    const initial = new Map();
    lvAssets.querySelectorAll(".lv-ac").forEach((card) => {
      const ck = card.querySelector(".lv-i-sel");
      if (ck) initial.set(ck, ck.checked);
    });
    _lvMarquee = { sx: e.clientX, sy: e.clientY, lx: e.clientX, ly: e.clientY, box: null, started: false, initial };
  }
  function _lvMarqueeMove(e) {
    const m = _lvMarquee;
    if (!m) return;
    m.lx = e.clientX; m.ly = e.clientY;
    if (!m.started) {
      if (Math.abs(m.lx - m.sx) < 6 && Math.abs(m.ly - m.sy) < 6) return;  
      m.started = true;
      e.preventDefault();
      const sel = window.getSelection(); if (sel) sel.removeAllRanges();
      m.box = document.createElement("div");
      m.box.className = "lv-marquee";
      document.body.appendChild(m.box);
      _lvScroll.classList.add("lv-marquee-ing");
    }
    const x1 = Math.min(m.sx, m.lx), y1 = Math.min(m.sy, m.ly);
    const x2 = Math.max(m.sx, m.lx), y2 = Math.max(m.sy, m.ly);
    m.box.style.left = x1 + "px"; m.box.style.top = y1 + "px";
    m.box.style.width = (x2 - x1) + "px"; m.box.style.height = (y2 - y1) + "px";
    
    let changed = false;
    lvAssets.querySelectorAll(".lv-ac").forEach((card) => {
      const r = card.getBoundingClientRect();
      const hit = r.right > x1 && r.left < x2 && r.bottom > y1 && r.top < y2;
      const ck = card.querySelector(".lv-i-sel");
      if (!ck) return;
      const was = !!m.initial.get(ck);
      const want = hit ? !was : was;
      card.classList.toggle("sel", want);
      if (ck.checked !== want) {
        ck.checked = want;
        const n = ck.getAttribute("data-name");
        if (want) _selNames.add(n); else _selNames.delete(n);
        changed = true;
      }
    });
    if (changed) syncSel();
  }
  function _lvMarqueeUp() {
    const m = _lvMarquee;
    if (!m) return;
    if (m.started) {
      if (m.box && m.box.parentNode) m.box.parentNode.removeChild(m.box);
      _lvScroll.classList.remove("lv-marquee-ing");
    }
    _lvMarquee = null;
  }
  _lvScroll.addEventListener("mousedown", _lvMarqueeDown);
  document.addEventListener("mousemove", _lvMarqueeMove);
  document.addEventListener("mouseup", _lvMarqueeUp);

  async function deleteAsset(name) {
    const a = lv.assets.find((x) => x.name === name);
    
    if (!(await lvConfirm({ title: "从本任务移除", message: "将「" + name + "」从本任务素材中移除；文件仍保留在资产库，可随时重新引用。", okText: "移除" }))) return;
    lv.assets = lv.assets.filter((x) => x.name !== name);
    renderAssets();   
    setMsg("已从本任务移除 " + name + "（文件保留在资产库）");
  }

  

  
  async function loadLibrary() {
    try {
      const r = await fetch(API + "/api/assets/registry");
      const j = await r.json();
      currentLibraryItems = j.items || [];
      setMsg("");
      
      if (lv && lv.assets) renderAssets();
    } catch (e) { err("加载资产库素材失败：" + e.message); }
  }









  
  window.uploadToSharedLibrary = async function (fileList) {
    const fd = new FormData();
    for (const f of fileList) fd.append("files", f);
    setMsg("上传到资产库中…");
    try {
      const r = await fetch(API + "/api/assets/batch_upload", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) { err(j.error || "上传失败"); return; }
      loadLibrary();
      setMsg("已上传到资产库");
    } catch (e) { err("上传异常：" + e.message); }
  };

  
  function addItemsToTask(items) {
    const run = () => {
      let added = 0;
      items.forEach((i) => {
        if (!i || lv.assets.find((x) => x.name === i.name)) return;
        lv.assets.push({ name: i.name, url: i.url, type: i.type, label: i.label || "", kind: i.kind || "", owner: i.owner || "", posture: i.posture || "", job_id: null });
        added++;
      });
      renderAssets();
      if (added) saveDraftNow().then(loadJobs);
      return added;
    };
    const done = (n) => setMsg(n ? `已把 ${n} 个资产库素材加入当前任务` : "所选素材已在本任务中");
    if (!lv.jobId) {
      ensureJob().then(() => done(run()));
      return;
    }
    done(run());
  }



  
  const _lvPickFromLib = $("lvPickFromLib");
  if (_lvPickFromLib) _lvPickFromLib.addEventListener("click", () => {
    if (typeof AssetPicker === "undefined") { err("资产库选择器未加载"); return; }
    AssetPicker.open({ source: "library", multi: true, title: "从资产库选择素材", onPick: (items) => addItemsToTask(items) });
  });
  loadLibrary();   

  $("lvTo2").addEventListener("click", () => goStep(2));
  
  $("lvNewTask").addEventListener("click", newTask);

  
  (function initSideCollapse() {
    const side = $("lvSide");
    const collapseBtn = $("lvSideCollapse");
    const expandBtn = $("lvSideExpand");
    if (!side) return;
    function setCollapsed(on) {
      side.classList.toggle("collapsed", !!on);
      try { localStorage.setItem("lvSideCollapsed", on ? "1" : "0"); } catch (_) {}
      const t = on ? "展开任务列表" : "收起任务列表";
      if (collapseBtn) { collapseBtn.title = t; collapseBtn.setAttribute("aria-label", t); }
      if (expandBtn) { expandBtn.title = t; expandBtn.setAttribute("aria-label", t); }
    }
    try { if (localStorage.getItem("lvSideCollapsed") === "1") side.classList.add("collapsed"); } catch (_) {}
    if (collapseBtn) collapseBtn.addEventListener("click", (e) => { e.stopPropagation(); setCollapsed(true); });
    if (expandBtn) expandBtn.addEventListener("click", (e) => { e.stopPropagation(); setCollapsed(false); });
  })();
  
  $("lvDelJobs").addEventListener("click", () => {
    if ($("lvDelJobs").classList.contains("cancel")) setJobManage(false);
    else deleteJobs();
  });
  $("lvSelAllJobs").addEventListener("change", (e) => {
    document.querySelectorAll("#lvJobsList .lv-job-sel").forEach((c) => (c.checked = e.target.checked));
    syncJobSel();
  });

  
  let _jobManage = false;
  function setJobManage(on) {
    _jobManage = on;
    $("lvSide").classList.toggle("managing", on);
    $("lvSideBulk").hidden = !on;
    if (!on) {
      document.querySelectorAll("#lvJobsList .lv-job-sel").forEach((c) => { c.checked = false; });
    }
    syncJobSel();   
  }

  
  const lvScript = $("lvScript");
  const lvShots = $("lvShots");
  const lvStep2Act = $("lvStep2Act");
  const lvOptModel = $("lvOptModel");
  const lvOptAspect = $("lvOptAspect");
  const lvOptRes = $("lvOptRes");

  
  function _segTx(segId) {
    const w = document.getElementById(segId); if (!w) return;
    const sel = w.querySelector("select"), tx = w.querySelector(".seg-tx");
    if (sel && tx) { const o = sel.options[sel.selectedIndex]; tx.textContent = o ? o.textContent : ""; }
  }
  
  
  const SEG_TITLES = { lvSegModel: "视频模型" };
  
  function _segRefresh(segId) {
    const w = document.getElementById(segId); if (!w) return;
    _segTx(segId);
    if (typeof initSeg === "function") {
      initSeg(segId);
      if (w._pop) {
        w._pop.classList.add("lv-seg-pop");             
        
        const title = SEG_TITLES[segId];
        if (title) {
          const h = document.createElement("div");
          h.className = "arsec-h lv-pop-h";
          h.textContent = title;
          w._pop.insertBefore(h, w._pop.firstChild);
        }
      }
    }
  }

  
  const ARRES = { wrap: null, panel: null, grid: null, sizes: null };
  
  function _syncArResTx() {
    const tx = document.getElementById("lvArResTx");
    if (tx) tx.textContent = `${lvOptAspect.value} · ${(lvOptRes.value || "").toUpperCase()}`;
  }
  
  function _renderArResAspects() {
    if (!ARRES.grid || typeof arIcon !== "function") return;   
    const grid = ARRES.grid;
    grid.innerHTML = "";
    [...lvOptAspect.options].forEach((o) => {
      const it = document.createElement("div");
      it.className = "ar-it" + (o.value === lvOptAspect.value ? " on" : "");
      it.dataset.val = o.value;
      it.innerHTML = `<span class="ar-ic">${arIcon(o.value)}</span><span class="ar-lb">${esc(o.value)}</span>`;
      it.addEventListener("click", (e) => {
        e.stopPropagation();
        lvOptAspect.value = o.value;
        grid.querySelectorAll(".ar-it").forEach((x) => x.classList.toggle("on", x.dataset.val === o.value));
        _syncArResTx();
        lvOptAspect.dispatchEvent(new Event("change"));
      });
      grid.appendChild(it);
    });
  }
  
  function _renderArResSizes() {
    if (!ARRES.sizes) return;
    const box = ARRES.sizes;
    const list = [...lvOptRes.options].map((o) => o.value);
    if (!list.length) return;
    const want = list.includes(lvOptRes.value) ? lvOptRes.value : list[0];
    lvOptRes.value = want;
    box.innerHTML = "";
    list.forEach((s) => {
      const el = document.createElement("div");
      el.className = "sz" + (s === want ? " on" : "");
      el.dataset.val = s;
      el.textContent = s;
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        lvOptRes.value = s;
        box.querySelectorAll(".sz").forEach((x) => x.classList.toggle("on", x.dataset.val === s));
        _syncArResTx();
        lvOptRes.dispatchEvent(new Event("change"));
      });
      box.appendChild(el);
    });
    _syncArResTx();
  }
  
  function _openArResPanel(cur) {
    const panel = ARRES.panel;
    panel.classList.add("show");
    const r = cur.getBoundingClientRect();
    const pw = panel.offsetWidth, ph = panel.offsetHeight;
    let left = r.left;
    let top = r.top - ph - 7;
    if (top < 8) top = r.bottom + 7;
    const maxLeft = window.innerWidth - pw - 8;
    if (left > maxLeft) left = Math.max(8, maxLeft);
    panel.style.left = left + "px";
    panel.style.top = top + "px";
  }
  function _initArRes() {
    const wrap = document.getElementById("lvSegArRes");
    if (!wrap || typeof closeAllSeg !== "function") return;   
    const cur = wrap.querySelector(".seg-cur");
    const panel = wrap.querySelector(".seg-pop");
    if (!cur || !panel) return;
    
    document.body.appendChild(panel);
    panel.classList.add("lv-arres-panel");
    ARRES.wrap = wrap; ARRES.panel = panel;
    ARRES.grid = panel.querySelector(".seg-ar-grid");
    ARRES.sizes = panel.querySelector(".arsec-sizes");
    wrap._pop = panel;
    if (!segList.includes(wrap)) segList.push(wrap);
    cur.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = wrap.classList.contains("open");
      closeAllSeg();                                  
      if (!isOpen) { _openArResPanel(cur); wrap.classList.add("open"); }
    });
    panel.querySelector(".arsec-done").addEventListener("click", (e) => { e.stopPropagation(); closeAllSeg(); });
    
    const seedInp = panel.querySelector("#lvSeedInput");
    const seedRnd = panel.querySelector("#lvSeedRand");
    if (seedInp) {
      seedInp.addEventListener("input", () => {
        const v = String(seedInp.value || "").trim();
        lv.opts.seed = v === "" ? null : Math.max(0, parseInt(v, 10) || 0);
        saveDraft();
      });
      seedInp.addEventListener("click", (e) => e.stopPropagation());
    }
    if (seedRnd) {
      seedRnd.addEventListener("click", (e) => {
        e.stopPropagation();
        const n = Math.floor(Math.random() * 1e9);
        lv.opts.seed = n;
        if (seedInp) seedInp.value = String(n);
        saveDraft();
      });
    }
    _renderArResAspects();
    _renderArResSizes();
    _syncArResSeed();
  }
  
  function _syncArResSeed() {
    const p = ARRES && ARRES.panel;
    const inp = p && p.querySelector("#lvSeedInput");
    if (!inp) return;
    const v = (lv.opts && lv.opts.seed);
    inp.value = (v === null || v === undefined || v === "") ? "" : String(v);
  }
  
  function _initOptsSegs() {
    _segRefresh("lvSegModel");
    _initArRes();
    _initH3JobParams();                              
  }

  
  
  
  const RES_ALL = ["720P", "1080P", "1K", "2K"];
  function _syncResOptions(model) {
    
    const lim = (typeof MODEL_LIMITS !== "undefined" && MODEL_LIMITS[model]) || null;
    let list, note;
    if (lim && Array.isArray(lim.sizes) && lim.sizes.length) {
      list = lim.sizes.slice();
      note = "可选档位：" + list.join(" / ");
    } else {
      const isFlash = (model || "").includes("flash");
      list = isFlash ? ["720P"] : RES_ALL;
      note = isFlash ? "Flash 模型固定 720P" : "720P / 1080P / 1K / 2K";
    }
    lvOptRes.innerHTML = list.map(r => `<option value="${r}">${r}</option>`).join("");
    lvOptRes.disabled = list.length <= 1;
    lvOptRes.title = note;
    if (list.length <= 1) lv.opts.resolution = list[0];
    
    if (![...lvOptRes.options].some(o => o.value === (lv.opts.resolution || list[0]))) {
      lv.opts.resolution = list[0];
    }
    lvOptRes.value = lv.opts.resolution || list[0];
    _renderArResSizes();                           
  }
  function _syncOptsToUI() {
    
    const pool = [...lvOptModel.options].map(o => o.value);
    const stored = (lv.opts && lv.opts.model) || "";
    if (!window.__lvModelPoolReady) {
      
      
      
      if (stored && pool.includes(stored)) lvOptModel.value = stored;
      else if (pool.length) lvOptModel.value = pool[0];
      _modelMismatch = "";
    } else if (pool.length && stored && !pool.includes(stored)) {
      const synced = pool.includes(lvOptModel.value) ? lvOptModel.value : pool[0];
      _modelMismatch = stored;                 
      lv.opts.model = synced;
      lvOptModel.value = synced;
      _warnModelSync(stored);
    } else {
      _modelMismatch = "";
      if (!stored && pool.length) { lv.opts.model = pool[0]; lvOptModel.value = pool[0]; }
      else if (stored && pool.includes(stored)) lvOptModel.value = stored;
    }
    lvOptAspect.value = lv.opts.aspect_ratio || "16:9";
    _syncResOptions(lv.opts.model);   
    _segRefresh("lvSegModel");
    _renderArResAspects();            
    _syncArResTx();
    _syncArResSeed();                 
    _syncH3JobVis();                  
    _syncH3JobValues();               
  }
  function _readOptsFromUI(modelChanged) {
    const _prev = lv.opts || {};
    lv.opts = {
      
      
      model: lvOptModel.value,
      aspect_ratio: lvOptAspect.value,
      resolution: lvOptRes.value,
      
      instance_tier: _prev.instance_tier,
      accel: _prev.accel,
      quality_tier: _prev.quality_tier,
      
      seed: _prev.seed,
      selflift: _prev.selflift,
    };
  }
  _syncOptsToUI();
  
  
  async function _checkModelSwitch() {
    if (!lv.shots.length) return;
    const newMax = lvSecBounds().max;
    const newMin = lvSecBounds().min;
    if (!newMax) return;
    const basis = lv.storyboardBasis;
    
    
    
    const over = lv.shots.filter((s) => (s.estimated_seconds || 5) > newMax);
    const under = lv.shots.filter((s) => (s.estimated_seconds || 5) < newMin);
    let msg;
    if (over.length || under.length) {
      over.forEach((s) => { s.estimated_seconds = newMax; });
      under.forEach((s) => { s.estimated_seconds = newMin; });
      msg = `已切换到 ${lv.opts.model}（单段 ${newMin}~${newMax} 秒）：` +
        (over.length ? `${over.length} 段时长已自动回退到 ${newMax} 秒` : `${under.length} 段时长已抬到 ${newMin} 秒`) +
        `。重新点「智能分镜」可按新模型能力更合理地适配拆段`;
    } else if (basis && basis.secMax && newMax > basis.secMax) {
      msg = `已切换到 ${lv.opts.model}（单段 ≤${newMax} 秒）：当前分镜按 ${basis.secMax} 秒拆了 ${lv.shots.length} 段，直接生成可跑；重新点「智能分镜」可减少段数/续接点`;
    } else {
      msg = `已切换到 ${lv.opts.model}（单段 ${newMin}~${newMax} 秒）`;
    }
    renderShots();          
    saveDraft();
    setMsg(msg);
  }
  [lvOptModel, lvOptAspect, lvOptRes].forEach((el) => {
    el.addEventListener("change", async () => {
      const isModel = el === lvOptModel;
      _readOptsFromUI(isModel);
      if (isModel) {
        _modelMismatch = "";             
        _modelMismatchShown = "";
        _syncResOptions(lv.opts.model);  
        await _checkModelSwitch();       
      }
      saveState(); saveDraft();
    });
  });
  
  
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _initOptsSegs);
  else _initOptsSegs();

  
  async function _persistDetachedShots(jobId, shots, script) {
    if (!jobId) { err("分镜已完成，但发起时没有任务归属，结果未保存"); return; }
    if (!shots.length) { setMsg("分镜未产出镜头，原任务未改动", "warn"); return; }
    try {
      
      const _body = { shots };
      if (script) _body.script = script;
      const r = await fetch(API + `/api/jobs/${encodeURIComponent(jobId)}/shots`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(_body),
      });
      const rj = await r.json().catch(() => ({}));
      if (!r.ok) { err(`原任务分镜保存失败：${rj.error || ""}（结果未写入）`); return; }
      
      
      if (lv.jobId === jobId) {
        try {
          const g = await fetch(API + `/api/jobs/${encodeURIComponent(jobId)}`);
          const gj = await g.json().catch(() => ({}));
          if (g.ok && lv.jobId === jobId) {
            lv.shots = Array.isArray(gj.shots) ? gj.shots : shots;
            if (gj.shots_budget_error) errFold("历史分镜超出模型上限，未阻止载入；该稿不能直接开始生成", gj.shots_budget_error);
            renderShots();
            lvStep2Act.hidden = lv.shots.length === 0;
            _syncStartBtn();
          }
        } catch (_) {}
        setMsg(`分镜已保存并刷新到当前任务（${shots.length} 个镜头）`, "warn");
      } else {
        setMsg(`分镜已保存到原任务（${shots.length} 个镜头），切回并重新打开该任务即可查看`, "warn");
      }
      loadJobs();
    } catch (e) {
      err("原任务分镜保存异常：" + (e && e.message ? e.message : String(e)));
    }
  }

  $("lvOptimize").addEventListener("click", () => {
    
    
    const _ownerScript = lvScript.value.trim();
    const _ownerJobIdAtClick = lv.jobId;
    const _ownerStatus = lv.jobStatus;
    
    const _ownerVideoModel = lvStoryboardModel();
    const myGen = ++_optGen;
    const _t0 = Date.now();
    
    
    const _reqId = "opt_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
    
    
    let ownerJobId = _ownerJobIdAtClick || null;
    _optActive = { jobId: ownerJobId, gen: myGen, t0: _t0, done: false, view: "owner",
                   reqId: _reqId, lastStage: "prepare" };
    const _isStale = () => myGen !== _optGen || !_optActive ||
                     _optActive.gen !== myGen || _optActive.view !== "owner";
    withBtn($("lvOptimize"), "准备中…", async () => {
      const script = _ownerScript;
      if (!script) { err("请先填写脚本"); return; }
      
      if (!ownerJobId) {
        if (_isStale()) return;
        ownerJobId = await ensureJob();
        if (_optActive && _optActive.gen === myGen) _optActive.jobId = ownerJobId;
        if (_isStale()) return;   
      }
      
      
      
      
      
      
      
      if (ownerJobId && _ownerStatus && _ownerStatus !== "draft") {
        err("分镜已定稿：该任务已开始生成，不能再整份重拆。要改某一镜，直接在分镜卡上改稿后点「重新生成」。");
        return;
      }
      
      
      
      
      
      setOptHint('<span class="lv-spin"></span>正在准备…');
      
      
      _startOptPhasePoller(_optActive);
      let r, j;
      try {
        r = await fetch(API + "/api/optimizer", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Opt-Req-Id": _reqId },
          
          
          body: JSON.stringify({ script, job_id: ownerJobId || null, video_model: _ownerVideoModel }),
        });
        j = await r.json();
      } catch (e) {
        _stopOptPhasePoller();
        if (_isStale()) return;
        err("分镜请求异常：网络挂了或服务端崩溃 — " + e.message);
        return;
      }
      _stopOptPhasePoller();
      if (!r.ok) {
        if (_isStale()) { err("原任务分镜失败，未改动任何任务：" + (j.error || "")); return; }
        err("分镜失败：" + (j.error || "") + (j.detail ? ("\n" + j.detail) : ""));
        return;
      }
      
      
      if (_isStale()) {
        await _persistDetachedShots(ownerJobId, j.shots || [], _ownerScript);
        return;
      }
      lv.shots = j.shots || [];
      if (j.job_id) lv.jobId = j.job_id;   
      
      lv.storyboardBasis = { model: j.video_model || (lv.opts && lv.opts.model) || "", secMax: (j.sec_bounds && j.sec_bounds[1]) || null };
      renderShots();
      lvStep2Act.hidden = lv.shots.length === 0;
      _syncStartBtn();   
      
      
      const _usedModel = j.llm_model || "当前生效 LLM";
      const _elapsed = Math.round((Date.now() - _t0) / 1000);
      const _basis = lv.storyboardBasis;
      const _basisTx = _basis.secMax ? `，按 ${_basis.model} 拆（单段不超过 ${_basis.secMax} 秒）` : "";
      
      const _variantTx = j.prompt_variant === "workbench" ? "分镜表版" : "通用版";
      console.info("[长视频] 分镜回声", { 引擎: _usedModel, 规约: _variantTx, 用时秒: _elapsed });
      
      setMsg(`已生成 ${lv.shots.length} 个镜头${_basisTx}。点「开始生成」就能出片`, "warn");
      
      
      _stopOptPhasePoller();
      clearOptHint();
      
      if (lv.shots.length) lvShots.scrollIntoView({ behavior: "smooth", block: "start" });
      saveState();
      if (_isStale()) return;   
      
      if (lv.shots.length) lvShowOptTip();
      saveDraftNow().then(loadJobs);   
    }, _isStale, () => {
      
      
      
      if (_optActive && _optActive.gen === myGen) { _optActive.done = true; clearOptHint(); }
      _stopOptPhasePoller();
    });
  });

  
  const _OPT_TIP_KEY = "wb_lv_opt_tip_v1";
  function _optTipSeen() {
    try { return localStorage.getItem(_OPT_TIP_KEY) === "1"; } catch (e) { return false; }
  }
  function _optTipMark() {
    try { localStorage.setItem(_OPT_TIP_KEY, "1"); } catch (e) {}
  }
  function lvHideOptTip() { const t = $("lvOptTip"); if (t) t.hidden = true; }
  function lvShowOptTip() {
    if (_optTipSeen()) return;
    const btn = $("lvOptimize"), host = $("lvOpts");
    if (!btn || !host) return;
    let tip = $("lvOptTip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "lv-opt-tip";
      tip.id = "lvOptTip";
      tip.hidden = true;
      tip.innerHTML =
        '<div class="lv-opt-tip-tx">对分镜结果不满意吗？可再次进行智能分镜哦~</div>' +
        '<div class="lv-opt-tip-ft"><button type="button" class="lv-opt-tip-ok">知道啦</button></div>';
      host.appendChild(tip);
      tip.querySelector(".lv-opt-tip-ok").addEventListener("click", (e) => {
        e.stopPropagation();
        _optTipMark();
        lvHideOptTip();
      });
    }
    tip.hidden = false;
    
    requestAnimationFrame(() => {
      if (tip.hidden) return;
      const hr = host.getBoundingClientRect();
      const br = btn.getBoundingClientRect();
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      const bx = (br.left - hr.left) + br.width / 2;             
      let left = bx - tw / 2;
      left = Math.max(0, Math.min(left, host.clientWidth - tw)); 
      tip.style.left = Math.round(left) + "px";
      tip.style.top = Math.round((br.top - hr.top) - th - 10) + "px";  
      
      tip.style.setProperty("--tip-ar-x", Math.round(bx - Math.round(left)) + "px");
    });
    
    setTimeout(() => document.addEventListener("mousedown", _optTipOutside, { once: true }), 0);
  }
  function _optTipOutside(e) {
    const t = $("lvOptTip");
    if (!t || t.hidden || t.contains(e.target)) return;
    _optTipMark();
    lvHideOptTip();
  }


  
  
  if (lvScript) lvScript.addEventListener("input", () => saveDraft());

  
  let _mentionPop = null, _mentionCtx = null, _mentionCtxHost = null, _mentionActiveIdx = 0;
  const _MENTION_MAX = 50;

  function _ensureMentionPop() {
    if (_mentionPop) return _mentionPop;
    _mentionPop = document.createElement("div");
    _mentionPop.className = "lv-mention-pop";
    _mentionPop.hidden = true;
    _mentionPop.addEventListener("mousedown", (e) => e.preventDefault());
    _mentionPop.addEventListener("click", (e) => {
      const mi = e.target.closest(".mi");
      if (!mi || !_mentionCtx) return;
      const it = _mentionCtx.items[parseInt(mi.dataset.i, 10)];
      if (it) _mentionInsert(_mentionCtx, it);
    });
    document.addEventListener("click", (e) => {
      if (_mentionPop && !_mentionPop.hidden && !_mentionPop.contains(e.target) && !(e.target.closest && e.target.closest(".lv-prompt-edit")))
        _hideMention();
    });
    document.body.appendChild(_mentionPop);
    return _mentionPop;
  }
  function _hideMention() {
    if (_mentionPop) _mentionPop.hidden = true;
    _mentionCtx = null;
  }
  
  
  
  function _assetLabel(name) {
    if (!name) return name;
    const a = (lv.assets || []).find((x) => x.name === name || x.label === name);
    return a ? (a.label || a.name) : name;
  }
  function _registryImgs() {
    return (lv.assets || []).filter((a) => a.type === "image").map((a) => ({ kind: "image", name: a.name, url: a.url, label: a.label || a.name }));
  }
  function _registryAuds() {
    return (lv.assets || []).filter((a) => a.type === "audio").map((a) => ({ kind: "audio", name: a.name, url: a.url, label: a.label || a.name }));
  }
  function _matsForShot(s) {
    const imgs = (s.images || []).map((name, i) => ({ kind: "image", idx: i + 1, name, url: _assetUrl(name, (s.images_urls || [])[i]), label: _assetLabel(name) }));
    const auds = (s.audio || []).map((who, i) => ({ kind: "audio", idx: i + 1, name: who, url: _assetUrl(who, (s.audio_urls || [])[i]), label: _assetLabel(who) }));
    return { imgs, auds };
  }
  function _matsForSeg(seg) {
    if (!seg) return { imgs: [], auds: [] };
    const keys = _parseArr(seg.images_keys).length ? _parseArr(seg.images_keys) : _parseArr(seg.images);
    const urls = _parseArr(seg.images_urls);
    const imgs = [];
    let seq = 0;
    keys.forEach((k, i) => { seq++; imgs.push({ kind: "image", idx: seq, name: k, url: _assetUrl(k, urls[i]), label: _assetLabel(k) }); });
    const auds = _parseArr(seg.audio).map((who, i) => ({ kind: "audio", idx: i + 1, name: who, url: _assetUrl(who, _parseArr(seg.audio_urls)[i]), label: _assetLabel(who) }));
    return { imgs, auds };
  }
  function _segCurrent() { return lv.segs.find((x) => x.seg_no === lv.selSeg); }

  
  
  function _matSame(a, b) {
    const norm = (v) => (v == null ? "" : String(v).trim().toLowerCase());
    const ka = [norm(a.name), norm(a.label)], kb = [norm(b.name), norm(b.label)];
    if (norm(a.url) && norm(a.url) === norm(b.url)) return true;
    return ka.some((x) => x && kb.indexOf(x) >= 0);
  }
  function _chipHtml(kind, idx, label, url) {
    const tag = (kind === "audio" ? "音频" : "图") + idx + (label ? " " + label : "");
    if (kind === "image") {
      if (label === "tail") {
        return '<span class="lv-mat tail" contenteditable="false" data-kind="image" data-idx="' + idx + '">'
          + '<span class="lv-mat-tail">尾</span>'
          + '<span class="lv-mat-tag">' + _esc("图" + idx + " 尾帧") + "</span></span>";
      }
      return '<span class="lv-mat' + (url ? "" : " miss") + '" contenteditable="false" data-kind="image" data-idx="' + idx + '">'
        + '<img class="lv-mat-img" src="' + _esc(_thumb(_encUrl(url), 128)) + '" alt="" onerror="this.classList.add(\'lv-mat-img-failed\');this.title=\'素材加载失败: \'+(this.src||\'(no url)\')">'
        + '<span class="lv-mat-tag">' + _esc(tag) + "</span></span>";
    }
    return '<span class="lv-mat audio" contenteditable="false" data-kind="audio" data-idx="' + idx + '">'
      + '<span class="lv-mat-ico ic ic-audio" aria-hidden="true"></span><span class="lv-mat-tag">' + _esc(tag) + "</span></span>";
  }
  function _promptToHtml(text, mats) {
    const re = /(图|音频)(\d{1,2})(?!\d)/g;
    let out = "", last = 0, m;
    const listOf = (kind) => (kind === "audio" ? mats.auds : mats.imgs);
    while ((m = re.exec(text))) {
      out += _esc(text.slice(last, m.index));
      const kind = m[1] === "音频" ? "audio" : "image";
      const idx = parseInt(m[2], 10);
      const info = listOf(kind).find((x) => x.idx === idx);
      out += _chipHtml(kind, idx, info ? info.label : "", info ? info.url : "");
      last = re.lastIndex;
    }
    out += _esc(text.slice(last));
    return out;
  }
  const _BLOCK_TAGS = { DIV: 1, P: 1, LI: 1, BLOCKQUOTE: 1, PRE: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, TR: 1 };
  
  function _promptToText(editor) {
    let out = "";
    (function walk(node) {
      node.childNodes.forEach((c) => {
        if (c.nodeType === Node.TEXT_NODE) { out += c.textContent; return; }
        if (c.nodeType !== Node.ELEMENT_NODE) return;
        if (c.nodeName === "BR") { out += "\n"; return; }
        if (c.classList && c.classList.contains("lv-mat")) {              
          out += (c.dataset.kind === "audio" ? "音频" : "图") + c.dataset.idx; return;
        }
        if (c.classList && c.classList.contains("lv-ph")) return;          
        const block = _BLOCK_TAGS[c.nodeName] === 1;
        if (block && out && !out.endsWith("\n")) out += "\n";
        walk(c);
        if (block && !out.endsWith("\n")) out += "\n";
      });
    })(editor);
    
    return out.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").replace(/^\n+|\n+$/g, "");
  }
  function _makeChipEl(kind, idx, label, url) {
    const span = document.createElement("span");
    span.className = "lv-mat" + (kind === "audio" ? " audio" : "") + (url ? "" : " miss");
    span.contentEditable = "false";
    span.dataset.kind = kind;
    span.dataset.idx = String(idx);
    if (kind === "image") {
      const img = document.createElement("img");
      img.className = "lv-mat-img"; img.src = _thumb(_encUrl(url || ""), 128); img.alt = "";
      img.onerror = () => { img.classList.add("lv-mat-img-failed"); img.title = "素材加载失败: " + (img.src || "(no url)"); };
      span.appendChild(img);
    } else {
      const ico = document.createElement("span");
      ico.className = "lv-mat-ico ic ic-audio";
      span.appendChild(ico);
    }
    const tag = document.createElement("span");
    tag.className = "lv-mat-tag";
    tag.textContent = (kind === "audio" ? "音频" : "图") + idx + (label ? " " + label : "");
    span.appendChild(tag);
    const x = document.createElement("span");
    x.className = "lv-mat-x"; x.innerHTML = '<span class="ic ic-cancel" aria-hidden="true"></span>'; x.title = "移除此素材引用";
    x.addEventListener("click", (e) => { e.stopPropagation(); span.remove(); if (span._onChange) span._onChange(); });
    span.appendChild(x);
    return span;
  }
  function _insertAtCaret(node) {
    const sel = window.getSelection();
    if (!sel.rangeCount) return false;
    const range = sel.getRangeAt(0);
    range.deleteContents();
    range.insertNode(node);
    const zw = document.createTextNode("\u200b");
    node.after(zw);
    const r = document.createRange();
    r.setStartAfter(zw); r.collapse(true);
    sel.removeAllRanges(); sel.addRange(r);
    return true;
  }
  
  function _sweepAssetTags(editor, host) {
    if (editor.textContent.indexOf("<") < 0) return;
    const mats = host.getMats() || { imgs: [], auds: [] };
    const TAG = /<(Picture|Audio|Video)\s+(\d+)>/gi;
    const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null);
    const texts = []; let n;
    while ((n = walker.nextNode())) { TAG.lastIndex = 0; if (TAG.test(n.nodeValue)) texts.push(n); }
    if (!texts.length) return;
    const sel = window.getSelection();
    if (!sel) return;
    texts.forEach(function (node) {
      let m, hits = []; TAG.lastIndex = 0;
      while ((m = TAG.exec(node.nodeValue))) hits.push({ i: m.index, len: m[0].length, kind: m[1].toLowerCase(), N: +m[2] });
      for (let k = hits.length - 1; k >= 0; k--) {   
        const h = hits[k];
        if (h.kind === "video") continue;            
        const list = h.kind === "audio" ? mats.auds : mats.imgs;
        const info = (list || []).find((x) => x.idx === h.N);
        if (!info || !info.url) continue;
        const r = document.createRange();
        r.setStart(node, h.i); r.setEnd(node, h.i + h.len);
        sel.removeAllRanges(); sel.addRange(r);      
        const chip = _makeChipEl(info.kind, info.idx, info.label, info.url);
        chip._onChange = () => { if (host.onCommit) host.onCommit(_promptToText(editor)); };
        _insertAtCaret(chip);
      }
    });
    if (host.onCommit) host.onCommit(_promptToText(editor));
  }
  
  function _lvCopyText(s) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(s);
    return new Promise(function (res, rej) {
      try {
        const ta = document.createElement("textarea");
        ta.value = s;
        ta.style.cssText = "position:fixed;top:-9999px;left:-9999px;opacity:0";
        document.body.appendChild(ta); ta.select();
        const ok = document.execCommand("copy");
        ta.remove();
        if (ok) res(); else rej(new Error("copy failed"));
      } catch (e) { rej(e); }
    });
  }
  
  function _copyShotPrompt(editor) {
    const CN = { image: "Picture", audio: "Audio" };
    let out = "";
    (function walk(node) {
      node.childNodes.forEach(function (c) {
        if (c.nodeType === Node.TEXT_NODE) { out += c.textContent; return; }
        if (c.nodeType !== Node.ELEMENT_NODE) return;
        if (c.nodeName === "BR") { out += "\n"; return; }
        if (c.classList && c.classList.contains("lv-mat")) {
          const k = c.dataset.kind === "audio" ? "audio" : "image";
          out += "<" + CN[k] + " " + c.dataset.idx + ">";
          return;
        }
        if (c.classList && c.classList.contains("lv-ph")) return;
        walk(c);
      });
    })(editor);
    out = out.replace(/图\s*(\d+)/g, function (m0, n1) { return "<Picture " + n1 + ">"; })
             .replace(/音频\s*(\d+)/g, function (m0, n1) { return "<Audio " + n1 + ">"; });
    return out.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  function _caretRect() {
    const sel = window.getSelection();
    if (!sel.rangeCount) return null;
    let rect = sel.getRangeAt(0).getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      const r2 = document.createRange();
      try { r2.selectNodeContents(sel.anchorNode); r2.collapse(false); rect = r2.getBoundingClientRect(); } catch (e) {}
    }
    return rect;
  }
  function _detectMention(editor) {
    const sel = window.getSelection();
    if (!sel.rangeCount) { _hideMention(); return; }
    const range = sel.getRangeAt(0);
    if (!editor.contains(range.startContainer)) { _hideMention(); return; }
    const pre = document.createRange();
    pre.selectNodeContents(editor);
    pre.setEnd(range.startContainer, range.startOffset);
    const before = pre.toString();
    const at = before.lastIndexOf("@");
    if (at === -1) { _hideMention(); return; }
    const left = at > 0 ? before[at - 1] : "";
    if (left && /[A-Za-z0-9]/.test(left)) { _hideMention(); return; }
    const query = before.slice(at + 1);
    if (/\s/.test(query)) { _hideMention(); return; }
    _showMention(editor, query);
  }
  function _showMention(editor, query) {
    const pop = _ensureMentionPop();
    if (!_mentionCtxHost) { _hideMention(); return; }
    const mats = _mentionCtxHost.getMats();
    const items = [];
    mats.imgs.forEach((it) => items.push(Object.assign({}, it, { grp: "本镜图片", act: "ins" })));
    mats.auds.forEach((it) => items.push(Object.assign({}, it, { grp: "本镜声线", act: "ins" })));
    if (_mentionCtxHost.onAddMaterial) {
      _registryImgs().forEach((it) => { if (!mats.imgs.some((x) => _matSame(x, it))) items.push(Object.assign({}, it, { grp: "其它图片", act: "add" })); });
      _registryAuds().forEach((it) => { if (!mats.auds.some((x) => _matSame(x, it))) items.push(Object.assign({}, it, { grp: "其它声线", act: "add" })); });
    }
    const q = (query || "").toLowerCase();
    const filtered = q ? items.filter((it) =>
      (it.label || "").toLowerCase().includes(q) ||
      (it.name || "").toLowerCase().includes(q) ||
      String(it.idx) === query ||
      ((it.kind === "audio" ? "音频" : "图") + it.idx) === query ||
      (it.grp || "").includes(query)
    ) : items;
    if (!filtered.length) {
      pop.innerHTML = '<div class="empty">无匹配素材 · 删掉 @ 取消</div>';
    } else {
      const shown = filtered.slice(0, _MENTION_MAX);
      let html = "", cur = "";
      shown.forEach((it, i) => {
        if (it.grp !== cur) { cur = it.grp; html += '<div class="grp">' + _esc(it.grp) + "</div>"; }
        const thumb = it.kind === "image"
          ? '<img src="' + _esc(_thumb(it.url || "")) + '" alt="" loading="lazy" decoding="async" onerror="this.style.visibility=\'hidden\'">'
          : '<span class="ico"><span class="ic ic-audio" aria-hidden="true"></span></span>';
        
        const isLib = it.act === "add";
        const bold = isLib
          ? _esc((it.kind === "audio" ? "声线·" : "图片·") + (it.label || it.name || ""))
          : _esc((it.kind === "audio" ? "音频" : "图") + it.idx) + (it.label ? " " + _esc(it.label) : "");
        html += '<div class="mi" data-i="' + i + '">' + thumb
          + '<span class="t"><b>' + bold + "</b>"
          + "<small>" + (it.act === "add" ? '<span class="ic ic-plus" aria-hidden="true"></span>加入本镜并引用' : "插入引用") + (it.name && !isLib ? " · " + _esc(it.name) : "") + "</small></span></div>";
      });
      pop.innerHTML = html;
    }
    _mentionCtx = { editor, items: filtered, queryLen: query.length };
    _mentionActiveIdx = 0;
    const rect = _caretRect();
    pop.hidden = false;
    if (rect) {
      const pw = pop.offsetWidth, ph = pop.offsetHeight;
      let left = rect.left, top = rect.bottom + 6;
      if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8;
      if (top + ph > window.innerHeight - 8) top = rect.top - ph - 6;
      pop.style.left = Math.max(8, left) + "px";
      pop.style.top = Math.max(8, top) + "px";
    }
    _highlightMentionItem();
  }
  function _highlightMentionItem() {
    if (!_mentionPop) return;
    _mentionPop.querySelectorAll(".mi").forEach((el, i) => el.classList.toggle("on", i === _mentionActiveIdx));
  }
  function _mentionInsert(ctx, it) {
    const sel = window.getSelection();
    if (sel.rangeCount) {
      for (let k = 0; k < ctx.queryLen + 1; k++) {
        try { sel.modify("extend", "backward", "character"); } catch (e) { break; }
      }
      try { sel.getRangeAt(0).deleteContents(); sel.collapseToEnd(); } catch (e) {}
    }
    let idx = it.idx, url = it.url, label = it.label, needRerender = false;
    if (it.act === "add" && _mentionCtxHost && _mentionCtxHost.onAddMaterial) {
      idx = _mentionCtxHost.onAddMaterial(it.kind, it.name, it.url);
      needRerender = true;
    }
    const chip = _makeChipEl(it.kind, idx, label, url);
    chip._onChange = () => { if (_mentionCtxHost) _mentionCtxHost.onCommit(_promptToText(ctx.editor)); };
    _insertAtCaret(chip);
    _hideMention();
    if (_mentionCtxHost) _mentionCtxHost.onCommit(_promptToText(ctx.editor));
    if (needRerender && _mentionCtxHost && _mentionCtxHost.onRerender) _mentionCtxHost.onRerender();
  }
  function createRichPromptEditor(host) {
    const editor = document.createElement("div");
    editor.className = "lv-prompt-edit";
    if (host.big) editor.classList.add("lv-prompt-big");
    editor.contentEditable = "true";
    editor.setAttribute("data-placeholder", host.placeholder || "");
    const render = (text, mats) => { editor.innerHTML = _promptToHtml(text || "", mats || host.getMats()); };
    render(host.text || "", host.getMats());
    editor.addEventListener("focus", () => { _mentionCtxHost = host; });
    let _lvComposing = false;
    editor.addEventListener("compositionstart", () => { _lvComposing = true; });
    editor.addEventListener("compositionend", () => {
      _lvComposing = false;
      _mentionCtxHost = host;
      if (host.onCommit) host.onCommit(_promptToText(editor));
      _detectMention(editor);
      _sweepAssetTags(editor, host);
    });
    editor.addEventListener("input", () => {
      _mentionCtxHost = host;
      if (host.onCommit) host.onCommit(_promptToText(editor));
      _detectMention(editor);
      if (!_lvComposing) _sweepAssetTags(editor, host);
    });
    editor.addEventListener("blur", () => {
      if (host.onCommit) host.onCommit(_promptToText(editor));
      setTimeout(() => { if (_mentionCtx && _mentionCtx.editor === editor) _hideMention(); }, 150);
    });
    editor.addEventListener("keydown", (e) => {
      if (_mentionPop && !_mentionPop.hidden && _mentionCtx && _mentionCtx.editor === editor) {
        const n = _mentionPop.querySelectorAll(".mi").length;
        if (e.key === "ArrowDown") { e.preventDefault(); _mentionActiveIdx = Math.min(_mentionActiveIdx + 1, n - 1); _highlightMentionItem(); return; }
        if (e.key === "ArrowUp") { e.preventDefault(); _mentionActiveIdx = Math.max(_mentionActiveIdx - 1, 0); _highlightMentionItem(); return; }
        if (e.key === "Enter") { e.preventDefault(); const it = _mentionCtx.items[_mentionActiveIdx]; if (it) _mentionInsert(_mentionCtx, it); return; }
        if (e.key === "Escape") { e.preventDefault(); _hideMention(); return; }
      }
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); document.execCommand("insertText", false, "\n"); return; }
    });
    editor.addEventListener("paste", (e) => {
      e.preventDefault();
      const raw = (e.clipboardData || window.clipboardData).getData("text/plain");
      
      
      document.execCommand("insertText", false, typeof cleanText === "function" ? cleanText(raw) : raw);
    });
    return {
      el: editor,
      getText: () => _promptToText(editor),
      setText: (t) => { host.text = t; render(t, host.getMats()); },
      
      setTextMixed: (t) => {
        editor.innerHTML = "";
        editor.focus();
        const sel = window.getSelection();
        if (sel) {
          const r = document.createRange();
          r.selectNodeContents(editor); r.collapse(true);
          sel.removeAllRanges(); sel.addRange(r);
        }
        document.execCommand("insertText", false, typeof cleanText === "function" ? cleanText(t) : t);
        _sweepAssetTags(editor, host);
      },
    };
  }

  
  const _shotOptSnap = new Map();
  const _SHOT_OPT_SNAP_KEY = "wb_lv_shot_opt_snaps_v1";
  function _shotOptSnapLoad() {
    try {
      const obj = JSON.parse(localStorage.getItem(_SHOT_OPT_SNAP_KEY) || "null");
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) return;
      Object.keys(obj).forEach(function (k) {
        if (k && typeof obj[k] === "string") _shotOptSnap.set(k, obj[k]);
      });
    } catch (e) {}
  }
  function _shotOptSnapFlush() {
    try {
      const obj = {};
      _shotOptSnap.forEach(function (v, k) { obj[k] = v; });
      localStorage.setItem(_SHOT_OPT_SNAP_KEY, JSON.stringify(obj));
    } catch (e) {}
  }
  function _shotOptSnapSet(k, v) { _shotOptSnap.set(k, v); _shotOptSnapFlush(); }
  function _shotOptSnapDel(k) { _shotOptSnap.delete(k); _shotOptSnapFlush(); }
  _shotOptSnapLoad();   

  
  let _pendingFocusShot = 0;

  function renderShots() {
    
    
    lvShots.innerHTML = "";
    
    lv.shots.forEach((s, idx) => {
      
      
      if (idx === 0 && s.is_continuation) {
        s.is_continuation = false;
        const imgs0 = (s.images || []);
        if (imgs0[0] === "tail") s.images = imgs0.filter((x) => x !== "tail");
      }
      
      const _segNo = idx + 1;
      const _segRow = (lv.segs || []).find((x) => x.seg_no === _segNo);
      
      
      const _histVers = _cardHistOf(_segNo);
      const _verTotal = 1 + _histVers.length;
      let _vi = parseInt((lv.segVer || {})[_segNo], 10);
      if (!_vi || _vi < 0 || _vi >= _verTotal) _vi = 0;   
      const _ver = _vi > 0 ? _histVers[_vi - 1] : null;   
      const _isHist = !!_ver;

      const div = document.createElement("div");
      div.className = "lv-shot" + (_isHist ? " hist" : "");
      div.dataset.idx = idx;
      div.dataset.segNo = s.shot_no;   

      
      const head = document.createElement("div");
      head.className = "lv-shot-h";
      
      
      
      
      const num = document.createElement("span");
      num.className = "lv-shot-no";
      num.title = `镜头 ${s.shot_no}`;
      const numUnit = document.createElement("i");
      numUnit.className = "lv-shot-no-u";
      numUnit.textContent = "镜";
      const numDigits = document.createElement("b");
      numDigits.className = "lv-shot-no-d";
      numDigits.textContent = String(s.shot_no).padStart(2, "0");
      num.append(numUnit, numDigits);
      head.appendChild(num);
      
      
      const badge = document.createElement("span");
      badge.className = s.is_continuation ? "lv-badge" : "lv-badge first";
      badge.innerHTML = s.is_continuation
        ? '<span class="ic ic-link" aria-hidden="true"></span>续接段'
        : '<span class="ic ic-resume" aria-hidden="true"></span>首段';
      head.appendChild(badge);
      
      if (_isHist) {
        const vTag = document.createElement("span");
        vTag.className = "lv-badge hist";
        vTag.innerHTML = '<span class="ic ic-clock" aria-hidden="true"></span>历史 v' + _esc(_ver.ver);
        vTag.title = "这一版已被覆盖归档" +
          (_ver.ts ? "（" + new Date(_ver.ts * 1000).toLocaleString("zh-CN") + "）" : "") +
          "；只读，用卡片左右箭头切回当前版";
        head.appendChild(vTag);
      }
      
      
      
      
      
      
      const secWrap = document.createElement("span");
      secWrap.className = "lv-shot-sec" + (_isHist ? " hist" : "");
      const secIcon = document.createElement("span");
      secIcon.className = "ic ic-timer";
      secIcon.setAttribute("aria-hidden", "true");
      secWrap.appendChild(secIcon);
      const secInput = document.createElement("input");
      secInput.type = "number";
      secInput.setAttribute("aria-label", "本镜时长（秒）");
      const _sb = lvSecBounds();   
      secInput.min = String(_sb.min); secInput.max = String(_sb.max);
      secInput.step = "1";
      
      const _secSrc = _isHist ? Number(_ver.seconds || 0) || 5 : (s.estimated_seconds || 5);
      secInput.value = String(Math.max(_sb.min, Math.min(_sb.max, _secSrc)));
      secInput.title = _isHist
        ? `历史 v${_ver.ver} 归档时的时长（只读）`
        : `本镜时长（秒，${_sb.min}-${_sb.max}，接口单段上限）`;
      secInput.disabled = _isHist;
      secInput.addEventListener("change", () => {
        if (_isHist) return;
        
        
        
        const _now = lvSecBounds();
        const v = Math.max(_now.min, Math.min(_now.max, parseInt(secInput.value, 10) || 5));
        secInput.value = String(v);
        s.estimated_seconds = v;
        saveDraft();
      });
      secWrap.appendChild(secInput);
      const secUnit = document.createElement("span");
      secUnit.className = "lv-shot-secunit";
      secUnit.textContent = "s";
      secWrap.appendChild(secUnit);
      head.appendChild(secWrap);
      
      
      if (idx > 0) {
        const contLabel = document.createElement("label");
        contLabel.className = "lv-shot-contlbl";
        const contBox = document.createElement("input");
        contBox.type = "checkbox";
        contBox.checked = !!s.is_continuation;
        contBox.title = "从上一段尾帧续接";
        contBox.addEventListener("change", () => {
          const on = contBox.checked;
          const imgs = (s.images || []);
          const urls = (s.images_urls || []);
          
          
          if (on) {
            s.is_continuation = true;
            if (imgs[0] !== "tail") {
              s.images = ["tail", ...imgs.filter((x) => x !== "tail")];
              
              if (urls.length === imgs.length) s.images_urls = [null, ...urls];
            } else if (urls.length === imgs.length - 1) {
              s.images_urls = [null, ...urls];   
            }
            
            
            if (s.prompt.indexOf(CONT_SENT) !== 0) {
              s.prompt = _prependContSentence(_shiftRefs(s.prompt, "图", +1));
            }
          } else {
            s.is_continuation = false;
            const ti = imgs.indexOf("tail");
            s.images = imgs.filter((x) => x !== "tail");
            
            if (ti === 0 && urls.length === imgs.length) s.images_urls = urls.slice(1);
            
            if (s.prompt.indexOf(CONT_SENT) === 0) {
              s.prompt = _shiftRefs(_stripContSentence(s.prompt), "图", -1);
            }
          }
          s.mode = "reference";
          
          renderShots();
          saveDraft();
        });
        contLabel.appendChild(contBox);
        contLabel.appendChild(document.createTextNode("续接"));
        head.appendChild(contLabel);
      }
      
      let addBtn = null;
      if (!_isHist) {
        addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "lv-shot-add";
        addBtn.innerHTML = '<span class="ic ic-plus" aria-hidden="true"></span>插入一镜';
        const _canAdd = _canEditShots();
        addBtn.disabled = !_canAdd;
        addBtn.title = _canAdd ? "在此后插入一镜" : "已开始生成，不能再增删镜头";
        addBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          if (addBtn.disabled) return;
          _addShot(idx + 1);
        });
      }
      
      const headActs = document.createElement("div");
      
      
      headActs.className = "lv-shot-acts" + (_isHist ? " is-hist" : "");
      head.appendChild(headActs);
      
      const delBtn = document.createElement("button");
      delBtn.className = "lv-shot-del";
      delBtn.textContent = "删除此镜";
      delBtn.title = "从分镜移除";
      delBtn.addEventListener("click", async () => {
        
        
        if (lv.jobStatus && lv.jobStatus !== "draft") { err("已开始生成，不能再增删镜头"); return; }
        
        const _delMsg = `确定删除镜头 ${s.shot_no}？相关的画面可在资产库中查看。`;
        if (!(await lvConfirm({ title: "删除镜头", message: _delMsg, danger: true, okText: "删除" }))) return;
        lv.shots.splice(idx, 1);
        
        lv.shots.forEach((sh, i) => { sh.shot_no = i + 1; });
        renderShots();
        lvStep2Act.hidden = lv.shots.length === 0;
        
        
        
        
        const _jid = (window.LV_JOB_ID || document.body.dataset.jobId || "");
        if (_jid) {
          try {
            const r = await fetch(`${API}/api/jobs/${encodeURIComponent(_jid)}/shots/remove`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ index: idx }),
            });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) err(j.error || "删除该镜的已生成数据失败");
          } catch (ex) { err("删除该镜的已生成数据异常：" + ex.message); }
        }
        saveDraft();
      });
      
      if (_isH3() && !_isHist) {   
        const _h3p = _h3SegParamsHtml(s, idx);
        if (_h3p.html) headActs.insertAdjacentHTML("beforebegin", _h3p.html);
      }
      
      const copyBtn = document.createElement("button");
      copyBtn.className = "lv-shot-copy";
      copyBtn.innerHTML = '<span class="ic ic-copy" aria-hidden="true"></span>';
      copyBtn.title = "复制本镜提示词与素材引用";
      copyBtn.addEventListener("click", () => {
        const text = _copyShotPrompt(ed.el);
        if (!text.trim()) { setMsg("本镜还没有可复制的提示词", "warn"); return; }
        _lvCopyText(text).then(function () {
          setMsg("已复制本镜提示词与素材引用");
        }, function () {
          err("复制失败，请手动选中复制");
        });
      });
      
      if (_isH3()) {
        const optBtn = document.createElement("button");
        optBtn.className = "lv-shot-opt";
        optBtn.innerHTML = '<span class="ic ic-spark" aria-hidden="true"></span>';
        optBtn.title = "优化本镜提示词";
        const _snapKey = (lv.jobId || "") + ":" + s.shot_no;
        if (_shotOptSnap.has(_snapKey)) {
          optBtn.dataset.undo = "1";
          optBtn.classList.add("can-undo");
          optBtn.title = "撤销本次提示词优化";
        }
        optBtn.addEventListener("click", async () => {
          if (optBtn.dataset.busy === "1") return;
          if (optBtn.dataset.undo === "1") {
            const snap = _shotOptSnap.get(_snapKey);
            _shotOptSnapDel(_snapKey);   
            optBtn.dataset.undo = "";
            optBtn.classList.remove("can-undo");
            optBtn.title = "优化本镜提示词";
            if (snap != null) {
              ed.setTextMixed(snap);
              s.prompt = ed.getText();
              saveDraft();
              setMsg("已撤销本次提示词优化");
            }
            return;
          }
          const text = _copyShotPrompt(ed.el);
          if (!text.trim()) { setMsg("本镜还没有可优化的提示词", "warn"); return; }
          const mats = _matsForShot(s);
          const materials = mats.imgs.concat(mats.auds).map((x) => ({
            kind: x.kind, idx: x.idx, label: x.label || "", name: x.name || "", url: x.url || "",
          }));
          optBtn.dataset.busy = "1";
          optBtn.disabled = true;
          optBtn.classList.add("busy");
          try {
            const r = await fetch(API + "/api/optimize-shot-prompt", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ prompt: text, materials }),
            });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
            const out = (j.prompt || "").trim();
            if (!out) throw new Error("分镜引擎返回空提示词");
            _shotOptSnapSet(_snapKey, text);   
            ed.setTextMixed(out);
            s.prompt = ed.getText();
            saveDraft();
            optBtn.dataset.undo = "1";
            optBtn.classList.add("can-undo");
            optBtn.title = "撤销本次提示词优化";
            setMsg("已按 H3 六段优化本镜提示词（点同一图标可撤销）");
          } catch (ex) {
            err("提示词优化失败：" + (ex.message || ex));
          } finally {
            optBtn.dataset.busy = "";
            optBtn.classList.remove("busy");
          }
        });
        headActs.appendChild(optBtn);
      }
      headActs.appendChild(copyBtn);
      if (addBtn) headActs.appendChild(addBtn);   
      headActs.appendChild(delBtn);
      
      const _h3Anchor = _isH3() && s.is_continuation;
      if (!_h3Anchor) {
        const genBtn = document.createElement("button");
        genBtn.className = "lv-shot-gen";
        const _hasProduct = !!((lv.segs || []).find((x) => x.seg_no === idx + 1 && x.status === "completed"));
        genBtn.textContent = _hasProduct ? "重生成" : "生成";
        
        genBtn.title = _hasProduct ? "重新生成这一镜" : "只生成这一镜";
        genBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          _submitSingleShot(idx + 1);
        });
        headActs.appendChild(genBtn);
      }
      div.appendChild(head);

      
      
      const _lblAssetOf = (L) => (lv.assets || []).find((a) => a.type === "image" && (a.label || "").trim() === L)
                           || (currentLibraryItems || []).find((a) => a.type === "image" && (a.label || "").trim() === L);
      
      const badLines = (s.dialogue || []).filter((d) => d.needs_review && (d.line || "").startsWith("[脚本片段中未找到具体台词]"));
      const reviewChips = badLines.map((d) => {
        const bare = (d.line || "").replace(/^\[脚本片段中未找到具体台词\]/, "").trim();
        return `<span class="lv-chip review" title="脚本片段未确认这句对白，请人工补全"><span class="ic ic-warn" aria-hidden="true"></span>待补:${d.character || "?"}「${(bare || "（空）").slice(0, 24)}…」</span>`;
      }).join("");
      
      const warn = (s.unresolved_images && s.unresolved_images.length)
        ? `<div class="lv-warn">未匹配素材：${s.unresolved_images.join(", ")}（这些图已被剔除，请补传或人工调整 prompt）</div>` : "";
      
      const unmatchedChars = (s.characters || []).filter((c) => {
        if (c.matched !== false) return false;
        const _la = _lblAssetOf((c.label || "").trim());
        return !(_la && (_la.kind === "scene" || _la.kind === "prop"));
      }).map((c) => c.label);
      const unmatchedNote = unmatchedChars.length
        ? `<div class="lv-warn">未在脚本片段确认角色：${unmatchedChars.join("、")}（若有引用，将靠 prompt 文字描述）</div>` : "";
      
      
      
      const noImgChip = !(s.images_urls || []).filter((u) => u !== "tail").length
        && (s.characters || []).length > 0
        ? `<div class="lv-warn">本镜头未匹配任何素材图，prompt 中的角色是「猜的」，请补传或人工校对。</div>` : "";

      const warnBox = document.createElement("div");
      warnBox.innerHTML = warn + unmatchedNote + noImgChip + (reviewChips ? `<div class="lv-chips">${reviewChips}</div>` : "");
      div.appendChild(warnBox);

      
      
      
      
      if (!_isHist) {
        const matTiles = document.createElement("div");
        matTiles.className = "lv-mat-tiles";

        
        const addTile = document.createElement("div");
        addTile.className = "lv-mat-add";
        addTile.innerHTML = '<span class="ic ic-plus" aria-hidden="true"></span>';
        addTile.title = "从本任务素材里选一个加入本镜";
        addTile.addEventListener("click", () => { _pickAnyForShot(s); });
        matTiles.appendChild(addTile);

        
        
        const imgsArr = (s.images || []);
        const urlsArr = (s.images_urls || []);
        const charsArr = (s.characters || []);
        const segJobId = (window.LV_JOB_ID || document.body.dataset.jobId || "");
        const _imgStart = s.is_continuation ? 2 : 1;
        let _imgSeq = _imgStart - 1;
        const _assetOf = (nm) => (lv.assets || []).find((a) => a.name === nm)
                          || (currentLibraryItems || []).find((a) => a.name === nm);
        const imgToChar = {};           
        const consumedImg = new Set();
        charsArr.forEach((c, ci) => {
          const L = (c && c.label || "").trim();
          if (!L) return;               
          const _la = _lblAssetOf(L);
          if (_la && (_la.kind === "scene" || _la.kind === "prop")) return; 
          for (let ii = 0; ii < imgsArr.length; ii++) {
            if (consumedImg.has(ii)) continue;
            const a = _assetOf(imgsArr[ii]);
            if (a && a.kind === "character" && (a.label || "").trim() === L) {
              imgToChar[ii] = ci; consumedImg.add(ii); break;
            }
          }
        });

        
        imgsArr.forEach((key, i) => {
          const isTail = key === "tail";
          const url = urlsArr[i];
          const tile = document.createElement("span");
          if (isTail) {
            tile.className = "lv-thumb-wrap tail";
            tile.dataset.kind = "tail";
            tile.dataset.shotIdx = String(idx);
            tile.dataset.segNo = String(s.seg_no);
            tile.dataset.jobId = _esc(segJobId);
            tile.innerHTML = '<div class="lv-thumb-tail">尾帧<br><small style="opacity:.7;font-weight:400">续接</small></div>'
              + '<button class="lv-thumb-x" title="移除此尾帧引用" data-act="rm-img" data-i="' + i + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
            matTiles.appendChild(tile);
            _tailThumbsToLoad.push(tile);
            tile.querySelector("button").addEventListener("click", () => {
              s.images.splice(i, 1);
              if (s.images_urls) s.images_urls.splice(i, 1);
              s.prompt = _stripRefFromPrompt(s.prompt, "图", i + 1);
              renderShots(); saveDraft();
            });
            return;
          }
          _imgSeq++;
          if (consumedImg.has(i)) {
            
            const ci = imgToChar[i];
            const c = charsArr[ci] || {};
            const unmatched = c.matched === false;
            tile.className = "lv-thumb-wrap lv-combo" + (unmatched ? " review" : "");
            tile.dataset.kind = "image";
            tile.dataset.idx = String(_imgSeq);
            tile.dataset.shotIdx = String(idx);
            tile.title = _esc(c.label || _assetLabel(key));
            tile.innerHTML = '<img class="lv-thumb" src="' + _esc(_thumb(url || "", 128)) + '" alt="">'
              + '<span class="lv-thumb-idx">图' + _imgSeq + '</span>'
              + '<span class="lv-combo-lbl">' + _esc(c.label || "?")
              + (unmatched ? ' <span class="ic ic-warn" aria-hidden="true"></span>' : "") + '</span>'
              + '<button class="lv-thumb-x" title="移除该角色及其参考图" data-act="rm-combo" data-i="' + i + '" data-ci="' + ci + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
            matTiles.appendChild(tile);
            tile.querySelector("button").addEventListener("click", () => {
              
              s.images.splice(i, 1);
              if (s.images_urls) s.images_urls.splice(i, 1);
              s.prompt = _stripRefFromPrompt(s.prompt, "图", i + 1);
              if (s.characters) s.characters.splice(ci, 1);
              renderShots(); saveDraft();
            });
          } else {
            
            tile.className = "lv-thumb-wrap";
            tile.dataset.kind = "image";
            tile.dataset.idx = String(_imgSeq);
            tile.dataset.shotIdx = String(idx);
            tile.title = _esc(_assetLabel(key));
            tile.innerHTML = '<img class="lv-thumb" src="' + _esc(_thumb(url || "", 128)) + '" alt="">'
              + '<span class="lv-thumb-idx">图' + _imgSeq + '</span>'
              + '<button class="lv-thumb-x" title="移除此图引用" data-act="rm-img" data-i="' + i + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
            matTiles.appendChild(tile);
            tile.querySelector("button").addEventListener("click", () => {
              s.images.splice(i, 1);
              if (s.images_urls) s.images_urls.splice(i, 1);
              s.prompt = _stripRefFromPrompt(s.prompt, "图", i + 1);
              renderShots(); saveDraft();
            });
          }
        });

        
        const boundChars = new Set(Object.values(imgToChar));
        charsArr.forEach((c, i) => {
          if (boundChars.has(i)) return;
          const _lbl = (c && c.label || "").trim();
          
          if (_lbl && !(s.prompt || "").includes(_lbl)) return;
          const _la = _lbl ? _lblAssetOf(_lbl) : null;
          if (_la && (_la.kind === "scene" || _la.kind === "prop")) return; 
          const unmatched = c.matched === false;
          const tile = document.createElement("span");
          tile.className = "lv-mat-tile char" + (unmatched ? " review" : "");
          tile.title = (unmatched ? "未在脚本片段确认：" : "") + _esc(c.label || "?");
          tile.innerHTML = '<span class="lv-mat-tile-lbl">' + _esc(c.label || "?") + "</span>"
            + '<button class="lv-tile-x" title="移除此角色" data-act="rm-char" data-i="' + i + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
          tile.querySelector("button").addEventListener("click", () => {
            s.characters.splice(i, 1);
            renderShots();
            saveDraft();
          });
          matTiles.appendChild(tile);
        });

        
        const _auds = s.audio_urls || [];
        const _audWho = s.audio || [];
        const _n = Math.max(_auds.length, _audWho.length);
        for (let i = 0; i < _n; i++) {
          const u = _auds[i];
          const who = _audWho[i] || "";
          const tile = document.createElement("span");
          tile.className = "lv-chip audio";
          tile.dataset.kind = "audio";
          tile.dataset.idx = String(i + 1);
          tile.dataset.shotIdx = String(idx);
          const fname = u ? (u.split("/").pop() || u) : "";
          tile.innerHTML = '<span class="ic ic-audio" aria-hidden="true"></span>音频' + (i + 1) + " " + _esc(who || fname)
            + '<button class="lv-tile-x" title="移除此声线" data-act="rm-aud" data-i="' + i + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
          tile.querySelector("button").addEventListener("click", () => {
            if (Array.isArray(s.audio)) s.audio.splice(i, 1);
            if (Array.isArray(s.audio_urls)) s.audio_urls.splice(i, 1);
            s.prompt = _stripRefFromPrompt(s.prompt, "音频", i + 1);
            renderShots();
            saveDraft();
          });
          if (u) tile.title = _esc(_assetLabel(who) || who || u);
          matTiles.appendChild(tile);
        }

        div.appendChild(matTiles);
      } else {
        
        const matTiles = document.createElement("div");
        matTiles.className = "lv-mat-tiles hist";
        const _hImgs = Array.isArray(_ver.images) ? _ver.images : [];
        const _hUrls = Array.isArray(_ver.images_urls) ? _ver.images_urls : [];
        let _hSeq = 0;
        _hImgs.forEach((nm, i) => {
          const tile = document.createElement("span");
          if (nm === "tail") {
            tile.className = "lv-thumb-wrap tail";
            tile.innerHTML = '<div class="lv-thumb-tail">尾帧<br><small style="opacity:.7;font-weight:400">续接</small></div>';
            matTiles.appendChild(tile);
            return;
          }
          _hSeq++;
          tile.className = "lv-thumb-wrap";
          tile.title = _esc(_assetLabel(nm) || nm) + "（历史快照，只读）";
          
          tile.innerHTML = '<img class="lv-thumb" src="' + _esc(_thumb(_hUrls[i] || "", 128)) + '" alt="">'
            + '<span class="lv-thumb-idx">图' + _hSeq + '</span>';
          matTiles.appendChild(tile);
        });
        const _hAuds = Array.isArray(_ver.audio) ? _ver.audio : [];
        _hAuds.forEach((who, i) => {
          
          const tile = document.createElement("span");
          tile.className = "lv-chip audio";
          tile.title = (who || "") + "（历史快照，只读）";
          tile.innerHTML = '<span class="ic ic-audio" aria-hidden="true"></span>音频' + (i + 1) + " " + _esc(_assetLabel(who) || who || "");
          matTiles.appendChild(tile);
        });
        if (!_hImgs.length && !_hAuds.length) {
          const none = document.createElement("div");
          none.className = "lv-hist-nomat";
          none.textContent = "这一版没有绑定任何素材";
          matTiles.appendChild(none);
        }
        div.appendChild(matTiles);
      }


      
      
      
      const _promptOwner = _isHist
        ? {
            images: Array.isArray(_ver.images) ? _ver.images : [],
            images_urls: Array.isArray(_ver.images_urls) ? _ver.images_urls : [],
            audio: Array.isArray(_ver.audio) ? _ver.audio : [],
            audio_urls: Array.isArray(_ver.audio_urls) ? _ver.audio_urls : [],
          }
        : s;
      const wrap = document.createElement("div");
      wrap.className = "lv-prompt-edit-wrap" + (_isHist ? " hist" : "");
      wrap.style.position = "relative";
      const ed = createRichPromptEditor({
        text: _isHist ? (_ver.prompt || "") : (s.prompt || ""),
        placeholder: "本镜提示词（写足：场景+角色外貌+互动+对白(声线：台词，嘴形同步)+SFX+风格，不限制字数）。输入 @ 可把本镜素材缩略图插入此处。",
        getMats: () => _matsForShot(_promptOwner),
        onCommit: (t) => { if (_isHist) return; s.prompt = t; saveDraft(); },
        onAddMaterial: (kind, name, url) => {
          if (kind === "image") {
            s.images = s.images || []; s.images_urls = s.images_urls || [];
            if (!s.images.includes(name)) { s.images.push(name); s.images_urls.push(url); }
            return s.images.length;
          }
          s.audio = s.audio || []; s.audio_urls = s.audio_urls || [];
          if (!s.audio.includes(name)) { s.audio.push(name); s.audio_urls.push(url); }
          return s.audio.length;
        },
        onRerender: () => renderShots(),
      });
      if (_isHist) ed.el.contentEditable = "false";   
      wrap.appendChild(ed.el);
      div.appendChild(wrap);

      
      div.addEventListener("click", (e) => {
        const mat = e.target.closest(".lv-mat[data-kind][data-idx]");
        if (mat && wrap.contains(mat)) {
          _flashInShot(div, { kind: mat.dataset.kind, idx: parseInt(mat.dataset.idx, 10), origin: "bg" }, mat);
          return;
        }
        const thumb = e.target.closest(".lv-thumb-wrap[data-kind=image]");
        if (thumb && !e.target.closest("button")) {
          _flashInShot(div, { kind: "image", idx: parseInt(thumb.dataset.idx, 10), origin: "thumb" });
          return;
        }
        const aChip = e.target.closest(".lv-chip.audio[data-idx]");
        if (aChip && !e.target.closest("button")) {
          _flashInShot(div, { kind: "audio", idx: parseInt(aChip.dataset.idx, 10), origin: "audio" });
          return;
        }
      });

      
      
      
      
      const _segForCard = lv.segs.find((x) => x.seg_no === _segNo);
      if (_segForCard) {
        const stEl = document.createElement("div");
        stEl.className = "lv-shot-st";
        div.appendChild(stEl);
        _fillShotStatusLine(stEl, _segForCard);
      }

      
      if (_verTotal > 1) {
        const nav = document.createElement("div");
        nav.className = "lv-ver-nav";
        const mkBtn = (cls, icon, title, target) => {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "lv-ver-btn " + cls;
          b.innerHTML = '<span class="ic ic-chevron-' + icon + '" aria-hidden="true"></span>';
          b.title = title;
          b.disabled = target === null;
          b.addEventListener("click", (ev) => {
            ev.stopPropagation();
            if (target === null) return;
            _renderVerSwitch(_segNo, target);
          });
          return b;
        };
        nav.appendChild(mkBtn("prev", "left", "上一版（更新，最左是当前稿）", _vi > 0 ? _vi - 1 : null));
        nav.appendChild(mkBtn("next", "right", "下一版（更旧）", _vi < _verTotal - 1 ? _vi + 1 : null));
        const cnt = document.createElement("span");
        cnt.className = "lv-ver-count" + (_isHist ? " hist" : "");
        cnt.textContent = (_vi + 1) + "/" + _verTotal;
        cnt.title = _isHist
          ? "正在看历史版" + (_ver.ts ? "（归档于 " + new Date(_ver.ts * 1000).toLocaleString("zh-CN") + "）" : "") + "；只读"
          : "当前版（最新）";
        nav.appendChild(cnt);
        div.appendChild(nav);
      }

      lvShots.appendChild(div);
      
      if (_isH3()) _wireH3SegParams(div, s, idx);
      
      if (lv.shots[idx + 1] && lv.shots[idx + 1].is_continuation) {
        const link = document.createElement("div");
        link.className = "lv-shot-link";
        link.setAttribute("aria-hidden", "true");
        link.innerHTML = '<span class="lv-shot-snap"><span class="ic ic-link"></span></span>';
        lvShots.appendChild(link);
      }
    });
    
    if (lv.segs.length) _updateShotStatusLines();
    
    
    _loadTailThumbs();
    _mountAddRow();
  }

  
  function _mountAddRow() {
    const _empty = lv.shots.length === 0;
    const row = document.createElement("div");
    row.className = "lv-addrow" + (_empty ? " empty" : "");
    if (_empty) {
      const tip = document.createElement("div");
      tip.className = "lv-addrow-tip";
      tip.innerHTML = "还没有分镜。可以自己写第一镜，也可以在左侧粘贴脚本后点「智能分镜」让 AI 拆。";
      row.appendChild(tip);
    }
    const b = document.createElement("button");
    b.type = "button";
    b.className = "lv-addrow-btn";
    b.innerHTML = '<span class="ic ic-plus" aria-hidden="true"></span>' + (_empty ? "手动添加第一镜" : "添加一镜");
    const _ok = _canEditShots();
    b.disabled = !_ok;
    b.title = !_ok ? "已开始生成，不能再增删镜头" : (_empty ? "添加第一镜" : "在末尾添加一镜");
    b.addEventListener("click", () => { if (!b.disabled) _addShot(null); });
    row.appendChild(b);
    lvShots.appendChild(row);
    
    if (_pendingFocusShot) {
      const _no = _pendingFocusShot;
      _pendingFocusShot = 0;
      const card = lvShots.querySelector('.lv-shot[data-seg-no="' + _no + '"]')
                || lvShots.querySelectorAll(".lv-shot")[_no - 1];
      if (card) {
        card.scrollIntoView({ block: "center" });
        const edEl = card.querySelector(".lv-prompt-edit");
        if (edEl) setTimeout(() => { try { edEl.focus(); } catch (_) {} }, 30);
      }
    }
  }

  function _esc(s) {
    return String(s == null ? "" : s).replace(/[&<>\"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
  }
  
  function _thumb(u, w) {
    return typeof thumbUrl === "function" ? thumbUrl(u, w) : u;
  }
  
  
  
  function _stripRefFromPrompt(text, prefix, removedIdx) {
    if (!text || typeof text !== 'string') return text;
    const safe = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return text.replace(new RegExp(safe + "(\d{1,2})(?!\d)", "g"), (m, numStr) => {
      const n = parseInt(numStr, 10);
      if (n === removedIdx) return "";
      if (n > removedIdx) return prefix + (n - 1);
      return m;
    });
  }
  
  
  
  
  const CONT_SENT = "图1是上一段视频的最后一帧。请从这个镜头接着往下拍：";
  
  
  function _shiftRefs(text, prefix, delta) {
    if (!text || typeof text !== "string") return text;
    const safe = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return text.replace(new RegExp(safe + "(\\d{1,2})(?!\\d)", "g"), (m, numStr) => {
      const n = parseInt(numStr, 10) + delta;
      return n >= 1 ? prefix + n : "";
    });
  }
  function _prependContSentence(t) {
    const v = String(t || "");
    return v.indexOf(CONT_SENT) === 0 ? v : CONT_SENT + v;
  }
  function _stripContSentence(t) {
    const v = String(t || "");
    return v.indexOf(CONT_SENT) === 0 ? v.slice(CONT_SENT.length) : v;
  }
    function _encUrl(u) {
    try {
      const m = String(u || "").match(/^([a-z]+:\/\/[^/]*)(\/.*)$/i);
      if (m) return m[1] + m[2].split("/").map((seg, i) => i === 0 ? seg : encodeURIComponent(decodeURIComponent(seg))).join("/");
      return "/" + String(u || "").replace(/^\//, "").split("/").map((seg) => encodeURIComponent(decodeURIComponent(seg))).join("/");
    } catch (e) { return u; }
  }
  
  
  
  function _assetUrl(name, url) {
    if (url) return url;
    if (!name) return "";
    const s = String(name);
    if (/^(https?:|data:|\/)/i.test(s)) return s;
    return "/assets/" + s;
  }
    

  
  function _flashInShot(scope, target, bgEl) {
    if (!scope || !target) return;
    scope.querySelectorAll('.lv-flash').forEach((el) => el.classList.remove('lv-flash'));
    scope.querySelectorAll('.ref.lv-flash').forEach((el) => el.classList.remove('lv-flash'));
    let sel = '';
    if (target.kind === 'image') sel = '.lv-thumb-wrap[data-kind=image][data-idx="'+target.idx+'"]';
    else if (target.kind === 'audio') sel = '.lv-chip.audio[data-idx="'+target.idx+'"]';
    else return;
    const el = scope.querySelector(sel);
    if (el) { el.classList.add('lv-flash'); setTimeout(() => el.classList.remove('lv-flash'), 1700); }
    
    
    const ref = bgEl || scope.querySelector('.lv-mat[data-kind="'+target.kind+'"][data-idx="'+target.idx+'"]');
    if (ref) { ref.classList.add('lv-flash'); setTimeout(() => ref.classList.remove('lv-flash'), 1700); }
  }

async function _pickImageForShot(s) {
    if (!lv.assets || !lv.assets.length) { err("本任务还没有任何素材，先到「素材登记」屏上传"); return; }
    const list = lv.assets.filter((a) => a.type === "image");
    if (!list.length) { err("本任务里没有图片素材"); return; }
    
    const a = await lvPick({ title: "选一张作为本镜参考图", items: list.map((x) => ({ name: x.name, label: (x.label || x.name) + (x.kind ? " · " + x.kind : ""), url: x.url, type: x.type })) });
    if (!a) return;
    s.images = s.images || [];
    s.images_urls = s.images_urls || [];
    if (!s.images.length && s.is_continuation) s.images.push("tail");
    s.images.push(a.name);
    s.images_urls.push(a.url);
    
    
    
    var _userImgs = s.images.filter(function (x) { return x !== "tail"; });
    var _n = _userImgs.length;
    var _tag = "图" + _n;
    if (String(s.prompt || "").indexOf(_tag) < 0) {
      s.prompt = String(s.prompt || "").replace(/\s+$/, "") + " " + _tag;
    }
    renderShots();
    saveDraft();
  }
  async function _pickCharacterForShot(s) {
    const list = (lv.assets || []).filter((a) => a.type === "image" && a.kind === "character");
    if (!list.length) { err("本任务里没有「角色」类图片（请到「素材登记」屏把图片类型改为「角色」）；"); return; }
    const a = await lvPick({ title: "选一个角色加入本镜", items: list.map((x) => ({ name: x.name, label: x.label || x.name, url: x.url, type: x.type })) });
    if (!a) return;
    
    s.images = s.images || [];
    s.images_urls = s.images_urls || [];
    s.characters = s.characters || [];
    if (s.characters.some(function (c) { return (c.label || "").trim() === (a.label || a.name).trim(); })) { err("该角色已在本镜"); return; }
    if (!s.images.length && s.is_continuation) s.images.push("tail");
    s.images.push(a.name);
    s.images_urls.push(a.url);
    var _uImgs = s.images.filter(function (x) { return x !== "tail"; });
    var _nC = _uImgs.length;
    var _tagC = "图" + _nC;
    if (String(s.prompt || "").indexOf(_tagC) < 0) {
      s.prompt = String(s.prompt || "").replace(/\s+$/, "") + " " + _tagC;
    }
    s.characters.push({ label: a.label || a.name, matched: true, voice_source: "model_default" });
    renderShots();
    saveDraft();
  }


  
  
  async function _pickAnyForShot(s) {
    if (!lv.assets || !lv.assets.length) { err("本任务还没有任何素材，先到「素材登记」屏上传"); return; }
    const a = await lvPick({ title: "选素材加入本镜", items: lv.assets.map((x) => ({ name: x.name, label: (x.label || x.name) + (x.kind ? " · " + x.kind : ""), url: x.url, type: x.type, kind: x.kind })) });
    if (!a) return;
    
    
    const _real = (lv.assets || []).find(function (x) { return x.name === a.name; }) || a;
    if (a.type === "image" && a.kind === "character") {
      
      s.images = s.images || [];
      s.images_urls = s.images_urls || [];
      s.characters = s.characters || [];
      if (s.images.some(function (x) { return x === a.name; })) { err("该图片已在本镜"); return; }
      if (s.characters.some(function (c) { return (c.label || "").trim() === (_real.label || _real.name || "").trim(); })) { err("该角色已在本镜"); return; }
      if (!s.images.length && s.is_continuation) s.images.push("tail");
      s.images.push(a.name);
      s.images_urls.push(a.url);
      var _uImgs = s.images.filter(function (x) { return x !== "tail"; });
      var _nC = _uImgs.length;
      var _tagC = "图" + _nC;
      if (String(s.prompt || "").indexOf(_tagC) < 0) {
        s.prompt = String(s.prompt || "").replace(/\s+$/, "") + " " + _tagC;
      }
      s.characters.push({ label: _real.label || _real.name, matched: true, voice_source: "model_default" });
    } else if (a.type === "image") {
      s.images = s.images || [];
      s.images_urls = s.images_urls || [];
      if (s.images.some(function (x) { return x === a.name; })) { err("该图片已在本镜"); return; }
      if (!s.images.length && s.is_continuation) s.images.push("tail");
      s.images.push(a.name);
      s.images_urls.push(a.url);
      var _userImgs = s.images.filter(function (x) { return x !== "tail"; });
      var _n = _userImgs.length;
      var _tag = "图" + _n;
      if (String(s.prompt || "").indexOf(_tag) < 0) {
        s.prompt = String(s.prompt || "").replace(/\s+$/, "") + " " + _tag;
      }
    }
    renderShots();
    saveDraft();
  }
  
  function _syncStartBtn() {
    const bar = $("lvStep2Act");
    const btn = $("lvTo3");
    if (!bar || !btn) return;
    const running = lv.jobStatus === "processing" || (lv.segs || []).some((s) => s.status === "processing");
    bar.hidden = lv.shots.length === 0;
    btn.hidden = false;
    btn.disabled = running;
    btn.classList.remove("danger");
    btn.textContent = "批量生成";
    _syncOptBtn();   
  }

  
  function _syncOptBtn() {
    const btn = $("lvOptimize");
    if (!btn) return;
    const _started = !!(lv.jobId && lv.jobStatus && lv.jobStatus !== "draft")
      || (lv.segs || []).some((x) => x.status === "completed" || x.status === "processing" || x.video_id);
    btn.disabled = _started;
    btn.title = _started
      ? "已开始生成，分镜已定稿。改某一镜请直接改稿重生成；要整份重拆请新建任务"
      : "用当前剧本拆一份分镜";
  }

  
  function _canEditShots() {
    return !(lv.jobStatus && lv.jobStatus !== "draft");
  }
  function _blankShot(shotNo) {
    const _sb = lvSecBounds();
    return {
      shot_no: shotNo,
      prompt: "",
      
      estimated_seconds: Math.max(_sb.min, Math.min(_sb.max, 5)),
      
      is_continuation: false,
      images: [], images_urls: [], audio: [], audio_urls: [],
      mode: "reference",
      
      post_refine: {}, post_face: {},
    };
  }
  
  async function _addShot(at) {
    if (!_canEditShots()) {
      err("已开始生成，不能再增删镜头");
      return;
    }
    if (!lv.jobId) await ensureJob();       
    if (!lv.jobId) { err("任务创建失败，请稍后重试"); return; }
    const pos = (at == null || at > lv.shots.length) ? lv.shots.length : Math.max(0, at);
    
    const _nextWasCont = pos < lv.shots.length && !!lv.shots[pos].is_continuation;
    lv.shots.splice(pos, 0, _blankShot(pos + 1));
    lv.shots.forEach((sh, i) => { sh.shot_no = i + 1; });   
    _pendingFocusShot = pos + 1;
    renderShots();
    lvStep2Act.hidden = lv.shots.length === 0;
    _syncStartBtn();
    saveDraft();
    if (_nextWasCont) {
      setMsg(`已插入第 ${pos + 1} 镜；原第 ${pos + 1} 镜现在是第 ${pos + 2} 镜，请确认它还要不要续接`, "warn");
    } else {
      setMsg(`已插入第 ${pos + 1} 镜，填好提示词即可`);
    }
  }

  
  $("lvTo3").addEventListener("click", async () => {
    withBtn($("lvTo3"), "提交中…", async () => {
      if (!lv.shots.length) { err("分镜数据未加载完成，请稍候重试"); return; }
      
      if (!lv.jobId) await ensureJob();
      if (lv.jobStatus === "processing") { err("该任务正在生成中，请等待完成"); return; }
      const ownerJobId = lv.jobId || null;   
      setMsg("正在补齐未生成的镜头…");
      let r, j;
      try {
        r = await fetch(API + "/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_id: lv.jobId || null,
            shots: lv.shots,
            assets: _cleanAssets(lv.assets),
            script: lvScript ? lvScript.value : "",
            
            gen_params: lv.opts || {},
          }),
        });
        j = await r.json().catch(() => ({}));
      } catch (e) {
        err("批量生成网络异常：" + (e && e.message ? e.message : e));
        return;
      }
      if (!r.ok) { err("提交失败：" + (j.error || `HTTP ${r.status}`)); return; }
      
      if (_ownerGone(ownerJobId)) { loadJobs(); return; }
      if (!_adoptJobState(j, { claim: true })) { loadJobs(); return; }
      saveState();
      renderShots();   
      _refreshStatusUI();
      startPoll();
      const _cur = lvShots.querySelector(".lv-shot");
      if (_cur) _cur.scrollIntoView({ behavior: "smooth", block: "start" });
      loadJobs();
      setMsg("已提交，后台补齐未生成的镜头（已生成的保留）");
    });
  });

  
  async function _submitSingleShot(segNo) {
    if (!lv.shots.length) { err("分镜数据未加载完成"); return; }
    if (lv.jobStatus === "processing" || (lv.segs || []).some((x) => x.status === "processing")) {
      err("有镜头正在生成，请稍候再提交这一镜"); return;
    }
    const seg = (lv.segs || []).find((x) => x.seg_no === segNo);
    
    if (seg && seg.status === "completed") { await _regenFromCard(segNo); return; }
    
    if (!lv.jobId) await ensureJob();
    const ownerJobId = lv.jobId || null;   
    let segNos = [segNo];
    if (_isH3()) {
      
      for (let i = segNo; i < lv.shots.length; i++) {
        if (i === segNo - 1 || lv.shots[i].is_continuation) segNos.push(i + 1);
        else break;
      }
      segNos = [...new Set(segNos)].sort((a, b) => a - b);
    }
    withBtn(lvShots.querySelector(`.lv-shot[data-idx="${segNo - 1}"] .lv-shot-gen`), "提交中…", async () => {
      let r, j;
      try {
        r = await fetch(API + "/api/jobs", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_id: lv.jobId, shots: lv.shots,
            assets: _cleanAssets(lv.assets), script: lvScript ? lvScript.value : "",
            seg_nos: segNos, gen_params: lv.opts || {},
          }),
        });
        j = await r.json().catch(() => ({}));
      } catch (e) { err("单镜提交网络异常：" + (e.message || e)); return; }
      if (!r.ok) { err("单镜提交失败：" + (j.error || `HTTP ${r.status}`)); return; }
      
      if (_ownerGone(ownerJobId)) { loadJobs(); return; }
      if (!_adoptJobState(j, { claim: true })) { loadJobs(); return; }   
      saveState();
      renderShots();
      _refreshStatusUI();
      startPoll();
      loadJobs();
      setMsg(`第 ${segNo} 镜已提交${segNos.length > 1 ? `（含续接链共 ${segNos.length} 段）` : ""}，后台生成中`);
    });
  }

  
  
  let _pollGen = 0;

  function startPoll() {
    stopPoll();
    pollJob();
    lv.poll = setInterval(pollJob, 4000);
  }
  function stopPoll() {
    _pollGen++;
    if (lv.poll) { clearInterval(lv.poll); lv.poll = null; }
  }


  
  function _adoptJobState(j, opts) {
    const o = opts || {};
    if (!j || !j.state) return false;
    const st = j.state;
    
    const owner = st.job_id || j.job_id || (j.job && j.job.id) || null;
    if (owner) {
      if (o.claim) {
        if (lv.jobId && lv.jobId !== owner) return false;
        lv.jobId = owner;
      } else if (lv.jobId !== owner) {
        return false;
      }
    } else if (!lv.jobId && !o.claim) {
      return false;
    }
    lv.state = st;
    
    if (Array.isArray(j.segments)) lv.segs = j.segments;
    if ("queue_state" in j) lv.queueState = j.queue_state || null;
    
    lv.jobStatus = (lv.state && lv.state.status) || null;
    return true;
  }
  
  function _ownerGone(ownerJobId) {
    return (lv.jobId || null) !== (ownerJobId || null);
  }
  
  function _refreshStatusUI() {
    _syncStartBtn();
    _updateProgSum();
    if ((lv.segs || []).length) _updateShotStatusLines();
  }

  async function pollJob() {
    if (!lv.jobId) return;
    const gen = _pollGen;       
    const jid = lv.jobId;       
    try {
      const r = await fetch(API + "/api/jobs/" + jid);
      const j = await r.json().catch(() => ({}));
      
      if (gen !== _pollGen || jid !== lv.jobId) return;
      
      _adoptJobState(j);
      if (r.status === 404) {
        
        
        stopPoll();
        lv.jobId = null; lv.jobStatus = null; lv.segs = []; lv.state = null;
        _refreshStatusUI();
        loadJobs();
        setMsg("任务已被删除，已回到草稿（可重新编辑）");
        return;
      }
      if (!r.ok) { err("查询失败：" + (j.error || "")); return; }
      
      _syncStartBtn();          
      _updateProgSum();         
      _updateShotStatusLines(); 
      const _anyProc = lv.segs.some((s) => s.status === "processing");
      
      const _stLabel = (lv.state && lv.state.label) || "";
      if (_stLabel !== lv._jobLabelSeen) {
        lv._jobLabelSeen = _stLabel;
        loadJobs();
      }
      if (j.job.status === "completed" && !_anyProc) {
        stopPoll();
        lv.finalUrl = j.final_url || null;
        _verifyFinal();
        setMsg("成片已生成，可在右侧预览（点分镜卡定位到对应段）");
        buildStrip();   
        loadJobs();
      } else if (j.job.status === "failed" && !_anyProc) {
        stopPoll();
        
        err("生成失败：" + ((lv.state && lv.state.detail) || j.job.error || ""));
        loadJobs();     
      } else if (j.job.status === "cancelled" && !_anyProc) {
        
        
        stopPoll();
        loadJobs();     
      } else if (j.job.status !== "processing" && _anyProc) {
        
        
      }
    } catch (e) {  }
  }

  function _fmtDur(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    const m = Math.floor(sec / 60), s = sec % 60;
    return m > 0 ? `${m}分${s}秒` : `${s}秒`;
  }
  
  
  function _updateProgSum() {
    const box = $("lvProgSum");
    if (!box) return;
    const _stObj = lv.state || {};
    const js = _stObj.status || null;                       
    const started = !!(lv.jobId && js && js !== "draft");
    box.hidden = !started || !lv.segs.length;
    if (box.hidden) return;
    
    const total = (_stObj.total != null && _stObj.total > 0) ? _stObj.total : (lv.segs.length || 0);
    const done = (_stObj.done != null) ? _stObj.done : lv.segs.filter((s) => s.status === "completed").length;
    const pct = total ? Math.round((done / total) * 100) : 0;
    
    const jobCN = _stObj.label || "—";
    
    const elapsed = _stObj.elapsed || 0;
    const eta = (_stObj.eta == null) ? 0 : _stObj.eta;
    const cls = js === "completed" ? "green" : js === "failed" ? "red" : js === "processing" ? "amber" : "";
    
    box.classList.toggle("st-processing", js === "processing");
    box.classList.toggle("st-completed", js === "completed");
    box.classList.toggle("st-failed", js === "failed");
    box.classList.toggle("st-stopped", js === "cancelled");
    const el = $("lvPsN");
    if (el) el.textContent = `${done}/${total}`;
    const el2 = $("lvPsElapsed");
    if (el2) { el2.textContent = _fmtDur(elapsed); el2.className = "ps-v " + cls; }
    const el3 = $("lvPsEta");
    
    if (el3) { el3.textContent = eta > 0 ? _fmtDur(eta) : "—"; el3.className = "ps-v"; }
    const el4 = $("lvPsSt");
    
    if (el4) {
      const _d = (_stObj.detail || "").trim();
      el4.textContent = jobCN + (_d ? " · " + _d : "");
      el4.className = "ps-v " + cls;
    }
    
    
    
    if (!lvShots.querySelector(".lv-shot.sel")) _prevShowJobState();
    
    const _costK = $("lvPsCostK"), _costV = $("lvPsCost");
    if (_costV) {
      let _point = 0, _coins = 0, _money = 0, _unitP = "", _unitC = "", _unitM = "", _any = false;
      (lv.segs || []).forEach((s) => {
        if (s && s.is_continuation) return;          
        const c = s && s.cost;
        if (!c) return;
        if (c.point != null && c.point !== "") { _point += Number(c.point) || 0; _unitP = c.point_unit || _unitP; _any = true; }
        if (c.coins != null && c.coins !== "") { _coins += Number(c.coins) || 0; _unitC = c.coins_unit || _unitC; _any = true; }
        if (c.money != null && c.money !== "") { _money += Number(c.money) || 0; _unitM = c.money_unit || _unitM; _any = true; }
      });
      const _txt = _costText({ point: _any && _point ? _point : null,
                               coins: _coins, money: _any && _money ? _money : null,
                               point_unit: _unitP, coins_unit: _unitC, money_unit: _unitM });
      if (_costK) _costK.hidden = !_any;
      _costV.hidden = !_any;
      _costV.textContent = _any ? _txt : "—";
    }
    const bar = $("lvPsBar");
    if (bar) bar.style.width = pct + "%";
    
    
    
    const rb = $("lvRetry");
    if (rb) { rb.hidden = !(js === "failed"); rb.disabled = rb.hidden; }
    const rs = $("lvResume");
    if (rs) { rs.hidden = !(js === "cancelled"); rs.disabled = rs.hidden; }   
    const sb = $("lvStopBtn");
    if (sb) { sb.hidden = !(js === "processing"); sb.disabled = sb.hidden; }
    const hint = $("lvPsHint");
    
    
    const _segRunning = (lv.segs || []).some((s) => s && s.status === "processing");
    if (hint) hint.textContent = _segRunning
      ? "正在生成当前段，请保持页面打开。"
      : (js === "processing" ? "正在生成，请保持页面打开。"
      : (js === "cancelled" ? "已停止：在飞段已收尾，点「继续生成」续跑剩余段。" : ""));
  }

  
  
  
  function _updateShotStatusLines() {
    lvShots.querySelectorAll(".lv-shot").forEach((card) => {
      const segNo = parseInt(card.dataset.segNo, 10);
      const s = lv.segs.find((x) => x.seg_no === segNo);
      let st = card.querySelector(".lv-shot-st");
      if (!s) { if (st) st.remove(); return; }   
      if (!st) { st = document.createElement("div"); st.className = "lv-shot-st"; card.appendChild(st); }
      _fillShotStatusLine(st, s);
    });
  }

  
  function _costText(cost) {
    if (!cost || (cost.point == null && cost.coins == null && cost.money == null)) return "";
    const _ent = !!(window.__rhAccount
      && String(window.__rhAccount.api_type || "NORMAL").toUpperCase() !== "NORMAL");
    const pu = cost.point_unit || "", cu = cost.coins_unit || "", mu = cost.money_unit || "";
    const _hasPoint = cost.point != null && cost.point !== "";
    const _hasCoins = cost.coins != null && cost.coins !== "";
    const _hasMoney = cost.money != null && cost.money !== "";
    
    
    if (_hasPoint) return Number(Number(cost.point).toFixed(3)) + " " + pu;
    if (_ent && _hasMoney) return mu + Number(cost.money).toFixed(2);
    if (_hasCoins) return String(cost.coins) + " " + cu;
    if (_hasMoney) return mu + Number(cost.money).toFixed(2);
    return "";
  }

  
  const _TIER_T = { fast: "快速（6步）", hq: "标准（20步）", hq25: "精细（25步）" };
  const _INST_T = { default: "Default", plus: "Plus", ultra: "Ultra" };
  const _REFINE_MODE = { refine: "仅精修", upscale: "放大+精修", latent_upscale: "仅放大" };
  function _objVal(v) {
    if (!v) return null;
    if (typeof v === "object") return v;
    try { const o = JSON.parse(v); return (o && typeof o === "object") ? o : null; } catch (e) { return null; }
  }
  
  function _h3MetaWanted(s) {
    const m = String((s && s.model) || (lv.opts && lv.opts.model) || "");
    if (m) return /h3/i.test(m);
    return _isH3();
  }
  function _h3JobMetaRows(s) {
    
    if (!_h3MetaWanted(s)) return [];
    const gp = lv.opts || {};
    const rows = [];
    if (gp.instance_tier) rows.push(["运行档位", _INST_T[String(gp.instance_tier).toLowerCase()] || gp.instance_tier]);
    if (gp.quality_tier) rows.push(["质量档", _TIER_T[gp.quality_tier] || gp.quality_tier]);
    if ("accel" in gp) rows.push(["Lora加速", (gp.accel === true || String(gp.accel) === "1") ? "开" : "关"]);
    return rows;
  }
  function _h3SegMetaRows(s) {
    if (!_h3MetaWanted(s)) return [];   
    const rows = [];
    const rf = _objVal(s.post_refine);
    if (rf) {
      if (rf.mode && rf.mode !== "off") {
        const parts = [_REFINE_MODE[rf.mode] || rf.mode];
        if (rf.steps != null) parts.push(rf.steps + " 步");
        if (rf.mp != null) parts.push(rf.mp + " MP");
        rows.push(["二次采样", parts.join(" · ")]);
      } else {
        rows.push(["二次采样", "关"]);
      }
    }
    const fc = _objVal(s.post_face);
    if (fc) rows.push(["脸部修复", fc.enabled ? "开" : "关"]);
    return rows;
  }

  
  function _fillShotStatusLine(st, s) {
    let durTxt = "";
    if (s.started_at) {
      
      const _endAt = s.finished_at || s.updated_at;
      if (s.status === "completed" && _endAt) durTxt = " · 耗时" + _fmtDur(_endAt - s.started_at);
      else if (s.status === "processing") durTxt = " · 已" + _fmtDur(Date.now() / 1000 - s.started_at);
    }
    
    const _ss = s.state || {};
    st.className = "lv-shot-st st-" + (_ss.phase || s.status || "pending");
    let html = `<span class="st-dot"></span><span class="st-txt">${_esc(_ss.label || "—")}${durTxt}</span>`;
    if (s.status === "failed" || s.status === "cancelled" || _ss.skipped) {
      
      const reason = _ss.detail || "";
      if (reason) html += `<span class="st-err" title="${_esc(s.error || reason)}">${_esc(reason)}</span>`;
      
      if (_ss.can_retry === false) {
        html += `<span class="st-grp" title="该段属于续接组，整组一次提交，需从组首重试">` +
                `随第${_ss.retry_owner || "?"}段整组重试</span>`;
      } else {
        html += `<button class="st-retry" type="button" data-seg="${s.seg_no}">` +
                `${_esc(_ss.retry_label || "重试本段")}</button>`;
      }
    } else if (s.status === "completed") {
      const _tv = Math.round(s.finished_at || s.updated_at || 0);
      
      
      
      const _costT = s.is_continuation ? "" : _costText(s.cost);
      html += `<span class="st-thumb" data-seg="${s.seg_no}" title="点击在右侧预览本段成片">
                <img src="${API}/api/jobs/${lv.jobId}/segment/${s.seg_no}/thumb?v=${_tv}" alt="" onerror="this.parentNode.classList.add('noimg');this.remove()">
              </span>`
              + (_costT ? `<span class="st-cost" title="本次任务消耗（整组续接合计一笔）">本次 ${_esc(_costT)}</span>` : "")
              + `<button class="st-view" type="button" data-seg="${s.seg_no}">预览本段</button>`;
    }
    st.innerHTML = html;
  }

  
  lvShots.addEventListener("click", (e) => {
    const retryBtn = e.target.closest(".st-retry");
    if (retryBtn) {
      e.stopImmediatePropagation();
      
      _submitSingleShot(parseInt(retryBtn.dataset.seg, 10));
      return;
    }
    const viewBtn = e.target.closest(".st-view, .st-thumb");
    if (viewBtn) {
      e.stopImmediatePropagation();
      
      selectSeg(parseInt(viewBtn.dataset.seg, 10));
      return;
    }
  });

  
  async function _regenFromCard(n) {
    const s = lv.segs.find((x) => x.seg_no === n);
    if (!s) return;
    if (s.status === "processing") { err("该段正在生成，请稍候"); return; }
    
    const _shot = (lv.shots || [])[n - 1];
    const _prompt = _shot && typeof _shot.prompt === "string" ? _shot.prompt : (s.prompt || "");
    
    
    const _sec = _shot && _shot.estimated_seconds ? parseInt(_shot.estimated_seconds, 10) : undefined;
    
    const title = "重新生成";
    const message = `确定重新生成第 ${n} 个分镜吗？` +
      (s.status === "failed" ? "" : `\n\n旧版会自动归档。`);
    if (!(await lvConfirm({
      title,
      message,
      danger: true, okText: "重新生成",
    }))) return;
    setMsg(`第 ${n} 个分镜重新生成中…`);
    const ownerJobId = lv.jobId || null;   
    
    const _pr = (_shot && _shot.post_refine) || null;
    const _pf = (_shot && _shot.post_face) || null;
    const _asp = (((_shot && _shot.aspect_ratio) || "").trim()) || ((lv.opts && lv.opts.aspect_ratio) || "");
    const _res = (((_shot && _shot.resolution) || "").trim()) || ((lv.opts && lv.opts.resolution) || "");
    try {
      const r = await fetch(API + `/api/jobs/${lv.jobId}/segment/${n}/regen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: _prompt, seconds: _sec,
          post_refine: _pr, post_face: _pf,
          aspect_ratio: _asp, resolution: _res,
          gen_params: lv.opts || {},
        }),
      });
      const j = await r.json();
      if (!r.ok) { err("重生成失败：" + (j.error || "")); return; }
      
      if (_ownerGone(ownerJobId)) { loadJobs(); return; }
      if (!_adoptJobState(j)) { loadJobs(); return; }
      saveState();
      _refreshStatusUI();
      startPoll();
      loadJobs();
      setMsg(`第 ${n} 个分镜已加入队列，后台生成中…`);
    } catch (e) { err("重生成异常：" + e.message); }
  }
  function _fillShotStatusLineFor(n) {
    const s = lv.segs.find((x) => x.seg_no === n);
    if (!s) return;
    const card = lvShots.querySelector(`.lv-shot[data-seg-no="${n}"]`);
    if (!card) return;
    const st = card.querySelector(".lv-shot-st");
    if (st) _fillShotStatusLine(st, s);
  }

  
  $("lvRetry").addEventListener("click", () => {
    if (!lv.jobId) return;
    const ownerJobId = lv.jobId;   
    withBtn($("lvRetry"), "重试中…", async () => {
      setMsg("正在重新生成失败的镜头…");
      try {
        const r = await fetch(API + `/api/jobs/${lv.jobId}/retry`, { method: "POST" });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { err("重试失败：" + (j.error || "")); return; }
        
        if (_ownerGone(ownerJobId)) { loadJobs(); return; }
        if (!_adoptJobState(j)) { loadJobs(); return; }
        saveState();
        _refreshStatusUI();
        startPoll();
        loadJobs();
        const _rn = Number(j.retry_segments || 0);
        setMsg(_rn ? `已重新加入队列：${_rn} 段（已完成段保留，不重跑）` : "已重新加入队列生成失败的镜头…");
      } catch (e) {
        err("重试请求异常：" + e.message);
      }
    });
  });

  
  $("lvResume").addEventListener("click", () => {
    if (!lv.jobId) return;
    const ownerJobId = lv.jobId;   
    withBtn($("lvResume"), "启动中…", async () => {
      setMsg("正在继续生成剩余镜头…");
      try {
        const r = await fetch(API + `/api/jobs/${lv.jobId}/retry`, { method: "POST" });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { err("继续失败：" + (j.error || "")); return; }
        
        if (_ownerGone(ownerJobId)) { loadJobs(); return; }
        if (!_adoptJobState(j)) { loadJobs(); return; }
        saveState();
        _refreshStatusUI();
        startPoll();
        loadJobs();
        const _rn2 = Number(j.retry_segments || 0);
        setMsg(_rn2 ? `已继续生成：${_rn2} 段重新排队（已完成段保留）` : "已继续生成剩余镜头…");
      } catch (e) {
        err("继续请求异常：" + e.message);
      }
    });
  });

  
  const lvVideo = $("lvVideo");
  const lvPlayIc = $("lvPlayIc");
  const lvJump = $("lvJump");
  const lvPrevCap = $("lvPrevCap");
  const lvPrevSec = $("lvPrevSec");
  const lvPrevStatus = $("lvPrevStatus");
  const lvPrevMeta = $("lvPrevMeta");

  function _statusCN(s) {
    if (!s) return "—";
    
    const _ss = s.state || {};
    const base = _ss.label || "—";
    if (s.status === "failed") {
      const r = _ss.detail || (s.error || "");
      
      return base + (r ? "：" + r : "");
    }
    return base;
  }
  function _statusKey(s) {
    if (!s) return "muted";
    if (s.status === "completed") return "completed";
    if (s.status === "failed") return "failed";
    
    const _ss = s.state || {};
    if (s.status === "processing") return _ss.phase || "processing";
    return "editing";
  }
  function _parseArr(v) {
    if (Array.isArray(v)) return v;
    if (!v) return [];
    if (typeof v === "string") {
      try { const p = JSON.parse(v); return Array.isArray(p) ? p : []; } catch (e) { return []; }
    }
    return [];
  }
  function _matChips(s) {
    
    
    
    const out = [];
    let rawImgs = _parseArr(s.images_keys);
    if (!rawImgs.length) rawImgs = _parseArr(s.images);
    const rawUrls = _parseArr(s.images_urls);
    const isCont = !!s.is_continuation;
    if (isCont) out.push({ kind: "image", idx: 1, label: "尾帧", isTail: true, url: _assetUrl("tail", rawUrls[0]) });
    const startIdx = isCont ? 2 : 1;
    const imgs = rawImgs.filter((k) => k && k !== "tail");
    if (imgs.length) {
      imgs.forEach((key, i) => {
        
        
        const friendly = _assetLabel(key);
        let lbl;
        if (friendly === key) {
          const clean = String(key || "").replace(/^lv_[a-f0-9]+_?/i, "").replace(/^lv_/i, "").replace(/\.(png|jpe?g|webp|bmp)$/i, "");
          lbl = clean.length > 10 ? clean.slice(0, 10) + "…" : (clean || "参考图");
        } else {
          lbl = friendly;
        }
        const urlIdx = isCont ? 1 + i : i;
        out.push({ kind: "image", idx: startIdx + i, label: lbl, url: _assetUrl(key, rawUrls[urlIdx]) });
      });
    } else if (!isCont) {
      out.push({ kind: "image", idx: 1, label: "无图", url: "", isMiss: true });
    }
    
    
    const aud = _parseArr(s.audio);
    const audUrls = _parseArr(s.audio_urls);
    aud.forEach((who, i) => {
      const friendly = _assetLabel(who);
      out.push({ kind: "audio", idx: i + 1, label: friendly === who ? who : friendly, url: _assetUrl(who, audUrls[i]) });
    });
    return out;
  }
  
  let lvContinuous = false;
  function _useFinal() { return lvContinuous && !!lv.finalUrl; }
  
  function _segStart(n) {
    let t = 0;
    for (const s of lv.segs) { if (s.seg_no >= n) break; t += (s.real_seconds || s.seconds || 5); }
    return t;
  }
  function _segAt(t) {
    let acc = 0;
    for (const s of lv.segs) {
      const d = (s.real_seconds || s.seconds || 5);
      if (t < acc + d) return s.seg_no;
      acc += d;
    }
    return lv.segs.length;
  }
  
  function _resetPrevInfo() {
    if (lvPrevStatus) { lvPrevStatus.textContent = "状态：—"; lvPrevStatus.className = "lv-prev-status s-muted"; }
    if (lvPrevMeta) lvPrevMeta.innerHTML = "";
    if (lvPrevSec) lvPrevSec.textContent = "本段时长：5s";
    if (lvPrevCap) lvPrevCap.textContent = "";
    if (lvPlayIc) lvPlayIc.style.display = "";
    if (lvVideo) {
      try { lvVideo.pause(); lvVideo.removeAttribute("src"); lvVideo.load(); } catch (_) {}
    }
    lvContinuous = false;
  }
  
  function _resetProgSum() {
    const box = $("lvProgSum");
    if (box) {
      box.hidden = true;
      box.classList.remove("st-processing", "st-completed", "st-failed", "st-stopped");
    }
    const _put = (id, tx, cls) => { const e = $(id); if (e) { e.textContent = tx; if (cls) e.className = cls; } };
    _put("lvPsN", "0/0");
    _put("lvPsElapsed", "—", "ps-v");
    _put("lvPsEta", "—", "ps-v");
    _put("lvPsSt", "—", "ps-v amber");
    _put("lvPsHint", "");
    const _ck = $("lvPsCostK"), _cv = $("lvPsCost");
    if (_ck) _ck.hidden = true;
    if (_cv) { _cv.hidden = true; _cv.textContent = "—"; }
    const bar = $("lvPsBar"); if (bar) bar.style.width = "0%";
    ["lvRetry", "lvResume", "lvStopBtn"].forEach((id) => {
      const b = $(id); if (b) { b.hidden = true; b.disabled = true; }
    });
  }
  
  function _resetJobContext() {
    stopPoll();
    lv.state = null;
    lv.jobStatus = null;        
    lv.queueState = null;
    lv.segs = [];
    lv.finalUrl = null;
    lv.selSeg = 1;
    lv.shotsBudgetError = "";
    lv._jobLabelSeen = null;    
    _resetPrevInfo();
    _resetProgSum();
  }
  
  function _prevShowJobState() {
    if (!lvPrevStatus) return;
    const st = lv.state || {};
    if (!st.label) return;
    lvPrevStatus.textContent = "状态：" + st.label + (st.detail ? "：" + st.detail : "");
    lvPrevStatus.className = "lv-prev-status s-" + (st.phase || (st.status === "failed" ? "failed" : "muted"));
  }
  
  function _syncSegUI(n) {
    lv.selSeg = n;
    saveState();
    const s = lv.segs.find((x) => x.seg_no === n);
    
    
    
    if (!s) {
      _resetPrevInfo();
      _prevShowJobState();
      return;
    }
    if (lvPrevSec) lvPrevSec.textContent = "本段时长：" + (s.seconds || 5) + "s";
    if (lvPrevStatus) {
      lvPrevStatus.textContent = "状态：" + _statusCN(s);
      lvPrevStatus.className = "lv-prev-status s-" + _statusKey(s);
    }
    if (lvPrevMeta) {
      const pick = (...vs) => { for (const v of vs) { const t = (v == null ? "" : String(v)).trim(); if (t) return t; } return "—"; };
      const model = pick(s.model, lv.opts && lv.opts.model);
      const aspect = pick(s.aspect_ratio, lv.opts && lv.opts.aspect_ratio);
      const res = pick(s.resolution, lv.opts && lv.opts.resolution);
      const fmt = (k, v) => '<span class="m"><b>' + k + '：</b>' + _esc(v) + '</span>';
      let _extra = [];
      try { _extra = _h3JobMetaRows(s).concat(_h3SegMetaRows(s)); } catch (e) { _extra = []; }
      lvPrevMeta.innerHTML = fmt("模型", model) + fmt("画幅", aspect) + fmt("分辨率", res) + _extra.map((r) => fmt(r[0], r[1])).join("");
    }
    if (lvPrevCap) lvPrevCap.textContent = "";
    
    document.querySelectorAll(".lv-shot[data-seg-no]").forEach((c) =>
      c.classList.toggle("sel", +c.getAttribute("data-seg-no") === n)
    );
  }
  
  function selectSeg(n, autoplay) {
    if (!lv.segs.length) return;
    n = Math.max(1, Math.min(n, lv.segs.length));
    if (autoplay === undefined) autoplay = true;
    _syncSegUI(n);
    _playSegSrc(n, autoplay);
  }
  
  function _cardHistOf(segNo) {
    const seg = (lv.segs || []).find((x) => x.seg_no === segNo);
    const all = (seg && Array.isArray(seg.prompt_history)) ? seg.prompt_history : [];
    return all
      .filter((h) => h && Number(h.ver) > 0)          
      .sort((a, b) => Number(b.ver) - Number(a.ver)); 
  }

  
  function _verOf(segNo, vi) {
    const hist = _cardHistOf(segNo);
    return vi > 0 ? (hist[vi - 1] || null) : null;
  }
  
  function _renderVerSwitch(segNo, vi) {
    lv.segVer = lv.segVer || {};
    lv.segVer[segNo] = vi;
    const _st = lvShots ? lvShots.scrollTop : 0;
    renderShots();
    if (lvShots) lvShots.scrollTop = _st;
    const ver = _verOf(segNo, vi);
    _syncSegUI(segNo);
    _playSegSrc(segNo, false);
    if (ver) setMsg(`第 ${segNo} 镜 · 历史版 v${ver.ver}（只读，右栏是归档画面）`);
    else setMsg(`第 ${segNo} 镜 · 已回到当前版`);
  }
  function _playSegSrc(n, autoplay) {
    
    
    const _vi = parseInt((lv.segVer || {})[n], 10) || 0;
    const _ver = _vi > 0 ? _verOf(n, _vi) : null;
    if (_ver) {
      lvVideo.src = API + `/api/jobs/${lv.jobId}/segment/${n}/v/${_ver.ver}.mp4?t=${Date.now()}`;
      lvVideo.load();
      if (autoplay) { lvPlayIc.style.display = "none"; lvVideo.play().catch(() => { lvPlayIc.style.display = ""; }); }
      else lvPlayIc.style.display = "";
      return;
    }
    if (_useFinal()) {
      const want = API + lv.finalUrl + "?t=" + Date.now();
      const changingSrc = !lvVideo.src || !lvVideo.src.includes("/final.mp4") || !lvVideo.src.includes(lv.jobId);
      if (changingSrc) { lvVideo.src = want; lvVideo.load(); }
      const seekTo = _segStart(n) + 0.01;
      const go = () => {
        try { lvVideo.currentTime = seekTo; } catch (_) {}
        if (autoplay) { lvPlayIc.style.display = "none"; lvVideo.play().catch(() => { lvPlayIc.style.display = ""; }); }
        else lvPlayIc.style.display = "";
      };
      if (changingSrc) lvVideo.addEventListener("loadedmetadata", go, { once: true });
      else go();
    } else {
      lvVideo.src = API + `/api/jobs/${lv.jobId}/segment/${n}.mp4?t=${Date.now()}`;
      lvVideo.load();
      if (autoplay) { lvPlayIc.style.display = "none"; lvVideo.play().catch(() => { lvPlayIc.style.display = ""; }); }
      else lvPlayIc.style.display = "";
    }
  }
  
  function buildStrip() {
    if (lv.segs.length) _syncSegUI(lv.selSeg || 1);
    else _resetPrevInfo();   
  }
  
  const lvPlayAll = $("lvPlayAll");
  if (lvPlayAll) lvPlayAll.addEventListener("click", () => {
    if (!lv.finalUrl) { setMsg("成片尚未生成（全段完成后自动拼接），当前只能逐段预览", "warn"); return; }
    lvContinuous = true;
    lvVideo.src = API + lv.finalUrl + "?t=" + Date.now();
    lvVideo.load();
    lvPlayIc.style.display = "none";
    lvVideo.play().catch(() => { lvPlayIc.style.display = ""; });
    setMsg("正在播放全片");
  });

  
  lvVideo.addEventListener("timeupdate", () => {
    if (_useFinal() && lv.segs.length) {
      const cur = _segAt(lvVideo.currentTime);
      if (cur !== lv.selSeg) { _syncSegUI(cur); }
    }
  });
  lvVideo.addEventListener("play", () => { lvPlayIc.style.display = "none"; });
  lvVideo.addEventListener("pause", () => { if (!lvVideo.ended) lvPlayIc.style.display = ""; });
  lvVideo.addEventListener("ended", () => {
    
    lvPlayIc.style.display = "";
    if (lvPrevStatus && lv.selSeg >= lv.segs.length) { lvPrevStatus.textContent = "状态：播放完毕"; lvPrevStatus.className = "lv-prev-status s-completed"; }
  });
  lvJump.addEventListener("click", () => selectSeg(lv.selSeg || 1, true));
