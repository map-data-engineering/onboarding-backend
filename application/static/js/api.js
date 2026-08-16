// Shared API helpers. The frontend is served by Django on the SAME origin as the
// API, so we use a relative base path -- no CORS, no env var, no hard-coded host.
const API = "/api";

// Thrown for any non-2xx response. `data` holds the parsed body (field-error map
// for 400s, {detail: ...} for auth errors, etc.) so callers can render it.
class ApiError extends Error {
  constructor(status, data) {
    super(`API error ${status}`);
    this.status = status;
    this.data = data;
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// CSRF token rendered into the page by Django. Sent on unsafe requests so DRF's
// SessionAuthentication accepts them (the session cookie rides along same-origin).
//
// The cookie is the fallback rather than the primary source because a page can be
// served before Django has had reason to set it; the meta tag is always current.
function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const fromMeta = meta ? (meta.getAttribute("content") || "").trim() : "";
  if (fromMeta) return fromMeta;
  const cookie = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return cookie ? decodeURIComponent(cookie[1]) : "";
}

// Attach the header only when we actually have a token. Sending an empty one is
// worse than sending none: Django rejects it as "CSRF token ... has incorrect
// length", which reads like the token is corrupt rather than absent.
function withCsrf(headers, method) {
  if (!UNSAFE.has(method)) return headers;
  const token = csrfToken();
  if (token) headers["X-CSRFToken"] = token;
  return headers;
}

async function parseBody(res) {
  const ctype = res.headers.get("content-type") || "";
  if (ctype.includes("application/json")) {
    try { return await res.json(); } catch { return null; }
  }
  return await res.text();
}

// JSON request. `token` (optional) is sent as a DRF Token header.
async function apiJson(method, path, body, token) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Token ${token}`;
  withCsrf(headers, method);

  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await parseBody(res);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

// Multipart request (used only for the application form + CV upload).
// NOTE: never set Content-Type yourself -- the browser adds the multipart boundary.
async function apiForm(method, path, formData) {
  const headers = withCsrf({}, method);
  const res = await fetch(`${API}${path}`, { method, headers, body: formData });
  const data = await parseBody(res);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}
