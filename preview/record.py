#!/usr/bin/env python3
"""Renders a preview page with WebKit (the engine Übersicht uses) to a PNG or a looping GIF.

  python3 preview/build.py --demo         # first: the HUD with made-up data
  uv run --with pyobjc-framework-WebKit preview/record.py png docs/hud.png
  uv run --with pyobjc-framework-WebKit preview/record.py gif docs/hud.gif
  uv run --with pyobjc-framework-WebKit preview/record.py png docs/social-preview.png --page preview/social.html --size 1280x640

GIF options: --seconds 12 (loop length, a multiple of the 2 s refresh), --fps 10, --width 1024.
The GIF needs ffmpeg. Each frame is drawn at an exact time (see window.hudFrame in build.py),
so the result doesn't depend on how fast the machine is.
"""
import argparse, os, shutil, subprocess, sys, tempfile
from AppKit import NSApplication, NSBitmapImageRep, NSPNGFileType, NSWindow, NSBackingStoreBuffered
from Foundation import NSURL, NSMakeRect, NSTimer
from WebKit import WKWebView, WKWebViewConfiguration, WKSnapshotConfiguration

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["png", "gif"])
ap.add_argument("out")
ap.add_argument("--page", default=os.path.join(ROOT, "preview", "index.html"))
ap.add_argument("--size", default="2048x1152", help="page size in CSS pixels")
ap.add_argument("--width", type=int, help="output width (default: page width for PNG, 1024 for GIF)")
ap.add_argument("--seconds", type=float, default=12)
ap.add_argument("--fps", type=float, default=10)
a = ap.parse_args()
W, H = (int(x) for x in a.size.split("x"))
width = a.width or (W if a.mode == "png" else 1024)
out = os.path.abspath(a.out)
frames = [i / a.fps for i in range(round(a.seconds * a.fps))] if a.mode == "gif" else [None]
tmp = tempfile.mkdtemp(prefix="hud-frames-")

app = NSApplication.sharedApplication()
win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(-6000, 0, W, H), 0, NSBackingStoreBuffered, False)
view = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, W, H), WKWebViewConfiguration.alloc().init())
win.setContentView_(view)
win.orderBack_(None)
view.loadFileURL_allowingReadAccessToURL_(NSURL.fileURLWithPath_(os.path.abspath(a.page)), NSURL.fileURLWithPath_(ROOT))


def later(sec, fn):
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(sec, False, lambda _t: fn())


def fail(msg):
    print(msg, file=sys.stderr, flush=True)
    app.terminate_(None)


def save(image, path):
    rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    rep.representationUsingType_properties_(NSPNGFileType, {}).writeToFile_atomically_(path, True)


def shoot(i):
    if i == len(frames):
        return finish()
    def snap():
        conf = WKSnapshotConfiguration.alloc().init()
        conf.setSnapshotWidth_(width)
        def done(image, err):
            if err:
                return fail(f"snapshot failed: {err}")
            save(image, out if a.mode == "png" else os.path.join(tmp, f"{i:04d}.png"))
            shoot(i + 1)
        view.takeSnapshotWithConfiguration_completionHandler_(conf, done)
    if frames[i] is None:
        return snap()
    view.evaluateJavaScript_completionHandler_(f"hudFrame({frames[i]}, {a.seconds})", lambda _r, err: fail(f"hudFrame: {err}") if err else later(0.1, snap))


def finish():
    if a.mode == "gif":
        vf = ("split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
              "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(a.fps), "-i", os.path.join(tmp, "%04d.png"),
                        "-vf", vf, "-loop", "0", out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"saved {out} ({os.path.getsize(out) / 1e6:.1f} MB)", flush=True)
    app.terminate_(None)


def wait_ready(tries=[0]):
    tries[0] += 1
    if tries[0] > 100:
        return fail("page never became ready (offline? the preview loads React and fonts from CDNs)")
    js = "window.hudReady === true && document.fonts.status === 'loaded' && [...document.images].every(i => i.complete)"
    view.evaluateJavaScript_completionHandler_(js, lambda ok, _e: later(1.5, lambda: shoot(0)) if ok else later(0.3, wait_ready))


later(0.5, wait_ready)
app.run()
