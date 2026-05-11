/**
 * drive.js — MemoryBridge Phase 1
 * Google Drive API v3 helpers using Chrome Identity API.
 * All functions are async and throw on unrecoverable errors.
 * Imported as ES module by background.js.
 */

const DRIVE_API = "https://www.googleapis.com/drive/v3";
const DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3";
const FOLDER_NAME = "MemoryBridge";
const FOLDER_MIME = "application/vnd.google-apps.folder";
const SCOPE = "https://www.googleapis.com/auth/drive.file";

// ── Auth ──────────────────────────────────────────────────────────────────

/**
 * Obtain a valid OAuth2 access token.
 * Automatically removes stale cached tokens and retries once.
 *
 * @param {boolean} interactive - show consent screen if needed
 * @returns {Promise<string>}
 */
export async function getAuthToken(interactive = true) {
  return new Promise((resolve, reject) => {
    chrome.identity.getAuthToken({ interactive, scopes: [SCOPE] }, (token) => {
      if (chrome.runtime.lastError || !token) {
        reject(new Error(chrome.runtime.lastError?.message ?? "Auth failed."));
      } else {
        resolve(token);
      }
    });
  });
}

/**
 * Remove a cached token (call after a 401) and get a fresh one.
 * @param {string} staleToken
 * @returns {Promise<string>}
 */
async function refreshToken(staleToken) {
  await new Promise((resolve) => {
    chrome.identity.removeCachedAuthToken({ token: staleToken }, resolve);
  });
  return getAuthToken(true);
}

// ── Generic authenticated fetch with 401-retry ────────────────────────────

async function driveRequest(url, options, token, retried = false) {
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(options.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });

  if (res.status === 401 && !retried) {
    const newToken = await refreshToken(token);
    return driveRequest(url, options, newToken, true);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Drive API ${res.status}: ${body.slice(0, 200)}`);
  }

  return res;
}

// ── Folder management ─────────────────────────────────────────────────────

/**
 * Find or create the "MemoryBridge" folder in Google Drive root.
 * @param {string} token
 * @returns {Promise<string>} folder ID
 */
export async function ensureMemoryBridgeFolder(token) {
  // Search for existing folder
  const q = encodeURIComponent(
    `name='${FOLDER_NAME}' and mimeType='${FOLDER_MIME}' and trashed=false`
  );
  const res = await driveRequest(
    `${DRIVE_API}/files?q=${q}&fields=files(id,name)`,
    { method: "GET" },
    token
  );
  const data = await res.json();

  if (data.files && data.files.length > 0) {
    return data.files[0].id;
  }

  // Create folder
  const createRes = await driveRequest(
    `${DRIVE_API}/files`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: FOLDER_NAME,
        mimeType: FOLDER_MIME,
      }),
    },
    token
  );
  const folder = await createRes.json();
  return folder.id;
}

// ── Upload ────────────────────────────────────────────────────────────────

/**
 * Upload a zip Blob to the MemoryBridge folder using multipart upload.
 *
 * @param {string} token
 * @param {string} folderId
 * @param {Blob}   zipBlob
 * @param {string} filename  e.g. "abc123xy.zip"
 * @returns {Promise<string>} Drive file ID
 */
export async function uploadPackage(token, folderId, zipBlob, filename) {
  const metadata = {
    name: filename,
    parents: [folderId],
    mimeType: "application/zip",
  };

  const boundary = "mb_boundary_" + Date.now();
  const metaPart =
    `--${boundary}\r\n` +
    `Content-Type: application/json; charset=UTF-8\r\n\r\n` +
    JSON.stringify(metadata) +
    `\r\n`;
  const filePart =
    `--${boundary}\r\n` +
    `Content-Type: application/zip\r\n\r\n`;
  const closing = `\r\n--${boundary}--`;

  // Build multipart body
  const encoder = new TextEncoder();
  const parts = [
    encoder.encode(metaPart),
    encoder.encode(filePart),
    new Uint8Array(await zipBlob.arrayBuffer()),
    encoder.encode(closing),
  ];

  const totalLength = parts.reduce((sum, p) => sum + p.byteLength, 0);
  const body = new Uint8Array(totalLength);
  let offset = 0;
  for (const part of parts) {
    body.set(part, offset);
    offset += part.byteLength;
  }

  const res = await driveRequest(
    `${DRIVE_UPLOAD_API}/files?uploadType=multipart&fields=id`,
    {
      method: "POST",
      headers: {
        "Content-Type": `multipart/related; boundary=${boundary}`,
      },
      body: body.buffer,
    },
    token
  );

  const file = await res.json();
  return file.id;
}
