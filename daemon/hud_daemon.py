#!/usr/bin/env python3
"""Desktop HUD data daemon.

Collects system, Claude, Bambu Lab, GitHub and weather data at different
rates and writes one JSON file that the Übersicht widget reads.
Standard library only. Runs under launchd (see install.sh).
"""
import ctypes, ctypes.util, glob, json, os, re, socket, ssl, struct, subprocess
import resource, threading, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
APP = os.path.join(HOME, "Library/Application Support/DesktopHUD")
STATE = os.path.join(APP, "state.json")
CONFIG = os.path.join(APP, "config.json")
BAMBU = os.path.join(APP, "bambu.json")
LOCATION = os.path.join(APP, "location.json")
LOCATOR = os.path.join(APP, "HUDLocate.app")
CLAUDE = os.path.join(HOME, ".claude")
UA = "DesktopHUD/1.0"
PATH = "/usr/local/bin:/opt/homebrew/bin:" + os.path.join(HOME, ".local/bin") + ":/usr/bin:/bin:/usr/sbin:/sbin"
os.environ["PATH"] = PATH

state = {"sys": {}, "net": {}, "claude": {}, "printer": {}, "github": {}, "weather": {}, "errors": {}}
lock = threading.Lock()


def log_err(key, e):
    with lock:
        state["errors"][key] = f"{type(e).__name__}: {e}"[:200]


def clear_err(key):
    with lock:
        state["errors"].pop(key, None)


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data, mode=0o644):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def http_json(url, headers=None, data=None, timeout=15):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# config.json in APP; every key is optional. Set a source to false to switch it off.
DEFAULTS = {
    "github": {"owner": None, "focusRepo": None},  # owner None = the account `gh` is signed in to
    "bambu": True,                                 # Bambu Lab cloud printer (needs bambu_login.py)
    "weatherWarnings": None,                       # "aemet" = official warnings for Spain; None = off
    "recentPrompts": True,                         # show your last Claude Code prompts
}


def cfg(key):
    v = load_json(CONFIG, {}).get(key, DEFAULTS[key])
    if isinstance(DEFAULTS[key], dict) and isinstance(v, dict):
        return {**DEFAULTS[key], **v}
    return v


def run(cmd, timeout=20):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


# ---------------------------------------------------------------- system ---
libc = ctypes.CDLL(ctypes.util.find_library("c"))
libc.mach_host_self.restype = ctypes.c_uint
libc.mach_task_self.restype = ctypes.c_uint
HOST = libc.mach_host_self()


def sysctl_raw(name, size=64):
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t(size)
    if libc.sysctlbyname(name.encode(), buf, ctypes.byref(n), None, ctypes.c_size_t(0)) != 0:
        return None
    return buf.raw[: n.value]


def sysctl_int(name):
    raw = sysctl_raw(name, 8)
    if raw is None:
        return None
    return int.from_bytes(raw, "little")


def cpu_ticks():
    """Per-core (user+sys+nice, total) ticks via host_processor_info."""
    count = ctypes.c_uint()
    info = ctypes.POINTER(ctypes.c_int)()
    info_cnt = ctypes.c_uint()
    if libc.host_processor_info(HOST, 2, ctypes.byref(count), ctypes.byref(info), ctypes.byref(info_cnt)) != 0:
        return []
    out = []
    for i in range(count.value):
        u, s, idle, n = (info[i * 4 + k] for k in range(4))
        out.append((u + s + n, u + s + n + idle))
    libc.vm_deallocate(libc.mach_task_self(), ctypes.cast(info, ctypes.c_void_p), ctypes.c_size_t(info_cnt.value * 4))
    return out


libproc = ctypes.CDLL("/usr/lib/libproc.dylib")


