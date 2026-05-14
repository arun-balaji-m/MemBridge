/**
 * popup.js — MemoryBridge Phase 1
 * Drives the popup UI: URL auto-fill, pipeline trigger, progress updates,
 * session key display, and session history.
 */

// ── DOM refs ───────────────────────────────────────────────────────────────
const urlInput      = document.getElementById("chat-url");
const extractBtn    = document.getElementById("extract-btn");
const progressSec   = document.getElementById("progress-section");
const resultSec     = document.getElementById("result-section");
const sessionKeyEl  = document.getElementById("session-key");
const copyBtn       = document.getElementById("copy-btn");
const errorBanner   = document.getElementById("error-banner");
const errorMsg      = document.getElementById("error-message");
const historyList   = document.getElementById("history-list");

// ── Helpers ────────────────────────────────────────────────────────────────

function showError(msg) {
  errorMsg.textContent = msg;
  errorBanner.classList.remove("hidden");
}

function hideError() {
  errorBanner.classList.add("hidden");
  errorMsg.textContent = "";
}

function setStep(step, status, label) {
  const el = document.getElementById(`step-${step}`);
  if (!el) return;
  el.className = `step ${status}`;
  const labelEl = el.querySelector(".step-label");
  if (label && labelEl) labelEl.textContent = label;
}

function resetSteps() {
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById(`step-${i}`);
    if (el) el.className = "step";
    const icon = el?.querySelector(".step-icon");
    if (icon) icon.textContent = "";
  }
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric", year: "numeric",
    });
  } catch { return iso; }
}

// ── Session history ─────────────────────────────────────────────────────────

async function loadHistory() {
  const res = await chrome.runtime.sendMessage({ action: "getSessions" });
  const sessions = res?.sessions ?? {};
  const entries = Object.values(sessions).sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  );

  historyList.innerHTML = "";
  if (entries.length === 0) {
    historyList.innerHTML = '<li class="history-empty">No sessions yet.</li>';
    return;
  }

  for (const s of entries) {
    const li = document.createElement("li");
    li.className = "history-item";
    li.innerHTML = `
      <span class="h-key">${s.key}</span>
      <span class="h-project" title="${s.source_url}">${s.project}</span>
      <span class="h-date">${formatDate(s.created_at)}</span>
    `;
    historyList.appendChild(li);
  }
}

// ── Auto-fill URL from active tab ──────────────────────────────────────────

async function prefillUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return;
  const host = new URL(tab.url).hostname;
  if (host.includes("claude.ai") || host.includes("chat.openai.com") || host.includes("chatgpt.com")) {
    urlInput.value = tab.url;
  }
}

// ── Progress listener (from background.js) ─────────────────────────────────

const STEP_LABELS = {
  1: ["Scraping chat…",              "Chat scraped ✓",          "Scraping failed"],
  2: ["Classifying chunks…",         "Chunks classified ✓",     "Classification failed"],
  3: ["Generating embeddings…",      "Embeddings ready ✓",      "Embedding failed"],
  4: ["Creating memory package…",    "Package created ✓",       "Packaging failed"],
  5: ["Uploading to Google Drive…",  "Uploaded to Drive ✓",     "Upload failed"],
  6: ["Finalising session key…",     "Done!",                   "Session error"],
};

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type !== "progress") return;
  const { step, status, message } = msg;

  const [runLabel, doneLabel, errLabel] = STEP_LABELS[step] ?? ["…", "✓", "Error"];

  if (status === "running") {
    setStep(step, "running", runLabel);
  } else if (status === "done") {
    if (step < 6) {
      setStep(step, "done", doneLabel);
    } else {
      // Final step: message IS the session key
      setStep(6, "done", "Done!");
      sessionKeyEl.textContent = message;
      resultSec.classList.remove("hidden");
      extractBtn.disabled = false;
      loadHistory();
    }
  } else if (status === "error") {
    setStep(step, "error", errLabel);
    showError(message);
    extractBtn.disabled = false;
  }
});

// ── Extract button ─────────────────────────────────────────────────────────

extractBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    showError("Please enter a chat URL.");
    return;
  }

  try {
    new URL(url);
  } catch {
    showError("Invalid URL.");
    return;
  }

  const host = new URL(url).hostname;
  if (!host.includes("claude.ai") && !host.includes("chat.openai.com") && !host.includes("chatgpt.com")) {
    showError("Only Claude.ai and ChatGPT URLs are supported.");
    return;
  }

  hideError();
  resetSteps();
  progressSec.classList.remove("hidden");
  resultSec.classList.add("hidden");
  extractBtn.disabled = true;

  const res = await chrome.runtime.sendMessage({ action: "extract", url });
  if (!res?.ok) {
    showError(res?.error ?? "Failed to start extraction.");
    extractBtn.disabled = false;
  }
});
// ── Get LLM Prompt button ───────────────────────────────────────────────────

const promptBtn      = document.getElementById('prompt-btn');
const promptSection  = document.getElementById('prompt-section');
const promptText     = document.getElementById('prompt-text');
const copyPromptBtn  = document.getElementById('copy-prompt-btn');

const API_BASE = 'https://membridge-production.up.railway.app'; // ← update after Railway deploy

promptBtn.addEventListener('click', async () => {
  const key = sessionKeyEl.textContent;
  if (!key || key === '—') return;

  promptBtn.disabled = true;
  promptBtn.textContent = 'Fetching…';

  try {
    // Get a fresh Drive token from Chrome identity
    const token = await new Promise((resolve, reject) => {
      chrome.identity.getAuthToken({ interactive: false }, (t) => {
        if (chrome.runtime.lastError || !t) reject(new Error('Token unavailable'));
        else resolve(t);
      });
    });

    const res = await fetch(`${API_BASE}/prompt?key=${key}`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail?.message ?? `API error ${res.status}`);
    }

    const data = await res.json();
    promptText.value = data.prompt;
    promptSection.classList.remove('hidden');
    promptBtn.textContent = 'Refresh Prompt';
  } catch (err) {
    showError('Could not fetch LLM prompt: ' + err.message);
    promptBtn.textContent = 'Get LLM Prompt';
  } finally {
    promptBtn.disabled = false;
  }
});

copyPromptBtn.addEventListener('click', async () => {
  if (!promptText.value) return;
  await navigator.clipboard.writeText(promptText.value);
  copyPromptBtn.textContent = '✓ Copied!';
  setTimeout(() => { copyPromptBtn.textContent = '⎘ Copy'; }, 1800);
});
// ── Copy button ────────────────────────────────────────────────────────────

copyBtn.addEventListener("click", async () => {
  const key = sessionKeyEl.textContent;
  if (!key || key === "—") return;
  await navigator.clipboard.writeText(key);
  copyBtn.textContent = "✓ Copied!";
  setTimeout(() => { copyBtn.textContent = "⎘ Copy"; }, 1800);
});

// ── Initialise ─────────────────────────────────────────────────────────────

(async () => {
  await prefillUrl();
  await loadHistory();
})();
