
import json
import math
import os
import re
import sqlite3
import threading


RH_ID = "minimax-h3"
RH_LABEL = "MiniMax H3"
WORKFLOW_ID = "2084788947984666625"
API_TYPE = 5
BASE_URL = "https://www.runninghub.cn"


N_MAIN_UNET = "1"
N_MAIN_DIRECTOR = "12"
N_SAGE_MAIN = "17"
N_SAGE_REFINE = "22"
N_LORA_MAIN = "25"
N_LORA_REFINE = "24"
N_SELFLIFT = "26"
N_REFINE = "18"
N_FACE = "27"






UNET_MAIN_REF2VA = "minimax_h3_ref2va_bf16.safetensors"
UNET_MAIN_FL2VA = "minimax_h3_fl2va_bf16.safetensors"












DEFAULT_NODE_ALLOWLIST = ("1", "12", "17", "25")
POST_SAMPLE_NODES = ("18", "20", "27")



UNET_BY_MODE = {
    "reference": UNET_MAIN_REF2VA,
    "keyframe":  UNET_MAIN_FL2VA,
    "text":      UNET_MAIN_FL2VA,
    "i2v":       UNET_MAIN_FL2VA,
    "v2v":       UNET_MAIN_FL2VA,
    "rv2v":      UNET_MAIN_FL2VA,
}

TASK_TYPES = {
    "reference": "r2v — 参考主体生视频(Reference to Video)",
    "text": "t2v — 文生视频(Text to Video)",
    "keyframe": "fl2v — 首尾帧生视频(First Last to Video)",
    "i2v": "i2v — 图生视频(Image to Video)",
    "v2v": "v2v — 视频生视频(Video to Video)",
    "rv2v": "rv2v — 参考视频生视频(Reference Video to Video)",
}
TASK_TYPE_CONFIRMED = {"reference"}


_ASPECTS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]


_MP_STEPS_16X9 = {
    0.2: [608, 352], 0.3: [736, 416], 0.4: [864, 480], 0.5: [960, 544],
    0.6: [1056, 608], 0.7: [1152, 640], 0.8: [1216, 672], 0.9: [1280, 736],
    0.98: [1344, 768], 1.0: [1376, 768], 1.2: [1504, 832], 1.5: [1664, 928],
    1.8: [1824, 1024], 2.0: [1920, 1088],
}
_MP_STEPS = sorted(_MP_STEPS_16X9.keys())


_SIZES = [
    "352p", "416p", "480p", "544p", "608p", "640p", "672p", "736p",
    "768p·0.98", "768p·1.0", "832p", "928p", "1024p", "1088p",
]
_SIZE_TO_MP = dict(zip(_SIZES, _MP_STEPS))
_SIZE_TO_HW = dict(zip(_SIZES, [_MP_STEPS_16X9[m] for m in _MP_STEPS]))