class _Timebase(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


class _RUsage(ctypes.Structure):  # rusage_info_v2 prefix; padding covers the rest
    _fields_ = [("uuid", ctypes.c_uint8 * 16), ("user", ctypes.c_uint64), ("system", ctypes.c_uint64),
                ("pad", ctypes.c_uint64 * 40)]


_tb = _Timebase()
libc.mach_timebase_info(ctypes.byref(_tb))
NS_PER_TICK = _tb.numer / _tb.denom


libc.responsibility_get_pid_responsible_for_pid.argtypes = [ctypes.c_int]


def proc_times():
    """{pid: (app name, cpu ns)} for every process we may inspect (macOS hides root-owned ones).
    Helpers (WebKit, renderers…) are named after the app responsible for them."""
    n = libproc.proc_listallpids(None, 0)
    buf = (ctypes.c_int * (n + 64))()
    n = libproc.proc_listallpids(buf, ctypes.sizeof(buf))
    ru, name, out = _RUsage(), ctypes.create_string_buffer(256), {}
    for pid in buf[:n]:
        if pid > 0 and libproc.proc_pid_rusage(pid, 2, ctypes.byref(ru)) == 0:
            owner = libc.responsibility_get_pid_responsible_for_pid(pid)
            libproc.proc_name(owner if owner > 0 else pid, name, 256)
            out[pid] = (name.value.decode(errors="replace"), (ru.user + ru.system) * NS_PER_TICK)
    return out


def app_name(proc):
    """Fold leftovers like 'Claude Helper (Renderer)' -> 'Claude'."""
    return re.sub(r" Helper.*$| \(.*$", "", proc).strip() or proc


class System:
    def __init__(self):
        self.prev = cpu_ticks()
        self.hist = []
        self.net_prev = None
        self.proc_prev = None
        self.due = {}

    def fast(self):  # every 2 s
        cur = cpu_ticks()
        cores = []
        for (b0, t0), (b1, t1) in zip(self.prev, cur):
            dt = t1 - t0
            cores.append(round(100 * (b1 - b0) / dt) if dt > 0 else 0)
        self.prev = cur
        cpu = round(sum(cores) / len(cores)) if cores else 0
        self.hist = (self.hist + [cpu])[-60:]
        level = sysctl_int("kern.memorystatus_level")  # % of memory free per pressure model
        sw = sysctl_raw("vm.swapusage", 32)
        swap = struct.unpack("<QQQ", sw[:24])[2] if sw else 0
        with lock:
            state["sys"].update({
                "cpu": cpu, "cores": cores, "cpuHist": self.hist,
                "memPressure": (100 - level) if level is not None else None,
                "swapGB": round(swap / 2**30, 1),
            })
        self.network()
        every(10, self.processes, "processes", self.due)
        every(30, self.battery, "battery", self.due)
        every(60, self.disk, "disk", self.due)
        every(60, self.static, "static", self.due)

    def disk(self):
        st = os.statvfs("/System/Volumes/Data")
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        with lock:
            state["sys"].update({"diskUsedPct": round(100 * (total - free) / total) if total else None,
                                 "diskFreeGB": round(free / 1e9)})

    def network(self):
        out = run(["netstat", "-ibn"], 5)
        rx = tx = 0
        for line in out.splitlines()[1:]:
            p = line.split()
            if len(p) >= 10 and p[0].startswith("en") and p[2].startswith("<Link#"):
                try:
                    rx += int(p[6]); tx += int(p[9])
                except ValueError:
                    pass
        now = time.time()
        if self.net_prev:
            t0, r0, x0 = self.net_prev
            dt = max(now - t0, 0.5)
            with lock:
                state["sys"]["down"] = max(0, (rx - r0) / dt)
                state["sys"]["up"] = max(0, (tx - x0) / dt)
        self.net_prev = (now, rx, tx)

    def processes(self):
        """Top apps by CPU over the last window (100 % = one core). Root-owned system
        processes are hidden from normal users, so their share is shown as the gap
        between total CPU and the sum of the visible apps."""
        now, procs, ticks = time.time(), proc_times(), cpu_ticks()
        if self.proc_prev:
            t0, p0, k0 = self.proc_prev
            dt = max(now - t0, 1)
            apps = {}
            for pid, (name, ns) in procs.items():
                if pid in p0 and p0[pid][0] == name:
                    key = app_name(name)
                    apps[key] = apps.get(key, 0) + 100 * (ns - p0[pid][1]) / 1e9 / dt
            total = sum(100 * (b1 - b0) / (a1 - a0) for (b0, a0), (b1, a1) in zip(k0, ticks) if a1 > a0)
            hidden = total - sum(apps.values())
            if hidden > 1:
                apps["macOS system"] = hidden
            top = [[n[:18], round(v)] for n, v in sorted(apps.items(), key=lambda x: -x[1])[:3]]
            with lock:
                state["sys"]["top"] = top
        self.proc_prev = (now, procs, ticks)

    def battery(self):
        out = run(["pmset", "-g", "batt"], 5)
        m = re.search(r"(\d+)%;\s*([^;]+);\s*([^\s;]+)", out)
        if m:
            remaining = m.group(3)
            with lock:
                state["sys"]["battery"] = {
                    "pct": int(m.group(1)), "state": m.group(2).strip(),
                    "ac": "AC Power" in out,
                    "remaining": remaining if re.match(r"\d+:\d+", remaining) else None,
                }

    def static(self):
        bt = sysctl_raw("kern.boottime", 16)
        boot = struct.unpack("<q", bt[:8])[0] if bt else None
        with lock:
            state["sys"]["uptime"] = int(time.time() - boot) if boot else None
            if "model" not in state["sys"]:
                state["sys"]["model"] = (sysctl_raw("hw.model") or b"").rstrip(b"\0").decode()
                cpu = (sysctl_raw("machdep.cpu.brand_string", 128) or b"").rstrip(b"\0").decode()
                state["sys"]["cpuName"] = re.sub(r"Intel\(R\) Core\(TM\) |CPU @ ", "", cpu).strip()
                state["sys"]["ramGB"] = round((sysctl_int("hw.memsize") or 0) / 2**30)
                state["sys"]["os"] = run(["sw_vers", "-productVersion"]).strip()


def wifi():
    out = run(["networksetup", "-getairportnetwork", "en0"], 5)
    m = re.search(r"Network: (.+)", out)
    ssid = m.group(1).strip() if m else None
    online = bool(ssid) or "inet " in run(["ifconfig", "en0"], 5)
    with lock:
        state["net"] = {"ssid": ssid, "online": online}


# ---------------------------------------------------------------- weather ---
def locate():
    """CoreLocation helper first (writes location.json), IP lookup as fallback."""
    loc = load_json(LOCATION, {})
    if time.time() - loc.get("time", 0) < 6 * 3600:
        return loc
    if os.path.isdir(LOCATOR):
        subprocess.run(["open", "-g", "-j", "-W", LOCATOR], timeout=60)
        new = load_json(LOCATION, {})
        if new.get("source") == "macos" and time.time() - new.get("time", 0) < 600:
            return new
    try:
        ip = http_json("https://ipapi.co/json/")
        loc = {"lat": ip["latitude"], "lon": ip["longitude"], "city": ip.get("city"), "source": "ip", "time": time.time()}
        save_json(LOCATION, loc)
    except Exception as e:
        log_err("location", e)
    return loc


AEMET = "https://www.aemet.es"
LEVELS = {"amarillo": "yellow", "naranja": "orange", "rojo": "red"}
EVENTS = {"Lluvias": "rain", "Tormentas": "storms", "Vientos": "wind", "Nevadas": "snow", "Nieblas": "fog",
          "Temperaturas máximas": "heat", "Temperaturas mínimas": "cold", "Costeros": "coastal",
          "Polvo en suspensión": "dust", "Aludes": "avalanches", "Deshielos": "thaw", "Galernas": "galerna",
          "Rissagas": "rissaga"}


def aemet_zone(loc):
    """AEMET warning zone (a named part of a province) for the located town, cached in location.json.
    AEMET's town search -> town page, which states its 'Zona de avisos'. Spain only."""
    city = (loc.get("city") or "").strip()
    if not city:
        return None
    if loc.get("zoneFor") == city:
        return loc.get("zone")
    import html as _html, unicodedata
    page = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=20).read().decode("utf-8", "replace")
    found = page(f"{AEMET}/es/eltiempo/prediccion/municipios?modo=and&orden=n&tipo=sta&str=" + urllib.parse.quote(city))
    ids = re.findall(r'href="/es/eltiempo/prediccion/municipios/([a-z0-9\-]+-id\d{5})"', found)
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode().lower()).strip("-")
    ids.sort(key=lambda i: i.rsplit("-id", 1)[0] != slug)  # exact town name first
    zone = None
    if ids:
        m = re.search(r"Zona de avisos</span>:(?:&nbsp;|\s)*([^<]+)<", page(f"{AEMET}/es/eltiempo/prediccion/municipios/{ids[0]}"))
        zone = _html.unescape(m.group(1)).strip() if m else None
    loc.update(zone=zone, zoneFor=city)
    save_json(LOCATION, loc)
    return zone


