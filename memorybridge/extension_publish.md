# MemoryBridge — Chrome Extension Publishing Guide

Step-by-step instructions to publish the MemoryBridge extension to the
Chrome Web Store so any user can install it.

---

## Prerequisites

| Requirement | Details |
|---|---|
| Google account | Must be the same account used for the developer dashboard |
| One-time developer fee | **$5 USD** — paid once, covers all future extensions |
| Railway deployment live | Public URL must be set in extension before publishing |
| Icons ready | 16×16, 48×48, 128×128 PNG files in `extension/icons/` |

---

## Step 1 — Set the Final Railway URL in the Extension

Before packaging, make sure both files point to your live Railway URL (not localhost):

**`extension/background/background.js`**
```javascript
const BACKEND = 'https://memorybridge-production.up.railway.app';
```

**`extension/popup/popup.js`**
```javascript
const API_BASE = 'https://memorybridge-production.up.railway.app';
```

---

## Step 2 — Get Your Extension ID (for OAuth)

Before packaging, load the extension unpacked to get the final Extension ID:

1. Go to `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** → select `memorybridge/extension/`
4. Copy the **Extension ID** shown (e.g. `abcdefghijklmnopqrstuvwxyzabcdef`)

You need this ID for Step 4 (OAuth setup).

---

## Step 3 — Lock the Extension ID with a Key

Without a fixed key, Chrome assigns a new ID every time you reload unpacked —
which breaks OAuth. Generate a stable key:

```bash
# Generate a private key
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out key.pem

# Extract the public key in the format Chrome expects
openssl rsa -in key.pem -pubout -outform DER \
  | openssl base64 -A
```

Copy the base64 output and add it to `extension/manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "MemoryBridge",
  "key": "PASTE_YOUR_BASE64_KEY_HERE",
  ...
}
```

Reload the extension — the ID will now stay fixed permanently.

> Keep `key.pem` safe — you'll need it if you ever re-generate the key.

---

## Step 4 — Update OAuth Client in Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/) →
   **APIs & Services** → **Credentials**
2. Click your existing OAuth 2.0 Client ID
3. Under **Item ID**, paste your fixed Extension ID from Step 2
4. Click **Save**

---

## Step 5 — Prepare Store Assets

You need these before submitting:

| Asset | Size | Notes |
|---|---|---|
| Icon | 128×128 PNG | Must have no transparent background for store listing |
| Screenshots | 1280×800 or 640×400 PNG | Minimum 1, maximum 5 |
| Small promo tile | 440×280 PNG | Optional but recommended |
| Description | Up to 132 chars | Short description shown in search |
| Detailed description | Up to 16,000 chars | Markdown not supported |

**Screenshot ideas:**
- Popup showing "Extract Memory" button on a ChatGPT page
- The 6-step progress bar completing
- Session key result screen
- Pasting the LLM prompt into Claude

---

## Step 6 — Package the Extension

```bash
cd /home/arunb/VSCode\ Projects/MemBridge/memorybridge

# Remove any dev-only files first
rm -f extension/.env extension/key.pem

# Create the ZIP
zip -r memorybridge-extension.zip extension/ \
  --exclude "*.DS_Store" \
  --exclude "*__MACOSX*" \
  --exclude "*.git*"
```

The ZIP must contain `manifest.json` at its root level (i.e. inside the
`extension/` folder, not a parent folder).

Verify:
```bash
unzip -l memorybridge-extension.zip | head -20
# Should show: extension/manifest.json at top level
```

If `manifest.json` isn't at root, re-zip from inside the extension folder:
```bash
cd extension/
zip -r ../memorybridge-extension.zip . \
  --exclude "*.DS_Store"
cd ..
```

---

## Step 7 — Create Developer Account

1. Go to [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
2. Sign in with your Google account
3. Accept the developer agreement
4. Pay the **$5 one-time registration fee**

---

## Step 8 — Upload the Extension

1. Click **New Item**
2. Click **Upload** → select `memorybridge-extension.zip`
3. Chrome Web Store will validate the ZIP and show a preview

---

## Step 9 — Fill in Store Listing

In the **Store Listing** tab:

**Name**
```
MemoryBridge
```

**Short description** (132 chars max)
```
Extract chat memories from Claude.ai and ChatGPT, store them in Google Drive, and retrieve context in any LLM.
```

**Detailed description**
```
MemoryBridge captures your AI conversations and turns them into searchable memory packages stored securely in your own Google Drive.

