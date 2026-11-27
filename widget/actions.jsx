// Desktop HUD — renewal buttons. Lives in Übersicht's interactive (foreground) layer,
// unlike the main HUD, and renders nothing unless a login needs renewing.
import { React, run } from "uebersicht";

const APP = "$HOME/Library/Application Support/DesktopHUD";
export const command = `cat "${APP}/state.json" 2>/dev/null`;
export const refreshFrequency = 15000;
export const className = "left:0;top:0;width:0;height:0;overflow:visible;";

export const initialState = { s: null, busy: {} };
export const updateState = (event, prev) => {
  if (event.type === "BUSY") return { ...prev, busy: { ...prev.busy, [event.key]: event.on } };
  try { return { ...prev, s: JSON.parse(event.output) }; } catch (e) { return prev; }
};

const RESTART = 'launchctl kickstart -k "gui/$(id -u)/local.desktop-hud"';
const ENV = 'PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"';
const ACTIONS = {
  // Same renewal the service tries hourly on its own; this is the manual fallback. If the CLI
  // is signed out there is nothing to renew, so open Terminal on `claude auth login` instead
  // (the browser sign-in needs you); the service restarts once you finish.
  claude: `cd "${APP}"; ${ENV}; C="$(command -v claude)"; ` +
          `if "$C" auth status --json 2>/dev/null | grep -Eq '"loggedIn": *true'; then ` +
          `"$C" -p --no-session-persistence --model haiku "Reply with: ok" >/dev/null 2>&1; ${RESTART}; ` +
          `else osascript -e "tell application \\"Terminal\\" to do script \\"$C auth login && launchctl kickstart -k gui/$(id -u)/local.desktop-hud\\"" ` +
          `-e 'tell application "Terminal" to activate' >/dev/null; fi`,
  // Opens macOS dialogs for email, password (hidden, not stored) and the emailed code.
  bambu: `${ENV}; python3 -I "${APP}/bambu_login.py" --gui`,
};

const Button = ({ id, label, style, busy, dispatch }) => (
  <div className={`ma-btn ${busy ? "busy" : ""}`} style={style} onClick={() => {
    if (busy) return;
    dispatch({ type: "BUSY", key: id, on: true });
    run(ACTIONS[id]).catch(() => {}).then(() => dispatch({ type: "BUSY", key: id, on: false }));
  }}>
    <i />{busy ? "RENEWING…" : label}
  </div>
);

export const render = ({ s, busy }, dispatch) => {
  if (!s) return null;
  const p = s.printer || {}, c = s.claude || {};
  const needBambu = !p.disabled && p.configured === false || (p.tokenExpiresAt && p.tokenExpiresAt - Date.now() / 1000 < 7 * 86400);
  const needClaude = !!c.limitsStale;
  if (!needBambu && !needClaude) return null;
  // same screen fit as hud.jsx (keep 1760 × 1060 in step with its MIN_W / MIN_H)
  const W = window.innerWidth, H = window.innerHeight;
  const k = Math.min(1, W / 1760, H / 1060);
  return (
    <div style={{ position: "absolute", left: 0, top: 0, transformOrigin: "0 0", transform: k < 1 ? `scale(${k})` : undefined }}>
      <style>{CSS}</style>
      {needClaude && <Button id="claude" label={c.signedOut ? "SIGN IN TO CLAUDE" : "RENEW CLAUDE SESSION"} busy={busy.claude} dispatch={dispatch}
        style={{ left: 40, top: 578 }} />}
      {needBambu && <Button id="bambu" label={p.configured === false ? "LINK BAMBU LAB" : "RENEW BAMBU LOGIN"} busy={busy.bambu}
        dispatch={dispatch} style={{ left: W / k - 280, top: 578 }} />}
    </div>
  );
};

const CSS = `
.ma-btn{position:absolute;width:240px;height:30px;display:flex;align-items:center;gap:10px;padding:0 14px;cursor:pointer;
  font-family:'Share Tech Mono',Menlo,monospace;font-size:12px;letter-spacing:.16em;color:#ff9b3d;
  background:rgba(6,22,51,.92);border:1px solid rgba(255,155,61,.7);box-shadow:0 0 10px rgba(255,155,61,.25)}
.ma-btn:hover{background:rgba(60,32,10,.92);color:#ffd2a6}
.ma-btn i{width:8px;height:8px;background:#ff9b3d;box-shadow:0 0 6px #ff9b3d}
.ma-btn.busy{cursor:default;color:#5ab4ff;border-color:rgba(90,180,255,.6);box-shadow:none}
.ma-btn.busy i{background:#5ab4ff;box-shadow:0 0 6px #5ab4ff;animation:ma-pulse 1.2s ease-in-out infinite;will-change:opacity}
@keyframes ma-pulse{50%{opacity:.2}}
`;