def aemet_warnings(loc):
    """Active and upcoming AEMET warnings for the located zone, from AEMET's national RSS (~40 KB).
    Item title: 'Aviso. Nivel amarillo. Lluvias. <zone>'; description holds 'de HH:MM DD-MM-YYYY … a …'."""
    zone = aemet_zone(loc)
    if not zone:
        return []
    req = urllib.request.Request(f"{AEMET}/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAE_RSS.xml", headers={"User-Agent": UA})
    xml = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    out = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        t = re.search(r"<title>Aviso\. Nivel (\w+)\. (.+?)\. (.+?)</title>", item)
        if not t or t.group(3).strip() != zone or t.group(1).lower() not in LEVELS:
            continue
        span = re.findall(r"(\d{2}:\d{2}) (\d{2})-(\d{2})-(\d{4})", item)
        times = [datetime(int(y), int(mo), int(d), int(hm[:2]), int(hm[3:])).timestamp() for hm, d, mo, y in span[:2]]
        if len(times) == 2 and times[1] > time.time():
            out.append({"level": LEVELS[t.group(1).lower()], "event": EVENTS.get(t.group(2), t.group(2).lower()),
                        "from": times[0], "to": times[1]})
    merged = []  # AEMET splits long warnings by day: join back-to-back ones of the same kind
    for a in sorted(out, key=lambda a: (a["level"], a["event"], a["from"])):
        p = merged[-1] if merged else None
        if p and (p["level"], p["event"]) == (a["level"], a["event"]) and a["from"] <= p["to"] + 120:
            p["to"] = max(p["to"], a["to"])
        else:
            merged.append(dict(a))
    rank = {"red": 0, "orange": 1, "yellow": 2}
    return sorted(merged, key=lambda a: (rank[a["level"]], a["from"]))[:3]


WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
       51: "drizzle", 53: "drizzle", 55: "drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
       71: "snow", 73: "snow", 75: "heavy snow", 80: "showers", 81: "showers", 82: "heavy showers",
       95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm"}


def weather():
    loc = locate()
    if not loc.get("lat"):
        return
    q = urllib.parse.urlencode({
        "latitude": round(loc["lat"], 2), "longitude": round(loc["lon"], 2),
        "current": "temperature_2m,weather_code", "hourly": "precipitation_probability",
        "daily": "temperature_2m_max,temperature_2m_min", "forecast_days": 2, "timezone": "auto"})
    w = http_json("https://api.open-meteo.com/v1/forecast?" + q)
    now = datetime.now().strftime("%Y-%m-%dT%H:00")
    times = w["hourly"]["time"]
    i = times.index(now) if now in times else 0
    rain = [[times[j][11:13], w["hourly"]["precipitation_probability"][j] or 0] for j in range(i, min(i + 12, len(times)))]
    try:
        alerts = aemet_warnings(loc) if cfg("weatherWarnings") == "aemet" else []
        clear_err("warnings")
    except Exception as e:  # warnings are a bonus; never lose the forecast over them
        log_err("warnings", e)
        alerts = (state.get("weather") or {}).get("alerts", [])
    with lock:
        state["weather"] = {
            "city": loc.get("city"), "source": loc.get("source"),
            "temp": round(w["current"]["temperature_2m"]), "desc": WMO.get(w["current"]["weather_code"], ""),
            "max": round(w["daily"]["temperature_2m_max"][0]), "min": round(w["daily"]["temperature_2m_min"][0]),
            "rain": rain, "alerts": alerts, "at": time.time()}


