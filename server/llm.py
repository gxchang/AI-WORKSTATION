
import os
import re
import threading
import time

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter





_USE_CASES = ("assistant", "storyboard")


LLM_PROVIDERS = (
    {"key": "custom", "label": "自定义 OpenAI"},
    {"key": "ms", "label": "魔搭 ModelScope"},
    {"key": "agnes", "label": "Agnes"},
)
LLM_PROVIDER_ORDER = tuple(p["key"] for p in LLM_PROVIDERS)
LLM_PROVIDER_LABELS = {p["key"]: p["label"] for p in LLM_PROVIDERS}

LLM_PROVIDER_HOSTS = tuple(k for k in LLM_PROVIDER_ORDER if k != "agnes")


_AGNES_MODEL_KEY = "chat_models"
_AGNES_DEFAULT_MODEL = ["agnes-3.0-flash", "agnes-2.5-flash"]


DEFAULT_MS_CHAT_MODEL = "ZhipuAI/GLM-5.3-Flash"

DEFAULT_MS_BUDGET = 4096

_LOCK = threading.RLock()



def _provider():
    
    import server.provider as _p
    return _p


def _ms():
    
    import server.ms_provider as _m
    return _m


def _custom():
    
    import server.custom_provider as _c
    return _c


def _host(key):
    
    return {"custom": _custom, "ms": _ms}.get(key, lambda: None)()






def _build_llm_session():
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=3,
        backoff_factor=0.8,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST", "HEAD", "PUT", "DELETE"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"Connection": "keep-alive"})
    return s


_LLM_SESSION = _build_llm_session()



def resolve_llm_provider(use_case, enabled, ready, selected=None):
    
    en = [k for k in LLM_PROVIDER_ORDER
          if k in LLM_PROVIDER_HOSTS and k in set(enabled or ())]
    sel = str(selected or "").strip().lower()
    if sel not in LLM_PROVIDER_LABELS:
        sel = en[0] if en else "agnes"
    rd = {k: bool((ready or {}).get(k)) for k in LLM_PROVIDER_ORDER}
    winner = sel
    conflict = len(en) > 1
    if not rd.get(sel, False):
        note = "尚未配置访问密钥。请点击左侧「服务商设置」填入密钥（或 .env 配置 AGNES_API_KEY 后重启）。"
    elif conflict:
        note = ("检测到多家同时勾选（%s），当前按选中的「%s」生效；重新勾选一家即可收敛。"
                % ("、".join(LLM_PROVIDER_LABELS[k] for k in en), LLM_PROVIDER_LABELS[sel]))
    else:
        note = ""
    return {"winner": winner, "selected": sel, "enabled": en, "conflict": conflict,
            "fallback": False, "ready": rd, "note": note}


def _resolve_now(use_case=None):
    
    en = [k for k in LLM_PROVIDER_HOSTS if _host(k).chat_model_enabled()]
    ready = {}
    for k in LLM_PROVIDER_HOSTS:
        h = _host(k)
        ok = True
        if hasattr(h, "ready_state"):
            ok, _why = h.ready_state()
        ready[k] = bool(ok) and bool(h.chat_model())
    ready["agnes"] = bool(_provider().get("api_key"))
    return resolve_llm_provider(None, en, ready, _provider().get_choice("llm", en))


def route(use_case=None):
    
    if use_case is not None and use_case not in _USE_CASES:
        raise ValueError(f"未知 LLM 用例：{use_case!r}（应为 assistant / storyboard，合并后仅作兼容）")
    return _resolve_now()["winner"]


def models_for(use_case=None):
    
    be = route()
    if be == "ms":
        return list(_ms().chat_model() or [DEFAULT_MS_CHAT_MODEL])
    if be == "custom":
        return list(_custom().chat_model() or [])
    lst = _provider().get(_AGNES_MODEL_KEY) or []
    return list(lst) if lst else list(_AGNES_DEFAULT_MODEL)


def default_model(use_case=None):
    
    m = models_for()
    if m:
        return m[0]
    return DEFAULT_MS_CHAT_MODEL if route() == "ms" else _AGNES_DEFAULT_MODEL[0]



def configured(use_case=None):
    
    be = route()
    if be == "ms":
        if not _ms().chat_model_enabled():
            return False, "已路由到魔搭，但未勾选「切换到魔搭接口」"
        if not _ms().chat_model():
            return False, "已路由到魔搭，但「魔搭」标签页未填模型（2026-11-14 起缺项只报错、不换家）"
        return True, ""
    if be == "custom":
        ok, why = _custom().ready_state()
        if not ok:
            return False, f"已路由到「自定义 OpenAI」，但{why}"
        return True, ""
    if not _provider().get("api_key"):
        return False, "尚未配置 Agnes 访问密钥（在「Agnes」标签页填写接口地址与密钥，或配置 .env）"
    return True, ""



