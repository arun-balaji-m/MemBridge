/**
 * background.js — MemoryBridge Phase 1
 * MV3 Service Worker — orchestrates the full extraction pipeline.
 *
 * Pipeline steps:
 *   1. Scrape chat DOM via content script
 *   2. Classify messages (rule-based)
 *   3. Chunk messages (sliding window)
 *   4. Generate embeddings (POST /embed → Python backend)
 *   5. Store vectors + create package (POST /store → Python backend)
 *   6. Upload package to Google Drive
 *   7. Generate & save session key
 */

import { getAuthToken, ensureMemoryBridgeFolder, uploadPackage } from "./drive.js";
import { generateSessionKey, saveSession, getAllSessions } from "./session.js";

const BACKEND = "https://membridge-production.up.railway.app"; // ← update after Railway deploy

// ── Progress reporting ─────────────────────────────────────────────────────

function notify(tabId, step, status, message) {
  chrome.runtime.sendMessage({ type: "progress", step, status, message }).catch(() => {
    // Popup may not be open; ignore
  });
}

// ── Step helpers ──────────────────────────────────────────────────────────

async function scrapeTab(tabId) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content/scraper.js"],
    world: "MAIN",
  });
  // After injection, call the scrape function
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => window.__memoryBridgeScrape(),
    world: "MAIN",
  });
  return result;
}

async function classifyMessages(tabId, messages) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content/classifier.js"],
    world: "MAIN",
  });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (msgs) => window.__memoryBridgeClassify.classifyAll(msgs),
    args: [messages],
    world: "MAIN",
  });
  return result;
}

async function chunkMessages(tabId, classifiedMessages) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content/chunker.js"],
    world: "MAIN",
  });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (msgs) => window.__memoryBridgeChunk.chunkMessages(msgs),
    args: [classifiedMessages],
    world: "MAIN",
  });
  return result;
}

async function embedChunks(chunks) {
  let res;
  try {
    res = await fetch(`${BACKEND}/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chunks }),
    });
  } catch {
    throw new Error(
      "Python backend unreachable. Start it with:\n  python backend/embedder.py"
    );
  }
  if (!res.ok) throw new Error(`Embedder error ${res.status}: ${await res.text()}`);
  const { vectors } = await res.json();
  return vectors; // parallel array to chunks
}

async function storeAndPackage(chunks, vectors, projectName, sourceUrl, sessionKey) {
  let res;
  try {
    res = await fetch(`${BACKEND}/store`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chunks,
        vectors,
        project_name: projectName,
        source_url: sourceUrl,
        session_key: sessionKey,
      }),
    });
  } catch {
    throw new Error(
      "Python backend unreachable. Start it with:\n  python backend/embedder.py"
    );
  }
  if (!res.ok) throw new Error(`Store error ${res.status}: ${await res.text()}`);
  // Backend returns the zip as base64
  const { zip_base64 } = await res.json();
  // Decode base64 → Blob
  const binary = atob(zip_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: "application/zip" });
}

// ── Main pipeline ─────────────────────────────────────────────────────────

async function runPipeline(tabId, sourceUrl) {
  // Step 1 — Scrape
  notify(tabId, 1, "running", "Scraping chat…");
  let messages;
  try {
    messages = await scrapeTab(tabId);
    notify(tabId, 1, "done", `Scraped ${messages.length} messages.`);
  } catch (err) {
    notify(tabId, 1, "error", err.message);
    return;
  }

  // Step 2 — Classify + Chunk
  notify(tabId, 2, "running", "Classifying and chunking…");
  let chunks;
  try {
    const classified = await classifyMessages(tabId, messages);
    chunks = await chunkMessages(tabId, classified);
    notify(tabId, 2, "done", `Created ${chunks.length} chunks.`);
  } catch (err) {
    notify(tabId, 2, "error", err.message);
    return;
  }

  // Step 3 — Embeddings
  notify(tabId, 3, "running", "Generating embeddings…");
  let vectors;
  try {
    vectors = await embedChunks(chunks);
    notify(tabId, 3, "done", `Generated ${vectors.length} embeddings.`);
  } catch (err) {
    notify(tabId, 3, "error", err.message);
    return;
  }

  // Step 4 — Package
  notify(tabId, 4, "running", "Creating memory package…");
  const sessionKey = generateSessionKey();
  const projectName = new URL(sourceUrl).pathname.split("/").filter(Boolean).pop() || "chat";
  let zipBlob;
  try {
    zipBlob = await storeAndPackage(chunks, vectors, projectName, sourceUrl, sessionKey);
    notify(tabId, 4, "done", "Memory package ready.");
  } catch (err) {
    notify(tabId, 4, "error", err.message);
    return;
  }

  // Step 5 — Drive upload
  notify(tabId, 5, "running", "Uploading to Google Drive…");
  let driveFileId;
  try {
    const token = await getAuthToken(true);
    const folderId = await ensureMemoryBridgeFolder(token);
    driveFileId = await uploadPackage(token, folderId, zipBlob, `${sessionKey}.zip`);
    notify(tabId, 5, "done", "Uploaded successfully.");
  } catch (err) {
    notify(tabId, 5, "error", "Drive upload failed: " + err.message);
    return;
  }

  // Step 6 — Session key
  await saveSession(sessionKey, projectName, driveFileId, sourceUrl);
  notify(tabId, 6, "done", sessionKey);
}

// ── Message listener ──────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "extract") {
    // Get the active tab
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (!tab) {
        sendResponse({ ok: false, error: "No active tab found." });
        return;
      }
      sendResponse({ ok: true }); // Acknowledge immediately; progress via separate messages
      runPipeline(tab.id, msg.url ?? tab.url);
    });
    return true; // async
  }

  if (msg.action === "getSessions") {
    getAllSessions().then((sessions) => sendResponse({ ok: true, sessions }));
    return true;
  }
});