# ----------------------------------------------------------------- claude ---
class Claude:
    def __init__(self):
        self.offsets = {}
        self.seen = {}  # (message id, request id) -> day, to count streamed duplicates once
        self.daily = {}  # yyyy-mm-dd -> tokens (excl. cache reads)
        self.recent_cache = {}  # path -> (mtime, title, prompt)
        self.last_nudge = 0
        self.oauth = None

    def sessions(self):
        out = []
        for f in glob.glob(os.path.join(CLAUDE, "sessions", "*.json")):
            d = load_json(f, {})
            try:
                os.kill(int(d.get("pid", 0)), 0)
            except Exception:
                continue
            out.append({"name": d.get("name") or os.path.basename(d.get("cwd", "")), "status": d.get("status", "idle"),
                        "since": d.get("statusUpdatedAt")})
        order = {"waiting": 0, "busy": 1}
        out.sort(key=lambda s: (order.get(s["status"], 2), -(s["since"] or 0)))
        with lock:
            state["claude"]["sessions"] = out[:5]
            state["claude"]["sessionCount"] = len(out)

    def scan(self):
        """Incremental token count and recent prompts from transcripts."""
        cutoff = time.time() - 8 * 86400
        files = [f for f in glob.glob(os.path.join(CLAUDE, "projects", "*", "*.jsonl")) if os.path.getmtime(f) > cutoff]
        for f in files:
            size = os.path.getsize(f)
            off = self.offsets.get(f, 0)
            if size <= off:
                continue
            with open(f, "rb") as fh:
                fh.seek(off)
                chunk = fh.read()
            end = chunk.rfind(b"\n") + 1
            self.offsets[f] = off + end
            for line in chunk[:end].splitlines():
                if b'"usage"' not in line or b'"assistant"' not in line:
                    continue
                try:
                    d = json.loads(line)
                    msg = d["message"]
                    key = (msg.get("id"), d.get("requestId"))
                    if key in self.seen:
                        continue
                    u = msg["usage"]
                    n = u.get("input_tokens", 0) + u.get("output_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                    day = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
                    self.seen[key] = day
                    self.daily[day] = self.daily.get(day, 0) + n
                except Exception:
                    continue
        today = datetime.now().date()
        oldest = (today - timedelta(days=8)).isoformat()
        self.seen = {k: v for k, v in self.seen.items() if v >= oldest}
        self.daily = {k: v for k, v in self.daily.items() if k >= oldest}
        self.offsets = {k: v for k, v in self.offsets.items() if k in files}
        self.recent_cache = {k: v for k, v in self.recent_cache.items() if k in files}
        monday = today - timedelta(days=today.weekday())
        week = sum(v for k, v in self.daily.items() if k >= monday.isoformat())
        recent = []
        for f in sorted(files, key=os.path.getmtime, reverse=True)[:4]:
            mtime = os.path.getmtime(f)
            cached = self.recent_cache.get(f)
            if cached and cached[0] == mtime:
                _, title, prompt = cached
            else:
                title = prompt = None
                with open(f, "rb") as fh:
                    fh.seek(max(0, os.path.getsize(f) - 400_000))
                    for line in fh.read().splitlines():
                        if b'"custom-title"' in line or b'"last-prompt"' in line:
                            try:
                                d = json.loads(line)
                            except Exception:
                                continue
                            title = d.get("customTitle", title)
                            prompt = d.get("lastPrompt", prompt)
                self.recent_cache[f] = (mtime, title, prompt)
            if prompt and cfg("recentPrompts"):
                recent.append({"t": int(mtime), "title": title or "", "prompt": " ".join(prompt.split())[:80]})
        with lock:
            state["claude"].update({"tokensToday": self.daily.get(today.isoformat(), 0), "tokensWeek": week, "recent": recent[:3]})

    @staticmethod
    def _keychain_oauth():
        raw = run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"], 10).strip()
        if not raw:
            raise RuntimeError("no Claude Code credentials in keychain")
        return json.loads(raw)["claudeAiOauth"]

    def _oauth(self):
        """Valid Claude Code OAuth credentials, renewing them through the official CLI if needed.

        The access token lives ~8 h and only the `claude` CLI renews it (the desktop app
        doesn't touch this keychain item). We never refresh it ourselves: rotating the
        refresh token behind the CLI's back could log it out. Instead we ask the CLI to do
        it, at most once an hour: first `claude auth status` (free); if that doesn't renew,
        a one-word Haiku request without saving a session (a few hundred tokens).
        """
        valid = lambda o: o.get("expiresAt", 0) / 1000 > time.time() + 300
        if self.oauth and valid(self.oauth):
            return self.oauth
        o = self.oauth = self._keychain_oauth()
        signed_out = not o.get("refreshToken")   # CLI logged out: nothing left to renew
        with lock:
            state["claude"]["signedOut"] = signed_out
        if signed_out:
            return None
        if valid(o) or time.time() - self.last_nudge < 3600:
            return o if valid(o) else None
        self.last_nudge = time.time()
        for how, cmd in (("auth status", ["claude", "auth", "status", "--json"]),
                         ("haiku ping", ["claude", "-p", "--no-session-persistence", "--model", "haiku", "Reply with: ok"])):
            subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=APP)
            o = self.oauth = self._keychain_oauth()
            if valid(o):
                print(f"{datetime.now():%Y-%m-%d %H:%M} Claude session renewed via {how}", flush=True)
                with lock:
                    state["claude"]["renewedVia"] = how
                return o
        return None

    def limits_interval(self):
        """Usage moves fast while an agent works and barely otherwise."""
        with lock:
            busy = any(x["status"] == "busy" for x in state["claude"].get("sessions", []))
        return 120 if busy else 600

    def limits(self):
        o = self._oauth()
        if not o:
            with lock:
                state["claude"]["limitsStale"] = True
            return
        u = http_json("https://api.anthropic.com/api/oauth/usage",
                      {"Authorization": "Bearer " + o["accessToken"], "anthropic-beta": "oauth-2025-04-20"})
        def part(k):
            p = u.get(k) or {}
            return {"pct": round(p.get("utilization") or 0), "resetsAt": p.get("resets_at")} if p else None
        with lock:
            state["claude"].update({"fiveHour": part("five_hour"), "week": part("seven_day"),
                                    "limitsAt": time.time(), "limitsStale": False, "plan": o.get("subscriptionType")})

    WATCHED = ("Claude Code", "Claude API (api.anthropic.com)")
    SEVERITY = {"operational": "none", "under_maintenance": "minor", "degraded_performance": "minor",
                "partial_outage": "major", "major_outage": "critical"}

    def status(self):
        """Status of the components Claude Code relies on only; the page-wide indicator also
        turns orange for unrelated products (e.g. an iOS sign-up issue on claude.ai)."""
        s = http_json("https://status.claude.com/api/v2/summary.json")
        comps = {c["id"]: c for c in s["components"] if c["name"] in self.WATCHED}
        order = ["none", "minor", "major", "critical"]
        worst = max((self.SEVERITY.get(c["status"], "minor") for c in comps.values()), key=order.index, default="none")
        incident = next((i["name"] for i in s.get("incidents", [])
                         if any(c["id"] in comps for c in i.get("components", []))), None)
        with lock:
            state["claude"]["service"] = {"indicator": worst, "incident": incident}


