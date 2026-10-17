




TTS_PROVIDERS = (
    {"key": "mimo", "label": "小米 MiMo"},
    {"key": "openrouter", "label": "OpenRouter"},
)
TTS_PROVIDER_ORDER = tuple(p["key"] for p in TTS_PROVIDERS)
TTS_PROVIDER_LABELS = {p["key"]: p["label"] for p in TTS_PROVIDERS}

TTS_PROVIDER_HOSTS = tuple(k for k in TTS_PROVIDER_ORDER if k != "openrouter")

TTS_BASE_PROVIDER = "openrouter"


def resolve_tts_provider(enabled, ready):
    
    en = [k for k in TTS_PROVIDER_ORDER
          if k in TTS_PROVIDER_HOSTS and k in set(enabled or ())]
    selected = en[0] if en else TTS_BASE_PROVIDER
    rd = {k: bool((ready or {}).get(k)) for k in TTS_PROVIDER_ORDER}
    rd[TTS_BASE_PROVIDER] = True
    winner = selected if rd.get(selected) else TTS_BASE_PROVIDER
    conflict = len(en) > 1
    fallback = winner != selected
    if fallback:
        note = ("已选定「%s」，但它尚未就绪（未开启或未配置密钥）→ 音频生成实际仍走「%s」。"
                % (TTS_PROVIDER_LABELS[selected], TTS_PROVIDER_LABELS[winner]))
    elif conflict:
        note = ("检测到多家同时开启（%s），已按优先级取「%s」；"
                "保存一次「音频服务商」即可收敛为一家。"
                % ("、".join(TTS_PROVIDER_LABELS[k] for k in en), TTS_PROVIDER_LABELS[winner]))
    else:
        note = ""
    return {"winner": winner, "selected": selected, "enabled": en,
            "conflict": conflict, "fallback": fallback, "ready": rd, "note": note}








_OPENROUTER_SPEED_VALUES = [round(0.25 * i, 2) for i in range(1, 17)]


def _speed_options(values, with_instruction=False):
    return [{"value": v, "label": ("%g×" % v)} for v in values]









































_TAG_GROUPS_ALL = ("emotion", "emotion_plus", "tone", "timbre", "persona",
                   "dialect", "role", "pace", "state", "voice", "cry")




_TAG_GROUPS_SING = _TAG_GROUPS_ALL + ("sing",)











MIMO_PRESET_VOICES = (
    {"id": "mimo_default", "name": "MiMo-默认", "lang": "", "gender": "",
     "note": "实际音色随部署集群（中国集群为「冰糖」）"},
    {"id": "冰糖", "name": "冰糖", "lang": "中文", "gender": "女", "note": ""},
    {"id": "茉莉", "name": "茉莉", "lang": "中文", "gender": "女", "note": ""},
    {"id": "苏打", "name": "苏打", "lang": "中文", "gender": "男", "note": ""},
    {"id": "白桦", "name": "白桦", "lang": "中文", "gender": "男", "note": ""},
    {"id": "Mia", "name": "Mia", "lang": "英文", "gender": "女", "note": ""},
    {"id": "Chloe", "name": "Chloe", "lang": "英文", "gender": "女", "note": ""},
    {"id": "Milo", "name": "Milo", "lang": "英文", "gender": "男", "note": ""},
    {"id": "Dean", "name": "Dean", "lang": "英文", "gender": "男", "note": ""},
)

TTS_MODELS = {




    "fish-audio/s2.1-pro-free:free": {
        "provider": "openrouter",
        "label": "通用配音",
        "caps": {

            "ref": {"mode": "optional", "formats": [], "maxBytes": 15 * 1024 * 1024},
            "preset": {"mode": "builtin"},
            "design": None,
            "speed": {"options": _speed_options(_OPENROUTER_SPEED_VALUES)},
            "tag_groups": (),
            "prompt_target": "assistant",
            "optimize_text_preview": False,
            "stream": False,
        },
    },







    "mimo-v2.5-tts": {
        "provider": "mimo",
        "label": "官方配音",
        "caps": {


            "ref": {"mode": "none", "formats": [], "maxBytes": 0},


            "preset": {"mode": "list", "voices": MIMO_PRESET_VOICES, "default": "mimo_default"},
            "design": None,
            "speed": None,
            "tag_groups": _TAG_GROUPS_SING,
            "prompt_target": "assistant",


            "optimize_text_preview": False,


            "stream": False,
        },
    },
    "mimo-v2.5-tts-voiceclone": {
        "provider": "mimo",
        "label": "参考配音",
        "caps": {

            "ref": {"mode": "required", "formats": ["mp3", "wav"],
                    "maxBytes": 7400000, "maxB64": 10 * 1000 * 1000},
            "preset": None,
            "design": None,
            "speed": None,
            "tag_groups": _TAG_GROUPS_ALL,
            "prompt_target": "assistant",
            "optimize_text_preview": False,
            "stream": False,
        },
    },
    "mimo-v2.5-tts-voicedesign": {
        "provider": "mimo",
        "label": "自定义配音",
        "caps": {

            "ref": {"mode": "none", "formats": [], "maxBytes": 0},
            "preset": None,
            "design": {"field": "prompt", "required": True},
            "speed": None,
            "tag_groups": _TAG_GROUPS_ALL,
            "prompt_target": "user",

            "optimize_text_preview": True,
            "stream": False,
        },
    },
}




