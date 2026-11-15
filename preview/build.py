#!/usr/bin/env python3
"""Builds preview/index.html: runs the real widget code in a normal browser,
so the HUD can be checked without showing the desktop.

  python3 preview/build.py          # your live data (the daemon's state.json)
  python3 preview/build.py --demo   # made-up data (preview/demo_state.py), safe to share

Serve with: python3 -m http.server -d preview 8765
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "preview"))
src = open(os.path.join(ROOT, "widget/hud.jsx")).read()
if "--demo" in sys.argv:
    import demo_state
    state = json.dumps(demo_state.make())
else:
    state = open(os.path.expanduser("~/Library/Application Support/DesktopHUD/state.json")).read()

src = re.sub(r'^import .*?;\n', "", src, flags=re.M)
src = src.replace("export const ", "const ")
html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Desktop HUD preview</title>
<style>html,body{{margin:0;width:2048px;height:1152px;overflow:hidden;background:#000}}#w{{position:absolute;left:0;top:0;width:2048px;height:1152px}}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js"></script>
</head><body><div id="w"></div>
<script type="text/babel" data-presets="react">
{src}
const STATE = {state};
ReactDOM.createRoot(document.getElementById('w')).render(render({{ s: STATE, err: null }}));
</script></body></html>"""
open(os.path.join(ROOT, "preview/index.html"), "w").write(html)
print("preview/index.html written" + (" (demo data)" if "--demo" in sys.argv else " (LIVE data: do not share)"))
