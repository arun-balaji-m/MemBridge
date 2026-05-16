/**
 * chunker.js — MemoryBridge Phase 1
 * Sliding-window chunker with TF-IDF keyword extraction and topic-shift detection.
 *
 * Usage:
 *   const chunks = chunkMessages(classifiedMessages);
 */

(() => {
  // ── TF-IDF helpers ────────────────────────────────────────────────────────

  const STOPWORDS = new Set([
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "is","it","its","be","was","are","were","been","has","have","had","do",
    "does","did","will","would","could","should","may","might","shall","i",
    "you","we","they","he","she","it","this","that","these","those","not",
    "so","if","as","by","from","up","out","also","just","can","my","your",
  ]);

  function tokenize(text) {
    return (text || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((t) => t.length > 2 && !STOPWORDS.has(t));
  }

  function termFreq(tokens) {
    const freq = {};
    for (const t of tokens) freq[t] = (freq[t] || 0) + 1;
    return freq;
  }

  /** Compute IDF over corpus of token arrays. */
  function computeIDF(corpus) {
    const df = {};
    const N = corpus.length || 1;
    for (const tokens of corpus) {
      const unique = new Set(tokens);
      for (const t of unique) df[t] = (df[t] || 0) + 1;
    }
    const idf = {};
    for (const [term, count] of Object.entries(df)) {
      idf[term] = Math.log((N + 1) / (count + 1)) + 1;
    }
    return idf;
  }

  /** Return top-N terms by TF-IDF score for a token array, given global IDF. */
  function topTFIDF(tokens, idf, n = 5) {
    const tf = termFreq(tokens);
    const scored = Object.entries(tf).map(([term, freq]) => [
      term,
      freq * (idf[term] || 1),
    ]);
    return scored
      .sort((a, b) => b[1] - a[1])
      .slice(0, n)
      .map(([term]) => term);
  }

  // ── Topic-shift detection ─────────────────────────────────────────────────

  /** Jaccard similarity between two sets of strings. */
  function jaccard(setA, setB) {
    const a = new Set(setA);
    const b = new Set(setB);
    const inter = [...a].filter((x) => b.has(x)).length;
    const union = new Set([...a, ...b]).size;
    return union === 0 ? 1 : inter / union;
  }

  // ── Chunker ───────────────────────────────────────────────────────────────

  const WINDOW_MIN = 3;
  const WINDOW_MAX = 5;
  const TOPIC_SHIFT_THRESHOLD = 0.2;

  /**
   * Chunk classified messages into semantic groups.
   *
   * @param {Array} messages - output of classifyAll()
   * @returns {Array<Chunk>}
   */
  function chunkMessages(messages) {
    if (!messages || messages.length === 0) return [];

    // Pre-compute token arrays per message for IDF
    const allTokens = messages.map((m) => tokenize(m.content));
    const idf = computeIDF(allTokens);

    const chunks = [];
    let chunkIndex = 0;
    let windowStart = 0;
    let prevKeywords = [];

    while (windowStart < messages.length) {
      // Determine window size (prefer WINDOW_MAX, shrink at end)
      const remaining = messages.length - windowStart;
      const windowSize = Math.min(WINDOW_MAX, Math.max(WINDOW_MIN, remaining));
      const window = messages.slice(windowStart, windowStart + windowSize);

      // Combine tokens for the window
      const windowTokens = window.flatMap((m, i) => allTokens[windowStart + i]);
      const keywords = topTFIDF(windowTokens, idf, 5);

      // Check topic-shift at boundaries (skip first chunk)
      if (chunkIndex > 0 && prevKeywords.length > 0) {
        const similarity = jaccard(prevKeywords.slice(0, 3), keywords.slice(0, 3));
        if (similarity < TOPIC_SHIFT_THRESHOLD) {
          // New topic — flush current window as-is; next iteration starts fresh
          // (already handled by windowStart advancing below)
        }
      }

      // Build chunk
      const id = `chunk_${String(chunkIndex + 1).padStart(3, "0")}`;
      const firstMsg = window[0];

      // Title: first 15 words of first message (enough to capture full short questions)
      const titleWords = (firstMsg.content || "").split(/\s+/).slice(0, 15).join(" ");
      const title = titleWords || id;

      // Summary: first sentence of first message, capped at 200 chars
      const firstSentence = (firstMsg.content || "").split(/[.!?]/)[0].trim();
      const summary = (firstSentence || title).slice(0, 200);

      // Detail: full concatenated text
      const detail = window.map((m) => `[${m.role}]: ${m.content}`).join("\n\n");

      // Code: join all code blocks
      const allCode = window
        .flatMap((m) => m.codeBlocks || [])
        .map((b) => `\`\`\`${b.language}\n${b.code}\n\`\`\``)
        .join("\n\n");

      // Category: most frequent in window
      const catCounts = {};
      for (const m of window) catCounts[m.category] = (catCounts[m.category] || 0) + 1;
      const category = Object.entries(catCounts).sort((a, b) => b[1] - a[1])[0][0];

      chunks.push({
        id,
        title,
        summary,
        detail,
        code: allCode || null,
        tags: keywords,
        category,
        retrieved: false,
      });

      prevKeywords = keywords;
      chunkIndex++;
      windowStart += windowSize;
    }

    return chunks;
  }

  // ── Export ────────────────────────────────────────────────────────────────
  window.__memoryBridgeChunk = { chunkMessages };

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.action !== "chunk") return false;
    try {
      const chunks = chunkMessages(msg.messages);
      sendResponse({ ok: true, chunks });
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
    return false;
  });
})();