VIDEO_MODEL_LIMITS = {
    RH_ID: {
        "label": RH_LABEL,

        "default_aspect_ratio": "16:9",
        "default_megapixels": 0.4,
        "default_res": "864x480",
        "default_size": "480p",
        "aspect_ratios": _ASPECTS,
        "aspect_ratio_values_confirmed": False,
        "mp_steps": _MP_STEPS,
        "sizes": _SIZES,
        "size_to_mp": _SIZE_TO_MP,
        "size_to_hw": _SIZE_TO_HW,
        "sizes_are_aspect_specific": "16:9",
        "non_16x9_pixels": "computed_by_us",
        "size_multiple": 32,

        "frame_rate": 24,
        "min_seconds": 1,
        "max_seconds": 15,
        "seconds_step": 1,
        "platform_seconds_limit_unknown": True,

        "max_images": 9, "max_audios": 3, "max_videos": 3,
        "allow_video": True,

        "modes_confirmed": ["reference"],
        "modes_assumed": ["text", "keyframe", "i2v", "v2v", "rv2v"],
        "unet_main_by_mode": {
            "reference": UNET_MAIN_REF2VA,
            "keyframe":  UNET_MAIN_FL2VA,
            "text":      UNET_MAIN_FL2VA,
        },
        "unet_main_note": "FL2V/T2V 用主模型 fl2va_bf16（不是精修链的 pruned_int8 采样模型）；I2V 暂不单独处理；节点21 出厂即 fl2va_pruned_int8，不随模式变",
        "native_audio": True,
        "multi_segment": True,

        "instance_tiers": {"default": "24G", "plus": "48G", "ultra": "84G"},
        "default_instance": "plus",






        "default_accel_off": True,
        "default_allow_compile": False,
        "default_steps": 20,
        "steps_with_accel": 8,
        "shift_video_with_accel": 12,
        "shift_audio_with_accel": 3,
        "shift_travels_with_steps": True,


        "sampler": "res_multistep",
        "scheduler": "simple",

        "steps_by_tier": {"hq": 20, "hq25": 25, "fast": 8},

        "selflift": {
            "via": "workflow",









            "params": [
                {"key": "scale", "label": "低清倍率", "type": "number",
                 "min": 0.25, "max": 1.0, "step": 0.05, "default": 0.5},
                {"key": "latent_upsample", "label": "上采样插值", "type": "enum",
                 "choices": [{"v": "bilinear", "t": "Bilinear"},
                             {"v": "nearest", "t": "Nearest"}],
                 "default": "bilinear"},
            ],


            "highres_choices": {"fast": [1, 2, 3], "hq": [3, 5, 8], "hq25": [4, 6, 10]},
            "default": {"enabled": False, "scale": 0.5, "latent_upsample": "bilinear",
                        "highres": {"fast": 2, "hq": 5, "hq25": 6}},

            "scale_choices": [0.5, 0.75],

            "latent_upscale_model": "minimax_h3_latent_upscaler_3d_bf16.safetensors",
        },

        "cancel_api": {"endpoint": "/task/openapi/cancel", "supported": True},


        "instance_tiers": [
            {"v": "default", "label": "Default", "vram": "24G",
             "coins_per_sec": 0.2, "yuan_per_hour": 4, "tip": "使用24G显存生成"},
            {"v": "plus",    "label": "Plus",    "vram": "48G",
             "coins_per_sec": 0.4, "yuan_per_hour": 6, "tip": "使用48G显存生成"},
            {"v": "ultra",   "label": "Ultra",   "vram": "84G",
             "coins_per_sec": 0.6, "yuan_per_hour": 9, "tip": "使用84G显存生成"},
        ],

        "account_api": {
            "endpoint": "/uc/openapi/accountStatus",
            "fields": {
                "api_type": "apiType",
                "coins": "remainCoins",
                "money": "remainMoney",
                "currency": "currency",
                "running": "currentTaskCounts",
            },


            "concurrency": {"enforce": False, "note": "官方接受即通过；被拒按错误翻译"},
            "note": "接口不提供会员等级（基础版/专业版），只有 apiType",
        },
        "usage": {
            "source": "task/openapi/outputs",
            "fields": {"coins": "consumeCoins", "seconds": "taskCostTime", "money": "consumeMoney"},
            "coins_unit": "RH币",
            "money_unit": "¥",
            "show_in_meta": True,

        },


        "post_refine": {
            "via": "workflow",









            "params": [
                {"key": "mode", "label": "模式", "type": "enum",
                 "choices": [{"v": "refine", "t": "只二采"},
                             {"v": "upscale", "t": "放大+二采"},
                             {"v": "latent_upscale", "t": "只放大"}],
                 "default": "upscale"},
                {"key": "upscale_method", "label": "放大算法", "type": "enum",
                 "choices": [{"v": "lanczos", "t": "Lanczos"},
                             {"v": "h3_latent", "t": "H3 潜空间"}],
                 "default": "lanczos"},
                {"key": "mp", "label": "放大目标", "type": "number",
                 "min": 0.5, "max": 2.0, "step": 0.1, "default": 1.0,
                 "note": "偏离 1.0 会脱离 768p LoRA 训练分辨率"},
                {"key": "passes", "label": "精修次数", "type": "number",
                 "min": 1, "max": 3, "step": 1, "default": 1},
                {"key": "steps", "label": "二采步数", "type": "number",
                 "min": 1, "max": 30, "step": 1, "default": 3},
                {"key": "denoise", "label": "重绘幅度", "type": "number",
                 "min": 0.05, "max": 0.6, "step": 0.05, "default": 0.25},
            ],
            "default": {"mode": "upscale", "mp": 1.0, "passes": 1, "steps": 3,
                        "denoise": 0.25, "upscale_method": "lanczos"},

            "modes": ["refine", "upscale", "latent_upscale"],
            "mp_choices": [1.0, 1.8, 2.0],
            "passes_choices": [1, 2, 3],
            "steps_choices": [3, 6, 10],
            "denoise_choices": [0.2, 0.25, 0.4],
        },
        "post_face": {
            "via": "workflow",






            "params": [
                {"key": "denoise", "label": "重绘幅度", "type": "number",
                 "min": 0.0, "max": 1.0, "step": 0.05, "default": 0.4},
                {"key": "steps", "label": "采样步数", "type": "number",
                 "min": 1, "max": 30, "step": 1, "default": 8},
                {"key": "confidence", "label": "检测阈值", "type": "number",
                 "min": 0.1, "max": 0.9, "step": 0.05, "default": 0.35},
                {"key": "mask_dilation", "label": "mask 膨胀", "type": "number",
                 "min": 0, "max": 64, "step": 1, "default": 16},
                {"key": "feather", "label": "羽化", "type": "number",
                 "min": 0, "max": 64, "step": 1, "default": 24},
                {"key": "select", "label": "选脸策略", "type": "enum",
                 "choices": [{"v": "largest_face", "t": "最大脸"},
                             {"v": "centre_most", "t": "最居中"}],
                 "default": "largest_face"},
                {"key": "paste_region", "label": "贴回范围", "type": "enum",
                 "choices": [{"v": "face_only", "t": "仅脸部"},
                             {"v": "face_ellipse", "t": "脸部椭圆"},
                             {"v": "full_crop", "t": "全裁剪区"}],
                 "default": "face_only"},
            ],
            "default": {"enabled": False, "denoise": 0.4, "steps": 8, "confidence": 0.35,
                        "mask_dilation": 16, "feather": 24, "select": "largest_face",
                        "paste_region": "face_only"},

            "steps_choices": [6, 8, 12],
            "denoise_choices": [0.2, 0.4, 0.6],
        },
        "refine_megapixels": 1.0,
        "refine_steps_default": 3, "refine_steps_range": [1, 30],
        "face_steps_default": 8, "face_steps_range": [1, 30],
        "face_denoise_default": 0.4,
        "refine_denoise_default": 0.25,

        "base_unet_task": "ref2va",
        "refine_unet_task": "fl2va",
        "main_lora_cross_form": True,
        "post_sample_in_scope": ["refine_chain_18_24", "face_refine_27"],
        "post_sample_out_of_scope": ["selflift_26", "third_party_sampler"],
        "third_party_sampler": False,
        "submit_gap_base": 5,
        "note": "原生音画同步+多段一气呵成；r2v 已确认；加速可关（默认关+20步）；默认 plus 防 OOM；"
                "二次采样/脸部修复为生成后采样（走结果卡悬挂图标面板）",
    },
}

_FALLBACK_LIMITS = {
    "label": "", "sizes": ["480p"],
    "min_seconds": 1, "max_seconds": 15,
    "max_images": 9, "max_audios": 3, "max_videos": 3, "allow_video": True,
    "submit_gap_base": 5,
    "note": "未识别的 RunningHub H3 变体：口径按 H3 已登记表取（不发明数字）",
}


def limits(model):
    
    lim = VIDEO_MODEL_LIMITS.get(str(model or "").strip())
    return dict(lim) if lim else dict(_FALLBACK_LIMITS, label=str(model or "").strip())



def ceil32(x):
    return int(math.ceil(float(x) / 32.0) * 32)


def ratio_value(r):
    
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)", str(r or ""))
    if not m:
        return 16 / 9
    a, b = float(m.group(1)), float(m.group(2))
    return a / b if b else 16 / 9


def mp_to_pixels(mp, aspect_ratio):
    
    ar = str(aspect_ratio or "").strip()
    if ar in ("16:9", "16:9 (宽屏)"):
        hit = _MP_STEPS_16X9.get(float(mp))
        if hit:
            return list(hit)
    r = ratio_value(ar)
    w = ceil32(math.sqrt(float(mp) * 1e6 * r))
    h = ceil32(float(mp) * 1e6 / w)
    return [w, h]



def task_type_for_mode(mode):
    
    return TASK_TYPES.get(str(mode or "reference").strip(), TASK_TYPES["reference"])


def _clamp_seconds(sec, lim):
    
    lo = int(lim.get("min_seconds") or 1)
    hi = int(lim.get("max_seconds") or 15)
    try:
        v = int(round(float(sec)))
    except (TypeError, ValueError):
        v = 5
    return max(lo, min(hi, v))


def _frame_count(duration_sec, frame_rate=24):
    return int(round(float(duration_sec) * int(frame_rate)))


