  
  let LV_SEC = { min: 4, max: 12 };
  (async () => {
    try {
      const d = await (await fetch("/api/config")).json();
      if (Array.isArray(d.lvSecBounds)) { LV_SEC.min = d.lvSecBounds[0]; LV_SEC.max = d.lvSecBounds[1]; }
    } catch (_e) {}
  })();
  function lvSecBounds() {
    const m = (lv.opts && lv.opts.model) || "";
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

  
  
  
  function _normStep(n) { return n === 3 ? 2 : n; }
  function canGoStep(n) {
    n = _normStep(n);
    if (n <= 2) return true;
    if (n === 4) return lv.jobStatus === "completed" || (lv.segs || []).some((s) => s.status === "completed");   
    return false;
  }
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
    
    
    if (n === 4) buildStrip();
    
    
    
    if (n === 2) {
      _updateProgSum({ status: lv.jobStatus });
      if (lv.segs.length) _updateShotStatusLines();
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
        const tip = n === 4 ? "该任务尚未生成成片（需先点「开始生成」完成）" : "请先完成「素材上传」与「智能分镜」";
        err(tip);
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
      fd.append("job_id", lv.jobId || "");
      const r = await fetch(API + "/api/assets/batch_upload", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) { err(j.error || "上传失败"); return; }
      
      const prev = {};
      lv.assets.forEach((a) => (prev[a.name] = a));
      j.uploaded.forEach((u) => {
        const ex = prev[u.name];
        lv.assets.push(ex ? { ...u, label: ex.label, kind: ex.kind, owner: ex.owner, posture: ex.posture, job_id: lv.jobId } : { ...u, posture: "", job_id: lv.jobId, kind: u.type === "audio" ? "voice" : "" });
      });
      renderAssets();
      setMsg(`已上传 ${j.uploaded.length} 个素材`);
      
      
      
      
      await saveDraftNow().then(loadJobs);
    } catch (e) { err("上传异常：" + e.message); }
  }

  
  let currentLibraryItems = [];
  
  
  
  
  
  function _libItem(a) {
    if (!a) return null;
    return (currentLibraryItems || []).find((x) => x.name === a.name) || null;
  }
  function _isInLibrary(a) { return !!_libItem(a); }
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
    
    let labelTip, labelTitle;
    if (isAudio) {
      labelTip = "声线靠下方『归属角色』绑定：选对角色即可自动配声，原始脚本无需标注声线；本标签名仅作显示";
      labelTitle = "声线绑定靠素材卡里的『归属角色』下拉（选到对应角色，如橘猫）——系统自动把这条声线配给该角色，原始脚本无需标注声线。本标签名仅作显示，不影响绑定";
    } else if (a.kind === "character") {
      labelTip = "角色名须与脚本里写的称呼一致（如脚本写『橘猫』就填『橘猫』），否则图加文无法绑定";
      labelTitle = "角色名须与脚本里写的称呼完全一致（如脚本写『橘猫』就填『橘猫』），否则图加文无法把这图绑进分镜";
    } else if (a.kind === "scene") {
      labelTip = "场景名须与脚本里写的场景一致（如脚本写『客厅』就填『客厅』），否则图加文无法绑定";
      labelTitle = "场景名须与脚本里写的场景完全一致（如脚本写『客厅』就填『客厅』），否则图加文无法把这图绑进分镜";
    } else if (a.kind === "prop") {
      labelTip = "道具名须与脚本里写的道具一致（如脚本写『毛线球』就填『毛线球』），否则图加文无法绑定";
      labelTitle = "道具名须与脚本里写的道具完全一致（如脚本写『毛线球』就填『毛线球』），否则图加文无法把这图绑进分镜";
    } else {
      labelTip = "标签须与脚本里的对应称呼一致（先在上方选类型：角色 / 场景 / 道具）";
      labelTitle = "标签名须与脚本中写的对应称呼一致（先在上方选类型：角色 / 场景 / 道具），否则图加文无法绑定";
    }
    return { isAudio, isChar, typeField, ownerField, voiceField, postureField, labelTip, labelTitle };
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
    box.innerHTML = `<span class="lbl">筛选</span>` + _FILTER_DEFS
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
      card.className = "lv-ac";
      const isInLib = _isInLibrary(a);   
      const badge = `<span class="lv-badges">` +
        (isInLib ? `<span class="lv-badge shared" title="在资产库中">资产库</span>` : "") +
        `<span class="lv-badge" title="已登记进本任务">本任务</span>` +
        `</span>`;
      const th = a.type === "image"
        ? `<div class="lv-th"><img src="${_esc(_thumb(a.url))}" alt="" loading="lazy" decoding="async"></div>`
        : `<div class="lv-th"><button type="button" class="lv-play" data-url="${a.url}" title="试听这条声线"><span class="ic ic-resume" aria-hidden="true"></span>试听</button></div>`;
      const f = _assetCardInner(a);
      card.innerHTML = `
        ${badge}
        <input type="checkbox" class="lv-i-sel" data-name="${a.name}"${_selNames.has(a.name) ? " checked" : ""}>
        ${th}
        <input class="lv-i-label" title="${f.labelTitle}" placeholder="${f.isAudio ? "标签＝声线名（如 橘猫声线）" : (a.kind === "scene" ? "标签＝场景名（如 客厅）" : a.kind === "prop" ? "标签＝道具名（如 毛线球）" : "标签＝角色名（如 橘猫）")}" value="${esc(a.label)}">
        <small class="lv-label-tip">${f.labelTip}</small>
        ${f.typeField}
        ${f.ownerField}
        ${f.voiceField}
        ${f.postureField}
        ${_appearanceBlockHtml(a)}
        <button class="lv-del" type="button" data-name="${a.name}" title="${isInLib ? "当前任务不再用它，素材还在资产库" : "文件会一起删除"}">${isInLib ? "移除" : "删除"}</button>`;
      card.querySelector(".lv-i-label").addEventListener("input", (e) => { a.label = e.target.value; saveDraft(); });
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
    
    let mineCnt = 0, sharedCnt = 0;
    picked.forEach((a) => {
      if (_isInLibrary(a)) sharedCnt++; else mineCnt++;
    });
    const promoteBtn = $("lvPromote");
    if (promoteBtn) promoteBtn.disabled = mineCnt === 0;
    
    
    $("lvBulkHint").textContent = sharedCnt ? `其中 ${sharedCnt} 个为资产库素材（仅移除使用，不影响资产库）` : "";
  }

  async function deleteSelected() {
    
    const names = lv.assets.filter((a) => _selNames.has(a.name)).map((a) => a.name);
    if (!names.length) return;
    
    
    
    let mineNames = [], sharedNames = [];
    names.forEach((n) => {
      const a = lv.assets.find((x) => x.name === n);
      if (a && _isInLibrary(a)) sharedNames.push(n); else mineNames.push(n);
    });
    let msg = "确定";
    if (mineNames.length) msg += `删除 ${mineNames.length} 个本任务素材（文件一并删除）`;
    if (sharedNames.length) msg += (mineNames.length ? "、移除 " : "删除 ") + `${sharedNames.length} 个库素材的使用`;
    msg += "？";
    if (!(await lvConfirm({ title: "删除素材", message: msg, danger: mineNames.length > 0, okText: mineNames.length ? "删除" : "移除" }))) return;
    setMsg("删除中…");
    try {
      let delCnt = 0, failCnt = 0, heldMsg = "";
      if (mineNames.length) {
        const r = await fetch(API + "/api/assets/delete_batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ names: mineNames, from_job: lv.jobId }),
        });
        const j = await r.json();
        if (!r.ok) { err(j.error || "批量删除失败"); return; }
        delCnt = j.count || 0;
        
        
        heldMsg = summarizeStillReferenced(j.still_referenced);
        failCnt = (j.failed && j.failed.length) || 0;
      }
      const gone = new Set([...mineNames, ...sharedNames]);
      lv.assets = lv.assets.filter((a) => !gone.has(a.name));
      renderAssets();   
      if (heldMsg) err(heldMsg.trim());
      else setMsg(`已删除 ${delCnt} 个素材` + (sharedNames.length ? `，移除使用 ${sharedNames.length} 个` : "") + (failCnt ? `，${failCnt} 个失败` : ""));
    } catch (e) { err("批量删除异常：" + e.message); }
  }

  $("lvBulkDel").addEventListener("click", deleteSelected);
  $("lvSelAll").addEventListener("change", (e) => {
    
    lvAssets.querySelectorAll(".lv-i-sel").forEach((c) => {
      c.checked = e.target.checked;
      const n = c.getAttribute("data-name");
      if (e.target.checked) _selNames.add(n); else _selNames.delete(n);
    });
    syncSel();
  });

  async function deleteAsset(name) {
    const a = lv.assets.find((x) => x.name === name);
    
    
    
    if (a && _isInLibrary(a)) {
      if (!(await lvConfirm({ title: "移除引用", message: "确定移除素材「" + name + "」的使用？它本身还在资产库中。", okText: "移除" }))) return;
      lv.assets = lv.assets.filter((x) => x.name !== name);
      renderAssets();
      setMsg("已从当前任务移除（资产库不受影响）");
      return;
    }
    if (!(await lvConfirm({ title: "删除素材", message: "确定删除素材「" + name + "」？文件会一并删除。", danger: true, okText: "删除" }))) return;
    setMsg("删除中…");
    try {
      
      
      const r = await fetch(API + "/api/assets/delete/" + encodeURIComponent(name), {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_job: lv.jobId }),
      });
      const j = await r.json();
      if (!r.ok) { err(j.error || "删除失败"); return; }
      lv.assets = lv.assets.filter((a) => a.name !== name);
      renderAssets();
      
      const held = summarizeStillReferenced({ [name]: j.still_referenced });
      if (held) err(held.trim()); else setMsg("已删除 " + name);
    } catch (e) { err("删除异常：" + e.message); }
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

  $("lvPromote").addEventListener("click", async () => {
    const names = [...lvAssets.querySelectorAll(".lv-i-sel:checked")].map((c) => c.getAttribute("data-name"));
    const mine = names.filter((n) => { const a = lv.assets.find((x) => x.name === n); return a && !_isInLibrary(a); });
    if (!mine.length) { err("请先勾选本任务的私有素材（资产库素材无需提升）"); return; }
    if (!(await lvConfirm({ title: "加入资产库", message: `确定把选中的 ${mine.length} 个本任务素材加入资产库？加入后所有任务都可用；之后在各任务里只能"移除使用"，真删需到「资产库」操作（将影响所有任务）。` }))) return;
    setMsg("加入资产库中…");
    try {
      
      const items = mine.map((n) => {
        const a = lv.assets.find((x) => x.name === n) || {};
        return {
          name: n, label: a.label || "", kind: a.kind || "", owner: a.owner || "", posture: a.posture || "",
          appearance: a.appearance == null ? null : a.appearance,
        };
      });
      const r = await fetch(API + "/api/assets/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ names: mine, job_id: lv.jobId, items: items }),
      });
      const j = await r.json();
      if (!r.ok) { err(j.error || "提升失败"); return; }
      lv.assets.forEach((a) => { if (mine.includes(a.name)) a.job_id = null; });
      renderAssets();
      await loadLibrary().catch(() => {});   
      renderAssets();
      setMsg(`已将 ${j.count} 个素材加入资产库`);
    } catch (e) { err("加入资产库异常：" + e.message); }
  });

  $("lvTo2").addEventListener("click", () => goStep(2));
  $("lvBack1").addEventListener("click", () => goStep(1));
  $("lvNewTask").addEventListener("click", newTask);
  
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
  
  
  const SEG_TITLES = { lvSegLlm: "分镜引擎", lvSegModel: "视频模型" };
  
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
    _renderArResAspects();
    _renderArResSizes();
  }
  
  
  
  function lvApplyLlmModels(prov) {
    if (!prov) return;
    const sel = document.getElementById("lvLlmModel");
    if (!sel) return;
    const models = (Array.isArray(prov.storyboardLlmModels) && prov.storyboardLlmModels.length)
      ? prov.storyboardLlmModels
      : (Array.isArray(prov.llmModels) ? prov.llmModels : []);
    if (!models.length) return;
    
    const keep = (lv.opts && lv.opts.llmModel && models.includes(lv.opts.llmModel))
      ? lv.opts.llmModel
      : (models.includes(sel.value) ? sel.value : ((lv.opts && lv.opts.llmModel) || models[0]));
    sel.innerHTML = models.map((m) => `<option value="${m}">${m}</option>`).join("");
    if (models.includes(keep)) sel.value = keep;
    _segRefresh("lvSegLlm");
  }
  window.lvApplyLlmModels = lvApplyLlmModels;
  
  async function lvSyncLlmModelsFromConfig() {
    try {
      const r = await fetch("/api/config");
      if (!r.ok) return;
      const d = await r.json();
      lvApplyLlmModels(d.provider || {});
    } catch (e) {}
  }
  function _initOptsSegs() {
    lvApplyLlmModels(window.__lvProvider || null);  
    lvSyncLlmModelsFromConfig();                     
    ["lvSegLlm", "lvSegModel"].forEach((id) => _segRefresh(id));
    _initArRes();
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
    lvOptModel.value = lv.opts.model || "agnes-video-2.5-flash";
    if (![...lvOptModel.options].some(o => o.value === lvOptModel.value)) {
      
      lvOptModel.value = lvOptModel.options[0] ? lvOptModel.options[0].value : "agnes-video-2.5-flash";
      lv.opts.model = lvOptModel.value;
    }
    
    const _llmSel = document.getElementById("lvLlmModel");
    if (_llmSel) {
      const _lm = lv.opts.llmModel || (_llmSel.options[0] ? _llmSel.options[0].value : "agnes-2.5-flash");
      if ([..._llmSel.options].some(o => o.value === _lm)) _llmSel.value = _lm;
      else if (_llmSel.options[0]) { _llmSel.value = _llmSel.options[0].value; lv.opts.llmModel = _llmSel.value; }
      _segRefresh("lvSegLlm");   
    }
    lvOptAspect.value = lv.opts.aspect_ratio || "16:9";
    _syncResOptions(lv.opts.model);   
    _segRefresh("lvSegModel");
    _renderArResAspects();            
    _syncArResTx();
  }
  function _readOptsFromUI() {
    const _lm = (function(){ const s=document.getElementById("lvLlmModel"); return s?s.value:null; })();
    lv.opts = {
      llmModel: _lm || (lv.opts && lv.opts.llmModel) || "agnes-2.5-flash",
      model: lvOptModel.value,
      aspect_ratio: lvOptAspect.value,
      resolution: lvOptRes.value,
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
    _syncSecStepper();
  }
  [lvOptModel, lvOptAspect, lvOptRes].forEach((el) => {
    el.addEventListener("change", async () => {
      _readOptsFromUI();
      if (el === lvOptModel) {
        _syncResOptions(lv.opts.model);  
        await _checkModelSwitch();       
        _syncSecStepper();               
      }
      saveState(); saveDraft();
    });
  });
  
  (function () {
    const _lm = document.getElementById("lvLlmModel");
    if (_lm) _lm.addEventListener("change", () => { _readOptsFromUI(); saveState(); saveDraft(); });
  })();
  
  
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _initOptsSegs);
  else _initOptsSegs();

  $("lvOptimize").addEventListener("click", () => {
    withBtn($("lvOptimize"), "分镜中…", async () => {
      const script = lvScript.value.trim();
      if (!script) { err("请先填写脚本"); return; }
      
      
      
      
      
      
      const _isReeditEntry = !!(lv.jobId && lv.jobStatus && lv.jobStatus !== "draft");
      if (_isReeditEntry) {
        if (!(await lvConfirm({
          title: "重新编排",
          message: "将解锁分镜进入重新编辑（不重新生成镜头）：\n· 分镜恢复可编辑（改提示词/秒数/绑定/删加镜头）\n· 已生成成片保留供对照\n· 需要重新生成镜头时，解锁后再点一次「智能分镜」\n· 改完点「开始生成」才会重新生成（旧视频会自动保留）\n\n进入重新编辑？",
          okText: "解锁编辑",
        }))) return;
        try {
          const rr = await fetch(API + `/api/jobs/${lv.jobId}/reedit`, { method: "POST" });
          const rj = await rr.json().catch(() => ({}));
          if (!rr.ok) { err("进入重编失败：" + (rj.error || "")); return; }
          lv.jobStatus = "draft";
          _autoJumpOK = false;
          renderShots();          
          _syncStartBtn();        
          _updateProgSum({ status: "draft" });
          saveState();
          setMsg("已进入重新编辑：分镜已解锁，可编辑现有分镜；需要重新生成镜头再点「智能分镜」");
        } catch (e) { err("重编请求异常：" + e.message); return; }
        return;   
      }
      
      
      setMsg("AI 正在分镜…（通常需要 20 秒到 1 分钟，取决于接口负载，请稍候）");
      
      
      const _tipEvery = 7;
      const _t0 = Date.now();
      let _tipI = 0;
      const _tipTimer = setInterval(() => {
        _tipI++;
        const sec = Math.round((Date.now() - _t0) / 1000);
        setMsg(`AI 正在分镜…（已等待 ${sec} 秒），请耐心等候`);
      }, _tipEvery * 1000);
      let r, j;
      try {
        r = await fetch(API + "/api/optimizer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ script, job_id: lv.jobId || null, llm_model: document.getElementById("lvLlmModel").value, video_model: (lv.opts && lv.opts.model) || "" }),
        });
        j = await r.json();
      } catch (e) {
        clearInterval(_tipTimer);
        err("分镜请求异常：网络挂了或服务端崩溃 — " + e.message);
        return;
      }
      clearInterval(_tipTimer);
      if (!r.ok) {
        err("分镜失败：" + (j.error || "") + (j.detail ? ("\n" + j.detail) : ""));
        return;
      }
      lv.shots = j.shots || [];
      if (j.job_id) lv.jobId = j.job_id;   
      
      lv.storyboardBasis = { model: j.video_model || (lv.opts && lv.opts.model) || "", secMax: (j.sec_bounds && j.sec_bounds[1]) || null };
      renderShots();
      lvStep2Act.hidden = lv.shots.length === 0;
      _syncStartBtn();   
      
      const _usedModel = j.llm_model || document.getElementById("lvLlmModel").value;
      const _elapsed = Math.round((Date.now() - _t0) / 1000);
      const _basis = lv.storyboardBasis;
      const _basisTx = _basis.secMax ? ` · 按 ${_basis.model}（单段 ≤${_basis.secMax} 秒）拆分` : "";
      setMsg(`已生成 ${lv.shots.length} 个镜头${_basisTx} · 分镜引擎 ${_usedModel} · 用时约 ${_elapsed}s（点「开始生成」生成视频）`);
      
      if (lv.shots.length) lvShots.scrollIntoView({ behavior: "smooth", block: "start" });
      saveState();
      
      try {
        if (lv.jobId && lv.shots.length) {
          const ar = await fetch(API + `/api/jobs/${lv.jobId}/shots/archive`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shots: lv.shots, source: lv.curShotVer >= 0 ? "重新分镜" : "智能分镜" }),
          });
          const arj = await ar.json().catch(() => ({}));
          if (ar.ok && typeof arj.idx === "number") {
            lv.curShotVer = arj.idx;             
            const g = await fetch(API + `/api/jobs/${lv.jobId}`);
            const gj = await g.json().catch(() => ({}));
            if (g.ok && Array.isArray(gj.shots_history)) lv.shotsHist = gj.shots_history;
          }
        }
      } catch (_) {  }
      $("lvShotsHist").hidden = !lv.shotsHist.length;
      saveDraftNow().then(loadJobs);   
    });
  });

  
  const _unlockBtn = $("lvUnlockEdit");
  if (_unlockBtn) _unlockBtn.addEventListener("click", () => _enterReedit());

  
  function openShotsHistPanel() {
    if (!lv.jobId) return;
    const _existing = document.querySelector(".lv-pk.shots-hist");
    if (_existing) _existing.remove();   
    (async () => {
      
      let _histMeta = [];
      try {
        const r = await fetch(API + `/api/jobs/${lv.jobId}`);
        const j = await r.json().catch(() => ({}));
        if (r.ok && Array.isArray(j.shots_history)) { _histMeta = j.shots_history; lv.shotsHist = _histMeta; }
        else _histMeta = lv.shotsHist || [];
      } catch (e) { _histMeta = lv.shotsHist || []; }
      if (!_histMeta.length) { setMsg("暂无分镜历史（每次智能分镜/重新分镜会留下一份）"); return; }
      const _total = _histMeta.length;
      const _cur = lv.curShotVer >= 0 ? lv.curShotVer : _total - 1;   
      const _currentK = _cur + 1;
      const items = _histMeta.slice().reverse();   
      const rows = items.map((v, ri) => {
        const k = items.length - ri;                  
        const _isCur = (k === _currentK);
        const t = v.ts ? new Date(v.ts * 1000).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
        return `<div class="lv-pk-it" data-i="${v.idx}" data-k="${k}" style="justify-content:space-between">
          <span class="nm">第 ${k} 版分镜<small>${t}${v.source ? " · " + _esc(v.source) : ""} · ${v.shot_count} 镜头</small></span>
          <span style="display:flex;gap:6px;flex:none">
            ${_isCur ? '<span class="mini" style="opacity:.6"><span class="ic ic-dot" aria-hidden="true"></span>当前</span>'
                     : '<button class="mini sh-restore">切换</button>'}
            <button class="mini sh-del" style="color:var(--err)">删除</button>
          </span>
        </div>`;
      }).join("");
      const _curTag = _currentK === _total ? "（最新分镜稿）" : "（来自历史，可随时切回最新）";
      const currentBar = `<div class="lv-pk-cur" style="padding:8px 14px;background:var(--ok-soft);color:var(--ok);border-bottom:1px solid var(--line);font-size:12.5px;line-height:1.5">
        <strong>当前在用 = v${_currentK}</strong>${_curTag} · 历史共 ${_total} 份，切换只移动指针、不新增版本
      </div>`;
      const wrap = document.createElement("div");
      wrap.className = "lv-pk shots-hist";
      wrap.innerHTML = `
        <div class="lv-pk-mask"></div>
        <div class="lv-pk-box" style="max-width:520px">
          <div class="lv-pk-t">分镜历史</div>
          ${currentBar}
          <div class="lv-pk-list">${rows || '<div class="lv-pk-empty">暂无归档</div>'}</div>
          <div style="padding:8px 14px;border-top:1px solid var(--line);display:flex;justify-content:flex-end">
            <button class="mini sh-close">关闭</button>
          </div>
        </div>`;
      const done = () => wrap.remove();
      wrap.querySelector(".lv-pk-mask").addEventListener("click", done);
      wrap.querySelector(".sh-close").addEventListener("click", done);
      wrap.addEventListener("click", async (e) => {
        const it = e.target.closest(".lv-pk-it");
        if (!it) return;
        const idx = parseInt(it.dataset.i, 10);
        const k = parseInt(it.dataset.k, 10);
        if (e.target.closest(".sh-del")) {
          e.stopImmediatePropagation();
          if (!(await lvConfirm({ title: "删除分镜历史", message: `确定删除第 ${k} 版分镜？相关的视频可在资产库中查看。`, danger: true, okText: "删除" }))) return;
          try {
            const r = await fetch(API + `/api/jobs/${lv.jobId}/shots_history/${idx}`, { method: "DELETE" });
            if (!r.ok) { const j = await r.json().catch(() => ({})); err("删除失败：" + (j.error || "")); return; }
            
            const g = await fetch(API + `/api/jobs/${lv.jobId}`);
            const gj = await g.json().catch(() => ({}));
            if (g.ok && Array.isArray(gj.shots_history)) lv.shotsHist = gj.shots_history;
            if (idx === lv.curShotVer || lv.curShotVer >= lv.shotsHist.length) lv.curShotVer = lv.shotsHist.length - 1;
            try { await fetch(API + `/api/jobs/${lv.jobId}/shots_history/current`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idx: lv.curShotVer }) }); } catch (_) {}
            $("lvShotsHist").hidden = lv.shotsHist.length === 0;
            openShotsHistPanel();   
            setMsg(`已删除第 ${k} 版分镜历史`);
          } catch (ex) { err("删除异常：" + ex.message); }
          return;
        }
        if (e.target.closest(".sh-restore")) {
          e.stopImmediatePropagation();
          if (!(await lvConfirm({
            title: "切换到分镜历史",
            message: `将把编辑界面切换到第 ${k} 版分镜查看/继续编辑：\n· 不会新增版本、历史份数不变\n· 当前编辑结果会先存回它所属版本\n· 切换后可继续编辑或重新生成镜头\n\n确认切换？`,
            okText: "切换查看",
          }))) return;
          try {
            
            const _curNow = lv.curShotVer >= 0 ? lv.curShotVer : (lv.shotsHist.length - 1);
            if (_curNow >= 0 && lv.shots.length) {
              try {
                await fetch(API + `/api/jobs/${lv.jobId}/shots_history/${_curNow}`, {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ shots: lv.shots }),
                });
              } catch (_) {}
            }
            
            const r = await fetch(API + `/api/jobs/${lv.jobId}/shots_history/${idx}`);
            const j = await r.json();
            if (!r.ok) { err("读取历史失败：" + (j.error || "")); return; }
            const old = (j.version || {}).shots || [];
            if (!old.length) { err("历史版本数据为空"); return; }
            lv.shots = old;
            lv.curShotVer = idx;       
            try { await fetch(API + `/api/jobs/${lv.jobId}/shots_history/current`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idx: idx }) }); } catch (_) {}
            renderShots();
            lvStep2Act.hidden = lv.shots.length === 0;
            _syncStartBtn();
            saveDraft();
            done();
            setMsg(`已切换到第 ${k} 版分镜（历史共 ${lv.shotsHist.length} 份，可随时切回）`);
          } catch (ex) { err("切换异常：" + ex.message); }
          return;
        }
      });
      document.body.appendChild(wrap);
    })();
  }
  $("lvShotsHist").addEventListener("click", openShotsHistPanel);

  
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
  function _registryImgs() {
    return (lv.assets || []).filter((a) => a.type === "image").map((a) => ({ kind: "image", name: a.name, url: a.url, label: a.label || a.name }));
  }
  function _registryAuds() {
    return (lv.assets || []).filter((a) => a.type === "audio").map((a) => ({ kind: "audio", name: a.name, url: a.url, label: a.label || a.name }));
  }
  function _matsForShot(s) {
    const imgs = (s.images || []).map((name, i) => ({ kind: "image", idx: i + 1, name, url: _assetUrl(name, (s.images_urls || [])[i]), label: name }));
    const auds = (s.audio || []).map((who, i) => ({ kind: "audio", idx: i + 1, name: who, url: _assetUrl(who, (s.audio_urls || [])[i]), label: who }));
    return { imgs, auds };
  }
  function _matsForSeg(seg) {
    if (!seg) return { imgs: [], auds: [] };
    const keys = _parseArr(seg.images_keys).length ? _parseArr(seg.images_keys) : _parseArr(seg.images);
    const urls = _parseArr(seg.images_urls);
    const imgs = [];
    let seq = 0;
    keys.forEach((k, i) => { seq++; imgs.push({ kind: "image", idx: seq, name: k, url: _assetUrl(k, urls[i]), label: k }); });
    const auds = _parseArr(seg.audio).map((who, i) => ({ kind: "audio", idx: i + 1, name: who, url: _assetUrl(who, _parseArr(seg.audio_urls)[i]), label: who }));
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
    editor.addEventListener("input", () => {
      _mentionCtxHost = host;
      if (host.onCommit) host.onCommit(_promptToText(editor));
      _detectMention(editor);
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
    };
  }

  function renderShots() {
    lvShots.innerHTML = "";
    
    
    const _ro = !!(lv.jobId && lv.jobStatus && lv.jobStatus !== "draft");
    const roHint = $("lvShotsRoHint");
    if (roHint) roHint.hidden = !_ro;
    let _lockTipAt = 0;   
    lv.shots.forEach((s, idx) => {
      
      
      if (idx === 0 && s.is_continuation) {
        s.is_continuation = false;
        const imgs0 = (s.images || []);
        if (imgs0[0] === "tail") s.images = imgs0.filter((x) => x !== "tail");
      }
      const div = document.createElement("div");
      div.className = "lv-shot" + (_ro ? " ro" : "");
      div.dataset.idx = idx;
      div.dataset.segNo = s.shot_no;   
      
      
      if (_ro) {
        div.addEventListener("click", (e) => {
          if (e.target.closest(".lv-shot-st")) return;   
          if (!e.target.closest("input, button, [contenteditable], .lv-chip, .lv-add-chip, .lv-mat-add, .lv-thumb-x, .lv-tile-x")) return;
          const now = Date.now();
          if (now - _lockTipAt < 2000) return;
          _lockTipAt = now;
          setMsg("分镜已锁定（生成后只读）——点上方「解锁编辑」进入重新编辑，或到「分镜与生成」屏逐分镜重新生成", "lock");
        });
      }

      
      const head = document.createElement("div");
      head.className = "lv-shot-h";
      const num = document.createElement("span");
      num.textContent = `镜头 ${s.shot_no} · `;
      head.appendChild(num);
      
      if (_ro) {
        const lock = document.createElement("span");
        lock.className = "lv-lock-badge";
        lock.innerHTML = '<span class="ic ic-lock" aria-hidden="true"></span>已锁定';
        lock.title = "生成后分镜为只读存档；点上方「解锁编辑」进入重新编排";
        head.appendChild(lock);
      }
      
      const badge = document.createElement("span");
      badge.className = s.is_continuation ? "lv-badge" : "lv-badge first";
      badge.textContent = s.is_continuation ? "续接段" : "首段";
      head.appendChild(badge);
      
      const secLabel = document.createElement("span");
      secLabel.className = "lv-shot-seclbl";
      secLabel.textContent = "时长";
      head.appendChild(secLabel);
      const secInput = document.createElement("input");
      secInput.type = "number";
      const _sb = lvSecBounds();   
      secInput.min = String(_sb.min); secInput.max = String(_sb.max);
      secInput.step = "1";
      secInput.value = String(Math.max(_sb.min, Math.min(_sb.max, s.estimated_seconds || 5)));
      secInput.title = `本镜时长（秒，${_sb.min}-${_sb.max}，接口单段上限）`;
      secInput.disabled = _ro;
      secInput.addEventListener("change", () => {
        if (_ro) return;
        
        
        
        const _now = lvSecBounds();
        const v = Math.max(_now.min, Math.min(_now.max, parseInt(secInput.value, 10) || 5));
        secInput.value = String(v);
        s.estimated_seconds = v;
        saveDraft();
      });
      head.appendChild(secInput);
      const secUnit = document.createElement("span");
      secUnit.textContent = "s";
      head.appendChild(secUnit);
      
      
      if (idx > 0) {
        const contLabel = document.createElement("label");
        contLabel.className = "lv-shot-contlbl";
        const contBox = document.createElement("input");
        contBox.type = "checkbox";
        contBox.checked = !!s.is_continuation;
        contBox.title = "勾选：本镜从上一段尾帧续接（图片1=tail）";
        contBox.disabled = _ro;
        contBox.addEventListener("change", () => {
          if (_ro) { contBox.checked = !!s.is_continuation; return; }
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
      
      const delBtn = document.createElement("button");
      delBtn.className = "lv-shot-del";
      delBtn.textContent = "删除此镜";
      delBtn.title = "从分镜移除（未开始生成前）";
      delBtn.disabled = _ro;
      delBtn.addEventListener("click", async () => {
        if (_ro) return;
        if (lv.jobStatus && lv.jobStatus !== "draft") { err("已开始生成的任务不可删除镜头"); return; }
        
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
      head.appendChild(delBtn);
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
        ? `<div class="lv-warn">本镜头未匹配任何素材图，prompt 中的角色是「猜的」，请补传或人工校对。</div>` : "";

      const warnBox = document.createElement("div");
      warnBox.innerHTML = warn + unmatchedNote + noImgChip + (reviewChips ? `<div class="lv-chips">${reviewChips}</div>` : "");
      div.appendChild(warnBox);

      
      
      
      const matTiles = document.createElement("div");
      matTiles.className = "lv-mat-tiles";

      
      const addTile = document.createElement("div");
      addTile.className = "lv-mat-add";
      addTile.innerHTML = '<span class="ic ic-plus" aria-hidden="true"></span>';
      addTile.title = "从本任务素材里选一个加入本镜（图片=参考图，角色图=角色）";
      addTile.addEventListener("click", () => { if (_ro) return; _pickAnyForShot(s); });
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
            if (_ro) return;
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
          tile.title = _esc(c.label || key);
          tile.innerHTML = '<img class="lv-thumb" src="' + _esc(_thumb(url || "", 128)) + '" alt="">'
            + '<span class="lv-thumb-idx">图' + _imgSeq + '</span>'
            + '<span class="lv-combo-lbl">' + _esc(c.label || "?")
            + (unmatched ? ' <span class="ic ic-warn" aria-hidden="true"></span>' : "") + '</span>'
            + '<button class="lv-thumb-x" title="移除该角色及其参考图" data-act="rm-combo" data-i="' + i + '" data-ci="' + ci + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
          matTiles.appendChild(tile);
          tile.querySelector("button").addEventListener("click", () => {
            if (_ro) return;
            
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
          tile.title = _esc(key);
          tile.innerHTML = '<img class="lv-thumb" src="' + _esc(_thumb(url || "", 128)) + '" alt="">'
            + '<span class="lv-thumb-idx">图' + _imgSeq + '</span>'
            + '<button class="lv-thumb-x" title="移除此图引用" data-act="rm-img" data-i="' + i + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
          matTiles.appendChild(tile);
          tile.querySelector("button").addEventListener("click", () => {
            if (_ro) return;
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
        const _la = _lbl ? _lblAssetOf(_lbl) : null;
        if (_la && (_la.kind === "scene" || _la.kind === "prop")) return; 
        const unmatched = c.matched === false;
        const tile = document.createElement("span");
        tile.className = "lv-mat-tile char" + (unmatched ? " review" : "");
        tile.title = (unmatched ? "未在脚本片段确认：" : "") + _esc(c.label || "?");
        tile.innerHTML = '<span class="lv-mat-tile-lbl">' + _esc(c.label || "?") + "</span>"
          + '<button class="lv-tile-x" title="移除此角色" data-act="rm-char" data-i="' + i + '"><span class="ic ic-cancel" aria-hidden="true"></span></button>';
        tile.querySelector("button").addEventListener("click", () => {
          if (_ro) return;
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
          if (_ro) return;
          if (Array.isArray(s.audio)) s.audio.splice(i, 1);
          if (Array.isArray(s.audio_urls)) s.audio_urls.splice(i, 1);
          s.prompt = _stripRefFromPrompt(s.prompt, "音频", i + 1);
          renderShots();
          saveDraft();
        });
        if (u) tile.title = u;
        matTiles.appendChild(tile);
      }

      div.appendChild(matTiles);


      
      const wrap = document.createElement("div");
      wrap.className = "lv-prompt-edit-wrap";
      wrap.style.position = "relative";
      const ed = createRichPromptEditor({
        text: s.prompt || "",
        placeholder: "本镜提示词（写足：场景+角色外貌+互动+对白(声线：台词，嘴形同步)+SFX+风格，不限制字数）。输入 @ 可把本镜素材缩略图插入此处。",
        getMats: () => _matsForShot(s),
        onCommit: (t) => { if (_ro) return; s.prompt = t; saveDraft(); },
        onAddMaterial: (kind, name, url) => {
          if (_ro) return 0;
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
      if (_ro) ed.el.contentEditable = "false";
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

      
      
      if (_ro) {
        const stEl = document.createElement("div");
        stEl.className = "lv-shot-st st-pending";
        stEl.innerHTML = `<span class="st-dot"></span><span class="st-txt">排队中</span>`;
        div.appendChild(stEl);
      }

      lvShots.appendChild(div);
    });
    
    if (_ro && lv.segs.length) _updateShotStatusLines();
    
    
    _loadTailThumbs();
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
    const st = lv.jobStatus;
    const isDraft = !lv.jobId || !st || st === "draft";
    const running = st === "processing" || (lv.segs || []).some((s) => s.status === "processing");
    if (isDraft) {
      bar.hidden = lv.shots.length === 0;
      btn.hidden = false;
      btn.disabled = false;
      btn.classList.remove("danger");
      btn.textContent = "开始生成";
    } else if (running) {
      bar.hidden = false;      
      btn.hidden = true;
    } else {
      
      bar.hidden = lv.shots.length === 0;
      btn.hidden = false;
      btn.classList.add("danger");
      btn.textContent = "重新编排";
    }
  }

  
  
  
  async function _enterReedit() {
    if (!lv.jobId) return;
    if (lv.jobStatus === "processing") { err("任务生成中，请等待完成后再重新编排"); return; }
    if (lv.jobStatus === "draft") { setMsg("任务已是可编辑状态（无需解锁）"); return; }
    if (!(await lvConfirm({
      title: "重新编排",
      message: "将解锁分镜进入重新编辑：\n· 分镜恢复可编辑（改提示词/秒数/绑定/删加镜头）\n· 已生成的成片保留在第 3 步供对照\n· 改完分镜点「开始生成」才会重新生成（旧视频会自动保留）\n\n进入重新编辑？",
      okText: "解锁编辑",
    }))) return;
    try {
      const r = await fetch(API + `/api/jobs/${lv.jobId}/reedit`, { method: "POST" });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { err("进入重编失败：" + (j.error || "")); return; }
      lv.jobStatus = "draft";
      _autoJumpOK = false;      
      saveState();
      renderShots();            
      _syncStartBtn();          
      _updateProgSum({ status: "draft" });   
      setMsg("已进入重新编辑：分镜已解锁，改完点「开始生成」重新生成（旧成片在第 3 步可对照）");
    } catch (e) { err("重编请求异常：" + e.message); }
  }

  $("lvTo3").addEventListener("click", async () => {
    
    
    const st = lv.jobStatus;
    if (lv.jobId && st && st !== "draft") {
      await _enterReedit();
      return;
    }
    withBtn($("lvTo3"), "创建中…", async () => {
      if (!lv.shots.length) { err("分镜数据未加载完成，请稍候重试"); return; }
      
      if (!lv.jobId) await ensureJob();
      
      if (lv.jobStatus === "processing") { err("该任务正在生成中，请等待完成"); return; }
      setMsg("开始生成中…");
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
          }),
        });
        j = await r.json().catch(() => ({}));
      } catch (e) {
        err("开始生成网络异常：" + (e && e.message ? e.message : e));
        return;
      }
      if (!r.ok) { err("创建失败：" + (j.error || `HTTP ${r.status}`)); return; }
      lv.jobId = j.job_id;
      lv.jobStatus = "processing";
      lv.genStartTs = Date.now() / 1000;
      saveState();
      _syncStartBtn();
      renderShots();   
      _updateProgSum({ status: "processing" });   
      _autoJumpOK = true;   
      startPoll();
      
      const _cur = lvShots.querySelector(".lv-shot");
      if (_cur) _cur.scrollIntoView({ behavior: "smooth", block: "start" });
      loadJobs();
    });
  });

  
  
  
  
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
  
  
  let _autoJumpOK = false;

  async function pollJob() {
    if (!lv.jobId) return;
    const gen = _pollGen;       
    const jid = lv.jobId;       
    try {
      const r = await fetch(API + "/api/jobs/" + jid);
      const j = await r.json().catch(() => ({}));
      
      if (gen !== _pollGen || jid !== lv.jobId) return;
      if (r.status === 404) {
        
        
        stopPoll();
        lv.jobId = null; lv.jobStatus = null; lv.segs = [];
        _syncStartBtn(); _updateProgSum({ status: "draft" }); _updateShotStatusLines();
        loadJobs();
        setMsg("任务已被删除，已回到草稿（可重新编辑）");
        return;
      }
      if (!r.ok) { err("查询失败：" + (j.error || "")); return; }
      lv.segs = j.segments || [];
      lv.jobStatus = j.job.status;
      _syncStartBtn();          
      _updateProgSum(j.job);    
      _updateShotStatusLines(); 
      const _anyProc = lv.segs.some((s) => s.status === "processing");
      if (j.job.status === "completed" && !_anyProc) {
        stopPoll();
        lv.finalUrl = j.final_url || null;
        _verifyFinal();
        setMsg("成片已生成");
        
        
        
        if (_autoJumpOK && lv.step === 2) {
          _autoJumpOK = false;
          goStep(4);
          setMsg("成片已生成，已自动进入成片预览");
        }
        loadJobs();
      } else if (j.job.status === "failed" && !_anyProc) {
        stopPoll();
        _autoJumpOK = false;    
        err("生成失败：" + (j.job.error || ""));
      } else if (j.job.status === "cancelled" && !_anyProc) {
        
        
        stopPoll();
      } else if (j.job.status !== "processing" && _anyProc) {
        
        
      }
    } catch (e) {  }
  }

  function _fmtDur(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    const m = Math.floor(sec / 60), s = sec % 60;
    return m > 0 ? `${m}分${s}秒` : `${s}秒`;
  }
  
  const _SEG_STATUS_CN = { pending: "排队中", processing: "生成中", completed: "已完成", failed: "失败", cancelled: "已停止" };
  const _JOB_STATUS_CN = { draft: "草稿", processing: "生成中", completed: "已完成", failed: "失败", cancelled: "已停止" };
  function _jobStatusCN(st) { return _JOB_STATUS_CN[st] || (st || "—"); }
  function _segStatusCN(st, jobSt) {
    if (st === "cancelled" || (jobSt === "cancelled" && (st === "pending" || !st))) return "已停止";
    return _SEG_STATUS_CN[st] || (st || "—");
  }
  
  
  
  function _updateProgSum(job) {
    const box = $("lvProgSum");
    if (!box) return;
    const started = !!(lv.jobId && lv.jobStatus && lv.jobStatus !== "draft");
    box.hidden = !started || !lv.segs.length;
    if (box.hidden) return;
    const total = lv.segs.length || 0;
    const done = lv.segs.filter((s) => s.status === "completed").length;
    const failed = lv.segs.filter((s) => s.status === "failed").length;
    const running = lv.segs.find((s) => s.status === "processing");
    const pct = total ? Math.round((done / total) * 100) : 0;
    
    
    const nowTs = Date.now() / 1000;
    const _endsAll = lv.segs.map((s) => s.finished_at).filter(Boolean);
    const _allDone = lv.segs.length > 0 && lv.segs.every((s) => s.status === "completed");
    let elapsed = 0;
    if (lv.genStartTs) {
      const _t1 = (_allDone && _endsAll.length) ? Math.max(..._endsAll) : nowTs;
      elapsed = Math.max(0, _t1 - lv.genStartTs);
    }
    
    
    
    const completedSegs = lv.segs.filter((s) => s.status === "completed" && s.started_at && (s.finished_at || s.updated_at));
    let eta = 0;
    if (completedSegs.length) {
      const avg = completedSegs.reduce((a, s) => a + ((s.finished_at || s.updated_at) - s.started_at), 0) / completedSegs.length;
      eta = (total - done) * avg;
    } else if (total - done > 0) {
      eta = (total - done) * 95;
    }
    const js = (job && job.status) || lv.jobStatus;
    const jobCN = _jobStatusCN(js);   
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
    if (el3) { el3.textContent = (eta > 0 && js !== "completed") ? _fmtDur(eta) : "—"; el3.className = "ps-v"; }
    const el4 = $("lvPsSt");
    if (el4) { el4.textContent = jobCN + (failed ? ` · 失败${failed}段` : ""); el4.className = "ps-v " + cls; }
    const bar = $("lvPsBar");
    if (bar) bar.style.width = pct + "%";
    
    
    
    const vb = $("lvTo4");
    if (vb) { vb.hidden = !lv.segs.some((s) => s.status === "completed"); vb.disabled = vb.hidden; }
    const rb = $("lvRetry");
    if (rb) { rb.hidden = !(js === "failed"); rb.disabled = rb.hidden; }
    const rs = $("lvResume");
    if (rs) { rs.hidden = !(js === "cancelled"); rs.disabled = rs.hidden; }   
    const sb = $("lvStopBtn");
    if (sb) { sb.hidden = !(js === "processing"); sb.disabled = sb.hidden; }
    const hint = $("lvPsHint");
    if (hint) hint.textContent = running
      ? "正在生成当前段，请保持页面打开。"
      : (js === "processing" ? "正在生成，请保持页面打开。"
      : (js === "cancelled" ? "已停止：在飞段已收尾，点「继续生成」续跑剩余段。" : ""));
  }

  
  
  function _updateShotStatusLines() {
    if (!lv.segs.length) return;
    lvShots.querySelectorAll(".lv-shot").forEach((card) => {
      const segNo = parseInt(card.dataset.segNo, 10);
      const s = lv.segs.find((x) => x.seg_no === segNo);
      if (!s) return;
      const st = card.querySelector(".lv-shot-st");
      if (!st) return;
      _fillShotStatusLine(st, s);
    });
  }

  
  function _fillShotStatusLine(st, s) {
    let durTxt = "";
    if (s.started_at) {
      
      const _endAt = s.finished_at || s.updated_at;
      if (s.status === "completed" && _endAt) durTxt = " · 耗时" + _fmtDur(_endAt - s.started_at);
      else if (s.status === "processing") durTxt = " · 已" + _fmtDur(Date.now() / 1000 - s.started_at);
    }
    
    const _stoppedLike = lv.jobStatus === "cancelled" && (s.status === "pending" || !s.status);
    const _effSt = _stoppedLike ? "cancelled" : (s.status || "pending");
    st.className = "lv-shot-st st-" + _effSt;
    let html = `<span class="st-dot"></span><span class="st-txt">${_segStatusCN(_effSt, lv.jobStatus)}${durTxt}</span>`;
    if (s.status === "failed") {
      const reason = (s.error || "").slice(0, 80);
      html += `<span class="st-err" title="${_esc(s.error || "")}">${reason ? _esc(reason) : ""}</span>` +
              `<button class="st-retry" type="button" data-seg="${s.seg_no}">重试本段</button>`;
    } else if (s.status === "completed") {
      const _tv = Math.round(s.finished_at || s.updated_at || 0);
      
      
      html += `<span class="st-thumb" data-seg="${s.seg_no}" title="点击进入④屏预览本段">
                <img src="${API}/api/jobs/${lv.jobId}/segment/${s.seg_no}/thumb?v=${_tv}" alt="" onerror="this.parentNode.classList.add('noimg');this.remove()">
              </span>
              <button class="st-view" type="button" data-seg="${s.seg_no}">预览本段</button>`;
    }
    st.innerHTML = html;
  }

  
  lvShots.addEventListener("click", (e) => {
    const retryBtn = e.target.closest(".st-retry");
    if (retryBtn) {
      e.stopImmediatePropagation();
      _regenFromCard(parseInt(retryBtn.dataset.seg, 10));
      return;
    }
    const viewBtn = e.target.closest(".st-view, .st-thumb");
    if (viewBtn) {
      e.stopImmediatePropagation();
      
      goStep(4);
      buildStrip();
      selectSeg(parseInt(viewBtn.dataset.seg, 10));
      return;
    }
  });

  
  async function _regenFromCard(n) {
    const s = lv.segs.find((x) => x.seg_no === n);
    if (!s) return;
    if (s.status === "processing") { err("该段正在生成，请稍候"); return; }
    
    
    
    
    
    const _isFailed = s.status === "failed";
    const title = _isFailed ? "重新生成（上次失败）" : "重新生成";
    const message = _isFailed
      ? `确定重新生成第 ${n} 个分镜吗？\n\n` +
        `ℹ 本段之前生成失败，没有产物可被覆盖。\n` +
        `🔧 重新生成会按当前提示词提交（没有已生成的视频可覆盖，重试不会覆盖任何旧视频）。\n` +
        `⚠ 若上次失败的原因没解决，重试仍可能再失败——可在第 4 步改完提示词再提交。\n` +
        `❌ 不需要重试？点「取消」放弃。\n\n` +
        `点「确定」开始重新生成，点「取消」放弃。`
      : `确定重新生成第 ${n} 个分镜吗？\n\n` +
        `⚠ 重新生成会覆盖「当前显示的版本」。\n` +
        `✅ 旧版本会自动保留（最多 3 个），不会丢失。\n` +
        `↩ 重新生成后可到第 4 步本分镜的「历史」查看旧稿/旧视频。\n` +
        `❌ 想保留当前版本？点「取消」，编辑器里的改动一并留在内存里。\n\n` +
        `点「确定」开始重新生成，点「取消」放弃。`;
    if (!(await lvConfirm({
      title,
      message,
      danger: true, okText: "重新生成",
    }))) return;
    setMsg(`第 ${n} 个分镜重新生成中…`);
    try {
      const r = await fetch(API + `/api/jobs/${lv.jobId}/segment/${n}/regen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: s.prompt }),
      });
      const j = await r.json();
      if (!r.ok) { err("重生成失败：" + (j.error || "")); return; }
      s.status = "processing";
      s.error = null;
      _fillShotStatusLineFor(n);
      
      _autoJumpOK = true;
      saveState();
      
      
      _updateProgSum({ status: "processing" });
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

  $("lvTo4").addEventListener("click", () => {
    goStep(4);
    buildStrip();
    
  });

  
  $("lvRetry").addEventListener("click", () => {
    if (!lv.jobId) return;
    withBtn($("lvRetry"), "重试中…", async () => {
      setMsg("正在重新生成失败的镜头…");
      try {
        const r = await fetch(API + `/api/jobs/${lv.jobId}/retry`, { method: "POST" });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { err("重试失败：" + (j.error || "")); return; }
        lv.jobStatus = "processing";
        saveState();
        _autoJumpOK = true;   
        
        lv.segs.forEach((s) => { if (s.status === "failed") { s.status = "pending"; s.error = null; } });
        _updateShotStatusLines();
        _updateProgSum({ status: "processing" });
        startPoll();
        setMsg("已重新加入队列生成失败的镜头…");
      } catch (e) {
        err("重试请求异常：" + e.message);
      }
    });
  });

  
  $("lvResume").addEventListener("click", () => {
    if (!lv.jobId) return;
    withBtn($("lvResume"), "启动中…", async () => {
      setMsg("正在继续生成剩余镜头…");
      try {
        const r = await fetch(API + `/api/jobs/${lv.jobId}/retry`, { method: "POST" });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { err("继续失败：" + (j.error || "")); return; }
        lv.jobStatus = "processing";
        saveState();
        _autoJumpOK = false;   
        lv.segs.forEach((s) => { if (s.status === "cancelled" || s.status === "failed") { s.status = "pending"; s.error = null; } });
        _updateShotStatusLines();
        _updateProgSum({ status: "processing" });
        startPoll();
        setMsg("已继续生成剩余镜头…");
      } catch (e) {
        err("继续请求异常：" + e.message);
      }
    });
  });

  
  const lvVideo = $("lvVideo");
  const lvStrip = $("lvStrip");
  const lvSegPrompt = $("lvSegPrompt");
  const _segEditor = createRichPromptEditor({
    big: true,
    text: "",
    placeholder: "本镜生成提示词（图N=参考图，音频N=声线）。输入 @ 可把素材缩略图插入此处。",
    getMats: () => _matsForSeg(_segCurrent()),
    onCommit: (t) => { const s = _segCurrent(); if (s) { s.prompt = t; saveDraft(); } _updateCC(); },
  });
  if (lvSegPrompt && lvSegPrompt.parentNode) lvSegPrompt.parentNode.replaceChild(_segEditor.el, lvSegPrompt);
  const lvCapSeg = $("lvCapSeg");
  const lvCapSec = $("lvCapSec");
  const lvPrevCap = $("lvPrevCap");
  const lvPrevSec = $("lvPrevSec");
  const lvPrevStatus = $("lvPrevStatus");
  const lvPrevMeta = $("lvPrevMeta");
  const lvCC = $("lvCC");
  const lvPrev = $("lvPrev");
  const lvNext = $("lvNext");
  const lvRegen = $("lvRegen");
  const lvJump = $("lvJump");
  const lvPlayIc = $("lvPlayIc");
  const lvCont = $("lvCont");
  const lvChip1 = $("lvChip1"), lvChip2 = $("lvChip2"), lvChip3 = $("lvChip3");
  const lvMatRow = $("lvMatRow");

  
  
  const lvSecEdit = $("lvSecEdit");
  const lvSecDown = $("lvSecDown");
  const lvSecUp = $("lvSecUp");
  let lvSecDirty = false;
  let lvSecVal = 5;   

  
  let lvContinuous = true;

  function _statusCN(s) {
    if (!s) return "—";
    if (s.status === "completed") return "已完成";
    if (s.status === "processing") return "生成中…";
    if (s.status === "failed") return "失败" + (s.error ? "：" + s.error : "");
    return s.status;
  }
  function _statusKey(s) {
    if (!s) return "muted";
    if (s.status === "completed") return "completed";
    if (s.status === "processing") return "processing";
    if (s.status === "failed") return "failed";
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
        const clean = String(key || "").replace(/^lv_[a-f0-9]+_?/i, "").replace(/^lv_/i, "").replace(/\.(png|jpe?g|webp|bmp)$/i, "");
        const lbl = clean.length > 10 ? clean.slice(0, 10) + "…" : clean;
        const urlIdx = isCont ? 1 + i : i;
        out.push({ kind: "image", idx: startIdx + i, label: lbl || "参考图", url: _assetUrl(key, rawUrls[urlIdx]) });
      });
    } else if (!isCont) {
      out.push({ kind: "image", idx: 1, label: "无图", url: "", isMiss: true });
    }
    
    const aud = _parseArr(s.audio);
    const audUrls = _parseArr(s.audio_urls);
    aud.forEach((who, i) => {
      out.push({ kind: "audio", idx: i + 1, label: who, url: _assetUrl(who, audUrls[i]) });
    });
    return out;
  }

  function buildStrip() {
    lvStrip.innerHTML = "";
    if (!lv.segs.length) {
      
      
      
      lvStrip.innerHTML = `<div style="color:var(--mut-2);font-size:12px;padding:8px 12px">暂无片段${lv.jobId ? "（任务已选中，segments 加载中…）" : "（请先选择任务）"}</div>`;
      return;
    }
    const arrL = document.createElement("button");
    arrL.className = "arr"; arrL.type = "button"; arrL.innerHTML = '<span class="ic ic-chevron-left" aria-hidden="true"></span>';
    const arrR = document.createElement("button");
    arrR.className = "arr"; arrR.type = "button"; arrR.innerHTML = '<span class="ic ic-chevron-right" aria-hidden="true"></span>';
    const inner = document.createElement("div");
    inner.style.cssText = "display:flex;gap:8px;overflow-x:auto;flex:1;scroll-behavior:smooth;padding:0 2px;";
    lvStrip.appendChild(arrL);
    lvStrip.appendChild(inner);
    lvStrip.appendChild(arrR);
    arrL.addEventListener("click", () => inner.scrollBy({ left: -inner.clientWidth * 0.8, behavior: "smooth" }));
    arrR.addEventListener("click", () => inner.scrollBy({ left: inner.clientWidth * 0.8, behavior: "smooth" }));
    
    
    
    
    const _syncArrows = () => {
      const max = inner.scrollWidth - inner.clientWidth;
      arrL.disabled = inner.scrollLeft <= 2;
      arrR.disabled = max <= 2 || inner.scrollLeft >= max - 2;
    };
    inner.addEventListener("scroll", _syncArrows, { passive: true });
    _syncArrows();
    requestAnimationFrame(() => { _syncArrows(); requestAnimationFrame(_syncArrows); });
    setTimeout(_syncArrows, 350);
    inner.querySelectorAll(".thumb img").forEach((im) => {
      im.addEventListener("load", _syncArrows, { once: true });
      im.addEventListener("error", _syncArrows, { once: true });
    });
    lv.segs.forEach((s) => {
      const b = document.createElement("div");
      b.className = "seg";
      b.setAttribute("data-seg", s.seg_no);
      const done = s.status === "completed";
      const stCN = s.status === "completed" ? "已完成" : s.status === "processing" ? "生成中" : s.status === "failed" ? "失败" : s.status;
      let thumb;
      if (done) {
        
        const src = API + `/api/jobs/${lv.jobId}/segment/${s.seg_no}/thumb?t=${Date.now()}`;
        thumb = `<div class="thumb"><img src="${src}" alt="镜头 ${s.seg_no}" referrerpolicy="no-referrer">`
          + `<span class="badge">${s.seg_no}</span><span class="playing">播放中</span>`
          + `<div class="ph" style="display:none"><span class="sp"><span class="ic ic-film" aria-hidden="true"></span></span>无预览</div></div>`;
      } else {
        const ic = s.status === "processing" ? "ic-loader" : s.status === "failed" ? "ic-fail" : "ic-more";
        thumb = `<div class="thumb"><span class="badge">${s.seg_no}</span>`
          + `<div class="ph"><span class="sp"><span class="ic ${ic}" aria-hidden="true"></span></span>${stCN}</div></div>`;
      }
      b.innerHTML = thumb
        + `<div class="cap"><span class="nm">镜头 ${s.seg_no}</span><span class="sc">${(s.seconds || 5)}s</span></div>`;
      if (done) {
        const img = b.querySelector("img");
        const ph = b.querySelector(".ph");
        img.addEventListener("error", () => { img.style.display = "none"; if (ph) ph.style.display = ""; });
      }
      b.addEventListener("click", () => selectSeg(s.seg_no));
      inner.appendChild(b);
    });
    if (lv.segs.length) selectSeg(1);
  }

  
  function _useFinal() {
    return lvContinuous && !!lv.finalUrl;
  }
  
  function _segStart(n) {
    let t = 0;
    for (const s of lv.segs) {
      if (s.seg_no >= n) break;
      t += (s.real_seconds || s.seconds || 5);
    }
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

  function selectSeg(n, autoplay) {
    if (!lv.segs.length) return;
    n = Math.max(1, Math.min(n, lv.segs.length));
    _syncSegUI(n);
    _playSegSrc(n, autoplay);
  }

  
  
  
  
  function _syncSecStepper() {
    const _sb = lvSecBounds();
    const _s = (lv.segs || []).find((x) => x.seg_no === lv.selSeg);
    const _secLock = !!(_s && _s.status === "processing");   
    if (lvSecDown) lvSecDown.disabled = _secLock || lvSecVal <= _sb.min;
    if (lvSecUp) lvSecUp.disabled = _secLock || lvSecVal >= _sb.max;
    if (lvSecEdit) {
      lvSecEdit.style.opacity = _secLock ? ".55" : "";
      lvSecEdit.title = `调整本段时长（${_sb.min}~${_sb.max} 秒，界随所选视频模型），改动会随「重新生成本段」一起生效`;
    }
  }

  
  function _syncSegUI(n) {
    lv.selSeg = n;
    saveState();
    const inner = lvStrip.querySelector("div");
    if (inner) inner.querySelectorAll(".seg").forEach((b) =>
      b.classList.toggle("on", +b.getAttribute("data-seg") === n)
    );
    const s = lv.segs.find((x) => x.seg_no === n);
    if (!s) return;
    lvCapSeg.textContent = "镜头 " + n;
    
    lvSecVal = s.seconds || 5;
    lvCapSec.textContent = lvSecVal + "s";
    lvSecDirty = false;
    if (lvSecEdit) lvSecEdit.classList.remove("dirty");
    
    _syncSecStepper();
    
    let chips = [];
    try { chips = _matChips(s); } catch (e) { console.error("[lv][matChips] err", e, s); chips = [{ label: "素材加载失败", isMiss: true }]; }
    
    
    if (lvMatRow) {
      Array.from(lvMatRow.querySelectorAll(".chip")).forEach((el) => el.remove());
      chips.forEach((item) => {
        const sp = document.createElement("span");
        const cls = ["chip", "lv-mat"];
        if (item.kind === "audio") cls.push("audio");
        if (item.isTail) cls.push("tail");
        if (item.isMiss) cls.push("miss");
        sp.className = cls.join(" ");
        if (item.kind === "image" && !item.isMiss && !item.isTail) {
          
          
          const img = document.createElement("img");
          img.className = "lv-mat-img";
          img.alt = "";
          img.loading = "lazy";
          img.decoding = "async";
          img.referrerPolicy = "no-referrer";
          img.src = _thumb(_encUrl(item.url || ""), 128);
          img.onerror = () => {
            img.removeAttribute("src");
            img.classList.add("lv-mat-img-failed");
            img.alt = "图片失效";
            sp.title = "素材加载失败: " + (item.url || "(no url)");
          };
          sp.appendChild(img);
        } else if (item.kind === "audio") {
          const ico = document.createElement("span");
          ico.className = "lv-mat-ico ic ic-audio";
          sp.appendChild(ico);
        } else if (item.isTail) {
          const ico = document.createElement("span");
          ico.className = "lv-mat-ico ic ic-continue";
          sp.appendChild(ico);
        }
        const tag = document.createElement("span");
        tag.className = "lv-mat-tag";
        if (!item.kind) {
          
          tag.textContent = item.label || "";
        } else if (item.isTail) {
          tag.textContent = "图1 尾帧";
        } else if (item.isMiss) {
          tag.textContent = "图1 无图";
        } else {
          const prefix = (item.kind === "audio" ? "音频" : "图") + item.idx;
          tag.textContent = item.label ? (prefix + " " + item.label) : prefix;
        }
        sp.appendChild(tag);
        lvMatRow.appendChild(sp);
      });
    } else {
      
      [lvChip1, lvChip2, lvChip3].forEach((el, i) => {
        const it = chips[i];
        if (!it) { el.style.display = "none"; return; }
        const txt = it.label ? ((it.kind === "audio" ? "音频" + it.idx : "图" + it.idx) + " " + it.label) : (it.label || "");
        el.innerHTML = (it.kind === "audio" ? '<span class="ic ic-audio" aria-hidden="true"></span>' : "") + _esc(txt);
        el.style.display = "";
      });
    }
    
    if (lvPrevMeta) {
      const model = (lv.opts && lv.opts.model) || "agnes-video-2.5-flash";
      const aspect = (lv.opts && lv.opts.aspect_ratio) || "16:9";
      const res = (lv.opts && lv.opts.resolution) || "720P";
      const fmt = (k, v) => '<span class="m"><b>' + k + '：</b>' + _esc(v) + '</span>';
      lvPrevMeta.innerHTML = fmt("模型", model) + fmt("画幅", aspect) + fmt("分辨率", res);
    }
    _segEditor.setText(s.prompt || "");
    _updateCC();
    
    
    lvPrevCap.textContent = "";
    if (lvPrevSec) lvPrevSec.textContent = "本段时长：" + (s.seconds || 5) + "s";
    lvPrevStatus.textContent = "状态：" + _statusCN(s);
    lvPrevStatus.className = "lv-prev-status s-" + _statusKey(s);
    lvPrev.disabled = n <= 1;
    lvNext.disabled = n >= lv.segs.length;
    if (inner) {
      const on = inner.querySelector(".seg.on");
      if (on) on.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }

  function _playSegSrc(n, autoplay) {
    if (_useFinal()) {
      
      const want = API + lv.finalUrl + "?t=" + Date.now();
      const changingSrc = !lvVideo.src || !lvVideo.src.includes("/final.mp4") || !lvVideo.src.includes(lv.jobId);
      if (changingSrc) {
        lvVideo.src = want;
        lvVideo.load();
      }
      const start = _segStart(n);
      
      
      
      
      
      
      const seekTo = start + 0.01;
      const go = () => {
        try { lvVideo.currentTime = seekTo; } catch (_) {}
        if (autoplay) {
          lvPlayIc.style.display = "none";
          lvVideo.play().catch(() => { lvPlayIc.style.display = ""; });
        } else {
          lvPlayIc.style.display = "";
        }
      };
      if (changingSrc) {
        
        lvVideo.addEventListener("loadedmetadata", go, { once: true });
      } else {
        go();   
      }
    } else {
      lvVideo.src = API + `/api/jobs/${lv.jobId}/segment/${n}.mp4?t=${Date.now()}`;
      lvVideo.load();
      if (autoplay) {
        lvPlayIc.style.display = "none";
        lvVideo.play().catch(() => { lvPlayIc.style.display = ""; });   
      } else {
        lvPlayIc.style.display = "";
      }
    }
  }

  function updatePlayingBadge() {
    const playing = !lvVideo.paused && !lvVideo.ended && lvVideo.currentTime > 0;
    lvStrip.querySelectorAll(".seg").forEach((b) =>
      b.classList.toggle("playing", +b.getAttribute("data-seg") === lv.selSeg && playing)
    );
  }

  function _updateCC() {
    lvCC.textContent = [..._segEditor.getText()].length + " 字符";
  }
  
  lvVideo.addEventListener("timeupdate", () => {
    if (_useFinal() && lv.segs.length) {
      const cur = _segAt(lvVideo.currentTime);
      if (cur !== lv.selSeg) {
        _syncSegUI(cur);
        updatePlayingBadge();
      }
    }
  });
  lvVideo.addEventListener("play", () => { lvPlayIc.style.display = "none"; updatePlayingBadge(); });
  lvVideo.addEventListener("pause", () => { if (!lvVideo.ended) lvPlayIc.style.display = ""; updatePlayingBadge(); });
  lvVideo.addEventListener("ended", () => {
    updatePlayingBadge();
    
    
    if (!_useFinal() && lvContinuous && lv.selSeg < lv.segs.length) {
      selectSeg(lv.selSeg + 1, true);
    } else {
      lvPlayIc.style.display = "";
      if (lv.selSeg >= lv.segs.length) { lvPrevStatus.textContent = "状态：播放完毕"; lvPrevStatus.className = "lv-prev-status s-completed"; }
    }
  });

  lvJump.addEventListener("click", () => selectSeg(lv.selSeg, true));                    
  
  

  
  const lvHistory = $("lvHistory");
  let _histEl = null;
  function _fmtTs(ts) {
    const d = new Date((ts || 0) * 1000);
    const p = (x) => String(x).padStart(2, "0");
    return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function _closeHist() { if (_histEl) { _histEl.remove(); _histEl = null; document.removeEventListener("keydown", _histKey, true); } }
  function _histKey(e) { if (e.key === "Escape") { e.stopPropagation(); _closeHist(); } }
  if (lvHistory) lvHistory.addEventListener("click", async () => {
    if (!lv.jobId || !lv.selSeg) { err("请先选择一个段落"); return; }
    const n = lv.selSeg;
    try {
      const r = await fetch(API + `/api/jobs/${lv.jobId}/segment/${n}/history`);
      const j = await r.json();
      if (!r.ok) { err("历史查询失败：" + (j.error || "")); return; }
      _closeHist();
      const wrap = document.createElement("div");
      wrap.className = "lv-pk";
      const hist = j.history || [];
      const vids = j.videos || [];   
      
      const _trunc = (x) => (x.length > 12 ? x.slice(0, 12) + "…" : x);
      const _matHtml = (list) => list.slice(0, 6).map((m) => `<span class="h-mat"><span class="ic ic-${m.ic}" aria-hidden="true"></span>${_esc(m.t)}</span>`).join("");
      const rows = hist.length
        ? hist.slice().reverse().map((h, ri) => {
            
            const ver = h.ver || (hist.length - ri);
            const idx = hist.length - ri;   
            const mats = _matHtml([
              ...(h.images || []).filter((k) => k !== "tail").map((k) => ({ ic: "image", t: "图·" + _trunc(k) })),
              ...(h.audio || []).map((a) => ({ ic: "audio", t: "·" + _trunc(a) })),
            ]);
            
            const vid = (vids || []).find((x) => x.v === ver);
            const vidBtn = vid
              ? `<button class="h-vid" data-url="${vid.url}" type="button" title="在预览区播放这一版当时生成的画面（不会重新生成）"><span class="ic ic-resume" aria-hidden="true"></span>看这版画面</button>`
              : `<span class="h-novid" title="历史画面最多保留 3 版，这一版已被更新的版本顶掉">旧画面已超出保留数量</span>`;
            
            const delBtn = `<button class="h-del" data-didx="${idx - 1}" data-dver="${ver}" type="button" title="删除这一版旧记录">删除</button>`;
            return `<div class="lv-hist-it" data-i="${idx - 1}" data-role="old">
              <div class="h-when"><b>v${ver}</b><span>${_fmtTs(h.ts)}</span><span>${(h.seconds || 5)}s</span><span style="margin-left:auto;color:var(--vio);font-size:11px">点击放回编辑器</span></div>
              <div class="h-txt">${_esc((h.prompt || "").slice(0, 160) || "（空）")}</div>
              <div class="h-mats">${mats}<span style="flex:1"></span>${vidBtn}${delBtn}</div>
            </div>`;
          }).join("")
        : `<div class="lv-hist-cur" style="padding:22px 6px;text-align:center">这一段还没有历史版本。<br>以后每次「重新生成本段」，替换前的旧提示词和旧画面都会自动保存在这里。</div>`;
      const cur = j.current || {};
      
      const _same = (cur.prompt || "") && hist.find((h) => (h.prompt || "") === (cur.prompt || ""));
      const curMats = _matHtml([
        ...(cur.images || []).filter((k) => k !== "tail").map((k) => ({ ic: "image", t: "图·" + _trunc(k) })),
        ...(cur.audio || []).map((a) => ({ ic: "audio", t: "·" + _trunc(a) })),
      ]);
      const curVidUrl = `/api/jobs/${lv.jobId}/segment/${n}.mp4?t=${Date.now()}`;
      wrap.innerHTML = `
        <div class="lv-pk-mask"></div>
        <div class="lv-pk-box" style="width:min(640px,94vw)">
          <div class="lv-pk-t">第 ${n} 段 · 历史版本<span class="lv-sub" style="margin-left:8px;font-weight:400">共 ${hist.length} 版旧记录 · 最下方「当前生效」是现在正在使用的版本</span></div>
          <div class="lv-pk-list" style="gap:6px">${rows}</div>
          <div class="lv-hist-it" data-role="cur" style="cursor:default;border-color:var(--vio-line);background:var(--vio-soft)">
            <div class="h-when"><b style="color:var(--txt)"><span class="ic ic-dot" aria-hidden="true"></span>当前生效</b><span>${cur.updated_at ? _fmtTs(cur.updated_at) : ""}</span><span>${(cur.seconds || 5)}s</span>${_same ? `<span style="color:var(--amber,#c80)">内容与 v${_same.ver || "?"} 相同（重提未改提示词）</span>` : ""}<span style="margin-left:auto"></span></div>
            <div class="h-txt">${_esc((cur.prompt || "").slice(0, 160) || "（空）")}</div>
            <div class="h-mats">${curMats}<span style="flex:1"></span><button class="h-vid" data-url="${curVidUrl}" type="button" title="在预览区播放这一段现在正在使用的画面"><span class="ic ic-resume" aria-hidden="true"></span>看当前画面</button></div>
          </div>
        </div>`;
      document.addEventListener("keydown", _histKey, true);
      wrap.querySelector(".lv-pk-mask").addEventListener("click", _closeHist);
      
      const _curVidBtn = wrap.querySelector('[data-role="cur"] .h-vid');
      if (_curVidBtn) _curVidBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        lvVideo.pause();
        lvVideo.src = e.currentTarget.dataset.url;
        lvVideo.play().catch(() => {});
        lvPrevCap.textContent = `镜头 ${n} · 当前画面`;
        setMsg(`正在预览第 ${n} 段当前画面（切换到其他段会自动恢复）`);
      });
      
      
      wrap.querySelector(".lv-pk-list").addEventListener("click", (e) => {
        
        const db = e.target.closest(".h-del");
        if (db) {
          e.stopPropagation();
          e.stopImmediatePropagation();   
          const didx = parseInt(db.dataset.didx, 10);
          const dver = parseInt(db.dataset.dver, 10);
          const _hasVid = (vids || []).some((x) => x.v === dver);
          (async () => {
            if (!(await lvConfirm({
              title: "删除历史版本",
              message: `确定删除第 ${dver} 版旧记录？`,
              danger: true, okText: "删除",
            }))) return;
            try {
              const r = await fetch(API + `/api/jobs/${lv.jobId}/segment/${n}/history/${didx}`, {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ver: dver, video_ver: _hasVid ? dver : null }),
              });
              const j = await r.json().catch(() => ({}));
              if (!r.ok) { err("删除失败：" + (j.error || "")); return; }
              setMsg(`已删除第 ${dver} 版${j.removed_video ? "（含已生成视频 " + j.removed_video + "）" : ""}`);
              _closeHist();
              lvHistory.click();   
            } catch (ex) { err("删除异常：" + ex.message); }
          })();
          return;
        }
        const vb = e.target.closest(".h-vid");
        if (vb) {
          e.stopPropagation();
          e.stopImmediatePropagation();   
          lvVideo.pause();
          lvVideo.src = vb.dataset.url;
          lvVideo.play().catch(() => {});
          const _vm = /v(\d)/.exec(vb.textContent);
          lvPrevCap.textContent = `镜头 ${n} · 归档画面 v${_vm ? _vm[1] : "?"}（回看中，切段恢复）`;
          setMsg(`正在预览第 ${n} 段的旧版画面（切换到其他段会自动恢复）`);
          return;
        }
      });
      wrap.querySelector(".lv-pk-list").addEventListener("click", (e) => {
        const it = e.target.closest(".lv-hist-it[data-role=old]");
        if (!it) return;
        const h = hist[parseInt(it.dataset.i, 10)];
        if (!h) return;
        
        _segEditor.setText(h.prompt || "");
        const _sb = lvSecBounds();
        if (h.seconds && h.seconds >= _sb.min && h.seconds <= _sb.max) {
          lvSecVal = h.seconds;
          lvCapSec.textContent = lvSecVal + "s";
          _syncSecStepper();
          
          const cur = _segCurrent();
          lvSecDirty = !!(cur && cur.seconds !== h.seconds);
          lvSecEdit.classList.toggle("dirty", lvSecDirty);
        }
        _updateCC();
        _closeHist();
        setMsg(`已把 v${(hist[parseInt(it.dataset.i, 10)] || {}).ver || "?"} 旧稿放回编辑器（还没有生效，确认内容后点「重新生成本段」才会真正生成）`);
      });
      document.body.appendChild(wrap);
      _histEl = wrap;
    } catch (e) { err("历史查询异常：" + e.message); }
  });
  lvCont.addEventListener("click", () => {
    lvContinuous = !lvContinuous;
    lvCont.classList.toggle("on", lvContinuous);
    lvCont.setAttribute("aria-pressed", lvContinuous ? "true" : "false");
    
    
    
    if (lv.jobId && lv.selSeg) {
      const wasPaused = lvVideo.paused;
      lvVideo.pause();
      selectSeg(lv.selSeg, !wasPaused);
    }
  });
  lvPrev.addEventListener("click", () => { if (lv.selSeg > 1) selectSeg(lv.selSeg - 1); });
  lvNext.addEventListener("click", () => { if (lv.selSeg < lv.segs.length) selectSeg(lv.selSeg + 1); });

  
  if (lvSecDown) lvSecDown.addEventListener("click", () => {
    const _sb = lvSecBounds();
    if (lvSecVal <= _sb.min) return;
    lvSecVal--; lvCapSec.textContent = lvSecVal + "s";
    _syncSecStepper();
    lvSecDirty = true; lvSecEdit.classList.add("dirty");
  });
  if (lvSecUp) lvSecUp.addEventListener("click", () => {
    const _sb = lvSecBounds();
    if (lvSecVal >= _sb.max) return;
    lvSecVal++; lvCapSec.textContent = lvSecVal + "s";
    _syncSecStepper();
    lvSecDirty = true; lvSecEdit.classList.add("dirty");
  });
  
  
  if (lvSecEdit) lvSecEdit.addEventListener("change", () => {
    const _sb = lvSecBounds();
    const v = parseInt(lvSecEdit.value, 10);
    if (!Number.isFinite(v)) { lvSecEdit.value = String(lvSecVal); return; }   
    const _clamped = Math.max(_sb.min, Math.min(_sb.max, v));
    lvSecVal = _clamped;
    lvSecEdit.value = String(_clamped);
    lvCapSec.textContent = lvSecVal + "s";
    if (_clamped !== v) setMsg(`时长已按当前模型界钳到 ${_clamped} 秒（${_sb.min}~${_sb.max}）`);
    const _cur = (lv.segs || []).find((x) => x.seg_no === lv.selSeg) || {};
    lvSecDirty = lvSecVal !== (_cur.seconds || 5);
    lvSecEdit.classList.toggle("dirty", lvSecDirty);
    _syncSecStepper();
  });

  lvRegen.addEventListener("click", async () => {
    const n = lv.selSeg;
    const s = lv.segs.find((x) => x.seg_no === n);
    if (s && s.status === "processing") { err("该段正在生成，请稍候"); return; }
    
    const _mainRunning = lv.jobStatus === "processing" || (lv.segs || []).some((s) => s.status === "processing");
    const _parallelNote = _mainRunning ? "\n\n· 提示：还有其他段正在生成，本段会排在它后面一起生成，等待时间可能变长。" : "";
    const _secNote = lvSecDirty ? `\n\n· 本段时长将由 ${s.seconds || 5}s 改为 ${lvSecVal}s。` : "";
    if (!(await lvConfirm({
      title: "重新生成本段",
      message: `将按编辑器里的提示词，重新生成第 ${n} 段视频（大约需要 2~3 分钟）。\n\n` +
        `· 生成完成后，现在这段视频会被新视频替换；\n` +
        `· 替换前的旧视频和旧提示词会自动存入「历史」，随时可以回看（旧提示词全部保留，旧画面保留最近 3 版）；\n` +
        `· 点「取消」则不做任何改动，编辑器里已修改的内容也仍会保留。` +
        `${_secNote}${_parallelNote}`,
      danger: true,
      okText: "开始重新生成",
    }))) return;
    withBtn(lvRegen, "生成中…", async () => {
      const prompt = _segEditor.getText().trim();
      
      const body = { prompt };
      if (lvSecDirty) body.seconds = lvSecVal;
      setMsg(`第 ${n} 段开始重新生成，预计 2~3 分钟，期间可以切换或操作其他段落`);
      const r = await fetch(API + `/api/jobs/${lv.jobId}/segment/${n}/regen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok) { err("重生成失败：" + (j.error || "")); return; }
      
      lvSecDirty = false;
      if (lvSecEdit) lvSecEdit.classList.remove("dirty");
      
      
      if (body.seconds && s) s.seconds = body.seconds;
      
      
      const _shot = (lv.shots || []).find((x) => x.shot_no === n);
      if (_shot) { _shot.prompt = prompt; saveDraft(); }
      
      
      setMsg(`第 ${n} 个分镜已加入队列，后台生成中…`);
      lv.finalUrl = null;   
      startPoll();
      buildStrip();
      selectSeg(n);
      loadJobs();
      setMsg("");
    });
  });
