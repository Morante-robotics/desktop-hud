#!/usr/bin/env python3
"""Sign in to Bambu Lab cloud and store the token for the HUD daemon.

Terminal:  python3 bambu_login.py
Dialogs:   python3 bambu_login.py --gui   (what the HUD's "Renew" button runs)

Your password is sent only to api.bambulab.com and is never stored. Only the
resulting token (valid ~90 days) and your email (to prefill next time) are saved,
readable by you only, at ~/Library/Application Support/DesktopHUD/bambu.json.
"""
import getpass, json, os, subprocess, sys, time, urllib.error, urllib.request

API = "https://api.bambulab.com"
OUT = os.path.expanduser("~/Library/Application Support/DesktopHUD/bambu.json")
GUI = "--gui" in sys.argv
TITLE = "Desktop HUD · Bambu Lab"


class Cancelled(Exception):
    pass


def _osa(script, *args):
    r = subprocess.run(["osascript", "-e", script, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise Cancelled()
    return r.stdout.rstrip("\n")


def ask(prompt, default="", hidden=False):
    if not GUI:
        return (getpass.getpass(prompt + ": ") if hidden else input(prompt + ": ")).strip()
    # values go in as argv, never interpolated into the AppleScript source
    return _osa('on run argv\n display dialog (item 1 of argv) default answer (item 2 of argv) '
                + ('with hidden answer ' if hidden else '')
                + f'with title "{TITLE}" buttons {{"Cancel", "OK"}} default button "OK"\n'
                ' return text returned of result\nend run', prompt, default).strip()


def tell(msg, error=False):
    if not GUI:
        print(msg)
    elif error:
        subprocess.run(["osascript", "-e", 'on run argv\n display alert "Bambu Lab sign-in failed" message (item 1 of argv) as critical\nend run', msg])
    else:
        subprocess.run(["osascript", "-e", f'on run argv\n display notification (item 1 of argv) with title "{TITLE}"\nend run', msg])


def post(path, data, token=None):
    h = {"Content-Type": "application/json", "User-Agent": "DesktopHUD/1.0"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API + path, data=json.dumps(data).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            return json.loads(body) if body.strip() else {}  # sendemail/code answers 200 with no body
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Bambu Lab answered {e.code}: {e.read().decode()[:300]}")


def get(path, token):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + token, "User-Agent": "DesktopHUD/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def login():
    prev = {}
    try:
        prev = json.load(open(OUT))
    except Exception:
        pass
    if not GUI:
        print("Bambu Lab sign-in for the desktop HUD (read-only printer status).")
    email = ask("Bambu Lab account email", prev.get("email", ""))
    pw = ask("Bambu Lab password (not stored)", hidden=True)
    r = post("/v1/user-service/user/login", {"account": email, "password": pw})
    if r.get("loginType") == "tfa":
        raise RuntimeError("Your account uses app-based two-factor auth; this script does not support it yet.")
    if not r.get("accessToken"):  # loginType "verifyCode": Bambu wants an emailed code
        post("/v1/user-service/user/sendemail/code", {"email": email, "type": "codeLogin"})
        code = ask("Bambu Lab emailed you a code. Enter it")
        r = post("/v1/user-service/user/login", {"account": email, "code": code})
    token = r.get("accessToken")
    if not token:
        raise RuntimeError(f"No token received: {r}")
    uid = get("/v1/design-user-service/my/preference", token).get("uid")
    devs = get("/v1/iot-service/api/user/bind", token).get("devices", [])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = {"accessToken": token, "uid": uid, "email": email, "region": "global",
            "expiresAt": time.time() + int(r.get("expiresIn", 7776000))}
    fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    # restart the HUD service so it reconnects with the new token right away
    subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/local.desktop-hud"], capture_output=True)
    names = ", ".join(d.get("name", "?") for d in devs) or "none"
    tell(f"Linked for ~90 days. Printers: {names}.")


def main():
    try:
        login()
    except Cancelled:
        pass
    except Exception as e:
        tell(str(e), error=True)
        if not GUI:
            sys.exit(1)


if __name__ == "__main__":
    main()