How it works:
1. Open any Claude.ai or ChatGPT conversation
2. Click "Extract Memory" in the extension popup
3. MemoryBridge scrapes, classifies, and chunks the conversation
4. Generates semantic embeddings for intelligent retrieval
5. Uploads a memory package to your Google Drive
6. Gives you a session key (e.g. "a3f8c1d2")

Later, in any new LLM chat:
- Click "Get LLM Prompt" with your session key
- Paste the generated prompt into any LLM (Claude, ChatGPT, Gemini)
- The LLM automatically retrieves relevant context and continues where you left off

Your data stays in YOUR Google Drive — MemoryBridge never stores your conversations.

Supported sites:
- claude.ai
- chat.openai.com (ChatGPT)

Requirements:
- Google account (for Drive storage)
- MemoryBridge API running (see github.com/yourname/memorybridge)
```

**Category**: `Productivity`

**Language**: `English`

---

## Step 10 — Privacy & Permissions Tab

In the **Privacy practices** tab, justify each permission:

| Permission | Justification |
|---|---|
| `activeTab` | Read the current chat page to extract conversation messages |
| `scripting` | Inject content scripts to scrape Claude.ai and ChatGPT DOM |
| `storage` | Store session keys and history locally in Chrome |
| `identity` | Google OAuth 2.0 for accessing user's own Google Drive |
| `tabs` | Read the current tab URL to auto-fill the chat URL field |
| Host: `claude.ai` | Required to scrape conversation content |
| Host: `chat.openai.com` | Required to scrape conversation content |
| Host: `railway.app` (your URL) | Required to call the MemoryBridge embedding and retrieval API |

**Single purpose description:**
```
Extract AI chat conversations and store them as searchable memory packages in the user's own Google Drive for later retrieval in any LLM.
```

---

## Step 11 — Submit for Review

1. Click **Submit for Review**
2. Google reviews extensions within **1–7 business days**
3. You'll receive an email when approved or if changes are required

### Common rejection reasons and fixes

| Rejection | Fix |
|---|---|
| Overly broad permissions | Narrow `host_permissions` to specific domains only |
| Missing privacy policy | Host a simple privacy policy page and link it |
| Unclear single purpose | Update the single purpose description to be more specific |
| OAuth scope too broad | Ensure you're using `drive.file` not `drive` |

---

## Step 12 — Privacy Policy (Required)

Google requires a privacy policy URL if the extension uses OAuth or accesses user data.

Host a simple one at GitHub Pages or any static host:

```markdown
# MemoryBridge Privacy Policy

MemoryBridge does not collect, store, or transmit your personal data to any
third-party servers.

- Chat conversations are processed locally in your browser
- Memory packages are stored exclusively in YOUR Google Drive account
- The MemoryBridge API server processes embeddings but does not retain content
- No conversation data is logged or stored server-side

Google Drive access uses the `drive.file` scope — the extension can only
access files it creates, not your entire Drive.

Contact: your@email.com
```

Add the URL to the store listing under **Privacy Policy URL**.

---

## After Approval

- Your extension gets a permanent Chrome Web Store URL to share
- Users install directly from the store — no Developer mode needed
- Updates: increment `version` in `manifest.json`, re-zip, upload in dashboard

### Update workflow
```bash
# 1. Make code changes
# 2. Bump version in manifest.json  e.g. "1.0.0" → "1.0.1"
# 3. Re-package
zip -r memorybridge-extension.zip extension/ --exclude "*.DS_Store"
# 4. Upload in Chrome Web Store Developer Dashboard → your extension → Package tab
# 5. Submit for review (updates review faster, ~1–3 days)
```

---

## Useful Links

| Resource | URL |
|---|---|
| Chrome Web Store Developer Dashboard | https://chrome.google.com/webstore/devconsole |
| Extension publishing guide | https://developer.chrome.com/docs/webstore/publish |
| MV3 permission documentation | https://developer.chrome.com/docs/extensions/mv3/declare_permissions |
| Google OAuth for extensions | https://developer.chrome.com/docs/extensions/reference/identity |