def build_timeline_data(data, file_names=None):
    
    file_names = file_names or {}
    fn = file_names
    lim = limits(data.get("model"))
    mode = str(data.get("mode") or "reference").strip()
    seconds = _clamp_seconds(data.get("seconds"), lim)
    frame_rate = int(lim.get("frame_rate") or 24)
    ar = str(data.get("aspect_ratio") or lim["default_aspect_ratio"]).strip()
    size_label = str(data.get("size") or "").strip()
    mp = _SIZE_TO_MP.get(size_label)
    if mp is None:
        mp = float(data.get("megapixels") or lim["default_megapixels"])
    w, h = mp_to_pixels(mp, ar)


    segs_in = data.get("segments") or []
    segments = []
    cursor = 0
    if segs_in:
        for i, s in enumerate(segs_in):
            dur = _clamp_seconds(s.get("seconds") or s.get("durationSec"), lim)
            fc = _frame_count(dur, frame_rate)
            segments.append({
                "id": f"seg{i}",
                "start": cursor,
                "length": fc,
                "frameCount": fc,
                "durationSec": dur,
                "prompt": str(s.get("prompt") or ""),
                "negativePrompt": str(s.get("negative_prompt") or s.get("negativePrompt") or ""),
                "taskType": "",
                "refs": [], "refAudios": [], "refVideos": [],
                "genImage": {"imageFile": "", "fileName": ""},
                "startImage": s.get("start_image") or s.get("startImage"),
                "endImage": s.get("end_image") or s.get("endImage"),
                "continuityFromPrev": bool(cursor) and bool(s.get("continuity", True)),
                "refImageSize": "match",
                "loras": [],
            })
            cursor += fc
    else:
        fc = _frame_count(seconds, frame_rate)
        segments.append({
            "id": "seg0",
            "start": 0,
            "length": fc,
            "frameCount": fc,
            "durationSec": seconds,
            "prompt": str(data.get("prompt") or ""),
            "negativePrompt": str(data.get("negative_prompt") or data.get("negativePrompt") or ""),
            "taskType": "",
            "refs": [], "refAudios": [], "refVideos": [],
            "genImage": {"imageFile": "", "fileName": ""},
            "startImage": None, "endImage": None,
            "continuityFromPrev": False,
            "refImageSize": "match",
            "loras": [],
        })
        cursor = fc





    keyframes = []
    ff = (fn.get("first_frame") or (data.get("first_frame") and "first_frame.png"))
    lf = (fn.get("last_frame") or (data.get("last_frame") and "last_frame.png"))
    if mode == "keyframe":
        for _img, _is_ff in ((ff, True), (lf, False)):
            if not _img:
                continue
            keyframes.append({
                "id": f"kf{len(keyframes)}", "imageFile": _img, "fileName": "",
                "width": w, "height": h,
                "start": 0, "length": cursor, "frameCount": cursor,
                "durationSec": cursor / float(frame_rate),


                "prompt": "",
                "negativePrompt": str(data.get("negative_prompt") or ""),
                "isStartFrame": _is_ff, "isEndFrame": not _is_ff,
            })

        if not segs_in and segments:
            segments[0]["startImage"] = ff or None
            segments[0]["endImage"] = lf or None




    fn = file_names or {}
    src_imgs = [x for x in (data.get("images") or []) if x]
    src_auds = [x for x in (data.get("audios") or []) if x]
    src_vids = [x for x in (data.get("videos") or []) if x]
    imgs = [f for f in (fn.get("images") or [f"image_{i + 1}.png" for i in range(len(src_imgs))]) if f][: int(lim["max_images"])]
    auds = [f for f in (fn.get("audios") or [f"audio_{i + 1}.wav" for i in range(len(src_auds))]) if f][: int(lim["max_audios"])]
    vids = [f for f in (fn.get("videos") or [f"video_{i + 1}.mp4" for i in range(len(src_vids))]) if f][: int(lim["max_videos"])]
    refs = [{"index": i, "imageFile": f, "fileName": "", "type": "input", "subfolder": ""}
            for i, f in enumerate(imgs)]


    ref_audios = [{"index": i, "audioFile": f, "fileName": "", "type": "input", "subfolder": ""}
                  for i, f in enumerate(auds)]
    ref_videos = [{"index": i, "videoFile": f, "fileName": "", "type": "input", "subfolder": ""}
                  for i, f in enumerate(vids)]







    _bind = []
    if imgs:
        _bind.append("、".join(f"<Picture {i + 1}>" for i in range(len(imgs))))
    if auds:
        _bind.append("、".join(f"<Audio {i + 1}>" for i in range(len(auds))))
    if vids:
        _bind.append("、".join(f"<Video {i + 1}>" for i in range(len(vids))))
    global_prompt = ("参考素材：" + "；".join(_bind) + "。") if _bind else ""

    return {
        "version": 5,
        "editMode": "segment",
        "timelineMode": "segment",
        "totalFrames": cursor,
        "frameRate": frame_rate,
        "durationSec": cursor / float(frame_rate),
        "width": w, "height": h, "refMaxSize": max(w, h),
        "video": {"fileName": "", "videoFile": "", "subfolder": "", "type": "input",
                  "frames": [], "frameMap": []},




        "liveTaePreview": False,




        "segments": segments,
        "keyframes": keyframes,
        "global": {
            "taskType": task_type_for_mode(mode),

            "prompt": global_prompt,
            "refs": refs,
            "refAudios": ref_audios,
            "refVideos": ref_videos,
            "referenceVideo": {"videoFile": "", "fileName": "", "type": "input", "subfolder": ""},

            "continuousReference": False,
            "genImage": {"imageFile": "", "fileName": ""},
            "sourceWidth": w, "sourceHeight": h,
            "commonEnabled": True, "commonCollapsed": False,
        },
        "output": {
            "mode": "fixed",
            "aspectRatio": ar,
            "megapixels": float(mp),
            "multiple": int(lim["size_multiple"]),
            "longEdge": max(w, h),
            "width": w, "height": h,
            "maxExportFrames": 0,
            "exportMode": "all",
            "audioMode": "generate",
            "exportSourceImages": False,
            "exportPreFaceRefine": False,
            "refImageSize": "match",
            "continuityEnabled": len(segments) > 1,
            "continuityOverlapFrames": 22,
            "continuityMode": "continue",
            "continuityRedraw": 0.1,
            "continuityKeepTail": True,
        },
    }