def _thinking_params(backend, thinking, use_case=None):
    
    if thinking is None:
        thinking = True
    if backend == "ms":


        m = ""
        try:
            lst = _ms().chat_model() or []
            m = (lst[0] if lst else "")
        except Exception:
            m = ""
        if "qwen" in m.lower():
            return {"chat_template_kwargs": {"enable_thinking": bool(thinking)}}
        if not thinking:
            return {"thinking": {"type": "disabled"}}
        budget = None
        if hasattr(_ms(), "chat_budget_tokens"):
            budget = _ms().chat_budget_tokens()
        p = {"thinking": {"type": "enabled"}}
        if budget:
            p["thinking"]["budget_tokens"] = budget
        return p
    if backend == "custom":
        if not thinking:
            return {}
        effort = None
        if hasattr(_custom(), "chat_budget_effort"):
            effort = _custom().chat_budget_effort()
        return {"reasoning_effort": effort} if effort else {}

    return {"chat_template_kwargs": {"enable_thinking": bool(thinking)}}


def thinking_params(use_case=None, backend=None):
    
    be = backend or route()
    host = _host(be)
    if be == "agnes" or host is None or not hasattr(host, "chat_thinking"):
        on = bool(_provider().chat_thinking())
    else:
        on = bool(host.chat_thinking())
    return _thinking_params(be, on)


def caps(use_case, kind):
    
    h = _host(route())
    if h is None or not hasattr(h, "chat_caps"):
        return True
    return bool(h.chat_caps(kind))


def ctx_limit(use_case=None):
    
    h = _host(route())
    if h is not None:
        return h.chat_ctx_limit() if hasattr(h, "chat_ctx_limit") else None
    return _provider().get("chat_ctx")


def max_output_for(use_case=None, default=None):
    
    h = _host(route())
    if h is not None:
        if hasattr(h, "chat_max_output"):
            v = h.chat_max_output()
            if v:
                return int(v)
        return default
    v = _provider().get("chat_max_output")
    return int(v) if v else default



def chat(use_case, messages, model=None, tools=None, tool_choice=None,
         stream=False, max_tokens=None, temperature=0.2,
         timeout=(10, 300)):
    
    if use_case is not None and use_case not in _USE_CASES:
        raise ValueError(f"未知 LLM 用例：{use_case!r}")

    be = route()
    host = _host(be)
    if be == "ms":
        base = _ms().get("base_url")
        key = _ms().get("api_key")
    elif be == "custom":
        base = _custom().get("base_url")
        key = _custom().get("api_key")
    else:
        base = _provider().get("base_url")
        key = _provider().get("api_key")

    if not key:
        raise RuntimeError(f"LLM 后端「{be}」未配置密钥，无法发起 chat 请求")


    _chosen_model = model or default_model()
    print(f"[llm.chat] use_case={use_case} backend={be} model={_chosen_model} url={base}/chat/completions", flush=True)

    model = _chosen_model
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"



    payload.update(thinking_params(backend=be))
    if stream:
        payload["stream"] = True

    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return _LLM_SESSION.post(url, headers=headers, json=payload, timeout=timeout, stream=stream)



def describe(r):
    
    try:
        code = r.status_code
        if code == 200:
            d = r.json() or {}
            ch = (d.get("choices") or [{}])[0]
            u = d.get("usage") or {}
            if ch.get("finish_reason") is None and not u.get("total_tokens"):
                return ("上游返回了空响应（未产生任何 token）—— 疑似限流/过载，"
                        "请稍后重试；若反复出现请更换模型或服务商标签页。")
            if ch.get("finish_reason") == "length":
                return "输出因达到 max_tokens 上限被截断 —— 请调大输出上限或缩减任务。"
            return ""
        if code == 429:
            return "触发上游限流（HTTP 429）—— 请稍后重试，或降低调用频率。"
        if code in (401, 403):
            return "访问令牌被拒绝（HTTP %d）—— 请核对该标签页的 API Key。" % code
        if code == 400:
            return ("请求被上游拒绝（HTTP 400）—— 常见原因：模型名不存在/已下线，"
                    "或参数超出该模型限制。请核对模型清单与参数。")
        if code >= 500:
            return "上游服务故障（HTTP %d）—— 请稍后重试。" % code
        return ""
    except Exception:
        return ""
