#!/usr/bin/env python3
"""
Mesh-Alerts + News Bridge
 - Alerts from live Pikud HaOref feed → channel 1
 - Breaking-news headlines from Ynet RSS → channel 2 (with URL)
"""

import json, time, requests, re, argparse, sys, os, threading, feedparser
from datetime import datetime, timezone, timedelta
from enum import Enum
from meshtastic import portnums_pb2 as portnums
import meshtastic.serial_interface

# ───── Config ─────────────────────────────────────────────────────────────
VERSION           = "MeshBridge v1.4 – Alerts + Ynet Breaking News"
LIVE_URL          = os.getenv("LIVE_URL", "https://alarms.cloudt.info/api/alerts/live")
YNET_RSS_URL      = "https://www.ynet.co.il/Integration/StoryRss1854.xml"
HEADERS           = { "User-Agent": "MeshAlerts/1.0 (+github)" }

MESHTASTIC_DEVICE = os.getenv("MESHTASTIC_DEVICE") or None
CHANNEL_ALERTS    = os.getenv("CHANNEL_ALERTS", "Alerts")
CHANNEL_NEWS      = os.getenv("CHANNEL_NEWS",   "News")
POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", 1.0))
NEWS_INTERVAL_S = int(os.getenv("NEWS_INTERVAL_S", 120))
MAX_CHUNK_LEN     = 180
DEFAULT_HOPS      = 7
# ───────────────────────────────────────────────────────────────────────────

IDLE_PATTERNS = {r"\r\n", "\"\\r\\n\"", "OK", ""}
_HTML_RE      = re.compile(r"<!doctype html>|<html", re.I)

# ─── Phase machine ---------------------------------------------------------
class Phase(Enum):
    NONE     = 0
    PRE      = 14
    ROCKET   = 1
    AIRCRAFT = 6
    CLEAR    = 13

PHASE_EMOJI = {
    Phase.PRE:      "🟡",
    Phase.ROCKET:   "🚨",
    Phase.AIRCRAFT: "✈️",
    Phase.CLEAR:    "✅",
}

current_phase: Phase = Phase.NONE
aircraft_id_last: str | None = None
seen_news = set()

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)
def now_il() -> str:
    return datetime.now(timezone(timedelta(hours=3))).strftime("%d/%m/%Y %H:%M:%S")

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
    if buf:
        yield buf

# ─── New send helper – uses sendData() ─────────────────────────────────────
def send_text(iface, ch_idx, message, hop_limit=DEFAULT_HOPS):
    log(f"TX → {message}")
    for part in split_chunks(message):
        iface.sendData(
            data=part.encode("utf-8"),
            wantAck=False,
            portNum=portnums.TEXT_MESSAGE_APP,    # 256 – user text
            channelIndex=ch_idx,
            hopLimit=hop_limit
        )
        time.sleep(0.3)

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
            f"סוג ההתרעה: {title} | חותמת זמן: {now_il()}")

def make_test(area_str: str) -> str:
    return f"איזור: {area_str} | סוג ההתרעה: בדיקה ידנית | חותמת זמן: {now_il()}"

# ─── ALERT THREAD ──────────────────────────────────────────────────────────
def alert_loop(iface, ch_alerts):
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
            cat_val  = int(first.get("cat", first.get("category", 0)))
            new_phase = Phase(cat_val) if cat_val in (1, 2, 6, 13, 14) else current_phase

            if new_phase != current_phase:
                aircraft_id_last = None
                locs  = flattened_locs(alerts, cats=(cat_val,))
                title = first.get("title", PHASE_EMOJI[new_phase])
                send_text(iface, ch_alerts, format_packet(new_phase, title, locs))
                current_phase = new_phase
                if new_phase == Phase.AIRCRAFT:
                    aircraft_id_last = first.get("id")

            elif current_phase == Phase.AIRCRAFT:
                cur_id = first.get("id")
                if cur_id and cur_id != aircraft_id_last:
                    locs  = flattened_locs(alerts, cats=(2, 6))
                    title = first.get("title", "חדירת כלי טיס עוין")
                    send_text(iface, ch_alerts, format_packet(Phase.AIRCRAFT, title, locs))
                    aircraft_id_last = cur_id

        except Exception as e:
            log(f"⚠️ ALERT: {e}")
        time.sleep(POLL_INTERVAL_S)

# ─── NEWS THREAD ───────────────────────────────────────────────────────────
def news_loop(iface, ch_news):
    global seen_news
    while True:
        try:
            feed = feedparser.parse(YNET_RSS_URL)
            for entry in reversed(feed.entries):
                link = entry.get('link', '').strip()
                if not link or link in seen_news:
                    continue
                title = entry.get('title', '').strip()
                msg = f"📰 {title}"

                full_msg = f"{msg} | {link}"
                if len(full_msg.encode("utf-8")) <= MAX_CHUNK_LEN:
                    send_text(iface, ch_news, full_msg)
                else:
                    send_text(iface, ch_news, msg)
                    send_text(iface, ch_news, link)

                seen_news.add(link)
                time.sleep(1)
        except Exception as e:
            log(f"⚠️ NEWS: {e}")
        time.sleep(NEWS_INTERVAL_S)

# ─── MAIN ───────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--test",      metavar="AREAS")
    p.add_argument("--test-only", metavar="AREAS")
    args = p.parse_args()

    print(f"\n🛰️  {VERSION}\n", flush=True)
    log("Connecting to Meshtastic …")
    iface      = meshtastic.serial_interface.SerialInterface(devPath=MESHTASTIC_DEVICE)
    ch_alerts  = channel_index_for(iface, CHANNEL_ALERTS)
    ch_news    = channel_index_for(iface, CHANNEL_NEWS)
    log(f"🟢 Channels ready → Alerts: {ch_alerts}, News: {ch_news}")

    if args.test or args.test_only:
        send_text(iface, ch_alerts, make_test(args.test or args.test_only))
        if args.test_only:
            sys.exit(0)

    threading.Thread(target=alert_loop, args=(iface, ch_alerts), daemon=True).start()
    threading.Thread(target=news_loop,   args=(iface, ch_news),   daemon=True).start()

    while True:
        time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopping…")
