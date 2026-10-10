

import json
import os

from flask import Blueprint, Response


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CSS_FILES = ["base.css"]
_JS_FILES = ["app.js"]

ui_bp = Blueprint("assets_ui", __name__, url_prefix="/api")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def build_ui_js():
    
    css = "\n".join(_read(os.path.join(_ROOT, "src", "assets", "css", f))
                    for f in _CSS_FILES)
    css_block = "const AL_CSS = " + json.dumps(css) + ";\n"
    js = "\n".join(_read(os.path.join(_ROOT, "src", "assets", "js", f))
                   for f in _JS_FILES)
    return css_block + js


@ui_bp.route("/assets_ui.js")
def assets_ui_js():
    
    try:
        body = build_ui_js()
    except OSError as e:
        return Response("/* 资产库前端资源缺失：%s */" % e,
                        status=404, mimetype="application/javascript")
    resp = Response(body, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@ui_bp.route("/assets_picker.js")
def assets_picker_js():
    
    try:
        body = _read(os.path.join(_ROOT, "src", "assets", "js", "picker.js"))
    except OSError as e:
        return Response("/* 资产库选择器资源缺失：%s */" % e,
                        status=404, mimetype="application/javascript")
    resp = Response(body, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@ui_bp.route("/waveform.js")
def waveform_js():
    
    try:
        body = _read(os.path.join(_ROOT, "src", "base", "js", "waveform.js"))
    except OSError as e:
        return Response("/* 波形组件资源缺失：%s */" % e,
                        status=404, mimetype="application/javascript")
    resp = Response(body, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