# ----------------------------------------------------------------- github ---
def gh(path):
    return json.loads(run(["gh", "api", path], 30) or "null")


_gh_login = None


def github_owner():
    """Configured owner (user or organisation), else the account `gh` is signed in to.
    None when the GitHub panel is switched off."""
    global _gh_login
    g = cfg("github")
    if g is False:
        with lock:
            state["github"] = {"disabled": True}
        return None
    with lock:
        state["github"].pop("disabled", None)
    if g.get("owner"):
        return g["owner"]
    if not _gh_login:
        _gh_login = (gh("user") or {}).get("login")
        if not _gh_login:
            raise RuntimeError("gh is not signed in (run: gh auth login)")
    return _gh_login


def github_focus():
    """Latest commits of the focus repo (configured, or the most recently pushed): 2 calls, every 15 min."""
    org = github_owner()
    if not org:
        return
    focus_name = cfg("github").get("focusRepo")
    if not focus_name:
        latest = gh(f"users/{org}/repos?type=owner&sort=pushed&per_page=1")
        focus_name = latest[0]["name"] if isinstance(latest, list) and latest else None
    commits = (gh(f"repos/{org}/{focus_name}/commits?per_page=2") or []) if focus_name else []
    with lock:
        state["github"]["focus"] = focus_name and {
            "name": focus_name, "commits": [[c["sha"][:7], c["commit"]["message"].splitlines()[0][:52]] for c in commits if isinstance(c, dict)]}


def github_traffic():
    """Stars, forks, views, unique visitors and referrers, every 3 h: 1 call for the repo list
    plus 2 per repo (GitHub buckets traffic by day; stars rarely move).
    Clones are left out on purpose: they count every automated clone (bots, archivers), not people."""
    org = github_owner()
    if not org:
        return
    listing = gh(f"users/{org}/repos?per_page=100&type=owner")
    if not isinstance(listing, list):
        raise RuntimeError(f"GitHub: {listing}")
    repos = [r for r in listing if not r.get("archived") and not r.get("private")]
    daily, rows, refs, visitors = {}, [], {}, 0
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    for r in repos:
        name = r["name"]
        v = gh(f"repos/{org}/{name}/traffic/views") or {}
        views = v.get("views", []) if isinstance(v, dict) else []
        visitors += v.get("uniques", 0) if views else 0
        for d in views:
            daily[d["timestamp"][:10]] = daily.get(d["timestamp"][:10], 0) + d["count"]
        d24 = views[-1]["count"] if views and views[-1]["timestamp"][:10] >= yesterday else 0
        rows.append({"name": name, "stars": r["stargazers_count"], "views": v.get("count", 0) if views else 0, "d24": d24})
        for ref in (gh(f"repos/{org}/{name}/traffic/popular/referrers") or []):
            if isinstance(ref, dict):
                refs[ref["referrer"]] = refs.get(ref["referrer"], 0) + ref["count"]
    rows.sort(key=lambda x: (x["views"], x["stars"]), reverse=True)
    days = [(datetime.now(timezone.utc).date() - timedelta(days=13 - i)).isoformat() for i in range(14)]
    tot = sum(refs.values()) or 1
    with lock:
        state["github"].update({
            "org": org, "stars": sum(r["stargazers_count"] for r in repos), "forks": sum(r["forks_count"] for r in repos),
            "views": sum(daily.values()), "visitors": visitors, "daily": [daily.get(d, 0) for d in days], "repos": rows[:3],
            "referrers": [[k, round(100 * v / tot)] for k, v in sorted(refs.items(), key=lambda x: -x[1])[:4]],
            "trafficAt": time.time()})


# ------------------------------------------------------------- bambu lab ---
API = "https://api.bambulab.com"