_WF_TEMPLATE_JSON = r"""
{
 "1": {
  "inputs": {
   "unet_name": "minimax_h3_ref2va_bf16.safetensors",
   "weight_dtype": "default"
  },
  "class_type": "UNETLoader",
  "_meta": {
   "title": "MiniMax H3 UNET"
  }
 },
 "2": {
  "inputs": {
   "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
   "type": "minimax",
   "device": "default"
  },
  "class_type": "CLIPLoader",
  "_meta": {
   "title": "CLIP (minimax / Qwen3-VL)"
  }
 },
 "3": {
  "inputs": {
   "vae_name": "minimax_h3_video_vae_fp16.safetensors"
  },
  "class_type": "VAELoader",
  "_meta": {
   "title": "Video VAE"
  }
 },
 "4": {
  "inputs": {
   "vae_name": "minimax_h3_audio_vae_fp32.safetensors"
  },
  "class_type": "VAELoader",
  "_meta": {
   "title": "Audio VAE"
  }
 },
 "6": {
  "inputs": {
   "fps": [
    "12",
    2
   ],
   "bit_depth": 8,
   "color_space": "sRGB",
   "codec": "none",
   "images": [
    "12",
    0
   ],
   "audio": [
    "12",
    1
   ]
  },
  "class_type": "CreateVideo",
  "_meta": {
   "title": "Create Video"
  }
 },
 "7": {
  "inputs": {
   "filename_prefix": "video/MiniMaxH3_Director_t2v",
   "format": "auto",
   "format.codec": "auto",
   "codec": "auto",
   "fw_video_preview": "",
   "video": [
    "6",
    0
   ]
  },
  "class_type": "SaveVideo",
  "_meta": {
   "title": "Save Video"
  }
 },
 "12": {
  "inputs": {
   "task_type": "r2v — 参考主体生视频(Reference to Video)",
   "global_prompt": "",
   "bd_grp_sample": "采样设置",
   "cfg": 1,
   "seed": 666,
   "frame_rate": 24,
   "width": 864,
   "height": 480,
   "ref_max_size": 864,
   "total_frames": 384,
   "timeline_data": "{}",
   "bd_grp_advanced": "高级采样",
   "steps": 8,
   "sampler": "res_multistep",
   "scheduler": "simple",
   "shift_video": 12,
   "shift_audio": 3,
   "export_source_images": false,
   "export_pre_face_refine": false,
   "bd_grp_perf": "",
   "clear_vram_between_segments": "",
   "clear_vram_before_refine": "db24e5ebba4284bbd58a0606166d7ec9",
   "clear_vram_before_face_refine": "",
   "cache_frames_codec": "",
   "cache_name": "",
   "minimax_director_ui": "",
   "model": [
    "16",
    0
   ],
   "video_vae": [
    "3",
    0
   ],
   "audio_vae": [
    "4",
    0
   ],
   "clip": [
    "2",
    0
   ],
   "selflift": [
    "26",
    0
   ],
   "refine": [
    "18",
    0
   ],
   "face_refine": [
    "27",
    0
   ]
  },
  "class_type": "MiniMaxH3Director",
  "_meta": {
   "title": "MiniMaxH3Director"
  }
 },
 "16": {
  "inputs": {
   "model": [
    "17",
    0
   ]
  },
  "class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
  "_meta": {
   "title": "MiniMax H3 Memory Efficient Sage Attention Patch"
  }
 },
 "17": {
  "inputs": {
   "sage_attention": "disabled",
   "allow_compile": false,
   "model": [
    "25",
    0
   ]
  },
  "class_type": "PathchSageAttentionKJ",
  "_meta": {
   "title": "Patch Sage Attention KJ"
  }
 },
 "18": {
  "inputs": {
   "mode": "upscale",
   "upscale_method": "lanczos",
   "latent_upscale_model": 0.25,
   "sampler": "euler",
   "passes": 1,
   "seed_mode": "inherit",
   "seed": 0,
   "aspect_ratio": "跟随导演台",
   "megapixels": 1,
   "width": 768,
   "height": 720,
   "skip_fl2v": false,
   "confirm_first_pass": false,
   "enable_latent_chunking": 2,
   "enable_tiling": 128,
   "tile_count": 2,
   "tile_overlap": 128,
   "refine_model": [
    "23",
    0
   ],
   "sigmas": [
    "20",
    0
   ],
   "upscale_model": [
    "19",
    0
   ]
  },
  "class_type": "MiniMaxH3DirectorRefine",
  "_meta": {
   "title": "MiniMax H3 Director Refine"
  }
 },
 "19": {
  "inputs": {
   "model_name": "4x-UltraSharp.pth"
  },
  "class_type": "UpscaleModelLoader",
  "_meta": {
   "title": "Load Upscale Model"
  }
 },
 "20": {
  "inputs": {
   "scheduler": "beta",
   "steps": 3,
   "denoise": 0.25000000000000006,
   "model": [
    "23",
    0
   ]
  },
  "class_type": "BasicScheduler",
  "_meta": {
   "title": "BasicScheduler"
  }
 },
 "21": {
  "inputs": {
   "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
   "weight_dtype": "default"
  },
  "class_type": "UNETLoader",
  "_meta": {
   "title": "MiniMax H3 UNET"
  }
 },
 "22": {
  "inputs": {
   "sage_attention": "disabled",
   "allow_compile": false,
   "model": [
    "24",
    0
   ]
  },
  "class_type": "PathchSageAttentionKJ",
  "_meta": {
   "title": "Patch Sage Attention KJ"
  }
 },
 "23": {
  "inputs": {
   "model": [
    "22",
    0
   ]
  },
  "class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
  "_meta": {
   "title": "MiniMax H3 Memory Efficient Sage Attention Patch"
  }
 },
 "24": {
  "inputs": {
   "lora_name": "minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors",
   "strength_model": 1,
   "model": [
    "21",
    0
   ]
  },
  "class_type": "LoraLoaderModelOnly",
  "_meta": {
   "title": "Load LoRA"
  }
 },
 "25": {
  "inputs": {
   "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
   "strength_model": 1,
   "model": [
    "1",
    0
   ]
  },
  "class_type": "LoraLoaderModelOnly",
  "_meta": {
   "title": "Load LoRA"
  }
 },
 "26": {
  "inputs": {
   "bd_grp_selflift_sample": "渐进采样",
   "split_mode": "highres_steps",
   "highres_steps": 2,
   "transition_step": 6,
   "lowres_scale": 0.5,
   "sampler_mode": "euler",
   "native_low_carry": true,
   "bd_grp_selflift_lift": "提升 / 3D",
   "latent_upscale_model": "minimax_h3_latent_upscaler_3d_bf16.safetensors",
   "latent_upsample": "bilinear",
   "rho": 0,
   "w_min": 0.5,
   "w_max": 1,
   "enable_latent_chunking": false,
   "bd_grp_selflift_tile": "高清分块",
   "enable_tiling": false,
   "tile_count": 2,
   "tile_overlap": 128
  },
  "class_type": "MiniMaxH3DirectorSelfLift",
  "_meta": {
   "title": "MiniMax H3 Director SelfLift"
  }
 },
 "27": {
  "inputs": {
   "bd_grp_face_detect": "脸部检测设置",
   "detector": "face_yolov8m.pt",
   "confidence": 0.35,
   "crop_factor": 2.5,
   "canvas_width": 768,
   "canvas_height": 768,
   "canvas_mode": "manual",
   "select": "largest_face",
   "bd_grp_face_sample": "采样设置",
   "denoise": 0.4,
   "steps": 8,
   "sampler": "euler",
   "scheduler": "simple",
   "seed_mode": "inherit",
   "bd_grp_face_paste": "贴回设置",
   "paste_region": "face_only",
   "mask_dilation": 16,
   "feather": 24,
   "colour_match": 1,
   "blend": 1
  },
  "class_type": "MiniMaxH3DirectorFaceRefine",
  "_meta": {
   "title": "MiniMax H3 Director FaceRefine"
  }
 }
}"""


