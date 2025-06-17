Thought for a couple of seconds

Below is the full **README.md** contents ready for copy-paste.  
Just select everything (including the opening and closing ```````), save as `README.md`, and commit!

```markdown
# 📡 Pikud-Mesh + Ynet News Bridge

Forward real-time **Home-Front Command (Pikud HaOref) alerts** and **Ynet breaking-news headlines** straight into your Meshtastic mesh:

| Source | Target Channel | Payload |
|--------|----------------|---------|
| Pikud HaOref live JSON feed | `Alerts` (slot 1) | 🚨 Rocket / ✈️ Aircraft / 🟢 Clear events |
| Ynet RSS feed | `News` (slot 2) | 📰 Headline • URL |

> **Hardware:** any Meshtastic-compatible node (e.g. LilyGO T-Beam) plugged into the host running Docker.

---

## ✨ Features

* **Instant** alerts (default 1 s poll) with clear emoji prefix  
* Headlines are **deduplicated** – you’ll never see the same link twice  
* Automatic multi-part sending (180-byte chunks)  
* Works through up to **7 hops** (default – configurable)  
* Minimal footprint: Python 3.12-slim, no local database

---

## 🚀 Quick Start (90 sec)

```bash
# 1. clone & cd
git clone https://github.com/<your-fork>/pikud-mesh-ynet-news.git
cd pikud-mesh-ynet-news

# 2. pull & run the published image
docker compose up -d
```

You should see:

```
🛰️  MeshBridge v1.4 – Alerts + Ynet Breaking News
[08:49:44] Connecting to Meshtastic …
[08:49:46] 🟢 Channels ready → Alerts: 1, News: 2
```

---

## 📦 Using the Pre-built Image

The image lives on Docker Hub:  
[`idan2025/pikud-mesh_ynet_news`](https://hub.docker.com/r/idan2025/pikud-mesh_ynet_news)

`docker-compose.yml` (already in the repo):

```yaml
version: "3.9"

services:
  pikud-mesh:
    image: idan2025/pikud-mesh_ynet_news:latest
    container_name: pikud-mesh

    # --- Serial-port pass-through ----------------------------
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"          # Linux USB-serial
    # For Docker-Desktop on Windows:
    # devices:
    #   - "\\\\.\\pipe\\com3:/dev/ttyUSB0"
    # ---------------------------------------------------------

    privileged: true   # simplest way to give serial permissions
    tty: true          # keeps /dev/ttyUSB0 open reliably

    environment:
      LIVE_URL:           "http://192.168.223.30:3000/api/alerts/live"
      CHANNEL_ALERTS:     "Alerts"
      CHANNEL_NEWS:       "News"
      POLL_INTERVAL_S:    1.0
      NEWS_INTERVAL_S:    120
      MESHTASTIC_DEVICE:  "/dev/ttyUSB0"
      TZ:                 "Asia/Jerusalem"

    restart: unless-stopped

    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"
```

```bash
docker compose up -d             # start
docker compose logs -f pikud-mesh
docker compose down              # stop
```

---

## 🔧 Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LIVE_URL`          | see code | Pikud HaOref JSON endpoint |
| `YNET_RSS_URL`      | hard-coded | RSS feed for breaking news |
| `CHANNEL_ALERTS`    | Alerts | **Long-name** of slot 1 on every node |
| `CHANNEL_NEWS`      | News | **Long-name** of slot 2 on every node |
| `POLL_INTERVAL_S`   | 1 s | Alert polling interval |
| `NEWS_INTERVAL_S`   | 120 s | RSS polling interval |
| `MESHTASTIC_DEVICE` | /dev/ttyUSB0 | Serial device inside container |
| `DEFAULT_HOPS`      | 7 | Hop-limit for outgoing packets |

Override any of these with `-e VAR=value` or in `environment:`.

---

## 🛠️ Build the Image Yourself

```bash
git clone https://github.com/<your-fork>/pikud-mesh-ynet-news.git
cd pikud-mesh-ynet-news
docker build -t pikud-mesh:local .
```

### Dockerfile

```dockerfile
# ---------- Dockerfile ----------
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=UTF-8 \
    TZ=Asia/Jerusalem

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir meshtastic requests feedparser

COPY bridge.py /app/bridge.py
WORKDIR /app

ENTRYPOINT ["python", "bridge.py"]
# ---------------------------------
```

Run your freshly built image:

```bash
docker run --name pikud-mesh \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  --privileged --tty \
  -e LIVE_URL="http://…" \
  pikud-mesh:local
```

> **Tip:** add `--platform linux/arm64` if you compile on x86 but deploy on a Pi.

---

## 🤝 Contributing

1. Fork → create feature branch → open PR  
2. Run `black bridge.py` before pushing  
3. Issues for new sources (Kan 11, Mako, etc.) are welcome!

---

## 📜 License

MIT © 2025 Idan L. – see `LICENSE`.

---

## ⭐️ Show your support

If this bridge keeps your community safer, please give it a ⭐️ on GitHub and share on the Meshtastic forums!
```

```
