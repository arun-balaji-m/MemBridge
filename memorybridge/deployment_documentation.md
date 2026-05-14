# MemoryBridge — Deployment Guide (Railway)

This guide deploys **Phase 1** (Flask embedder) and **Phase 2** (FastAPI retrieval API)
together in a single Railway service using Docker + supervisord.

Railway exposes **one public port (8000)**. Phase 2 proxies `/embed` and `/store` calls
internally to Phase 1 on port 8765, so the Chrome extension only needs one URL.

```
Chrome Extension
      │
      └──► https://your-app.railway.app
                ├── /embed  → proxied to localhost:8765 (Phase 1)
                ├── /store  → proxied to localhost:8765 (Phase 1)
                ├── /index  → Phase 2 retrieval API
                ├── /query  → Phase 2 retrieval API
                ├── /status → Phase 2 retrieval API
                ├── /prompt → Phase 2 retrieval API
                └── /health → health check
```

---

## Prerequisites

| Tool | Install |
|---|---|
| Docker | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| Railway CLI | `curl -fsSL https://railway.app/install.sh \| sh` |
| Railway account | [railway.app](https://railway.app) — sign up with GitHub |

---

## Step 1 — Install Railway CLI and Login

```bash
curl -fsSL https://railway.app/install.sh | sh
railway login
```

This opens a browser window. Log in with your GitHub account.

---

## Step 2 — Initialise Railway Project

```bash
cd /home/arunb/VSCode\ Projects/MemBridge/memorybridge/backend

railway init
```

- Select: **Create new project**
- Enter project name: `memorybridge`

---

## Step 3 — Set Environment Variables

```bash
railway variables set SECRET_KEY=<generate a random 32-char string>
railway variables set API_BASE_URL=https://your-app.railway.app
railway variables set GOOGLE_CLIENT_ID=<from Google Cloud Console>
railway variables set GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
railway variables set CACHE_TTL_SECONDS=3600
```

> You can also set these in the Railway dashboard:
> **Project → Variables tab → Add variable**

Generate a random SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 4 — Deploy

```bash
railway up
```

Railway detects the `Dockerfile` and `railway.toml` automatically.
First deploy takes **5–10 minutes** (model baking into image layer).
Subsequent deploys are faster (~2–3 min).

Watch live logs:
```bash
railway logs
```

---

## Step 5 — Get Your Public URL

```bash
railway domain
```

Output:
```
https://memorybridge-production.up.railway.app
```

Or assign a custom domain:
```bash
railway domain --set memorybridge.yourdomain.com
```

---

## Step 6 — Update API_BASE_URL Variable

```bash
railway variables set API_BASE_URL=https://memorybridge-production.up.railway.app
```

Then redeploy to pick up the change:
```bash
railway up
```

---

## Step 7 — Update Chrome Extension URLs

Open both files and replace `your-app.railway.app` with your actual Railway domain:

**`extension/background/background.js`**
```javascript
const BACKEND = 'https://memorybridge-production.up.railway.app';
```

**`extension/popup/popup.js`**
```javascript
const API_BASE = 'https://memorybridge-production.up.railway.app';
```

Then reload the extension in Chrome:
1. Go to `chrome://extensions`
2. Click the **reload icon** on MemoryBridge

---

## Step 8 — Verify Deployment

```bash
# Health check (both phases must be running)
curl https://memorybridge-production.up.railway.app/health

# Expected response:
# {"status":"ok","model_loaded":true,"uptime_seconds":42.1}
```

```bash
# Test Phase 1 proxy (embedding)
curl -X POST https://memorybridge-production.up.railway.app/embed \
  -H "Content-Type: application/json" \
  -d '{"chunks":[{"id":"c1","title":"test","summary":"test","detail":"test"}]}'

# Expected: {"vectors":[[...384 floats...]]}
```

```bash
# Test Phase 2 (retrieval) — needs a real session key and Drive token
curl "https://memorybridge-production.up.railway.app/index?key=YOUR_SESSION_KEY" \
  -H "Authorization: Bearer YOUR_DRIVE_TOKEN"
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `API_BASE_URL` | ✅ | Full public URL of the Railway deployment |
| `SECRET_KEY` | ✅ | Random secret string (32+ chars) |
| `GOOGLE_CLIENT_ID` | ✅ | OAuth client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | ✅ | OAuth client secret |
| `CACHE_TTL_SECONDS` | Optional | Session cache TTL (default: 3600) |

---

## Updating After Code Changes

```bash
cd /home/arunb/VSCode\ Projects/MemBridge/memorybridge/backend
railway up
```

Railway rebuilds the Docker image and redeploys automatically.

---

## Viewing Logs

```bash
# All logs (both phases)
railway logs

# Follow live
railway logs --tail
```

Supervisor logs both Phase 1 and Phase 2 to stdout — both appear in `railway logs`.

---

## Scaling / Production Notes

- **Free tier**: 500 hours/month — enough for personal use
- **Hobby plan ($5/month)**: always-on, no sleep, custom domains
- **Memory**: Model uses ~300 MB RAM; keep total under 512 MB (free tier limit)
- **Storage**: `/tmp` is ephemeral — wiped on redeploy. SQLite is re-downloaded from Drive on cold start (this is by design)

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `/health` returns 503 | Model still loading — wait 30 s and retry |
| `/embed` returns 502 | Phase 1 not ready yet — supervisor starts it with a 5s delay |
| Drive token expired (401) | Re-open the Chrome extension to refresh the token |
| `railway up` fails | Check `railway logs` for Docker build errors |
| Extension still hitting localhost | Make sure you updated and reloaded the extension in Step 7 |

---

## Local Development (no Railway)

Run both phases locally in separate terminals:

```bash
# Terminal 1 — Phase 1
cd memorybridge/backend
source venv/bin/activate
python embedder.py
# → http://localhost:8765

# Terminal 2 — Phase 2
cd memorybridge/backend
source venv/bin/activate
PYTHONPATH=. uvicorn api.main:app --reload --port 8000
# → http://localhost:8000
```

For local dev, temporarily revert the extension URLs back to localhost.
