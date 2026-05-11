/**
 * classifier.js — MemoryBridge Phase 1
 * Rule-based message classification.
 * Pure functions; no external dependencies.
 *
 * Usage:
 *   const classified = messages.map(classifyMessage);
 */

(() => {
  /** @type {Array<{category: string, pattern: RegExp}>} */
  const RULES = [
    { category: "error",     pattern: /error|exception|failed|not working|issue|bug/i },
    { category: "decision",  pattern: /let's go with|decided|chosen|we'll use|going with/i },
    { category: "state",     pattern: /currently|right now|status|done|completed/i },
    { category: "feature",   pattern: /feature|should|need to|functionality|implement/i },
    { category: "resolved",  pattern: /fixed|resolved|solution|works now/i },
  ];

  /**
   * Classify a single message object.
   *
   * @param {{ role: string, content: string, codeBlocks: Array }} message
   * @returns {{ ...message, category: string, confidence: number }}
   */
  function classifyMessage(message) {
    // Code blocks always take highest priority
    if (message.codeBlocks && message.codeBlocks.length > 0) {
      return { ...message, category: "code_artifact", confidence: 1.0 };
    }

    const text = message.content || "";
    let matchCount = 0;
    let primaryCategory = "general";

    // First matching rule wins the category; count all matches for confidence
    for (const rule of RULES) {
      const matches = (text.match(new RegExp(rule.pattern.source, "gi")) || []).length;
      if (matches > 0) {
        if (primaryCategory === "general") {
          primaryCategory = rule.category; // first hit sets category
        }
        matchCount += matches;
      }
    }

    const confidence = Math.min(1.0, matchCount * 0.2);

    return { ...message, category: primaryCategory, confidence };
  }

  /**
   * Classify an array of messages.
   *
   * @param {Array} messages
   * @returns {Array}
   */
  function classifyAll(messages) {
    return messages.map(classifyMessage);
  }

  // ── Export ────────────────────────────────────────────────────────────────
  window.__memoryBridgeClassify = { classifyMessage, classifyAll };

  // Listen for on-demand call from background
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.action !== "classify") return false;
    try {
      const classified = classifyAll(msg.messages);
      sendResponse({ ok: true, messages: classified });
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
    return false;
  });
})();
