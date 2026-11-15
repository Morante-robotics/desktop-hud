#!/usr/bin/env python3
"""Measures the HUD's real CPU cost (default 60 s). Leave the desktop VISIBLE while it
runs: macOS stops drawing the wallpaper when a window covers it.

`ps` only reports a process's own CPU, not the short-lived commands it launches, so the
service's figure comes from its own self+children counters in state.json. Übersicht's
`cat` launches every 2 s are not measurable from outside and are not included (~0.2 %).
Usage: ./measure.sh [seconds]"""
import ctypes, json, os, re, subprocess, sys, time

secs = int(sys.argv[1]) if len(sys.argv) > 1 else 60
STATE = os.path.expanduser("~/Library/Application Support/DesktopHUD/state.json")
libc = ctypes.CDLL(None)
libc.responsibility_get_pid_responsible_for_pid.argtypes = [ctypes.c_int]
UB = subprocess.run(["pgrep", "-f", "Contents/MacOS/.*bersicht$"], capture_output=True, text=True).stdout.split()


def procs():
    out = subprocess.run(["ps", "-Ao", "pid=,cputime=,command="], capture_output=True, text=True).stdout
    res = {}
    for line in out.splitlines():
        pid, cpu, cmd = line.split(None, 2)
        webkit = "WebKit.WebContent" in cmd and str(libc.responsibility_get_pid_responsible_for_pid(int(pid))) in UB
        if webkit or re.search(r"MacOS/.{1,3}bersicht$|bersicht\.app/Contents/Resources/node", cmd):
            m, s = cpu.split(":")
            res[pid] = (int(m) * 60 + float(s), re.sub(r".*/", "", cmd.split(" -")[0])[:40])
    return res


def service():
    c = json.load(open(STATE)).get("cpuSeconds", {})
    return c.get("self", 0), c.get("children", 0)


a, sa = procs(), service()
print(f"Measuring for {secs} s with the desktop visible…")
time.sleep(secs)
b, sb = procs(), service()
total = 0
for pid, (t1, name) in b.items():
    pct = 100 * (t1 - a.get(pid, (t1, ""))[0]) / secs
    total += pct
    print(f"{pid:>6} {pct:6.2f}%  {name}")
for label, i in (("hud_daemon.py (itself)", 0), ("hud_daemon.py (commands it runs)", 1)):
    pct = 100 * (sb[i] - sa[i]) / secs
    total += pct
    print(f"{'':>6} {pct:6.2f}%  {label}")
print(f"TOTAL ≈ {total:.1f} % of one core (4 threads = 400 %)")