def workflow_template():
    
    return json.loads(_WF_TEMPLATE_JSON)


def build_workflow(data, timeline, file_names=None, accel=None, quality=None,
                   sampler=None, refine=None, face=None):
    
    wf = workflow_template()
    rf = refine or {}
    fc = face or {}
    lim = limits(data.get("model"))
    mode = str(data.get("mode") or "reference").strip()

    def inputs(nid):
        return wf[str(nid)]["inputs"]


    inputs(1)["unet_name"] = UNET_BY_MODE.get(mode, UNET_MAIN_REF2VA)




    inputs(25)["strength_model"] = 1 if accel else 0


    i12 = inputs(12)
    d12 = {n["fieldName"]: n["fieldValue"] for n in
           build_node_info(data, timeline, accel=accel, quality=quality, sampler=sampler,
                           include_post_sample=False)}
    for k, v in d12.items():
        i12[k] = v


    if str(rf.get("mode") or "off") == "off":
        i12.pop("refine", None)
    else:




        i18 = inputs(18)
        _rp = {p["key"]: p for p in (lim.get("post_refine", {}).get("params") or [])}

        def _rpv(k):
            v = rf.get(k)
            if v is None or str(v).strip() == "":
                return (_rp.get(k) or {}).get("default")
            return v

        _m = str(_rpv("mode") or "upscale")
        i18["mode"] = _m
        if _m in ("upscale", "latent_upscale"):
            i18["megapixels"] = float(_rpv("mp"))
        i18["passes"] = max(1, int(_rpv("passes")))
        i18["skip_fl2v"] = True
        _um = _rpv("upscale_method")
        if _um:
            i18["upscale_method"] = str(_um)
        if _m in ("refine", "upscale"):
            inputs(20)["steps"] = int(_rpv("steps"))
            inputs(20)["denoise"] = float(_rpv("denoise"))

    if not fc.get("enabled"):
        i12.pop("face_refine", None)
    else:



        i27 = inputs(27)
        _fp = {p["key"]: p for p in (lim.get("post_face", {}).get("params") or [])}

        def _fpv(k):
            v = fc.get(k)
            if v is None or str(v).strip() == "":
                return (_fp.get(k) or {}).get("default")
            return v

        for _k in ("steps", "mask_dilation", "feather"):
            _v = _fpv(_k)
            if _v is not None:
                i27[_k] = int(_v)
        for _k in ("denoise", "confidence"):
            _v = _fpv(_k)
            if _v is not None:
                i27[_k] = float(_v)
        for _k in ("select", "paste_region"):
            _v = _fpv(_k)
            if _v is not None:
                i27[_k] = str(_v)


    i12.pop("selflift", None)








    i12["global_prompt"] = ""
    for k in ("bd_grp_sample", "bd_grp_advanced", "bd_grp_perf",
              "clear_vram_between_segments", "clear_vram_before_refine", "clear_vram_before_face_refine",
              "cache_frames_codec", "cache_name", "minimax_director_ui",
              "export_source_images", "export_pre_face_refine",
              "strength_model", "unet_name"):
        i12.pop(k, None)


    if str(rf.get("mode") or "off") == "off":
        for nid in ("18", "19", "20", "21", "22", "23", "24"):
            wf.pop(nid, None)
    if not fc.get("enabled"):
        wf.pop("27", None)

    sl = (data.get("selflift") or {})
    if sl.get("enabled") and "26" in wf:
        _t = str(data.get("quality_tier") or "hq")
        tier = _t if _t in ("hq", "hq25", "fast") else ("fast" if accel else "hq")
        _steps_map = lim.get("steps_by_tier") or {"hq": 20, "hq25": 25, "fast": 8}
        total = int(_steps_map.get(tier) or (8 if accel else 20))
        _sl_lim = lim.get("selflift") or {}
        _sl_def = _sl_lim.get("default") or {}
        _sl_params = {p["key"]: p for p in (_sl_lim.get("params") or [])}
        _hi_def = (_sl_def.get("highres") or {}).get(tier, 5)

        _hi_raw = sl.get("highres")
        if isinstance(_hi_raw, dict):
            hi = int(_hi_raw.get(tier) or _hi_def)
        else:
            hi = int(_hi_raw or _hi_def)
        hi = max(1, min(total - 1, hi))
        i12["selflift"] = ["26", 0]
        i26 = inputs(26)
        i26["split_mode"] = "highres_steps"
        i26["highres_steps"] = hi




        i26["transition_step"] = total - hi
        _sc_def = (_sl_params.get("scale") or {}).get("default", 0.5)
        i26["lowres_scale"] = float(sl.get("scale") if sl.get("scale") is not None else _sc_def)
        i26["sampler_mode"] = "euler"






        i26["native_low_carry"] = True
        i26["rho"] = 0
        i26["enable_tiling"] = False

        if _sl_lim.get("latent_upscale_model"):
            i26["latent_upscale_model"] = _sl_lim["latent_upscale_model"]

        _lu = sl.get("latent_upsample")
        if _lu is None or str(_lu).strip() == "":
            _lu = (_sl_params.get("latent_upsample") or {}).get("default") or "bilinear"
        i26["latent_upsample"] = str(_lu)
    else:
        i12.pop("selflift", None)
        wf.pop("26", None)





    return prune_to_outputs(wf, roots=("7",))


def prune_to_outputs(wf, roots=("7",)):
    
    keep, stack = set(), [str(r) for r in roots]
    while stack:
        nid = stack.pop()
        if nid in keep or nid not in wf:
            continue
        keep.add(nid)
        for v in (wf[nid].get("inputs") or {}).values():

            if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str) and v[0] in wf:
                stack.append(v[0])
    return {k: v for k, v in wf.items() if k in keep}


def _seed_of(data, sampler=None):
    
    s = sampler or {}
    v = s.get("seed")
    if v is None:
        v = data.get("seed")
    if v is None or str(v).strip() == "":
        import random as _rnd
        v = _rnd.randint(1, 2 ** 31 - 1)
    return int(v)


def _sampler_defaults(data, accel, sampler=None):
    
    lim = limits(data.get("model"))
    out = dict(sampler or {})
    if not out.get("steps"):
        tier = str(data.get("quality_tier") or ("fast" if accel else "hq"))
        m = lim.get("steps_by_tier") or {"hq": 20, "hq25": 25, "fast": 8}
        out["steps"] = int(m.get(tier) or (lim.get("steps_with_accel") if accel else lim.get("default_steps")) or (8 if accel else 20))
    out.setdefault("shift_video", 12)
    out.setdefault("shift_audio", 3)
    return out