class Bambu(threading.Thread):
    """Cloud MQTT client (MQTT 3.1.1 over TLS, read-only) plus REST task history."""
    daemon = True

    def __init__(self):
        super().__init__()
        self.report = {}

    def creds(self):
        return load_json(BAMBU)

    def rest(self, path, token):
        return http_json(API + path, {"Authorization": "Bearer " + token})

    def history(self, token):
        try:
            tasks = self.rest("/v1/user-service/my/tasks?limit=30", token).get("hits", [])
        except Exception as e:  # optional data; never drop the live connection over it
            log_err("bambu_history", e)
            return
        monday = datetime.now().date() - timedelta(days=datetime.now().weekday())
        week = [t for t in tasks if (t.get("startTime") or "")[:10] >= monday.isoformat()]
        last = tasks[0] if tasks else {}
        with lock:
            state["printer"]["week"] = {"count": len(week), "hours": round(sum(t.get("costTime", 0) for t in week) / 3600),
                                        "grams": round(sum(t.get("weight", 0) for t in week))}
            state["printer"]["last"] = {"title": last.get("title"), "status": last.get("status")}

    # --- minimal MQTT ---
    @staticmethod
    def _str(s):
        b = s.encode()
        return struct.pack(">H", len(b)) + b

    @staticmethod
    def _pkt(ptype, body):
        n, enc = len(body), b""
        while True:
            d, n = n % 128, n // 128
            enc += bytes([d | (0x80 if n else 0)])
            if not n:
                break
        return bytes([ptype]) + enc + body

    @staticmethod
    def _recvn(sock, n):
        data = b""
        while len(data) < n:
            try:
                chunk = sock.recv(n - len(data))
            except socket.timeout:
                raise ConnectionError("timeout inside a packet")
            if not chunk:
                raise ConnectionError("closed")
            data += chunk
        return data

    def _read(self, sock):
        """One MQTT packet; raises socket.timeout only if no packet started."""
        h = sock.recv(1)
        if not h:
            raise ConnectionError("closed")
        mult, n = 1, 0
        while True:
            b = self._recvn(sock, 1)[0]
            n += (b & 127) * mult
            mult *= 128
            if not b & 128:
                break
        return h[0], self._recvn(sock, n)

    def merge(self, d, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                self.merge(d[k], v)
            else:
                d[k] = v

    def publish_state(self, dev):
        p = self.report
        g = lambda *ks, default=None: next((p[k] for k in ks if k in p), default)
        nozzle, nozzle_t = g("nozzle_temper"), g("nozzle_target_temper")
        ext = (p.get("device") or {}).get("extruder", {}).get("info") or []
        if nozzle is None and ext:  # newer firmware packs current/target into one int
            t = ext[0].get("temp", 0)
            nozzle, nozzle_t = t & 0xFFFF, t >> 16
        bed, bed_t = g("bed_temper"), g("bed_target_temper")
        bedinfo = (p.get("device") or {}).get("bed", {}).get("info") or {}
        if bed is None and "temp" in bedinfo:
            bed, bed_t = bedinfo["temp"] & 0xFFFF, bedinfo["temp"] >> 16
        trays, active = [], str((p.get("ams") or {}).get("tray_now", ""))
        for unit in (p.get("ams") or {}).get("ams", [])[:1]:
            for t in unit.get("tray", [])[:4]:
                trays.append({"type": t.get("tray_type"), "color": "#" + (t.get("tray_color") or "00000000")[:6] if t.get("tray_type") else None,
                              "remain": t.get("remain"), "active": str(int(unit.get("id", 0)) * 4 + int(t.get("id", 0))) == active})
        hms = p.get("hms") or []
        with lock:
            state["printer"].update({
                "name": dev.get("name"), "online": True, "updated": time.time(),
                "state": p.get("gcode_state"), "pct": p.get("mc_percent"), "remainingMin": p.get("mc_remaining_time"),
                "layer": p.get("layer_num"), "layers": p.get("total_layer_num"), "job": p.get("subtask_name"),
                "nozzle": nozzle, "nozzleTarget": nozzle_t, "bed": bed, "bedTarget": bed_t,
                "ams": trays, "hms": len(hms), "hmsCodes": [f"{h.get('attr', 0):08X}-{h.get('code', 0):08X}" for h in hms[:3]]})

    def session(self, c):
        token = c["accessToken"]
        uid = c.get("uid") or self.rest("/v1/design-user-service/my/preference", token)["uid"]
        devs = self.rest("/v1/iot-service/api/user/bind", token).get("devices", [])
        if not devs:
            raise RuntimeError("no printers bound to account")
        dev = devs[0]
        with lock:
            state["printer"].update(name=dev.get("name"), model=dev.get("dev_product_name"), online=dev.get("online"))
        self.history(token)
        host = "cn.mqtt.bambulab.com" if c.get("region") == "cn" else "us.mqtt.bambulab.com"
        raw = socket.create_connection((host, 8883), timeout=30)
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as sock:
            self._mqtt(sock, dev, uid, token)

    def _mqtt(self, sock, dev, uid, token):
        body = self._str("MQTT") + bytes([4, 0xC2]) + struct.pack(">H", 60) + self._str(f"desktop-hud-{os.getpid()}") \
            + self._str(f"u_{uid}") + self._str(token)
        sock.sendall(self._pkt(0x10, body))
        t, d = self._read(sock)
        if t >> 4 != 2 or d[1] != 0:
            raise RuntimeError(f"MQTT connect refused ({d[1] if len(d) > 1 else '?'})")
        sid = dev["dev_id"]
        sock.sendall(self._pkt(0x82, struct.pack(">H", 1) + self._str(f"device/{sid}/report") + b"\x00"))
        push = json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}).encode()
        sock.sendall(self._pkt(0x30, self._str(f"device/{sid}/request") + push))
        clear_err("bambu")
        last_ping = last_hist = last_push = last_report = time.time()
        last_state = self.report.get("gcode_state")
        sock.settimeout(20)
        while True:
            try:
                t, d = self._read(sock)
                if t >> 4 == 3:
                    last_report = time.time()
                    tl = struct.unpack(">H", d[:2])[0]
                    payload = d[2 + tl + (2 if (t >> 1) & 3 else 0):]
                    msg = json.loads(payload)
                    if "print" in msg:
                        self.merge(self.report, msg["print"])
                        self.publish_state(dev)
                        st = self.report.get("gcode_state")
                        if st != last_state and st in ("FINISH", "FAILED"):  # a print just ended
                            self.history(token); last_hist = time.time()
                        last_state = st
            except socket.timeout:
                pass
            now = time.time()
            if now - last_ping > 45:
                sock.sendall(b"\xc0\x00"); last_ping = now
            if now - last_push > 300:  # resync full state now and then
                sock.sendall(self._pkt(0x30, self._str(f"device/{sid}/request") + push)); last_push = now
            if now - last_hist > 3600:
                self.history(token); last_hist = now
            if now - last_report > 360:  # a pushall goes out every 5 min; no answer means a dead subscription
                raise ConnectionError("no printer report for 6 min")

    def run(self):
        while True:
            if not cfg("bambu"):
                with lock:
                    state["printer"] = {"disabled": True}
                time.sleep(60)
                continue
            c = self.creds()
            if not c:
                with lock:
                    state["printer"] = {"configured": False}
                time.sleep(60)
                continue
            # Bambu's refresh endpoint rejects third-party clients (401), so the
            # ~90-day token can't be renewed here; the widget warns a week ahead.
            with lock:
                state["printer"].pop("configured", None)
                state["printer"]["tokenExpiresAt"] = c.get("expiresAt", 0)
            if c.get("expiresAt", 0) < time.time():
                with lock:
                    state["printer"]["online"] = False
                time.sleep(600)
                continue
            try:
                self.session(c)
            except Exception as e:
                log_err("bambu", e)
                with lock:
                    state["printer"]["online"] = False
            time.sleep(30)


