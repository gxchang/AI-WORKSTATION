
import os
import json


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CSS_FILES = ["base.css", "panes.css", "layout.css"]
_JS_FILES = ["core.js", "panes.js", "app.js"]


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def build_ui_js():
    
    css_dir = os.path.join(_ROOT, "src", "longvideo", "css")
    js_dir = os.path.join(_ROOT, "src", "longvideo", "js")

    css = "\n".join(_read(os.path.join(css_dir, f)) for f in _CSS_FILES)

    css_block = "const CSS = " + json.dumps(css) + ";\n"

    js = "\n".join(_read(os.path.join(js_dir, f)) for f in _JS_FILES)
    return css_block + js