def build_node_info(data, timeline, accel=None, quality=None, sampler=None,
                    include_post_sample=False, refine=None, face=None):
    
    accel = lim_default_accel() if accel is None else bool(accel)
    quality = quality or {}
    sampler = sampler or {}
    lim = limits(data.get("model"))

    steps = sampler.get("steps")
    if steps is None:
        steps = int(lim.get("steps_with_accel") or 8) if accel else int(lim.get("default_steps") or 20)
    shift_v = sampler.get("shift_video")
    shift_a = sampler.get("shift_audio")
    if shift_v is None or shift_a is None:

        shift_v, shift_a = 12, 3

    total_frames = int(timeline.get("totalFrames") or 0)
    w, h = int(timeline["width"]), int(timeline["height"])

    _mode = str(data.get("mode") or "reference").strip()
    nodes = [

        {"nodeId": N_MAIN_UNET, "fieldName": "unet_name",
         "fieldValue": UNET_BY_MODE.get(_mode, UNET_MAIN_REF2VA)},

        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "task_type",
         "fieldValue": task_type_for_mode(data.get("mode"))},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "steps", "fieldValue": int(steps)},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "sampler",
         "fieldValue": sampler.get("sampler") or limits(data.get("model")).get("sampler") or "res_multistep"},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "scheduler",
         "fieldValue": sampler.get("scheduler") or limits(data.get("model")).get("scheduler") or "simple"},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "cfg", "fieldValue": int(sampler.get("cfg") or 1)},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "shift_video", "fieldValue": int(shift_v)},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "shift_audio", "fieldValue": int(shift_a)},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "seed",
         "fieldValue": int(_seed_of(data, sampler))},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "frame_rate", "fieldValue": int(lim["frame_rate"])},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "width", "fieldValue": w},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "height", "fieldValue": h},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "ref_max_size", "fieldValue": max(w, h)},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "total_frames", "fieldValue": total_frames},
        {"nodeId": N_MAIN_DIRECTOR, "fieldName": "timeline_data",
         "fieldValue": json.dumps(timeline, ensure_ascii=False)},






        {"nodeId": N_LORA_MAIN, "fieldName": "strength_model", "fieldValue": 1 if accel else 0},
    ]


    if not include_post_sample:
        return nodes
    rf = refine or {}
    fc = face or {}
    rs = int(quality.get("refine_steps") or lim.get("refine_steps_default") or 3)
    fs = int(quality.get("face_steps") or lim.get("face_steps_default") or 8)
    rlo, rhi = lim.get("refine_steps_range") or [1, 30]
    flo, fhi = lim.get("face_steps_range") or [1, 30]
    rs = max(int(rlo), min(int(rhi), rs))
    fs = max(int(flo), min(int(fhi), fs))






    rf_mode = str(rf.get("mode") or "off")
    if rf_mode in ("refine", "upscale", "latent_upscale"):
        nodes.append({"nodeId": N_REFINE, "fieldName": "mode", "fieldValue": rf_mode})

        if rf_mode in ("upscale", "latent_upscale"):
            nodes.append({"nodeId": N_REFINE, "fieldName": "megapixels",
                          "fieldValue": float(rf.get("mp") or lim.get("refine_megapixels") or 1.0)})

        nodes.append({"nodeId": N_REFINE, "fieldName": "passes",
                      "fieldValue": max(1, int(rf.get("passes") or 1))})

        nodes.append({"nodeId": N_REFINE, "fieldName": "skip_fl2v", "fieldValue": True})

        if rf_mode in ("refine", "upscale"):
            nodes += [
                {"nodeId": "20", "fieldName": "steps",
                 "fieldValue": int(rf.get("steps") or rs)},
                {"nodeId": "20", "fieldName": "denoise",
                 "fieldValue": float(rf.get("denoise") if rf.get("denoise") is not None
                                     else (quality.get("refine_denoise")
                                           or lim.get("refine_denoise_default") or 0.25))},
            ]

    if fc.get("enabled"):
        nodes += [
            {"nodeId": N_FACE, "fieldName": "steps",
             "fieldValue": int(fc.get("steps") or fs)},
            {"nodeId": N_FACE, "fieldName": "denoise",
             "fieldValue": float(fc.get("denoise") if fc.get("denoise") is not None
                                 else (quality.get("face_denoise")
                                       or lim.get("face_denoise_default") or 0.4))},

            {"nodeId": N_FACE, "fieldName": "paste_region", "fieldValue": "face_only"},
        ]
    return nodes


def lim_default_accel():
    return not bool(VIDEO_MODEL_LIMITS[RH_ID].get("default_accel_off", True))


def build_submission(data, file_names=None, accel=None, quality=None, sampler=None, instance=None):
    
    if not str(data.get("prompt") or "").strip():
        return None, "请填写提示词。"
    lim = limits(data.get("model"))
    mode = str(data.get("mode") or "reference").strip()


    if mode == "keyframe":


        _has_ff = bool((file_names or {}).get("first_frame") or data.get("first_frame"))
        _has_lf = bool((file_names or {}).get("last_frame") or data.get("last_frame"))
        if not (_has_ff or _has_lf):
            return None, "首尾帧模式至少需要提供首帧或尾帧图片。"
    if mode == "reference":
        n_img = len([x for x in (data.get("images") or []) if x])
        n_aud = len([x for x in (data.get("audios") or []) if x])
        n_vid = len([x for x in (data.get("videos") or []) if x])
        if not (n_img or n_aud or n_vid):
            return None, "全能参考模式至少需要提供一张参考图片、一个参考音频或一段参考视频。"
        if n_img > int(lim["max_images"]):
            return None, f"参考图最多 {lim['max_images']} 张（ref2va 官方上限）。"
        if n_aud > int(lim["max_audios"]):
            return None, f"参考音频最多 {lim['max_audios']} 段（ref2va 官方上限）。"
        if n_vid > int(lim["max_videos"]):
            return None, f"参考视频最多 {lim['max_videos']} 段（ref2va 官方上限）。"

    timeline = build_timeline_data(data, file_names=file_names)
    _rf = data.get("refine") or {}
    _fc = data.get("face") or {}
    sampler = _sampler_defaults(data, accel, sampler)








    wf = build_workflow(data, timeline, file_names=file_names, accel=accel,
                        quality=quality, sampler=sampler, refine=_rf, face=_fc)
    inst = str(instance or data.get("instance") or lim["default_instance"]).strip().lower()
    if inst not in ("default", "plus", "ultra"):
        inst = str(lim["default_instance"])
    payload = {
        "apiKey": "<REDACTED — 由路由侧注入>",


        "workflowId": WORKFLOW_ID,
        "apiType": API_TYPE,
        "workflow": json.dumps(wf, ensure_ascii=False),
        "instanceType": inst,
        "nodeInfoList": [],
    }
    return payload, None