PROVIDER_DEFAULT_CAPS = {
    "openrouter": {
        "provider": "openrouter",
        "label": "",
        "caps": {
            "ref": {"mode": "optional", "formats": [], "maxBytes": 15 * 1024 * 1024},
            "preset": {"mode": "builtin"},
            "design": None,
            "speed": {"options": _speed_options(_OPENROUTER_SPEED_VALUES)},
            "tag_groups": (),
            "prompt_target": "assistant",
            "optimize_text_preview": False,
            "stream": False,
        },
    },
    "mimo": {
        "provider": "mimo",
        "label": "",
        "caps": {
            "ref": {"mode": "optional", "formats": ["mp3", "wav"],
                    "maxBytes": 7400000, "maxB64": 10 * 1000 * 1000},
            "preset": None,
            "design": None,
            "speed": None,
            "tag_groups": _TAG_GROUPS_ALL,
            "prompt_target": "assistant",
            "optimize_text_preview": False,
            "stream": False,
        },
    },
}


def model_entry(model_id, provider):
    
    mid = str(model_id or "").strip()
    ent = TTS_MODELS.get(mid)
    if ent:
        return {"provider": ent["provider"], "label": ent.get("label") or mid,
                "caps": ent["caps"], "registered": True}
    d = PROVIDER_DEFAULT_CAPS.get(str(provider or "").strip().lower()) \
        or PROVIDER_DEFAULT_CAPS[TTS_BASE_PROVIDER]
    return {"provider": d["provider"], "label": mid, "caps": d["caps"], "registered": False}





PARAM_CAP = {
    "speed": "speed",
    "voice_desc": "design",
    "preset_voice": "preset",
    "audio_url": "ref",
}

NON_PARAM_CAPS = frozenset({"tag_groups", "prompt_target", "optimize_text_preview", "stream"})


def param_cap_map():
    
    return dict(PARAM_CAP)


def caps_for(model_id, provider):
    
    return model_entry(model_id, provider)["caps"]


def model_label(model_id, provider):
    
    ent = TTS_MODELS.get(str(model_id or "").strip())
    return (ent.get("label") or "") if ent else ""


def tags_for(model_id, provider):
    
    allow = tuple(caps_for(model_id, provider).get("tag_groups") or ())
    return [{"key": g["key"], "label": g["label"], "bracket": g["bracket"],
             "tags": list(g["tags"])}
            for g in TAG_GROUPS if g["key"] in allow]


def all_tag_groups():
    
    return [{"key": g["key"], "label": g["label"], "bracket": g["bracket"],
             "tags": list(g["tags"])}
            for g in TAG_GROUPS]














TAG_GROUPS = (
    {"key": "emotion", "label": "基础情绪", "bracket": "()",
     "tags": ["开心", "悲伤", "愤怒", "恐惧", "惊讶", "兴奋", "委屈", "平静", "冷漠"]},
    {"key": "emotion_plus", "label": "复合情绪", "bracket": "()",
     "tags": ["怅然", "欣慰", "无奈", "愧疚", "释然", "嫉妒", "厌倦", "忐忑", "动情"]},
    {"key": "tone", "label": "整体语调", "bracket": "()",
     "tags": ["温柔", "高冷", "活泼", "严肃", "慵懒", "俏皮", "深沉", "干练", "凌厉"]},
    {"key": "timbre", "label": "音色定位", "bracket": "()",
     "tags": ["磁性", "醇厚", "清亮", "空灵", "稚嫩", "苍老", "甜美", "沙哑", "醇雅"]},
    {"key": "persona", "label": "人设腔调", "bracket": "()",
     "tags": ["夹子音", "御姐音", "正太音", "大叔音", "台湾腔"]},
    {"key": "dialect", "label": "方言", "bracket": "()",
     "tags": ["东北话", "四川话", "河南话", "粤语"]},
    {"key": "role", "label": "角色扮演", "bracket": "()",
     "tags": ["孙悟空", "林黛玉"]},





    {"key": "sing", "label": "唱歌", "bracket": "()",
     "tags": ["唱歌"]},



    {"key": "pace", "label": "语速与节奏", "bracket": "[]",
     "tags": ["吸气", "深呼吸", "叹气", "长叹一口气", "喘息", "屏息", "语速加快", "语速放慢"]},
    {"key": "state", "label": "情绪状态", "bracket": "[]",
     "tags": ["紧张", "害怕", "激动", "疲惫", "委屈", "撒娇", "心虚", "震惊", "不耐烦"]},
    {"key": "voice", "label": "语音特征", "bracket": "[]",
     "tags": ["颤抖", "声音颤抖", "变调", "破音", "鼻音", "气声", "沙哑"]},
    {"key": "cry", "label": "哭笑表达", "bracket": "[]",
     "tags": ["笑", "轻笑", "大笑", "冷笑", "抽泣", "呜咽", "哽咽", "嚎啕大哭"]},
)
