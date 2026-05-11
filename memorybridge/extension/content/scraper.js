/**
 * scraper.js — MemoryBridge Phase 1
 * Content script: scrapes all chat messages from Claude.ai and ChatGPT.
 * Injected on document_idle; also callable on-demand via chrome.scripting.executeScript.
 *
 * Returns (via window.__memoryBridgeScrape):
 *   Array<{ role: "user"|"assistant", content: string,
 *            timestamp: string|null, codeBlocks: Array<{language:string, code:string}> }>
 */

(() => {
  // ── Utilities ─────────────────────────────────────────────────────────────

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function detectSite() {
    const host = location.hostname;
    if (host.includes("claude.ai")) return "claude";
    if (host.includes("chat.openai.com") || host.includes("chatgpt.com")) return "chatgpt";
    return null;
  }

  function extractCodeBlocks(container) {
    const blocks = [];
    container.querySelectorAll("pre").forEach((pre) => {
      const codeEl = pre.querySelector("code");
      if (!codeEl) return;

      // Derive language from class like "language-python"
      let language = "plaintext";
      const cls = [...codeEl.classList].find((c) => c.startsWith("language-"));
      if (cls) language = cls.replace("language-", "");

      blocks.push({ language, code: codeEl.innerText.trim() });
    });
    return blocks;
  }

  function textWithoutCode(container) {
    // Clone, remove <pre> blocks, return remaining text
    const clone = container.cloneNode(true);
    clone.querySelectorAll("pre").forEach((p) => p.remove());
    return clone.innerText.trim();
  }

  // ── Sentinel wait ─────────────────────────────────────────────────────────

  async function waitForSentinel(selector, maxTries = 40, interval = 150) {
    for (let i = 0; i < maxTries; i++) {
      if (document.querySelector(selector)) return true;
      await sleep(interval);
    }
    return false;
  }

  // ── Auto-scroll to load all messages ──────────────────────────────────────

  async function scrollToLoadAll(scrollRoot) {
    // Scroll to top first
    scrollRoot.scrollTop = 0;
    await sleep(400);

    // Scroll down incrementally until no new content appears
    let lastHeight = 0;
    for (let i = 0; i < 50; i++) {
      scrollRoot.scrollTop = scrollRoot.scrollHeight;
      await sleep(300);
      if (scrollRoot.scrollHeight === lastHeight) break;
      lastHeight = scrollRoot.scrollHeight;
    }
    await sleep(500); // settle
  }

  // ── ChatGPT scraper ───────────────────────────────────────────────────────

  async function scrapeGPT() {
    const sentinel = "[data-message-author-role]";
    const found = await waitForSentinel(sentinel);
    if (!found) throw new Error("ChatGPT: message elements not found in DOM.");

    // Find the scroll container (ancestor of messages)
    const firstMsg = document.querySelector(sentinel);
    let scrollRoot = firstMsg?.closest("main") ?? document.documentElement;
    await scrollToLoadAll(scrollRoot);

    const nodes = [...document.querySelectorAll("[data-message-author-role]")];
    return nodes.map((node) => {
      const role = node.getAttribute("data-message-author-role"); // "user" | "assistant"
      const codeBlocks = extractCodeBlocks(node);
      const content = textWithoutCode(node);

      // Timestamp: look for a time element nearby
      const timeEl = node.querySelector("time") ?? node.closest("[data-testid]")?.querySelector("time");
      const timestamp = timeEl ? timeEl.getAttribute("datetime") ?? timeEl.innerText : null;

      return { role, content, timestamp, codeBlocks };
    });
  }

  // ── Claude.ai scraper ─────────────────────────────────────────────────────

  async function scrapeClaude() {
    // Claude uses aria attributes and structural patterns; no stable data-* attrs.
    // Strategy: wait for the main conversation region, then collect alternating turns.

    // Wait for any human message to appear (heuristic selectors)
    const candidates = [
      "[data-is-streaming]",           // streaming indicator disappears when done
      "[class*='human-turn']",
      "[class*='HumanTurn']",
      "article",
    ];

    let sentinel = null;
    for (const sel of candidates) {
      const found = await waitForSentinel(sel, 20, 100);
      if (found) { sentinel = sel; break; }
    }

    // Fallback: wait a flat 3 s for SPA to mount
    if (!sentinel) await sleep(3000);

    // Find scroll root — the main scrollable region
    const main = document.querySelector("main") ?? document.documentElement;
    await scrollToLoadAll(main);

    // Collect turns. Claude renders turns as sibling containers in the conversation.
    // We look for the deepest repeating structural pattern.
    const messages = [];

    // Try aria-role="presentation" or role="row" grouping first
    // Then fall back to a structural walk of <article> or alternating divs.
    const turnSelectors = [
      "[data-test-render-count]",     // sometimes present
      "article",
      `[class*="message"]`,
      `[class*="Message"]`,
    ];

    let turns = [];
    for (const sel of turnSelectors) {
      turns = [...document.querySelectorAll(sel)];
      if (turns.length >= 2) break;
    }

    // If still nothing, grab all top-level children of the conversation root
    if (turns.length < 2) {
      const conversationRoot =
        document.querySelector("[class*='conversation']") ??
        document.querySelector("main > div > div") ??
        document.querySelector("main");
      if (conversationRoot) {
        turns = [...conversationRoot.children];
      }
    }

    // Assign roles by alternation: first turn is always user
    turns.forEach((turn, idx) => {
      // If there's an explicit role indicator, prefer it
      let role;
      const roleAttr =
        turn.getAttribute("data-message-author-role") ??
        turn.getAttribute("aria-label");

      if (roleAttr) {
        role = roleAttr.toLowerCase().includes("human") || roleAttr.toLowerCase().includes("user")
          ? "user"
          : "assistant";
      } else {
        role = idx % 2 === 0 ? "user" : "assistant";
      }

      const codeBlocks = extractCodeBlocks(turn);
      const content = textWithoutCode(turn);

      if (!content && codeBlocks.length === 0) return; // skip empty nodes

      const timeEl = turn.querySelector("time");
      const timestamp = timeEl ? timeEl.getAttribute("datetime") ?? timeEl.innerText : null;

      messages.push({ role, content, timestamp, codeBlocks });
    });

    return messages;
  }

  // ── Entry point ───────────────────────────────────────────────────────────

  async function scrapeMessages() {
    const site = detectSite();
    if (!site) throw new Error("MemoryBridge: unsupported site — " + location.hostname);

    const messages = site === "claude" ? await scrapeClaude() : await scrapeGPT();

    if (messages.length === 0) {
      throw new Error("MemoryBridge: no messages found. Is this an active conversation?");
    }

    return messages;
  }

  // Expose globally so background.js can call via executeScript + world MAIN
  window.__memoryBridgeScrape = scrapeMessages;

  // Also listen for message from background service worker
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.action !== "scrape") return false;
    scrapeMessages()
      .then((msgs) => sendResponse({ ok: true, messages: msgs }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // async response
  });
})();