_STATUS_MAP = {


    "QUEUED": "queued", "RUNNING": "processing", "PROCESSING": "processing",
    "SUCCESS": "done", "SUCCEEDED": "done", "COMPLETED": "done",
    "FAILED": "failed", "FAIL": "failed", "ERROR": "failed", "CANCELED": "failed",
}


def parse_status(body):
    
    if not isinstance(body, dict):
        return {"status": "processing"}

    if body.get("status") and "results" in body:
        raw2 = str(body.get("status") or "").upper()
        out2 = {"status": _STATUS_MAP.get(raw2, "processing"), "video_url": None, "failed_reason": None}
        if out2["status"] == "done":
            for it in (body.get("results") or []):
                if isinstance(it, dict) and (it.get("url") or it.get("fileUrl")):
                    out2["video_url"] = it.get("url") or it.get("fileUrl")
                    break
        elif out2["status"] == "failed":
            fr = body.get("failedReason") or body.get("errorMessage")
            out2["failed_reason"] = (str(fr) if fr else None)
        return out2
    data = body.get("data")
    if isinstance(data, str):
        raw = data.upper()
        holder = {}
    elif isinstance(data, dict):
        raw = str(data.get("status") or data.get("taskStatus") or "").upper()
        holder = data
    else:
        raw = str(body.get("status") or "").upper()
        holder = body
    try:
        code = int(body.get("code")) if body.get("code") is not None else 0
    except (TypeError, ValueError):
        code = 0
    out = {"status": _STATUS_MAP.get(raw, "processing"), "video_url": None, "failed_reason": None}
    if code not in (0, 200):
        out["status"] = "failed"
        out["failed_reason"] = str(body.get("msg") or body.get("message") or f"code={code}")
        return out
    if out["status"] == "done":
        out["video_url"] = (holder.get("fileUrl") or holder.get("video_url") or holder.get("url")
                            or body.get("fileUrl"))
    elif out["status"] == "failed":


        _m = body.get("msg")
        if str(_m).strip().lower() in ("success", "ok", ""):
            _m = None
        out["failed_reason"] = (holder.get("failedReason") or holder.get("error")
                                or holder.get("errorMessage") or _m)
    return out


def parse_usage(body):
    
    items = []
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        data = body.get("data")
        items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    for it in items:
        if not isinstance(it, dict):
            continue
        coins = it.get("consumeCoins")
        secs = it.get("taskCostTime")
        money = it.get("consumeMoney")
        if coins not in (None, "", "0") or secs not in (None, ""):
            try:
                return {"coins": int(float(coins)) if coins not in (None, "") else None,
                        "seconds": int(float(secs)) if secs not in (None, "") else None,
                        "money": money}
            except (TypeError, ValueError):
                return {"coins": coins, "seconds": secs, "money": money}
    return None


def parse_outputs(body):
    
    if isinstance(body, list):
        items, reason = body, None
    elif isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            items = [body]
        reason = body.get("msg") if body.get("msg") not in ("success", None) else None
    else:
        return None, "无法解析上游响应"
    for it in items:
        if not isinstance(it, dict):
            continue
        url = it.get("fileUrl") or it.get("url") or it.get("video_url")
        if url:
            return url, None
        reason = reason or it.get("failedReason") or it.get("error")

    if isinstance(body, dict):
        fr = body.get("failedReason") or body.get("errorMessages")
        if fr:
            try:
                reason = (str(fr) if not isinstance(fr, (dict, list))
                          else "; ".join(f"{k}: {v}" for k, v in fr.items()) if isinstance(fr, dict)
                          else "; ".join(str(x) for x in fr))
            except Exception:
                reason = str(fr)
    return None, reason or "上游未返回产物地址"



_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")
_META_PREFIX = "rh:"
_LOCK = threading.RLock()
ENV_KEYS = {
    "api_key": "RUNNINGHUB_API_KEY",
    "enabled": "RUNNINGHUB_ENABLED",
    "workflow_id": "RUNNINGHUB_WORKFLOW_ID",
    "base_url": "RUNNINGHUB_BASE_URL",
}


