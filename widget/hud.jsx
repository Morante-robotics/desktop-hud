// Desktop HUD — Übersicht desktop widget.
// Reads the JSON written by the hud_daemon.py daemon; does no work of its own
// beyond drawing. Only transforms/opacity are animated (GPU), nothing else moves.
import { React } from "uebersicht";

export const command = 'cat "$HOME/Library/Application Support/DesktopHUD/state.json" 2>/dev/null';
export const refreshFrequency = 2000;
export const className = "left:0;top:0;width:100vw;height:100vh;pointer-events:none;";

export const initialState = { s: null };
// keep the last good snapshot if a read fails or catches the file mid-write
export const updateState = (event, prev) => {
  try { return { s: JSON.parse(event.output) }; } catch (e) { return prev; }
};

// ---------------------------------------------------------------- helpers
const C = { c: "#6fe3ff", sky: "#5ab4ff", blue: "#2f7fd6", hot: "#dff6ff", mute: "#4f7fae", warn: "#ff9b3d", crit: "#ff5a3c", ok: "#5fffc3", box: "#061633", txt: "#a9d4f5" };
const lvl = (v, w, c, low) => v == null ? "" : low ? (v <= c ? "crit" : v <= w ? "warn" : "") : (v >= c ? "crit" : v >= w ? "warn" : "");
const worst = (...l) => l.includes("crit") ? "crit" : l.includes("warn") ? "warn" : "";
const pad = (n) => String(n).padStart(2, "0");
const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const resetLabel = (iso) => {
  if (!iso) return "";
  const d = new Date(iso), now = new Date();
  return d - now < 20 * 3600e3 ? hhmm(d) : `${DAYS[d.getDay()]} ${hhmm(d)}`;
};
const rate = (b) => b == null ? "—" : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB/s` : `${Math.round(b / 1e3)} KB/s`;
const tok = (n) => n == null ? "—" : n >= 1e6 ? `${(n / 1e6).toFixed(2)} M` : `${Math.round(n / 1e3)} K`;
const dur = (min) => min == null ? "—" : min >= 60 ? `${Math.floor(min / 60)} h ${pad(min % 60)} min` : `${min} min`;
const uptime = (s) => { if (s == null) return ""; const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  return d ? `${d} D ${h} H` : h ? `${h} H` : `${Math.floor(s / 60)} MIN`; };
const polar = (deg, r) => [r * Math.sin((deg * Math.PI) / 180), -r * Math.cos((deg * Math.PI) / 180)];
const angleOf = (d) => ((d.getHours() + d.getMinutes() / 60) / 24) * 360;
const arc = (a0, a1, r) => {
  const [x0, y0] = polar(a0, r), [x1, y1] = polar(a1, r);
  let span = a1 - a0; if (span < 0) span += 360;
  return `M${x0},${y0} A${r},${r} 0 ${span > 180 ? 1 : 0} 1 ${x1},${y1}`;
};

const Bar = ({ pct, level, thick, marks = [75, 90] }) => (
  <div className={`mh-bar ${thick ? "thick" : ""} ${level}`}>
    <i style={{ width: `${Math.min(100, pct || 0)}%` }} />
    {marks.map((m) => <u key={m} style={{ left: `${m}%` }} />)}
  </div>
);
const Head = ({ title, sub, level, right }) => (
  <div className="mh-hd">
    <div className="mh-tag">{title}<small>{sub}</small></div>
    <div className="mh-rule" />
    {right || <div className={`mh-sq ${level}`} />}
  </div>
);

// ------------------------------------------------------------------ panels
const System = ({ s }) => {
  const y = s.sys || {};
  const cpuAvg = (y.cpuHist || []).slice(-10).reduce((a, b) => a + b, 0) / Math.max(1, Math.min(10, (y.cpuHist || []).length));
  const lc = lvl(cpuAvg, 85, 95), lm = lvl(y.memPressure, 75, 90), ld = lvl(y.diskUsedPct, 80, 90);
  const b = y.battery || {};
  const lb = b.ac ? "" : lvl(b.pct, 20, 10, true);
  const hist = y.cpuHist || [];
  const pts = hist.map((v, i) => `${(i / 59) * 440},${54 - (v / 100) * 50}`).join(" ");
  return (
    <div className="mh-sec" style={{ left: 40, top: 116, width: 440 }}>
      <Head title="SYSTEM" sub="DIAGNOSTICS · EVERY 2 S" level={worst(lc, lm, ld, lb)} />
      <div className={`mh-row ${lc}`}><span className="mh-lbl">CPU · {(y.cores || []).length} threads</span><span className="mh-big" style={{ fontSize: 34 }}>{y.cpu ?? "—"}<span style={{ fontSize: 18 }}>%</span></span></div>
      <svg width="440" height="54" style={{ display: "block", margin: "2px 0 4px" }}>
        {hist.length > 1 && <polyline fill="rgba(90,180,255,.07)" stroke={C.c} strokeWidth="1.2" points={`0,54 ${pts} ${((hist.length - 1) / 59) * 440},54`} />}
      </svg>
      <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>{(y.cores || []).map((c, i) => <div key={i} style={{ flex: 1 }}><Bar pct={c} marks={[]} /></div>)}</div>
      <div className={lm}><div className="mh-row"><span className="mh-lbl">Memory pressure · swap {y.swapGB ?? 0} GB</span><span><span className="mh-val">{y.memPressure ?? "—"}%</span>{lm && <span className="mh-st">{lm === "crit" ? "OUT OF MEMORY" : "HIGH"}</span>}</span></div><Bar pct={y.memPressure} level={lm} /></div>
      <div className={ld} style={{ marginTop: 12 }}><div className="mh-row"><span className="mh-lbl">Disk · {y.diskFreeGB ?? "—"} GB free</span><span><span className="mh-val">{y.diskUsedPct ?? "—"}%</span>{ld && <span className="mh-st">{ld === "crit" ? "ALMOST FULL" : "FILLING UP"}</span>}</span></div><Bar pct={y.diskUsedPct} level={ld} marks={[80, 90]} /></div>
      <div className={lb} style={{ marginTop: 12 }}>
        <div className="mh-row"><span className="mh-lbl">Battery · {b.ac ? (b.state === "charging" ? `charging${b.remaining && b.remaining !== "0:00" ? ` · full in ${b.remaining}` : ""}` : "plugged in") : `${b.remaining ? `${b.remaining} left` : "on battery"}`}</span><span className="mh-val">{b.pct ?? "—"}%</span></div>
        <div className={`mh-blocks ${lb}`}>{Array.from({ length: 10 }, (_, i) => <b key={i} className={i < Math.round((b.pct || 0) / 10) ? "on" : ""} />)}</div>
      </div>
      <div style={{ display: "flex", gap: 40, marginTop: 14 }}>
        <div><div className="mh-lbl">Down</div><div className="mh-val" style={{ fontSize: 18 }}>{rate(y.down)}</div></div>
        <div><div className="mh-lbl">Up</div><div className="mh-val" style={{ fontSize: 18 }}>{rate(y.up)}</div></div>
      </div>
      <div className="mh-lbl" style={{ marginTop: 14 }}>Top processes</div>
      <div className="mh-list">{(y.top || []).map(([n, p], i) => <span key={n}>{i > 0 && " · "}<b>{n}</b> {p}%</span>)}</div>
      <div className="mh-dim" style={{ marginTop: 6 }}>{[y.model, y.cpuName, y.ramGB && `${y.ramGB} GB`, y.os && `MACOS ${y.os}`, y.uptime && `LAST RESTART ${uptime(y.uptime)} AGO`].filter(Boolean).join(" · ").toUpperCase()}</div>
    </div>
  );
};

// a limit window whose reset time has passed is back at 0 %, even if the data is stale
const rolled = (p) => (p && p.resetsAt && new Date(p.resetsAt) < new Date() ? { pct: 0, resetsAt: null } : p);
const STATUS = { busy: ["WORKING", "busy", ""], waiting: ["NEEDS YOU", "wait", "hot"], needs_input: ["NEEDS YOU", "wait", "hot"], blocked: ["NEEDS YOU", "wait", "hot"] };
const Claude = ({ s }) => {
  const c = s.claude || {};
  const f = rolled(c.fiveHour), w = rolled(c.week);
  const lf = lvl(f && f.pct, 75, 90), lw = lvl(w && w.pct, 75, 90);
  const svc = c.service || {};
  const svcL = svc.indicator === "none" ? ["● OPERATIONAL", C.ok] : svc.indicator === "minor" ? ["● MINOR INCIDENT", C.warn] : svc.indicator ? ["● MAJOR INCIDENT", C.crit] : ["", C.mute];
  const Limit = ({ label, p, l, warnTxt }) => (
    <div className={l} style={{ marginTop: 12 }}>
      <div className="mh-row"><span className="mh-lbl">{label}{l && <span className="mh-st">{warnTxt}</span>}</span><span className="mh-big" style={{ fontSize: 28 }}>{p ? p.pct : "—"}<span style={{ fontSize: 15 }}>%</span></span></div>
      <Bar pct={p && p.pct} level={l} thick />
    </div>
  );
  return (
    <div className="mh-sec" style={{ left: 40, top: 620, width: 440 }}>
      <Head title="CLAUDE" sub="AGENTS · EVERY 30 S" right={<div className="mh-meta" style={{ color: svcL[1] }}>{svcL[0]}</div>} />
      {svc.incident && <div className="mh-dim mh-ell" style={{ color: svcL[1], opacity: 0.9, marginTop: -6 }}>{svc.incident.toUpperCase()}</div>}
      <Limit label={`5-hour window${f && f.resetsAt ? ` · resets ${resetLabel(f.resetsAt)}` : ""}`} p={f} l={lf} warnTxt={lf === "crit" ? "AT LIMIT" : "NEAR LIMIT"} />
      <Limit label={`Weekly${w && w.resetsAt ? ` · resets ${resetLabel(w.resetsAt)}` : ""}`} p={w} l={lw} warnTxt={lw === "crit" ? "AT LIMIT" : "NEAR LIMIT"} />
      {c.limitsStale && <div className="mh-dim" style={{ marginTop: 6, color: C.warn, opacity: 0.9 }}>{c.limitsAt ? `AS OF ${hhmm(new Date(c.limitsAt * 1000))} · ` : ""}SESSION EXPIRED · USE CLAUDE IN THE TERMINAL TO REFRESH</div>}
      <div className="mh-dim" style={{ marginTop: 8 }}>TOKENS TODAY {tok(c.tokensToday)} · THIS WEEK {tok(c.tokensWeek)}{c.plan ? ` · PLAN ${c.plan.toUpperCase()}` : ""}</div>
      <div className="mh-lbl" style={{ margin: "16px 0 4px" }}>Active sessions · {c.sessionCount ?? 0}</div>
      <div className="mh-list" style={{ fontSize: 14 }}>
        {(c.sessions || []).map((x, i) => {
          const [txt, ind, pill] = STATUS[x.status] || ["IDLE", "idle", "dimp"];
          return <div key={i} className="mh-row"><span className="mh-ell"><i className={`mh-ind ${ind}`} />{x.name}</span><span className={`mh-pill ${pill}`}>{txt}</span></div>;
        })}
        {!(c.sessions || []).length && <div className="mh-dim">NO OPEN SESSIONS</div>}
      </div>
      {(c.recent || []).length > 0 && <>
        <div className="mh-lbl" style={{ marginTop: 14 }}>Recent activity</div>
        <div className="mh-list" style={{ fontSize: 12, lineHeight: 1.7, color: C.mute }}>
          {c.recent.map((r, i) => <div key={i} className="mh-ell"><b>{hhmm(new Date(r.t * 1000))}</b> {r.title ? `${r.title} · ` : ""}“{r.prompt}”</div>)}
        </div>
      </>}
    </div>
  );
};

const PSTATE = { RUNNING: ["PRINTING", ""], PREPARE: ["PREPARING", ""], SLICING: ["PREPARING", ""], PAUSE: ["PAUSED", "warn"], FAILED: ["FAILED", "crit"], FINISH: ["FINISHED", ""], IDLE: ["IDLE", ""] };
const Printer = ({ s }) => {
  const p = s.printer || {};
  const frozen = p.online === false || (p.updated && Date.now() / 1000 - p.updated > 600);
  const [stTxt, stL] = frozen ? ["OFFLINE", "warn"] : PSTATE[p.state] || ["NO DATA", ""];
  const printing = !frozen && p.state === "RUNNING";
  const amsL = (p.ams || []).map((t) => (t.type ? lvl(t.remain, 20, 10, true) : ""));
  const days = p.tokenExpiresAt ? (p.tokenExpiresAt - Date.now() / 1000) / 86400 : null;
  const lt = days == null ? "" : days < 1 ? "crit" : days < 7 ? "warn" : "";
  const level = worst(stL, p.hms ? "crit" : "", lt, ...amsL);
  const pct = p.pct ?? 0;
  if (p.disabled) return null;
  if (p.configured === false) return (
    <div className="mh-sec" style={{ right: 40, top: 116, width: 440 }}>
      <Head title="FABRICATION" sub="BAMBU LAB · CLOUD" level="warn" />
      <div className="mh-list" style={{ fontSize: 13, color: C.txt }}>Printer not linked.</div>
      <div className="mh-dim" style={{ marginTop: 6 }}>RUN BAMBU_LOGIN.PY IN THE TERMINAL TO LINK YOUR ACCOUNT</div>
    </div>
  );
  return (
    <div className="mh-sec" style={{ right: 40, top: 116, width: 440 }}>
      <Head title="FABRICATION" sub={`${(p.model || "BAMBU LAB").toUpperCase()} · CLOUD`} level={level} />
      <div style={{ display: "flex", gap: 22, alignItems: "center" }}>
        <svg width="150" height="150" viewBox="-75 -75 150 150">
          <circle r="66" fill="none" stroke={C.sky} strokeWidth="2" strokeLinecap="round" strokeDasharray="0 6" opacity=".5" />
          <circle r="56" fill="none" stroke="rgba(60,120,200,.18)" strokeWidth="8" />
          <circle r="56" fill="none" stroke={stL === "crit" ? C.crit : stL === "warn" ? C.warn : C.c} strokeWidth="8" strokeDasharray={`${(pct / 100) * 351.9} 352`} transform="rotate(-90)" />
          <circle r="44" fill="none" stroke={C.blue} strokeDasharray="2 4" />
          <text y="10" textAnchor="middle" fontFamily="Share Tech Mono" fontSize="34" fill={C.hot}>{p.pct != null ? `${pct}%` : "—"}</text>
          <text y="28" textAnchor="middle" fontFamily="Share Tech Mono" fontSize="9" fill={stL === "crit" ? C.crit : stL === "warn" ? C.warn : C.sky} letterSpacing="2">{stTxt}</text>
        </svg>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="mh-lbl">Job</div><div className="mh-val mh-ell" style={{ fontSize: 15 }}>{p.job || (p.last && p.last.title) || "—"}</div>
          <div className="mh-row" style={{ marginTop: 8 }}><span className="mh-lbl">Layer</span><span className="mh-val">{p.layers ? `${p.layer} / ${p.layers}` : "—"}</span></div>
          <div className="mh-row"><span className="mh-lbl">Remaining</span><span className="mh-val">{printing ? dur(p.remainingMin) : "—"}</span></div>
          <div className="mh-row"><span className="mh-lbl">Estimated end</span><span className="mh-val">{printing && p.remainingMin != null ? hhmm(new Date(Date.now() + p.remainingMin * 60e3)) : "—"}</span></div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 26, marginTop: 12 }}>
        <div style={{ flex: 1 }}><div className="mh-row"><span className="mh-lbl">Nozzle</span><span className="mh-val">{p.nozzle != null ? `${Math.round(p.nozzle)} / ${Math.round(p.nozzleTarget || 0)} °C` : "—"}</span></div><Bar pct={p.nozzleTarget ? (100 * p.nozzle) / p.nozzleTarget : 0} marks={[]} /></div>
        <div style={{ flex: 1 }}><div className="mh-row"><span className="mh-lbl">Bed</span><span className="mh-val">{p.bed != null ? `${Math.round(p.bed)} / ${Math.round(p.bedTarget || 0)} °C` : "—"}</span></div><Bar pct={p.bedTarget ? (100 * p.bed) / p.bedTarget : 0} marks={[]} /></div>
      </div>
      <div className="mh-lbl" style={{ marginTop: 14 }}>AMS · filament</div>
      <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
        {(p.ams && p.ams.length ? p.ams : [{}, {}, {}, {}]).map((t, i) => (
          <div key={i} className={`mh-ams ${amsL[i] || ""} ${t.active ? "active" : ""} ${t.type ? "" : "empty"}`}>
            <i style={{ background: t.color || "transparent" }} />
            <span>{t.type ? `${t.type} · ${t.remain >= 0 ? `${t.remain}%` : "?"}` : "EMPTY"}</span>
          </div>
        ))}
      </div>
      <div className="mh-list" style={{ fontSize: 12, marginTop: 10 }}>
        {p.hms ? <span style={{ color: C.crit }}>● {p.hms} HMS alert{p.hms > 1 ? "s" : ""} · {(p.hmsCodes || []).join(" ")}</span> : <span><span style={{ color: C.ok }}>●</span> No HMS alerts</span>}
      </div>
      {lt && <div className="mh-dim" style={{ color: lt === "crit" ? C.crit : C.warn, opacity: 0.9 }}>{days < 0 ? "BAMBU LOGIN EXPIRED" : `BAMBU LOGIN EXPIRES IN ${Math.ceil(days)} D`} · RUN BAMBU_LOGIN.PY</div>}
      {p.week && <div className="mh-dim">THIS WEEK · {p.week.count} PRINTS · {p.week.hours} H · {p.week.grams} G{p.last && p.last.title ? ` · LAST: ${p.last.title.toUpperCase().slice(0, 28)}` : ""}</div>}
    </div>
  );
};

const GitHub = ({ s }) => {
  const g = s.github || {};
  const d = g.daily || [];
  const mx = Math.max(1, ...d);
  if (g.disabled) return null;
  return (
    <div className="mh-sec" style={{ right: 40, top: 620, width: 440 }}>
      <Head title="GITHUB" sub={`${(g.org || "").toUpperCase()} · EVERY 3 H · COMMITS 15 MIN`} />
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        {[["Stars", g.stars], ["Forks", g.forks], ["Views 14 d", g.views], ["Visitors 14 d", g.visitors]].map(([l, v]) => (
          <div key={l}><div className="mh-lbl">{l}</div><div className="mh-big" style={{ fontSize: 30 }}>{v ?? "—"}</div></div>))}
      </div>
      <svg width="440" height="40" style={{ display: "block", margin: "8px 0 6px" }}>
        {d.map((v, i) => { const h = Math.max(2, (v / mx) * 38); return <rect key={i} x={i * 31.4} y={40 - h} width="27" height={h} fill={i === d.length - 1 ? C.c : C.sky} opacity={i === d.length - 1 ? 1 : 0.35 + 0.5 * (v / mx)} />; })}
      </svg>
      <table className="mh-table"><tbody>
        <tr><th>Repo</th><th>★</th><th>Views</th><th>Δ 24 h</th></tr>
        {(g.repos || []).map((r) => <tr key={r.name}><td className="mh-ell" style={{ maxWidth: 250 }}>{r.name}</td><td className="n">{r.stars}</td><td className="n">{r.views}</td><td className="n" style={{ color: r.d24 > 0 ? C.ok : undefined }}>{r.d24 > 0 ? `+${r.d24}` : 0}</td></tr>)}
      </tbody></table>
      {(g.referrers || []).length > 0 && <>
        <div className="mh-lbl" style={{ marginTop: 10 }}>Referrers</div>
        <div className="mh-list" style={{ fontSize: 12 }}>{g.referrers.map(([n, p], i) => <span key={n}>{i > 0 && " · "}<b>{n}</b> {p}%</span>)}</div>
      </>}
      {g.focus && <>
        <div className="mh-lbl" style={{ marginTop: 8 }}>In focus · {g.focus.name}</div>
        <div className="mh-list" style={{ fontSize: 12, lineHeight: 1.7, color: C.mute }}>{(g.focus.commits || []).map(([sha, m]) => <div key={sha} className="mh-ell"><b>{sha}</b> {m}</div>)}</div>
      </>}
    </div>
  );
};

// AEMET warning time span, e.g. "TODAY 10:00 → 23:59" or "MON 10:00 → TUE 06:00"
const dayLabel = (d) => { const n = new Date(); const t = new Date(n.getFullYear(), n.getMonth(), n.getDate());
  const diff = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - t) / 864e5);
  return diff === 0 ? "TODAY" : diff === 1 ? "TOMORROW" : DAYS[d.getDay()].toUpperCase(); };
const alertSpan = (a) => { const f = new Date(a.from * 1000), t = new Date(a.to * 1000);
  const now = Date.now() >= f.getTime() ? "NOW" : `${dayLabel(f)} ${hhmm(f)}`;
  return `${now} → ${dayLabel(t) === dayLabel(f) && now !== "NOW" ? "" : dayLabel(t) + " "}${hhmm(t)}`; };

// Chance of rain for each of the next 12 hours, with a one-line summary.
const Rain = ({ rain }) => {
  const peak = rain.reduce((m, r) => (r[1] > m[1] ? r : m), rain[0]);
  const summary = peak[1] < 20 ? "dry" : `peak ${peak[1]}% at ${peak[0]}:00`;
  return (
    <div style={{ textAlign: "left" }}>
      <div className="mh-lbl">Rain · next 12 h · <span style={{ color: peak[1] >= 50 ? C.c : C.txt }}>{summary}</span></div>
      <svg width="216" height="32" viewBox="0 0 216 32" style={{ display: "block", marginTop: 3 }}>
        {rain.map(([h, p], i) => { const ht = Math.max(1.5, (p / 100) * 18);
          return <g key={i}>
            <rect x={i * 18} y={19 - ht} width="14" height={ht} fill={p >= 50 ? C.c : C.sky} opacity={0.35 + 0.65 * (p / 100)} />
            {i % 3 === 0 && <text x={i * 18 + 7} y="30" fontFamily="Share Tech Mono" fontSize="9" fill={C.mute} textAnchor="middle">{h}h</text>}
          </g>; })}
      </svg>
    </div>
  );
};

const TopStrip = ({ s }) => {
  const w = s.weather || {}, n = s.net || {};
  return (
    <div className="mh-sec" style={{ left: 40, right: 40, top: 22, height: 56 }}>
      <div style={{ position: "absolute", right: 0, top: 0, display: "flex", gap: 36, alignItems: "flex-end" }}>
        {w.temp != null && <div style={{ textAlign: "right" }}>
          <div className="mh-lbl">{w.city || "Current location"}{w.source === "ip" ? " · approx." : ""}</div>
          <div className="mh-val mh-glow" style={{ fontSize: 22 }}>{w.temp}° <span style={{ fontSize: 13, color: "#a9d4f5" }}>{w.desc} · {w.max}° / {w.min}°</span></div>
        </div>}
        {(w.alerts || []).map((a, i) => (
          <div key={i} className={`mh-alert ${a.level}`}>
            <b>⚠ {a.level.toUpperCase()} · {a.event.toUpperCase()}</b>
            <span>{alertSpan(a)}</span>
          </div>))}
        {(w.rain || []).length > 0 && <Rain rain={w.rain} />}
        <div style={{ textAlign: "right" }}><div className="mh-lbl">Wi-Fi</div><div className="mh-val" style={{ fontSize: 15 }}>{n.ssid || (n.online ? "CONNECTED" : "OFFLINE")}</div></div>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 54, height: 1, background: "rgba(90,180,255,.28)" }} />
    </div>
  );
};

// -------------------------------------------------------------------- core
const LOGO = "M32.00 38.80 L40.80 30.00 L43.00 30.00 L43.00 92.00 L32.00 92.00 Z M118.00 38.80 L109.20 30.00 L107.00 30.00 L107.00 74.00 L118.00 74.00 Z M46.00 32.81 L75.00 60.00 L104.00 32.81 L104.00 47.89 L75.00 75.08 L46.00 47.89 Z M34.53 44.85 a2.97 2.97 0 1 0 5.94 0 a2.97 2.97 0 1 0 -5.94 0 Z M72.03 67.54 a2.97 2.97 0 1 0 5.94 0 a2.97 2.97 0 1 0 -5.94 0 Z M109.53 44.85 a2.97 2.97 0 1 0 5.94 0 a2.97 2.97 0 1 0 -5.94 0 Z M101.50 76.00 L123.50 76.00 L123.50 97.52 L119.32 97.52 L119.32 80.95 L105.68 80.95 L105.68 97.52 L101.50 97.52 Z M27.05 94.00 L47.95 94.00 L47.95 97.52 L27.05 97.52 Z";
const TICKS = Array.from({ length: 96 }, (_, i) => i);
// logo joints in core coordinates (logo centred: drawn at x -128, y -94, scale 256/101, viewBox origin 25,27)
const JOINTS = [[37.5, 44.85], [75, 67.54], [112.5, 44.85]].map(([x, y]) => [-128 + (x - 25) * (256 / 101), -94 + (y - 27) * (256 / 101)]);
const Ring = ({ r, cls, children }) => (
  <div className={`mh-ring ${cls}`} style={{ left: 520 - r, top: 470 - r, width: 2 * r, height: 2 * r }}>
    <svg width={2 * r} height={2 * r} viewBox={`${-r} ${-r} ${2 * r} ${2 * r}`}>{children}</svg>
  </div>
);

const Core = ({ s }) => {
  const now = new Date();
  const aNow = angleOf(now);
  const R = 298, CIRC = 2 * Math.PI * R;
  const events = [];
  const p = s.printer || {};
  if (p.state === "RUNNING" && p.online !== false && p.remainingMin != null && Date.now() / 1000 - (p.updated || 0) < 600) {
    const end = new Date(now.getTime() + p.remainingMin * 60e3);
    if (p.remainingMin < 24 * 60) events.push({ a: angleOf(end), label: `PRINT · DONE ${hhmm(end)}`, color: C.c, arcFrom: aNow });
  }
  const c = s.claude || {};
  [[c.fiveHour, "CLAUDE · 5H RESET"], [c.week, "CLAUDE · WEEK RESET"]].forEach(([l, name]) => {
    if (l && l.resetsAt) {
      const d = new Date(l.resetsAt);
      if (d > now && d - now < 24 * 3600e3) events.push({ a: angleOf(d), label: `${name} ${hhmm(d)}`, color: C.hot });
    }
  });
  // callout layout: upper-half events go to a band above the dial, lower-half below
  const placed = [];
  ["top", "bottom"].forEach((band) => {
    const evs = events.filter((e) => (Math.cos((e.a * Math.PI) / 180) >= 0) === (band === "top")).sort((x, y) => Math.sin((x.a * Math.PI) / 180) - Math.sin((y.a * Math.PI) / 180));
    evs.forEach((e, i) => {
      const [ax, ay] = polar(e.a, 311);
      const w = e.label.length * 8.6 + 24;
      const side = ax >= 0 ? 1 : -1;
      const by = band === "top" ? -452 + i * 38 : 418 - i * 38;
      const edge = side > 0 ? Math.min(Math.max(ax + 120, 160), 520 - w) : Math.max(Math.min(ax - 120, -160), -520 + w);
      placed.push({ ...e, ax, ay, bx: side > 0 ? edge : edge - w, by, w, ex: edge });
    });
  });
  return (
    <div className="mh-core">
    <svg width="1040" height="940" viewBox="-520 -470 1040 940">
      <defs>
        <radialGradient id="mhHalo"><stop offset="0" stopColor={C.blue} stopOpacity=".22" /><stop offset=".6" stopColor={C.blue} stopOpacity=".06" /><stop offset="1" stopColor={C.blue} stopOpacity="0" /></radialGradient>
      </defs>
      <circle r="400" fill="url(#mhHalo)" />
      <circle r="318" fill="none" stroke={C.blue} strokeWidth="1" opacity=".6" />
      <circle r={R} fill="none" stroke="rgba(60,120,200,.16)" strokeWidth="22" />
      <circle r={R} fill="none" stroke="rgba(90,180,255,.22)" strokeWidth="22" strokeDasharray={`${(aNow / 360) * CIRC} ${CIRC}`} transform="rotate(-90)" />
      <g stroke={C.blue} strokeWidth="1">{TICKS.map((i) => <line key={i} y1="-309" y2={i % 4 ? -303 : -287} transform={`rotate(${i * 3.75})`} stroke={i % 4 ? undefined : C.c} />)}</g>
      <g fontFamily="Share Tech Mono" fontSize="13" fill={C.sky} textAnchor="middle" letterSpacing="1"><text y="-328">00</text><text x="336" y="5">06</text><text y="340">12</text><text x="-336" y="5">18</text></g>
      {events.filter((e) => e.arcFrom != null).map((e, i) => <path key={i} d={arc(e.arcFrom, e.a, R)} fill="none" stroke={e.color} strokeWidth="8" />)}
      {events.map((e, i) => <line key={i} y1="-326" y2="-270" stroke={e.color} strokeWidth="2" transform={`rotate(${e.a})`} />)}
      <g transform={`rotate(${aNow})`}><line y1="-330" y2="-262" stroke={C.hot} strokeWidth="3" /><circle cy="-330" r="4" fill={C.hot} /></g>
      <circle r="214" fill="rgba(4,18,42,.55)" stroke="rgba(90,180,255,.3)" />
      <circle r="200" fill="none" stroke={C.blue} strokeWidth="1" strokeDasharray="2 4" opacity=".6" />
      <svg x="-128" y="-94" width="256" height="188" viewBox="25 27 101 74">
        <path fillRule="evenodd" d={LOGO} fill="rgba(111,227,255,.14)" stroke={C.c} strokeWidth=".8" />
      </svg>
      <g fontFamily="Share Tech Mono" fontSize="12" letterSpacing="1.5">
        {placed.map((e, i) => {
          const { ax, ay } = e, ey = e.by + 14;
          return <g key={i}>
            <polyline points={`${ax},${ay} ${e.ex - Math.sign(e.ex) * 50},${ey} ${e.ex},${ey}`} fill="none" stroke={e.color} strokeWidth="1" />
            <circle cx={ax} cy={ay} r="3" fill={e.color} />
            <rect x={e.bx} y={e.by} width={e.w} height="28" fill={C.box} fillOpacity=".95" stroke={e.color} strokeOpacity=".7" />
            <text x={e.bx + 12} y={e.by + 19} fill={e.color}>{e.label}</text>
          </g>;
        })}
      </g>
    </svg>
    {/* Rotating rings and pulsing joints live in their own HTML layers: WebKit composites
        transforms/opacity of HTML elements on the GPU, but repaints the whole SVG on the CPU
        every frame when an element *inside* an SVG is animated. */}
    <Ring r={400} cls="r2">
      <circle r="396" fill="none" stroke={C.sky} strokeWidth="2.4" strokeLinecap="round" strokeDasharray="0 9" opacity=".55" />
      <path d="M-280,-280 A396,396 0 0 1 -60,-391" fill="none" stroke={C.c} strokeWidth="1.5" />
    </Ring>
    <Ring r={370} cls="r1">
      <circle r="368" fill="none" stroke={C.blue} strokeWidth="1" opacity=".7" />
      <path d="M0,-368 A368,368 0 0 1 260,-260" fill="none" stroke={C.c} strokeWidth="3" />
      <path d="M0,368 A368,368 0 0 1 -260,260" fill="none" stroke={C.c} strokeWidth="3" />
      <circle r="356" fill="none" stroke={C.sky} strokeWidth="6" strokeDasharray="1 5" opacity=".35" />
    </Ring>
    <Ring r={248} cls="r3"><circle r="246" fill="none" stroke={C.c} strokeWidth="2.6" strokeLinecap="round" strokeDasharray="0 7" opacity=".6" /></Ring>
    <Ring r={232} cls="r4"><circle r="230" fill="none" stroke={C.sky} strokeWidth="1" strokeDasharray="70 14 4 14" /></Ring>
    {JOINTS.map(([x, y], i) => <i key={i} className="mh-joint" style={{ left: 520 + x - 4, top: 470 + y - 4 }} />)}
    </div>
  );
};

// -------------------------------------------------------------------- root
export const render = ({ s }) => (
  <div className="mh-root">
    <style>{CSS}</style>
    <div className="mh-tex" />
    {!s ? <div className="mh-sec mh-lbl" style={{ left: 40, top: 40 }}>Waiting for the Desktop HUD service…</div> : <>
      <TopStrip s={s} />
      <System s={s} />
      <Claude s={s} />
      <Core s={s} />
      <Printer s={s} />
      <GitHub s={s} />
      {s.t && Date.now() / 1000 - s.t > 30 && <div className="mh-sec mh-dim" style={{ left: 40, bottom: 20, color: C.warn }}>DATA FROZEN SINCE {hhmm(new Date(s.t * 1000))} · HUD SERVICE NOT RESPONDING</div>}
    </>}
  </div>
);

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500&family=Share+Tech+Mono&display=swap');
.mh-root{position:absolute;inset:0;overflow:hidden;color:#a9d4f5;font-family:Rajdhani,'Helvetica Neue',sans-serif;
  background:radial-gradient(ellipse 80% 70% at 55% 50%,#0a2550 0,#06183a 45%,#030c1d 100%)}
.mh-tex{position:absolute;inset:0;background:repeating-linear-gradient(90deg,rgba(120,190,255,.035) 0 1px,transparent 1px 3px),radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(0,4,12,.55) 100%)}
.mh-sec{position:absolute}
.mh-glow{text-shadow:0 0 8px rgba(111,227,255,.45)}
.mh-lbl{font-family:'Share Tech Mono',Menlo,monospace;font-size:11px;letter-spacing:.16em;color:#4f7fae;text-transform:uppercase}
.mh-val{font-family:'Share Tech Mono',Menlo,monospace;color:#dff6ff}
.mh-big{font-family:'Share Tech Mono',Menlo,monospace;color:#6fe3ff;letter-spacing:.06em;line-height:1;text-shadow:0 0 10px rgba(111,227,255,.45)}
.mh-row{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.mh-ell{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.mh-tag{display:inline-block;background:rgba(38,104,176,.38);padding:6px 18px 5px 14px;font-weight:400;font-size:24px;letter-spacing:.24em;color:#dff6ff;text-shadow:0 0 8px rgba(111,227,255,.4)}
.mh-tag small{display:block;font-family:'Share Tech Mono',Menlo,monospace;font-size:9px;letter-spacing:.18em;color:#5ab4ff;opacity:.8;margin-top:-1px}
.mh-hd{display:flex;align-items:flex-end;gap:14px;margin-bottom:14px}
.mh-rule{flex:1;height:1px;background:linear-gradient(90deg,rgba(90,180,255,.28),transparent);margin-bottom:8px}
.mh-meta{font-family:'Share Tech Mono',Menlo,monospace;font-size:10px;letter-spacing:.14em;margin-bottom:5px}
.mh-sq{width:12px;height:12px;background:#6fe3ff;box-shadow:0 0 8px #6fe3ff;margin-bottom:8px}
.mh-sq.warn{background:#ff9b3d;box-shadow:0 0 8px #ff9b3d}.mh-sq.crit{background:#ff5a3c;box-shadow:0 0 10px #ff5a3c}
.mh-bar{height:5px;background:rgba(60,120,200,.18);position:relative;margin-top:5px}
.mh-bar.thick{height:10px}
.mh-bar i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#2f7fd6,#6fe3ff);box-shadow:0 0 8px rgba(111,227,255,.5)}
.mh-bar u{position:absolute;top:-3px;bottom:-3px;width:1px;background:#5ab4ff;opacity:.45}
.mh-bar.warn i{background:linear-gradient(90deg,#9a4f12,#ff9b3d);box-shadow:0 0 8px rgba(255,155,61,.55)}
.mh-bar.crit i{background:linear-gradient(90deg,#8f2414,#ff5a3c);box-shadow:0 0 8px rgba(255,90,60,.6)}
.warn .mh-val,.warn .mh-big,.warn .mh-st{color:#ff9b3d}.crit .mh-val,.crit .mh-big,.crit .mh-st{color:#ff5a3c}
.warn .mh-big{text-shadow:0 0 10px rgba(255,155,61,.45)}.crit .mh-big{text-shadow:0 0 10px rgba(255,90,60,.5)}
.mh-st{font-family:'Share Tech Mono',Menlo,monospace;font-size:10px;letter-spacing:.14em;margin-left:10px}
.mh-blocks{display:flex;gap:3px;margin-top:5px}.mh-blocks b{flex:1;height:7px;background:rgba(60,120,200,.18)}
.mh-blocks b.on{background:#5ab4ff;box-shadow:0 0 5px #5ab4ff}.mh-blocks.warn b.on{background:#ff9b3d;box-shadow:0 0 5px #ff9b3d}.mh-blocks.crit b.on{background:#ff5a3c;box-shadow:0 0 5px #ff5a3c}
.mh-dim{font-family:'Share Tech Mono',Menlo,monospace;font-size:10px;line-height:1.5;color:#4f7fae;opacity:.8;letter-spacing:.06em}
.mh-list{font-family:'Share Tech Mono',Menlo,monospace;font-size:13px;line-height:1.85;color:#a9d4f5}
.mh-list b{color:#6fe3ff;font-weight:400}
.mh-pill{flex:none;font-family:'Share Tech Mono',Menlo,monospace;font-size:10px;letter-spacing:.14em;padding:1px 7px;background:rgba(38,104,176,.3);color:#5ab4ff}
.mh-pill.hot{background:rgba(223,246,255,.16);color:#dff6ff}.mh-pill.dimp{opacity:.6}
.mh-ind{display:inline-block;width:8px;height:8px;margin-right:9px}
.mh-ind.busy{background:#6fe3ff;box-shadow:0 0 8px #6fe3ff;will-change:opacity;animation:mh-pulse 1.6s ease-in-out infinite}
.mh-ind.wait{background:#dff6ff;box-shadow:0 0 6px #dff6ff}.mh-ind.idle{border:1px solid #4f7fae}
.mh-table{border-collapse:collapse;width:100%;font-family:'Share Tech Mono',Menlo,monospace;font-size:13px;table-layout:fixed}
.mh-table td{padding:3px 0;color:#a9d4f5}.mh-table td.n{text-align:right;color:#dff6ff;width:60px}
.mh-table th{font-weight:400;text-align:right;font-size:10px;letter-spacing:.14em;color:#4f7fae;padding-bottom:5px}.mh-table th:first-child{text-align:left;width:250px}
.mh-ams{flex:1;padding:6px 6px 5px;background:rgba(38,104,176,.16);border-top:2px solid #5ab4ff}
.mh-ams.active{border-top-color:#6fe3ff;background:rgba(38,104,176,.3)}.mh-ams.warn{border-top-color:#ff9b3d}.mh-ams.crit{border-top-color:#ff5a3c}.mh-ams.empty{border-top-color:#4f7fae;opacity:.6}
.mh-ams i{display:block;height:14px}.mh-ams span{display:block;font-family:'Share Tech Mono',Menlo,monospace;font-size:11px;margin-top:5px}
.mh-ams.warn span{color:#ff9b3d}.mh-ams.crit span{color:#ff5a3c}
.mh-alert{display:flex;flex-direction:column;align-items:flex-end;padding:3px 10px;font-family:'Share Tech Mono',Menlo,monospace;font-size:10px;letter-spacing:.14em;border:1px solid}
.mh-alert b{font-weight:400;font-size:12px}
.mh-alert.yellow{color:#ffd84d;border-color:rgba(255,216,77,.7);background:rgba(255,216,77,.10);box-shadow:0 0 8px rgba(255,216,77,.25)}
.mh-alert.orange{color:#ff9b3d;border-color:rgba(255,155,61,.8);background:rgba(255,155,61,.12);box-shadow:0 0 8px rgba(255,155,61,.3)}
.mh-alert.red{color:#ff5a3c;border-color:rgba(255,90,60,.9);background:rgba(255,90,60,.15);box-shadow:0 0 10px rgba(255,90,60,.4)}
.mh-core{position:absolute;left:50%;top:50%;width:1040px;height:940px;margin:-480px 0 0 -520px}
.mh-core>svg{position:absolute;left:0;top:0}
.mh-ring{position:absolute;will-change:transform}.mh-ring svg{display:block}
.mh-joint{position:absolute;width:8px;height:8px;border-radius:50%;background:#dff6ff;will-change:opacity;animation:mh-fade 3s ease-in-out infinite}
.r1{animation:mh-spin 120s linear infinite}.r2{animation:mh-spinr 180s linear infinite}.r3{animation:mh-spin 60s linear infinite}.r4{animation:mh-spinr 90s linear infinite}
@keyframes mh-pulse{50%{opacity:.25}}@keyframes mh-fade{50%{opacity:.3}}
@keyframes mh-spin{to{transform:rotate(360deg)}}@keyframes mh-spinr{to{transform:rotate(-360deg)}}
`;
