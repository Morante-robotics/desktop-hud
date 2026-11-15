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
if "--demo" in sys.argv:  # six refreshes that loop, like the live HUD every 2 s
    import demo_state
    states = json.dumps([demo_state.make(k) for k in range(6)])
else:
    states = "[" + open(os.path.expanduser("~/Library/Application Support/DesktopHUD/state.json")).read() + "]"

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
const STATES = {states};
const root = ReactDOM.createRoot(document.getElementById('w'));
const DEMO = {json.dumps("--demo" in sys.argv)};  // demo data is always "just written"
const show = (i) => {{
  const s = STATES[i % STATES.length];
  ReactDOM.flushSync(() => root.render(render({{ s: DEMO ? {{ ...s, t: Date.now() / 1000 }} : s, err: null }})));
}};
let frame = 0;
show(0);
const timer = setInterval(() => show(++frame), refreshFrequency);
// Used by preview/record.py: stop the clock and draw the HUD as it is t seconds into a loop
// of `loop` seconds, so every frame is exact however long a snapshot takes.
window.hudFrame = (t, loop) => {{
  clearInterval(timer);
  show(Math.floor(t * 1000 / refreshFrequency));
  for (const a of document.getAnimations()) {{
    const d = a.effect.getTiming().duration;
    // whole turns per loop so the GIF loops seamlessly; slow rings turn faster than in real life
    const turns = d > loop * 1000 ? ({{60000: 2}}[d] || 1) : Math.max(1, Math.round(loop * 1000 / d));
    a.pause();
    a.currentTime = ((t / loop) * turns * d) % d;
  }}
}};
window.hudReady = true;
</script></body></html>"""
open(os.path.join(ROOT, "preview/index.html"), "w").write(html)
print("preview/index.html written" + (" (demo data)" if "--demo" in sys.argv else " (LIVE data: do not share)"))
