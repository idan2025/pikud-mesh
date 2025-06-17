#!/usr/bin/env python3
"""
Mesh-Alerts LIVE bridge  •  phase tracking  •  per-ID aircraft updates
Adds full web-app wording (איזור | סוג ההתרעה | חותמת זמן) to every packet.
"""

import json, time, requests, re, argparse, sys, os
from datetime import datetime, timezone, timedelta
from enum import Enum
import meshtastic.serial_interface

# ───── Config (env-override ready) ───────────────────────────────────────
LIVE_URL          = os.getenv("LIVE_URL",
                     "https://alarms.cloudt.info/api/alerts/live")
HEADERS           = { "User-Agent": "MeshAlerts/1.0 (+github)" }

MESHTASTIC_DEVICE = os.getenv("MESHTASTIC_DEVICE") or None
CHANNEL_NAME      = os.getenv("CHANNEL_NAME", "Alerts")
POLL_INTERVAL_S   = 1.0
MAX_CHUNK_LEN     = 180
# ─────────────────────────────────────────────────────────────────────────

IDLE_PATTERNS = {r"\r\n", "\"\\r\\n\"", "OK", ""}
_HTML_RE      = re.compile(r"<!doctype html>|<html", re.I)

# ─── Phase machine -------------------------------------------------------
class Phase(Enum):
    NONE = 0
    PRE  = 14   # stay near shelter
    ROCKET = 1  # rocket red-alert
    AIRCRAFT = 6  # hostile aircraft (cats 2 or 6)
    CLEAR = 13  # all-clear

PHASE_EMOJI = {
    Phase.PRE:     "🟡",
    Phase.ROCKET:  "🚨",
    Phase.AIRCRAFT:"✈️",
    Phase.CLEAR:   "✅",
}

current_phase: Phase = Phase.NONE
aircraft_id_last: str | None = None
# ─────────────────────────────────────────────────────────────────────────

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)
def now_il() -> str:
    return datetime.now(timezone(timedelta(hours=3))).strftime("%d/%m/%Y %H:%M:%S")

# ─── Serial helpers ──────────────────────────────────────────────────────
def channel_index_for(iface, long_name: str) -> int:
    iface.waitForConfig()
    for idx, ch in enumerate(iface.localNode.channels):
        if ch and getattr(ch.settings, "name", None) == long_name:
            return idx
    raise RuntimeError(f"Channel “{long_name}” not found")

def split_chunks(msg: str, limit=MAX_CHUNK_LEN):
    buf = ""
    for word in msg.split():
        if len((buf + " " + word).encode()) > limit:
            yield buf
            buf = word
        else:
            buf = f"{buf} {word}".strip()
    if buf: yield buf

def send_text(iface, ch_idx, message):
    log(f"TX → {message}")
    for part in split_chunks(message):
        iface.sendText(part, channelIndex=ch_idx)
        time.sleep(0.3)

# ─── Feed parsing helpers ────────────────────────────────────────────────
def fetch_body():
    r = requests.get(LIVE_URL, headers=HEADERS, timeout=4)
    r.raise_for_status()
    return r.text.strip()

def parse_alerts(raw):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, str):
        return []
    return data if isinstance(data, list) else [data]

def flattened_locs(alerts, cats):
    out = []
    for a in alerts:
        if int(a.get("cat", a.get("category", 0))) in cats:
            d = a.get("data", [])
            if isinstance(d, list):
                out.extend(d)
            elif isinstance(d, str):
                out.append(d)
    return ", ".join(out) or "כללי"

def format_packet(phase: Phase, title: str, locs: str) -> str:
    return (f"{PHASE_EMOJI[phase]} איזור: {locs} | "
            f"סוג ההתרעה: {title} | "
            f"חותמת זמן: {now_il()}")

def make_test(area_str: str) -> str:
    return (f"איזור: {area_str} | סוג ההתרעה: בדיקה ידנית | "
            f"חותמת זמן: {now_il()}")
# ─────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--test",      metavar="AREAS")
    p.add_argument("--test-only", metavar="AREAS")
    args = p.parse_args()

    log("Connecting to Meshtastic …")
    iface  = meshtastic.serial_interface.SerialInterface(devPath=MESHTASTIC_DEVICE)
    ch_idx = channel_index_for(iface, CHANNEL_NAME)
    log(f"🟢 Ready – channel “{CHANNEL_NAME}” (slot {ch_idx})")

    if args.test or args.test_only:
        send_text(iface, ch_idx, make_test(args.test or args.test_only))
        if args.test_only:
            sys.exit(0)

    global current_phase, aircraft_id_last
    while True:
        try:
            raw = fetch_body()
            if raw in IDLE_PATTERNS or _HTML_RE.match(raw):
                time.sleep(POLL_INTERVAL_S); continue

            alerts = parse_alerts(raw)
            if not alerts:
                time.sleep(POLL_INTERVAL_S); continue

            first = alerts[0]
            cat_val = int(first.get("cat", first.get("category", 0)))
            new_phase = (Phase(cat_val)
                         if cat_val in (1,2,6,13,14)
                         else current_phase)

            # ── phase changed ─────────────────────────────────
            if new_phase != current_phase:
                aircraft_id_last = None     # reset ID memory
                locs  = flattened_locs(alerts, cats=(cat_val,))
                title = first.get("title", PHASE_EMOJI[new_phase])
                send_text(iface, ch_idx, format_packet(new_phase, title, locs))
                current_phase = new_phase
                if new_phase == Phase.AIRCRAFT:
                    aircraft_id_last = first.get("id")

            # ── still AIRCRAFT: new ID? ───────────────────────
            elif current_phase == Phase.AIRCRAFT:
                cur_id = first.get("id")
                if cur_id and cur_id != aircraft_id_last:
                    locs  = flattened_locs(alerts, cats=(2,6))
                    title = first.get("title", "חדירת כלי טיס עוין")
                    send_text(iface, ch_idx, format_packet(Phase.AIRCRAFT, title, locs))
                    aircraft_id_last = cur_id

        except Exception as e:
            log(f"⚠️  {e}")
        time.sleep(POLL_INTERVAL_S)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopping…")
