
import base64
import binascii
import json
import os
import subprocess
import tempfile
import time

import media_tools as _mt


_MIMO_REF_FORMATS = ("mp3", "wav")
_MIME_BY_EXT = {"mp3": "audio/mpeg", "wav": "audio/wav"}



_MP3_BITRATES = ("128k", "96k", "64k", "48k")




_TIMEOUT_OPENROUTER = (10, 120)
_TIMEOUT_MIMO = (10, 180)


class UpstreamError(Exception):
    

    def __init__(self, message, code="error", status=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status









_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF = 1.0


def _post_with_retry(spec, base):
    
    import requests as _rq
    attempts = max(1, int(_RETRY_ATTEMPTS))
    last_code, last_msg = "unreachable", ""
    for i in range(attempts):
        try:
            return _rq.post(spec["url"], headers=spec["headers"], json=spec["payload"],
                            timeout=spec["timeout"])
        except _rq.exceptions.ChunkedEncodingError as e:
            t = spec["timeout"]
            last_code = "upstream_interrupted"
            last_msg = ("上游响应中途断开（连接已建立、数据未传完）" +
                        ("" if attempts == 1 else "，第 %d/%d 次" % (i + 1, attempts)))
            _ = t
        except _rq.exceptions.ReadTimeout:

            t = spec["timeout"]
            secs = t[1] if isinstance(t, (tuple, list)) and len(t) > 1 else t
            raise UpstreamError("上游生成超时（超过 %s 秒未返回）" % secs, code="timeout")
        except _rq.exceptions.ConnectionError as e:

            raise UpstreamError("无法连接音频接口 %s：%s" % (base, e), code="unreachable")
        except Exception as e:
            raise UpstreamError("请求异常 %s：%s" % (type(e).__name__, e), code="unreachable")
        if i < attempts - 1:
            time.sleep(_RETRY_BACKOFF * (i + 1))
    raise UpstreamError(last_msg or "上游请求失败", code=last_code)


def _ext_of(path):
    return os.path.splitext(path or "")[1].lstrip(".").lower()


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _data_url(data, ext):
    
    mime = _MIME_BY_EXT.get(ext) or "audio/mpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())


def _ffmpeg_to_mp3(src, bitrate):
    
    exe = _mt.resolve("ffmpeg")
    if not exe:
        return None
    fd, tmp = tempfile.mkstemp(suffix=".mp3", prefix="tts_ref_")
    os.close(fd)
    try:
        p = subprocess.run(
            [exe, "-y", "-v", "error", "-i", src, "-vn",
             "-c:a", "libmp3lame", "-b:a", bitrate, tmp],
            capture_output=True, text=True, timeout=120,
        )
        if p.returncode != 0 or not os.path.isfile(tmp):
            return None
        data = _read_bytes(tmp)
        return data or None
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass





def _openrouter_request(base, key, model, intent):
    
    payload = {"model": model, "input": intent["text"],
               "response_format": "mp3", "speed": intent["speed"]}
    ref = intent.get("ref_data_url") or ""
    if ref:
        payload["input_references"] = [
            {"type": "input_audio", "input_audio": {"data": ref}}
        ]
    return {
        "url": "%s/audio/speech" % base,
        "headers": {"Authorization": "Bearer %s" % key, "Content-Type": "application/json"},
        "payload": payload,
        "timeout": _TIMEOUT_OPENROUTER,
    }


def _mimo_ref_voice(intent, caps):
    
    spec = (caps or {}).get("ref") or {}
    max_bytes = int(spec.get("maxBytes") or 7400000)
    max_b64 = int(spec.get("maxB64") or 10 * 1000 * 1000)

    path = intent.get("ref_path") or ""
    data = None
    ext = _ext_of(path)

    if path and os.path.isfile(path):
        if ext in _MIMO_REF_FORMATS:
            raw = _read_bytes(path)

            if len(raw) <= max_bytes and len(raw) * 4 // 3 <= max_b64:
                return _data_url(raw, ext)

        for br in _MP3_BITRATES:
            out = _ffmpeg_to_mp3(path, br)
            if out and len(out) <= max_bytes and len(out) * 4 // 3 <= max_b64:
                return _data_url(out, "mp3")
        if not _mt.resolve("ffmpeg"):
            raise UpstreamError(
                "参考音频不是 mp3/wav，而本机没有可用的 ffmpeg 可用于转码。"
                "请安装 ffmpeg，或改用 mp3 / wav 格式的参考音频。",
                code="ref_too_large",
            )
        raise UpstreamError(
            "参考音频过大（已尝试压缩）仍超出上限（约 %.1f MB）。请裁剪或压缩后再试。"
            % (max_bytes / 1024 / 1024),
            code="ref_too_large",
        )


    ref = intent.get("ref_data_url") or ""
    if ref:
        b64 = ref.split(",", 1)[1] if "," in ref else ref
        if len(b64) <= max_b64:
            return ref
        raise UpstreamError(
            "参考音频过大（约 %.1f MB），MiMo 的音色复刻上限约 %.1f MB。请裁剪或压缩后再试。"
            % (len(b64) * 3 / 4 / 1024 / 1024, max_b64 / 1000 / 1000),
            code="ref_too_large",
        )
    return ""


def _mimo_request(base, key, model, intent, caps):
    
    text = intent["text"]
    target = (caps or {}).get("prompt_target") or "assistant"
    audio = {"format": "mp3"}

    ref_mode = ((caps or {}).get("ref") or {}).get("mode")
    if ref_mode in ("required", "optional"):
        voice = _mimo_ref_voice(intent, caps)
        if voice:
            audio["voice"] = voice
        elif ref_mode == "required":
            raise UpstreamError(
                "该模型需要一段参考音频才能合成（音色复刻）。"
                "请从音色库选一个音色，或上传一段参考音频。",
                code="bad_reference",
            )





    preset = (caps or {}).get("preset") or {}
    if preset.get("mode") == "list":
        pv = (intent.get("preset_voice") or "").strip()
        if pv:
            ids = [v.get("id") for v in (preset.get("voices") or [])]
            if pv not in ids:
                raise UpstreamError(
                    "厂商预置音色里没有「%s」。可选：%s。" % (pv, "、".join(ids)),
                    code="bad_preset_voice",
                )
            audio["voice"] = pv



    opt = intent.get("optimize_text_preview", None)
    optimize_on = opt is True or (opt is None and (caps or {}).get("optimize_text_preview"))
    if optimize_on:
        audio["optimize_text_preview"] = True




    vd = (intent.get("voice_desc") or "").strip()
    if vd and target == "user":
        messages = [{"role": "user", "content": vd}, {"role": "assistant", "content": text}]
    elif target == "user" and not optimize_on:
        messages = [{"role": "user", "content": text}, {"role": "assistant", "content": text}]
    else:
        messages = [{"role": target, "content": text}]

    return {
        "url": "%s/chat/completions" % base,
        "headers": {"api-key": key, "Content-Type": "application/json"},
        "payload": {"model": model, "messages": messages, "audio": audio},
        "timeout": _TIMEOUT_MIMO,
    }





def _extract_binary(resp, payload=None):
    
    if resp.status_code == 200 and resp.content:
        return {"data": resp.content, "text": ""}
    return None


def _extract_mimo_audio(resp, payload=None):
    
    if resp.status_code != 200:
        return None
    try:
        j = resp.json()
    except Exception:
        raise UpstreamError("MiMo 返回的不是合法 JSON。", code="http")
    choices = j.get("choices") or []
    if not choices:
        raise UpstreamError("MiMo 未返回任何结果（choices 为空）。", code="http")
    ch0 = choices[0] or {}
    if (ch0.get("finish_reason") or "") == "content_filter":
        raise UpstreamError(
            "合成内容被上游内容策略拦截（content_filter）。请调整文本后重试。",
            code="bad_request",
        )
    msg = (ch0.get("message") or {})
    audio = (msg.get("audio") or {})
    b64 = audio.get("data") or ""
    if not b64:
        raise UpstreamError("MiMo 未返回音频数据（audio.data 为空）。", code="http")
    try:
        data = base64.b64decode(b64)
    except (binascii.Error, ValueError):
        raise UpstreamError("MiMo 返回的音频 base64 解码失败。", code="http")
    if not data:
        raise UpstreamError("MiMo 返回了空音频。", code="http")


    text = ((msg.get("final_text_preview") or "").strip()
            or (msg.get("content") or "").strip()
            or (audio.get("transcript") or "").strip())
    return {"data": data, "text": text}





def _body_snippet(resp, n=300):
    try:
        return (resp.text or "")[:n]
    except Exception:
        return ""


def _raise_openrouter(resp):
    body = _body_snippet(resp)
    st = resp.status_code
    if st in (401, 403):
        raise UpstreamError("音频接口鉴权失败（密钥无效或已过期）。请检查 OpenRouter Key。",
                            code="auth", status=st)
    if st == 429:
        raise UpstreamError("音频接口额度已用尽或请求过于频繁（免费模型每日限量）。请稍后再试。",
                            code="quota", status=429)
    if st == 402:
        raise UpstreamError("音频接口需要付费额度（HTTP 402）。", code="quota", status=402)
    if st == 400:
        raise UpstreamError("音频接口拒绝请求（HTTP 400）：%s" % body,
                            code="bad_request", status=400)
    raise UpstreamError("音频接口返回 HTTP %s：%s" % (st, body), code="http", status=st)


def _raise_mimo(resp):
    
    body = _body_snippet(resp)
    st = resp.status_code
    if st in (401, 403):
        raise UpstreamError("MiMo 鉴权失败（`api-key` 无效或已过期）。请检查 MiMo API Key。",
                            code="auth", status=st)
    if st == 429:
        raise UpstreamError("MiMo 请求过于频繁或额度受限，请稍后再试。", code="quota", status=429)
    if st == 402:
        raise UpstreamError("MiMo 接口需要付费额度（HTTP 402）。", code="quota", status=402)
    if st == 400:
        raise UpstreamError(
            "MiMo 拒绝请求（HTTP 400）：%s\n"
            "常见原因：该模型必填的字段没给（比如音色复刻必须传参考音频样本）。" % body,
            code="bad_request", status=400)
    raise UpstreamError("MiMo 接口返回 HTTP %s：%s" % (st, body), code="http", status=st)





def synthesize(intent):
    
    import requests as _rq

    prov = str(intent.get("provider") or "openrouter").strip().lower()
    base = (intent.get("base_url") or "").rstrip("/")
    key = intent.get("key") or ""
    model = intent.get("model") or ""
    caps = intent.get("caps") or {}

    if not key:
        raise UpstreamError(
            "未配置音频接口密钥。请在「服务商设置」对应标签页填入密钥。", code="no_key")
    if not base:
        raise UpstreamError("未配置音频接口地址。请在「服务商设置」对应标签页填写。",
                            code="no_key")

    if prov == "mimo":
        spec = _mimo_request(base, key, model, intent, caps)
        extract = _extract_mimo_audio
        raise_err = _raise_mimo
    else:
        spec = _openrouter_request(base, key, model, intent)
        extract = _extract_binary
        raise_err = _raise_openrouter

    resp = _post_with_retry(spec, base)

    res = extract(resp, spec["payload"])
    data = res.get("data") if isinstance(res, dict) else res
    if data:
        if isinstance(res, dict):
            return res
        return {"data": data, "text": ""}
    raise_err(resp)


def probe(provider, base, key, model, caps=None):
    
    import requests as _rq

    prov = str(provider or "openrouter").strip().lower()
    base = (base or "").rstrip("/")
    out = {"ok": False, "status": 0, "audio_bytes": 0,
           "model_used": model or "", "detail": ""}

    if not base:
        out["detail"] = "未填写接口地址。"
        return out
    if not key:
        out["detail"] = "未填写密钥。"
        return out

    if prov == "mimo":
        probe_model = model
        if caps is None or ((caps.get("ref") or {}).get("mode") != "none"):
            probe_model = "mimo-v2.5-tts-voicedesign"
        out["model_used"] = probe_model
        payload = {
            "model": probe_model,
            "messages": [{"role": "user", "content": "自然平和的嗓音"}],
            "audio": {"format": "mp3", "optimize_text_preview": True},
        }
        headers = {"api-key": key, "Content-Type": "application/json"}
        url, timeout = "%s/chat/completions" % base, _TIMEOUT_MIMO
    else:
        out["model_used"] = model
        payload = {"model": model, "input": "啊", "response_format": "mp3", "speed": 1.0}
        headers = {"Authorization": "Bearer %s" % key, "Content-Type": "application/json"}
        url, timeout = "%s/audio/speech" % base, _TIMEOUT_OPENROUTER

    try:
        resp = _rq.post(url, headers=headers, json=payload, timeout=timeout)
    except Exception as e:
        out["detail"] = "无法连接 %s：%s: %s" % (base, type(e).__name__, e)
        return out

    out["status"] = resp.status_code
    if prov == "mimo":
        try:
            data = _extract_mimo_audio(resp)
        except UpstreamError as e:
            out["detail"] = e.message
            return out
        audio = data.get("data") if isinstance(data, dict) else data
        out["ok"] = bool(audio)
        out["audio_bytes"] = len(audio or b"")
        out["detail"] = ("MiMo 音频接口可用，密钥有效（用「%s」生成最小片段，%d 字节）"
                         % (out["model_used"], out["audio_bytes"]))
        return out

    ctype = (resp.headers.get("Content-Type") or "").lower()
    if resp.status_code == 200 and ("audio" in ctype or len(resp.content) > 100):
        out["ok"] = True
        out["audio_bytes"] = len(resp.content)
        out["detail"] = "音频接口可用，密钥有效（生成最小片段 %d 字节）" % out["audio_bytes"]
    elif resp.status_code in (401, 403):
        out["detail"] = "地址可达，但密钥被拒绝（HTTP %s）" % resp.status_code
    else:
        out["detail"] = "地址可达，但返回 HTTP %s：%s" % (resp.status_code, _body_snippet(resp, 160))
    return out
