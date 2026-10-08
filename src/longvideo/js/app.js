  
  window.__viewHooks = window.__viewHooks || {};
  window.__viewHooks.longvideo = { onHide: function () {
    
    if (window.MediaStop) { try { window.MediaStop.stopAll("view:longvideo"); } catch (e) { } }
    const back = _preLVMedia || "video";
    if (mediaSel.value !== "longvideo") mediaSel.value = back;
    const tx = document.querySelector("#mediaSel .seg-tx");
    if (tx) tx.textContent = { video: "视频生成", image: "图片生成" }[back] || "视频生成";
    if (typeof setMedia === "function") { try { setMedia(back); } catch (e) {} }
  }};
  window.lvHide = hideLV;   

  
  (window.__viewOpeners = window.__viewOpeners || {})["longvideo"] = showLV;

  
  window.lvOpenJob = function (jobId) {
    if (!jobId) return false;
    try {
      if (window.Views) Views.show("longvideo"); else overlay.hidden = false;   
      openJob(jobId, null, false);       
      return true;
    } catch (e) {
      console.warn("[lvOpenJob] 打开长视频任务失败：", e);
      return false;
    }
  };
})();
