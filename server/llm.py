
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


_AGNES_MODEL_KEY = {
    "assistant": "agent_models",
    "storyboard": "llm_models",
}
_AGNES_DEFAULT_MODEL = {
    "assistant": ["agnes-3.0-flash"],
    "storyboard": ["agnes-2.5-flash", "agnes-3.0-flash"],
}


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



def resolve_llm_provider(use_case, enabled, ready):
    
    en = [k for k in LLM_PROVIDER_ORDER
          if k in LLM_PROVIDER_HOSTS and k in set(enabled or ())]
    selected = en[0] if en else "agnes"
    rd = {k: bool((ready or {}).get(k)) for k in LLM_PROVIDER_ORDER}
    rd["agnes"] = True
    winner = selected if rd.get(selected) else "agnes"
    conflict = len(en) > 1
    fallback = winner != selected
    note = ""
    if fallback:
        note = ("已勾选「%s」，但它尚未就绪（缺地址/令牌/模型）→ LLM 实际仍走「%s」。"
                % (LLM_PROVIDER_LABELS[selected], LLM_PROVIDER_LABELS[winner]))
    elif conflict:
        note = ("检测到多家同时勾选（%s），已按优先级取「%s」；保存一次设置即可收敛。"
                % ("、".join(LLM_PROVIDER_LABELS[k] for k in en), LLM_PROVIDER_LABELS[selected]))
    return {"winner": winner, "selected": selected, "enabled": en, "conflict": conflict,
            "fallback": fallback, "ready": rd, "note": note}


def _resolve_now(use_case):
    
    en = [k for k in LLM_PROVIDER_HOSTS if _host(k).chat_model_enabled(use_case)]
    ready = {}
    for k in LLM_PROVIDER_HOSTS:
        h = _host(k)
        ok = True
        if hasattr(h, "ready_state"):
            ok, _why = h.ready_state(use_case)
        ready[k] = bool(ok) and bool(h.chat_model(use_case))
    return resolve_llm_provider(use_case, en, ready)


def route(use_case):
    
    if use_case not in _USE_CASES:
        raise ValueError(f"未知 LLM 用例：{use_case!r}（应为 assistant / storyboard）")
    return _resolve_now(use_case)["winner"]


def models_for(use_case):
    
    if use_case not in _USE_CASES:
        raise ValueError(f"未知 LLM 用例：{use_case!r}")
    be = route(use_case)
    if be == "ms":
        return list(_ms().chat_model(use_case) or [DEFAULT_MS_CHAT_MODEL])
    if be == "custom":
        return list(_custom().chat_model(use_case) or [])

    lst = _provider().get(_AGNES_MODEL_KEY[use_case]) or []
    return list(lst) if lst else list(_AGNES_DEFAULT_MODEL[use_case])


def default_model(use_case):
    
    m = models_for(use_case)
    if m:
        return m[0]
    return DEFAULT_MS_CHAT_MODEL if route(use_case) == "ms" else _AGNES_DEFAULT_MODEL[use_case][0]



def configured(use_case):
    
    if use_case not in _USE_CASES:
        return False, f"未知 LLM 用例：{use_case!r}"
    be = route(use_case)
    if be == "ms":

        if not _ms().chat_model_enabled(use_case):
            return False, "已路由到魔搭，但本用例未勾选「切换到魔搭接口」"
        if not _ms().chat_model(use_case):
            return False, "已路由到魔搭，但本用例在「魔搭」标签页未填对话/推理模型（留空 = 回落 Agnes）"
        return True, ""
    if be == "custom":
        h = _custom()
        ok, why = h.ready_state(use_case)
        if not ok:
            return False, f"已路由到「自定义 OpenAI」，但{why}"
        return True, ""

    if not _provider().get("api_key"):
        return False, "尚未配置 Agnes 访问密钥（在「Agnes」标签页填写接口地址与密钥，或配置 .env）"
    return True, ""



def _thinking_params(backend, thinking, use_case=None):
    
    if backend == "ms":



        m = ""
        if use_case:
            try:
                lst = _ms().chat_model(use_case) or []
                m = (lst[0] if lst else "")
            except Exception:
                m = ""
        if "qwen" in m.lower():
            return {"chat_template_kwargs": {"enable_thinking": bool(thinking)}}
        if not thinking:
            return {"thinking": {"type": "disabled"}}
        budget = None
        if use_case and hasattr(_ms(), "chat_budget_tokens"):
            budget = _ms().chat_budget_tokens(use_case)
        p = {"thinking": {"type": "enabled"}}
        if budget:
            p["thinking"]["budget_tokens"] = budget
        return p
    if backend == "custom":
        if not thinking:
            return {}
        effort = None
        if use_case and hasattr(_custom(), "chat_budget_effort"):
            effort = _custom().chat_budget_effort(use_case)
        return {"reasoning_effort": effort} if effort else {}

    return {"chat_template_kwargs": {"enable_thinking": bool(thinking)}}



def caps(use_case, kind):
    
    be = route(use_case)
    h = _host(be)
    if h is None or not hasattr(h, "chat_caps"):
        return True
    return bool(h.chat_caps(use_case, kind))


def ctx_limit(use_case):
    
    h = _host(route(use_case))
    if h is not None:
        if hasattr(h, "chat_ctx_limit"):
            return h.chat_ctx_limit(use_case)
        return None
    import server.provider as _p
    return _p.get("agent_ctx_limit" if use_case == "assistant" else "llm_ctx_limit")


def max_output_for(use_case, default=None):
    
    h = _host(route(use_case))
    if h is not None:
        if hasattr(h, "chat_max_output"):
            v = h.chat_max_output(use_case)
            if v:
                return int(v)
        return default
    import server.provider as _p
    v = _p.get("agent_max_output" if use_case == "assistant" else "llm_max_output")
    return int(v) if v else default


def chat(use_case, messages, model=None, tools=None, tool_choice=None,
         stream=False, thinking=None, max_tokens=None, temperature=0.2,
         timeout=(10, 300)):
    
    if use_case not in _USE_CASES:
        raise ValueError(f"未知 LLM 用例：{use_case!r}")
    be = route(use_case)
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


    _chosen_model = model or default_model(use_case)
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

    if thinking is None and host is not None and hasattr(host, "chat_thinking"):
        thinking = bool(host.chat_thinking(use_case))
    payload.update(_thinking_params(be, thinking, use_case))
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
