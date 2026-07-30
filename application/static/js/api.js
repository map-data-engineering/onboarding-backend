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

// CSRF token rendered into the page by Django. Sent on unsafe requests so DRF's
// SessionAuthentication accepts them (the session cookie rides along same-origin).
function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute("content") : "";
}
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

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
  if (UNSAFE.has(method)) headers["X-CSRFToken"] = csrfToken();

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
  const headers = {};
  if (UNSAFE.has(method)) headers["X-CSRFToken"] = csrfToken();
  const res = await fetch(`${API}${path}`, { method, headers, body: formData });
  const data = await parseBody(res);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}
