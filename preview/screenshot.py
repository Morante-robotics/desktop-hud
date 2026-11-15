#!/usr/bin/env python3
"""Renders preview/index.html with WebKit (the engine Übersicht uses) and saves a PNG.

  uv run --with pyobjc-framework-WebKit preview/screenshot.py [out.png] [seconds]

Build the page first (python3 preview/build.py --demo). `seconds` is how long the page
gets to load its fonts and scripts before the shot (default 6).
"""
import os, sys
import objc
from AppKit import NSApplication, NSBitmapImageRep, NSPNGFileType, NSWindow, NSBackingStoreBuffered
from Foundation import NSURL, NSMakeRect, NSTimer
from WebKit import WKWebView, WKWebViewConfiguration, WKSnapshotConfiguration

W, H = 2048, 1152
ROOT = os.path.dirname(os.path.abspath(__file__))
out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "..", "docs", "hud.png"))
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 6

app = NSApplication.sharedApplication()
win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(-5000, 0, W, H), 0, NSBackingStoreBuffered, False)
view = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, W, H), WKWebViewConfiguration.alloc().init())
win.setContentView_(view)
win.orderBack_(None)
page = NSURL.fileURLWithPath_(os.path.join(ROOT, "index.html"))
view.loadFileURL_allowingReadAccessToURL_(page, NSURL.fileURLWithPath_(ROOT))


def done(image, error):
    if error:
        print("snapshot failed:", error)
    else:
        rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
        rep.representationUsingType_properties_(NSPNGFileType, {}).writeToFile_atomically_(out, True)
        print("saved", out)
    app.terminate_(None)


def shoot(_timer):
    conf = WKSnapshotConfiguration.alloc().init()
    conf.setSnapshotWidth_(W)
    view.takeSnapshotWithConfiguration_completionHandler_(conf, done)


NSTimer.scheduledTimerWithTimeInterval_repeats_block_(wait, False, shoot)
app.run()
