/**
 * session.js — MemoryBridge Phase 1
 * Session key generation and chrome.storage.local management.
 * Imported as ES module by background.js.
 */

const STORAGE_KEY = "memorybridge_sessions";

/**
 * Generate a random 8-character session key.
 * @returns {string}
 */
export function generateSessionKey() {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 8);
}

/**
 * Persist a session record to chrome.storage.local.
 *
 * @param {string} key          8-char session key
 * @param {string} project      Human-readable project / page title
 * @param {string} driveFileId  Google Drive file ID of the uploaded package
 * @param {string} sourceUrl    The original chat URL
 * @returns {Promise<void>}
 */
export async function saveSession(key, project, driveFileId, sourceUrl) {
  const all = await getAllSessions();
  all[key] = {
    key,
    project,
    source_url: sourceUrl,
    drive_file_id: driveFileId,
    created_at: new Date().toISOString(),
    status: "active",
  };
  await chrome.storage.local.set({ [STORAGE_KEY]: all });
}

/**
 * Load all stored sessions.
 * @returns {Promise<Record<string, object>>}
 */
export async function getAllSessions() {
  const result = await chrome.storage.local.get(STORAGE_KEY);
  return result[STORAGE_KEY] ?? {};
}

/**
 * Update the status field of a stored session.
 *
 * @param {string} key
 * @param {"active"|"archived"|"error"} status
 * @returns {Promise<void>}
 */
export async function updateSessionStatus(key, status) {
  const all = await getAllSessions();
  if (all[key]) {
    all[key].status = status;
    await chrome.storage.local.set({ [STORAGE_KEY]: all });
  }
}
