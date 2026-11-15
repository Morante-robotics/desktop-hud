#!/bin/bash
# Installs the Desktop HUD: data daemon (launchd), location helper and the Übersicht widget.
# Re-run after editing any source file. Uninstall with: ./install.sh --uninstall
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Library/Application Support/DesktopHUD"
WIDGETS="$HOME/Library/Application Support/Übersicht/widgets"
AGENT="$HOME/Library/LaunchAgents/local.desktop-hud.plist"
LABEL="local.desktop-hud"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$AGENT"; rm -rf "$WIDGETS/desktop-hud"
  echo "Uninstalled (data and tokens remain in $APP; delete it by hand if you want)."
  exit 0
fi

mkdir -p "$APP" "$WIDGETS/desktop-hud" "$HOME/Library/LaunchAgents"

# daemon
cp "$SRC/daemon/hud_daemon.py" "$SRC/daemon/bambu_login.py" "$APP/"
[[ -f "$APP/config.json" ]] || cp "$SRC/config.example.json" > "$APP/config.json"

# location helper app (ad-hoc signed so macOS can ask for location permission)
BUNDLE="$APP/HUDLocate.app/Contents"
mkdir -p "$BUNDLE/MacOS"
cp "$SRC/locate/Info.plist" "$BUNDLE/Info.plist"
clang -fobjc-arc -O2 -mmacosx-version-min=12.0 -framework Foundation -framework CoreLocation \
  -o "$BUNDLE/MacOS/HUDLocate" "$SRC/locate/main.m"
codesign --force --sign - "$APP/HUDLocate.app" >/dev/null

# launchd agent: starts at login, restarts if it dies, low priority
PY="$(command -v python3)"
cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>-I</string><string>$APP/hud_daemon.py</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>20</integer>
  <key>ProcessType</key><string>Background</string>
  <key>Nice</key><integer>10</integer>
  <key>StandardErrorPath</key><string>$APP/daemon.log</string>
  <key>StandardOutPath</key><string>$APP/daemon.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT"

# widget
cp "$SRC/widget/hud.jsx" "$WIDGETS/desktop-hud/hud.jsx"
cp "$SRC/widget/actions.jsx" "$WIDGETS/desktop-hud/actions.jsx"   # foreground layer: renewal buttons
# Übersicht only paints widgets flagged "inBackground" in its desktop-level window when
# interaction is off; set the flag once (Übersicht must be stopped while its settings change).
SETTINGS="$HOME/Library/Application Support/tracesOf.Uebersicht/WidgetSettings.json"
# The renewal buttons need Übersicht's interaction layer on (clicks only land on widgets in it).
NEED_RESTART=0
if [[ "$(defaults read tracesOf.Uebersicht enableInteraction 2>/dev/null)" != "1" ]]; then
  NEED_RESTART=1
fi
if ! python3 -I -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("desktop-hud-hud-jsx",{}).get("inBackground") else 1)' "$SETTINGS" 2>/dev/null; then
  NEED_RESTART=1
fi
if [[ $NEED_RESTART == 1 ]]; then
  pkill -TERM -f 'Contents/MacOS/.*bersicht$' || true; sleep 2
  defaults write tracesOf.Uebersicht enableInteraction -bool true
  python3 -I - "$SETTINGS" <<'PY'
import json, os, sys
f = sys.argv[1]
d = json.load(open(f)) if os.path.exists(f) else {}
d.setdefault("desktop-hud-hud-jsx", {"showOnAllScreens": True, "hidden": False, "screens": []})["inBackground"] = True
json.dump(d, open(f, "w"))
PY
  open -g -b tracesOf.Uebersicht
fi
echo "Desktop HUD installed."
