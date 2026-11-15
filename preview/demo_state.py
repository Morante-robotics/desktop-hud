"""Made-up state.json for screenshots and for trying the widget without the daemon.
Times are relative to now, so the HUD never shows it as frozen or expired.
Nothing here comes from a real machine or account."""
import math, time
from datetime import datetime, timedelta, timezone


def make():
    now = time.time()
    iso = lambda h: (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()
    hist = [round(22 + 14 * math.sin(i / 6) + 9 * math.sin(i / 2.3)) for i in range(60)]
    return {
        "t": now,
        "sys": {
            "cpu": hist[-1], "cores": [31, 18, 44, 12, 27, 9, 38, 15], "cpuHist": hist,
            "memPressure": 46, "swapGB": 0.4, "down": 2.4e6, "up": 3.1e5,
            "top": [["Bambu Studio", 41], ["Claude", 18], ["macOS system", 9]],
            "battery": {"pct": 84, "state": "charging", "ac": True, "remaining": "0:42"},
            "diskUsedPct": 63, "diskFreeGB": 371, "uptime": 3 * 86400 + 5 * 3600,
            "model": "MacBookPro18,3", "cpuName": "Apple M1 Pro", "ramGB": 16, "os": "15.1",
        },
        "net": {"ssid": "WORKSHOP-5G", "online": True},
        "claude": {
            "fiveHour": {"pct": 38, "resetsAt": iso(2.6)}, "week": {"pct": 57, "resetsAt": iso(52)},
            "plan": "max", "limitsAt": now - 60, "limitsStale": False,
            "service": {"indicator": "none", "incident": None},
            "tokensToday": 3_480_000, "tokensWeek": 21_900_000,
            "sessions": [
                {"name": "robot-arm · gripper CAD", "status": "busy", "since": (now - 300) * 1000},
                {"name": "desktop-hud · NAS panel", "status": "waiting", "since": (now - 900) * 1000},
                {"name": "build-log draft", "status": "idle", "since": (now - 4000) * 1000},
            ],
            "sessionCount": 3,
            "recent": [
                {"t": int(now - 240), "title": "desktop-hud", "prompt": "Add a panel with my NAS disk temperatures, every 5 min"},
                {"t": int(now - 1900), "title": "robot-arm", "prompt": "Make the gripper jaw 0.2 mm looser and re-run the fit check"},
                {"t": int(now - 5200), "title": "", "prompt": "Summarise today's build log in three lines"},
            ],
        },
        "printer": {
            "name": "Workshop printer", "model": "Bambu Lab P2S", "online": True, "updated": now - 3,
            "state": "RUNNING", "pct": 62, "remainingMin": 74, "layer": 148, "layers": 236,
            "job": "gripper_jaw_v3.3mf", "nozzle": 220, "nozzleTarget": 220, "bed": 65, "bedTarget": 65,
            "ams": [{"type": "PLA", "color": "#1b1b1b", "remain": 71, "active": True},
                    {"type": "PLA", "color": "#f2f2f2", "remain": 34, "active": False},
                    {"type": "PETG", "color": "#2f7fd6", "remain": 12, "active": False},
                    {"type": None, "color": None, "remain": -1, "active": False}],
            "hms": 0, "hmsCodes": [], "tokenExpiresAt": now + 60 * 86400,
            "week": {"count": 9, "hours": 31, "grams": 640}, "last": {"title": "servo bracket", "status": "finish"},
        },
        "github": {
            "org": "your-name", "stars": 128, "forks": 17, "views": 2140, "visitors": 611,
            "daily": [96, 120, 88, 140, 210, 180, 132, 118, 150, 172, 260, 198, 164, 101],
            "repos": [{"name": "robot-arm", "stars": 74, "views": 1260, "d24": 58},
                      {"name": "desktop-hud", "stars": 41, "views": 690, "d24": 31},
                      {"name": "build-notes", "stars": 13, "views": 190, "d24": 0}],
            "referrers": [["github.com", 41], ["youtube.com", 27], ["google.com", 19], ["reddit.com", 13]],
            "focus": {"name": "robot-arm", "commits": [["a41c9e2", "Gripper jaw v3: looser fit, chamfered edge"],
                                                        ["7d03b51", "Build log: first grip test"]]},
            "trafficAt": now,
        },
        "weather": {
            "city": "Lisbon", "source": "macos", "temp": 19, "desc": "partly cloudy", "max": 22, "min": 14,
            "rain": [[f"{(datetime.now().hour + i) % 24:02d}", p] for i, p in
                     enumerate([0, 0, 5, 10, 20, 45, 60, 55, 30, 10, 5, 0])],
            "alerts": [], "at": now,
        },
        "errors": {},
    }
