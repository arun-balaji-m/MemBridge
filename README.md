# MemoryBridge — Phase 1

Extract chat conversations from Claude.ai and ChatGPT, package them as searchable memory, and upload to Google Drive.

---

## Quick Start

### 1. Python Backend

```bash
cd memorybridge/backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python embedder.py               # starts server on http://localhost:8765
```

**Verify:**
```bash
curl http://localhost:8765/health
# → {"status": "ok", "model": "all-MiniLM-L6-v2"}
```

### 2. Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID of type **Chrome Extension**
3. Set the Extension ID (get it from `chrome://extensions` after loading unpacked)
4. Copy the Client ID into `extension/manifest.json` → `oauth2.client_id`
5. Enable the **Google Drive API** in your project

### 3. Load the Chrome Extension

1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** → select `memorybridge/extension/`
4. Pin the MemoryBridge extension

### 4. Use It

1. Open a Claude.ai or ChatGPT conversation
2. Click the MemoryBridge icon
3. The URL is auto-filled — click **Extract Memory**
4. Watch the 6-step progress bar
5. Copy your session key (e.g. `a3f8c1d2`)

---

## Project Structure

```
memorybridge/
  backend/
    embedder.py        Flask server — /embed and /store endpoints
    vectorstore.py     SQLite + sqlite-vec operations
    packager.py        Zip packaging
    requirements.txt
  extension/
    manifest.json      MV3 config + OAuth2
    content/
      scraper.js       DOM extraction (Claude + ChatGPT)
      classifier.js    Rule-based message classification
      chunker.js       Sliding-window chunker + TF-IDF tags
    background/
      background.js    Pipeline orchestration
      drive.js         Google Drive upload
      session.js       Session key management
    popup/
      popup.html
      popup.css
      popup.js
    icons/             (add icon16.png, icon48.png, icon128.png)
```

---

## Architecture

```
[Claude.ai / ChatGPT tab]
        ↓  chrome.scripting.executeScript
[scraper.js → classifier.js → chunker.js]
        ↓  chrome.runtime.sendMessage
[background.js]
        ↓  POST /embed          ↓  POST /store
[embedder.py (Flask)]    [vectorstore.py + packager.py]
        ↓                       ↓
   384-dim vectors         {key}.zip (memory.db + index.json + metadata.json)
                                ↓
                    [Google Drive API v3]
                                ↓
                         session key → popup UI
```

---

## Notes

- **Python backend must be running** before clicking Extract Memory
- First run downloads the `all-MiniLM-L6-v2` model (~90 MB) — cached in `~/.cache/huggingface/`
- Uses `sqlite-vec` (not sqlite-vss) — actively maintained, zero native dependencies
- OAuth scope is `drive.file` — extension only sees files it creates