def _conn():
    conn = sqlite3.connect(_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _meta_get(key, default=None):
    with _LOCK:
        try:
            conn = _conn()
        except sqlite3.Error:
            return default
        try:
            row = conn.execute("SELECT value FROM meta WHERE key=?",
                               (_META_PREFIX + key,)).fetchone()
            return row["value"] if row else default
        except sqlite3.OperationalError:
            return default
        finally:
            conn.close()


def _meta_set(key, value):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO meta(key, value) VALUES(?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (_META_PREFIX + key, value))
            conn.commit()
        finally:
            conn.close()


def _load_env_once():
    p = os.path.join(_ROOT, ".env")
    if not os.path.exists(p):
        return
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k in ENV_KEYS.values() and k not in os.environ:
                    os.environ[k] = v.strip().strip("\"'")
    except Exception:
        pass


_load_env_once()


def get(key, default=None):
    
    v = _meta_get(key)
    if v in (None, ""):
        env = ENV_KEYS.get(key)
        v = os.environ.get(env) if env else None
    return default if v in (None, "") else v


def save(patch):
    
    allowed = {"enabled", "video_enabled", "api_key", "workflow_id", "base_url"}
    for k, v in (patch or {}).items():
        if k not in allowed:
            continue
        _meta_set(k, "1" if (k in ("enabled", "video_enabled") and v) else ("" if v in (None, "") else str(v)))


def api_key():
    return str(get("api_key") or "")


def ready():
    
    on = str(get("enabled") or "").strip().lower()
    master = on in ("1", "true", "yes", "on") if on else False
    return bool(master or video_enabled()) and bool(api_key())


def video_enabled():
    
    v = _meta_get("video_enabled")
    if v in (None, ""):
        v = os.environ.get("RUNNINGHUB_VIDEO_ENABLED")
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def video_ready():
    
    return video_enabled() and bool(api_key())


def is_video_model(model):
    return str(model or "").strip() == RH_ID


def video_models():
    return [RH_ID]


def key_fp(k=None):
    
    k = str(api_key() if k is None else k or "")
    return f"{k[:4]}…{k[-4:]}(len={len(k)})" if k else "(empty)"


def mask_key(k):
    k = str(k or "")
    return f"{k[:3]}…{k[-4:]}" if len(k) > 8 else ("****" if k else "")


def dry_run(data, **kw):
    
    payload, err = build_submission(data, **kw)
    if err:
        return {"ok": False, "error": err}
    body = dict(payload)
    body.pop("apiKey", None)
    return {"ok": True, "workflowId": WORKFLOW_ID, "apiType": API_TYPE,
            "instanceType": body["instanceType"], "nodeInfoList": body["nodeInfoList"],
            "node_count": len(body["nodeInfoList"])}



def submit(payload, timeout=(10, 600)):
    
    import requests


    key = str(api_key() or "").strip()
    if not key:
        return None, "RunningHub 未配置 API Key。"
    body = dict(payload)
    body["apiKey"] = key
    base = str(get("base_url") or BASE_URL).rstrip("/")
    try:
        resp = requests.post(f"{base}/task/openapi/create", json=body,
                             headers={"Content-Type": "application/json"}, timeout=timeout)
    except requests.RequestException as e:
        return None, f"请求 RunningHub 失败：{e}"
    try:
        out = resp.json()
    except Exception:
        return None, f"无法解析 RunningHub 响应：{resp.text[:200]}"
    if resp.status_code != 200:
        return None, f"RunningHub 拒绝请求（{resp.status_code}）：{str(out)[:200]}"
    return out, None


def poll_status(task_id, timeout=30):
    
    import requests
    base = str(get("base_url") or BASE_URL).rstrip("/")
    try:

        resp = requests.post(f"{base}/task/openapi/status",
                             json={"apiKey": api_key(), "taskId": str(task_id).strip()},
                             headers={"Content-Type": "application/json"}, timeout=timeout)
    except requests.RequestException as e:
        return None, f"RunningHub 查询失败：{e}"
    try:
        body = resp.json()
    except Exception:
        return None, f"RunningHub 状态响应无法解析（{resp.status_code}）：{resp.text[:200]}"
    _msg = str(body.get("msg") or "") if isinstance(body, dict) else ""
    _code = str(body.get("code") or "") if isinstance(body, dict) else ""
    _bad = (resp.status_code != 200) or (_code not in ("0", "200", "")) or ("APIKEY_TASK_STATUS_ERROR" in _msg)
    if _bad:



        print(f"[runninghub] 旧族 status 失败（{resp.status_code} {_code} {_msg[:80]}）→ 试 v2/query，key={key_fp()}")
        try:
            r2 = requests.post(f"{base}/openapi/v2/query",
                               json={"taskId": str(task_id).strip()},
                               headers={"Authorization": f"Bearer {api_key()}",
                                        "Content-Type": "application/json"}, timeout=timeout)
            b2 = r2.json()
            if r2.status_code == 200 and isinstance(b2, dict) and b2.get("status"):
                print(f"[runninghub] v2/query 命中：{str(b2)[:200]}")
                return b2, None
            return None, (f"RunningHub 查不到任务（旧族 {resp.status_code}/{_code} {_msg[:80]}；"
                          f"新族 {r2.status_code} {str(b2)[:120]}）key={key_fp()}")
        except requests.RequestException as e:
            return None, f"RunningHub 状态查询失败：{e}（key={key_fp()}）"
    return body, None


def fetch_account(key=None, base_url=None, timeout=20):
    
    import requests

    key = str(key or api_key() or "").strip()
    if not key:
        return None, "RunningHub 未配置 API Key。"
    base = str(base_url or get("base_url") or BASE_URL).rstrip("/")
    try:
        r = requests.post(f"{base}/uc/openapi/accountStatus",
                          json={"apikey": key},
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          timeout=timeout)
    except requests.RequestException as e:
        return None, f"查询账户失败：{e}"
    if r.status_code != 200:
        return None, f"账户接口返回 HTTP {r.status_code}"
    try:
        body = r.json()
    except Exception:
        return None, "账户接口响应无法解析"
    if int(body.get("code") or 0) != 0:
        return None, str(body.get("msg") or "账户接口返回错误")
    d = body.get("data") or {}
    return {"api_type": d.get("apiType"), "coins": d.get("remainCoins"),
            "money": d.get("remainMoney"), "currency": d.get("currency"),
            "running": d.get("currentTaskCounts")}, None


def cancel(task_id, timeout=20):
    
    import requests
    key = str(api_key() or "").strip()
    if not key:
        return False, "RunningHub 未配置 API Key。"
    base = str(get("base_url") or BASE_URL).rstrip("/")
    try:
        r = requests.post(f"{base}/task/openapi/cancel",
                          json={"apiKey": key, "taskId": str(task_id).strip()},
                          headers={"Content-Type": "application/json"}, timeout=timeout)
    except requests.RequestException as e:
        return False, f"取消请求失败：{e}"
    try:
        body = r.json()
    except Exception:
        return False, f"取消响应无法解析（{r.status_code}）"
    code = str(body.get("code"))
    msg = str(body.get("msg") or "")
    if r.status_code == 200 and code in ("0", "200"):
        return True, ""
    if code == "807" or "TASK_NOT_FOUND" in msg:
        return True, ""
    return False, f"{code} {msg}".strip()


def fetch_workflow_json(workflow_id=None, timeout=30):
    
    import requests
    key = api_key()
    if not key:
        return None, "RunningHub 未配置 API Key。"
    base = str(get("base_url") or BASE_URL).rstrip("/")
    wid = str(workflow_id or get("workflow_id") or WORKFLOW_ID)
    for method in ("post", "get"):
        try:
            if method == "post":
                r = requests.post(f"{base}/api/openapi/getJsonApiFormat",
                                  json={"apiKey": key, "workflowId": wid}, timeout=timeout)
            else:
                r = requests.get(f"{base}/api/openapi/getJsonApiFormat",
                                 params={"apiKey": key, "workflowId": wid}, timeout=timeout)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        try:
            body = r.json()
        except Exception:
            continue
        wf = body.get("data") if isinstance(body.get("data"), dict) else body
        if isinstance(wf, dict) and wf and all(isinstance(v, dict) and "class_type" in v for v in wf.values()):
            return wf, None
    return None, "拿不到线上工作流 JSON（接口名/权限待确认）"


def workflow_nodes(workflow_id=None):
    
    wf, err = fetch_workflow_json(workflow_id)
    if err:
        return None, err
    out = []
    for nid in sorted(wf.keys(), key=lambda x: int(x) if str(x).isdigit() else 9999):
        v = wf[nid] or {}
        out.append({"nodeId": str(nid), "class_type": v.get("class_type"),
                    "title": (v.get("_meta") or {}).get("title", "")})
    return out, None


def fetch_outputs(task_id, timeout=30):
    import requests
    base = str(get("base_url") or BASE_URL).rstrip("/")
    try:
        resp = requests.post(f"{base}/task/openapi/outputs",
                             json={"apiKey": api_key(), "taskId": str(task_id).strip()},
                             headers={"Content-Type": "application/json"}, timeout=timeout)
        return resp.json(), None
    except requests.RequestException as e:
        return None, f"查询失败：{e}"