# ------------------------------------------------------------------- main ---
def every(sec, fn, key, sched):
    """Run fn if `sec` seconds passed since its last run (sec may vary from call to call)."""
    if time.time() - sched.get(key, 0) >= sec:
        sched[key] = time.time()
        try:
            fn()
            clear_err(key)
        except Exception as e:
            log_err(key, e)


def slow_loop(cl):
    # after a restart, don't repeat slow fetches whose seeded data is still fresh
    sched = {"github_traffic": state["github"].get("trafficAt", 0), "weather": state["weather"].get("at", 0)}
    while True:
        every(60, wifi, "wifi", sched)
        every(60, cl.scan, "tokens", sched)
        every(cl.limits_interval(), cl.limits, "limits", sched)
        every(300, cl.status, "status", sched)
        every(1800, weather, "weather", sched)
        every(900, github_focus, "github_focus", sched)
        every(3 * 3600, github_traffic, "github_traffic", sched)
        time.sleep(2)


def main():
    os.makedirs(APP, exist_ok=True)
    # seed slow sources from the last run so panels aren't empty while they refresh
    prev = load_json(STATE, {})
    for k in ("github", "weather"):
        state[k] = prev.get(k) or {}
    state["claude"].update({k: v for k, v in (prev.get("claude") or {}).items() if k in ("fiveHour", "week", "plan", "service")})
    sysm, cl = System(), Claude()
    Bambu().start()
    threading.Thread(target=slow_loop, args=(cl,), daemon=True).start()
    sched = {}
    while True:
        t0 = time.time()
        every(0, sysm.fast, "sys", sched)
        every(30, cl.sessions, "sessions", sched)
        ru_self, ru_kids = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        with lock:
            state["t"] = time.time()
            state["cpuSeconds"] = {"self": ru_self.ru_utime + ru_self.ru_stime, "children": ru_kids.ru_utime + ru_kids.ru_stime}
            save_json(STATE, state)
        time.sleep(max(0.2, 2 - (time.time() - t0)))


if __name__ == "__main__":
    main()
