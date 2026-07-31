# Frontend Developer Guide — Onboarding Portal

This guide documents the API and frontend architecture for the two user interfaces:

1. **The Applicant Portal** — the public page where people apply and take the timed quiz.
2. **The Custom Admin Panel** — the internal dashboard where staff review applicants, mark them
   **selected/rejected**, and delete them.

> **A working reference frontend already ships with the project** (vanilla HTML/CSS/JS, no build
> step). Use this document to understand the API and to extend or replace that frontend. You do
> **not** need to know Python or Django.

---

## 1. Architecture & how to talk to the backend

### The frontend is served by Django, same-origin
Django serves the pages itself, so the browser and the API share one origin — **there is no CORS
to configure**:

| URL | Page | Source file |
|-----|------|-------------|
| `/` | Applicant portal | `application/templates/applicant/portal.html` + `static/js/applicant.js` |
| `/panel/` | Staff panel | `application/templates/panel/index.html` + `static/js/panel.js` |
| `/api/…` | REST API | `application/urls.py` |

Shared helpers live in `application/static/js/api.js`. Because everything is same-origin, the JS
uses a **relative base path** — no host, no env var:

```js
const API = "/api";   // e.g. fetch(`${API}/applications/`)
```

> **Only if you build a *separate* SPA on a different origin** (e.g. a Vite app on
> `http://localhost:5173`) would you need `django-cors-headers` on the backend. The shipped
> same-origin setup does not.

### Data formats
- **Creating an application → `multipart/form-data`** (a CV file is uploaded).
- **Everything else → `application/json`**.

### Authentication
- **Applicant** endpoints are **open** — no login, no token. Don't build a login for the portal.
- **Admin** endpoints are **staff-only, token-authenticated** — see [section 4](#4-the-custom-admin-panel).

---

## 2. The applicant flow (end to end)

Order of API calls:

```
Step 1  POST /applications/                              -> create the applicant + upload CV
Step 2  POST /applications/{application_id}/quiz/start/  -> begin the timed quiz, get question #1
Step 3  (loop) POST /quiz/{session_id}/answer/           -> submit answer, receive next question
Step 4  GET  /quiz/{session_id}/result/                  -> show final score
```

Two IDs to keep in app state:
- `application_id` — returned by Step 1.
- `session_id` — returned by Step 2 (the field is named `session`). Used by every quiz call after.

---

### Step 1 — Submit the application form

`POST /api/applications/` — send as `multipart/form-data`.

**Fields to collect** (all required unless marked optional):

| Field                  | Type        | Notes                                    |
|------------------------|-------------|------------------------------------------|
| `first_name`           | text        |                                          |
| `last_name`            | text        |                                          |
| `email`                | email       | validated by the server                  |
| `phone`                | text        |                                          |
| `nationality`          | text        |                                          |
| `country_of_residence` | text        |                                          |
| `gender`               | text        | use a dropdown on your side              |
| `institution`          | text        |                                          |
| `institution_type`     | text        | e.g. University / NGO / Government        |
| `role`                 | text        |                                          |
| `education`            | text        | e.g. BSc / MSc / PhD                      |
| `r_experience`         | text        | self-rated, e.g. Beginner/Intermediate   |
| `bayesian_knowledge`   | text        | self-rated                               |
| `motivation`           | textarea    | **optional**                             |
| `expectations`         | textarea    | **optional**                             |
| `cv`                   | **file**    | required — PDF/DOC upload                 |

**Example (browser `FormData`):**

```js
const form = new FormData();
form.append("first_name", "Ada");
form.append("last_name", "Lovelace");
form.append("email", "ada@example.org");
// ...append every field above...
form.append("cv", fileInput.files[0]);   // the <input type="file">

const res = await fetch(`${API}/applications/`, { method: "POST", body: form });
// NOTE: do NOT set Content-Type yourself — the browser sets the multipart boundary.

if (res.status === 201) {
  const app = await res.json();
  const applicationId = app.id;   // <-- save this
}
```

**Success:** `201 Created` with the full application JSON (`id`, a `cv` URL, `created_at`, and the
staff-review fields `decision` (defaults to `"PENDING"`) and `decision_at` (`null`) — the applicant
UI can ignore those two).

**Validation errors:** `400 Bad Request` with a field→messages map:

```json
{ "email": ["Enter a valid email address."], "cv": ["No file was submitted."] }
```

---

### Step 2 — Start the quiz

`POST /api/applications/{application_id}/quiz/start/` — no body needed.

**Success:** `201 Created` with the first question:

```json
{
  "session": "90adba6d-7418-452a-9b44-1298ff409270",
  "position": 0,
  "total": 12,
  "question": {
    "id": 5,
    "text": "Which package is primarily used for handling spatial vector data in R?",
    "category": "SPATIAL",
    "options": ["sf", "randomForest", "shiny", "glm"],
    "time_limit_seconds": 40
  },
  "time_limit_seconds": 40,
  "deadline": "2026-07-28T12:10:29.840351Z"
}
```

Save `session` → that is your `session_id`. (`time_limit_seconds` appears both at the top level and
inside `question` — same value, provided in both places for convenience.)

> **The quiz can only be started once per applicant.** Calling this twice returns `400`
> `"A quiz session already exists for this application."` Don't offer a "restart" button — the
> backend forbids it (it would hand out a fresh timer).

---

### Step 3 — The timer, and answering questions

**The clock is server-authoritative.** Each question carries a `deadline` (ISO timestamp). Render
your countdown against that `deadline`, not a local `setTimeout` (they drift). The server allows
`time_limit_seconds` + a 3s network grace.

- The `question` object **never** contains the correct answer — don't look for it.
- Re-fetching the current question does **not** reset the timer (safe on page reload).
- Show `position + 1` of `total` as progress ("Question 1 of 12").

`POST /api/quiz/{session_id}/answer/` — send JSON:

```js
const res = await fetch(`${API}/quiz/${sessionId}/answer/`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ answer: selectedOptionString }),  // must be one of the option strings
});
const data = await res.json();
```

**Response:**

```json
{
  "timed_out": false,
  "accepted": true,
  "finished": false,
  "next": { "session": "…", "position": 1, "total": 12, "question": { … }, "deadline": "…" },
  "result": null
}
```

Drive your UI from the response:
- `timed_out: true` → time ran out; the answer wasn't counted. Move on.
- `finished: false` → render `next` as the new current question (restart the countdown to its `deadline`).
- `finished: true` → `next` is `null` and `result` holds the final score. Go to the results screen.

> **Correctness is hidden on purpose.** The response never tells the applicant whether an answer was
> right — only the final score, at the end. Don't build per-question right/wrong feedback.

**Resume after a refresh:** call `GET /api/quiz/{session_id}/current/`. It returns the current
question, or the result object if the quiz is already done. Persist `session_id` in `localStorage`.

---

### Step 4 — Show the result

`GET /api/quiz/{session_id}/result/`

```json
{ "id": "90adba6d-…", "score": 12, "total": 12, "completed_at": "2026-07-28T12:10:29.840Z" }
```

`completed_at` is `null` if not finished yet.

---

## 3. Suggested applicant-portal screens

1. **Application form** → Step 1. On success, store `application_id`, go to (2).
2. **Quiz intro** ("40s per question, no going back") → button calls Step 2.
3. **Quiz question** → renders one question + countdown + options; submit calls Step 3; auto-advances.
4. **Results** → Step 4.

Persist in `localStorage`: `application_id`, `session_id` — that lets you resume a quiz.

---

## 4. The Custom Admin Panel

Staff-only endpoints under `/api/admin/`, protected by **token auth**. Staff can list applicants,
open details/CV, view the quiz breakdown, **mark applicants selected/rejected**, and **delete** them.

### Auth model (token)
1. Staff log in with username + password → the API returns a **token**.
2. Send that token on **every** other admin request:
   ```js
   fetch(`${API}/admin/applications/`, { headers: { Authorization: `Token ${token}` } });
   ```
3. Store the token in `sessionStorage` (not `localStorage`, to reduce XSS exposure). If any admin
   call returns **`401`**, the token is missing/expired/invalid → send the user to the login screen.
   Call logout to invalidate the token on sign-out.

Only accounts with `is_staff = true` can log in. Create staff via `manage.py createsuperuser` (or
Django admin). Token auth does **not** require a CSRF header.

### Admin endpoints

**Login** — `POST /api/admin/login/` (JSON, no token needed):
```js
// 200 -> { token, user: { username, email, is_superuser } }   (save token)
// 401 -> { detail: "Invalid credentials or not a staff account." }
```

**Who am I** — `GET /api/admin/me/` → `{ username, email, is_superuser }` (validate a saved token on load).

**Logout** — `POST /api/admin/logout/` → `204`, invalidates the current token.

**List applicants** — `GET /api/admin/applications/` (paginated, 25/page):
```
?search=<text>   filter by first/last name, email, or institution
?page=<n>        page number
```
```json
{
  "count": 42, "next": "…?page=2", "previous": null,
  "results": [
    { "id": "…", "first_name": "Ada", "last_name": "Lovelace", "email": "…",
      "institution": "…", "country_of_residence": "…", "created_at": "…",
      "decision": "PENDING", "quiz_status": "completed", "score": 12, "total": 12 }
  ]
}
```
- `decision` is one of `"PENDING" | "SELECTED" | "REJECTED"`.
- `quiz_status` is one of `"not_started" | "in_progress" | "completed"`. `score`/`total` are `null`
  until a quiz exists.

**Applicant detail** — `GET /api/admin/applications/{id}/` → all profile fields + an absolute `cv`
URL + `decision`, `decision_at`, and quiz summary (`quiz_status`, `score`, `total`, `completed_at`).

**Update decision** — `PATCH /api/admin/applications/{id}/`
```js
await fetch(`${API}/admin/applications/${id}/`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json", Authorization: `Token ${token}` },
  body: JSON.stringify({ decision: "SELECTED" }),   // "SELECTED" | "REJECTED" | "PENDING"
});
// 200 -> the updated applicant detail (with new decision + decision_at)
// 400 -> { "decision": ["Must be one of ['PENDING', 'REJECTED', 'SELECTED']."] }
```

**Delete applicant** — `DELETE /api/admin/applications/{id}/` → `204`. Also removes the uploaded CV
and the quiz (cascade). Irreversible — confirm in the UI first.

**Bulk action** — `POST /api/admin/applications/bulk/` (for checkbox selection in the table):
```js
await fetch(`${API}/admin/applications/bulk/`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Token ${token}` },
  body: JSON.stringify({ ids: ["<uuid>", "<uuid>"], action: "select" }),
});
```
- `action`: `"select"` | `"reject"` | `"pending"` | `"delete"`.
- Response: `{ "updated": 2, "decision": "SELECTED" }` for select/reject/pending, or
  `{ "deleted": 2 }` for delete.
- `400` if `ids` is empty or `action` is invalid.

**Quiz breakdown** — `GET /api/admin/applications/{id}/quiz/`:
```json
{
  "session": "…", "score": 12, "total": 12, "completed_at": "…",
  "questions": [
    { "position": 0, "question_text": "…", "category": "R",
      "submitted_answer": "read.csv()", "correct_answer": "read.csv()",
      "is_correct": true, "timed_out": false, "served_at": "…", "answered_at": "…" }
  ]
}
```
Returns `404` if the applicant never started the quiz. (Exposes `correct_answer` — staff-only.)

### Suggested admin-panel screens
1. **Login** → `POST /admin/login/`, store token.
2. **Applicants table** → `GET /admin/applications/` with search (`?search=`) + pagination.
   Add row checkboxes + a bulk toolbar (Mark selected / Mark rejected / Reset to pending / Delete)
   wired to `POST /admin/applications/bulk/`. Show the `decision` as a colored badge.
3. **Applicant detail** → `GET /admin/applications/{id}/` (fields + "Download CV" link).
   Add Select / Reject / Pending buttons (`PATCH`) and a Delete button (`DELETE`).
4. **Quiz breakdown** (tab on the detail page) → `GET /admin/applications/{id}/quiz/`.

> Django's built-in admin at **`/admin/`** also exists (superuser login) and shows the `decision`
> column/filter — a ready-made fallback UI.

---

## 5. Running the backend locally

```bash
# from the project root
.venv/Scripts/python.exe manage.py migrate         # first time only
.venv/Scripts/python.exe manage.py seed_questions   # loads the 12 quiz questions
.venv/Scripts/python.exe manage.py createsuperuser  # a staff login for the panel (optional)
.venv/Scripts/python.exe manage.py runserver 8000   # or another port if 8000 is busy
```

- Applicant portal: `http://127.0.0.1:8000/`
- Staff panel: `http://127.0.0.1:8000/panel/`
- Applicant API: `http://127.0.0.1:8000/api/…`
- Custom admin API: `http://127.0.0.1:8000/api/admin/…` (token auth — see [section 4](#4-the-custom-admin-panel))
- Django built-in admin: `http://127.0.0.1:8000/admin/`
- Browsable API: open any GET endpoint in the browser to see it rendered by DRF.

For ready-to-run request examples (Thunder Client), see `README_API_TESTING.md` (kept locally).

---

## 6. Quick reference — all endpoints

| Method | Path                                          | Body                   | Auth            | Purpose                          |
|--------|-----------------------------------------------|------------------------|-----------------|----------------------------------|
| POST   | `/api/applications/`                          | multipart form         | —               | Create applicant + upload CV     |
| POST   | `/api/applications/{id}/quiz/start/`          | —                      | —               | Start quiz, get question #1       |
| GET    | `/api/quiz/{session}/current/`                | —                      | —               | Current question (or result)      |
| POST   | `/api/quiz/{session}/answer/`                 | `{"answer": ""}`       | —               | Submit answer, get next question  |
| GET    | `/api/quiz/{session}/result/`                 | —                      | —               | Final score                       |
| POST   | `/api/admin/login/`                           | `{username,password}`  | —               | Staff login → token               |
| POST   | `/api/admin/logout/`                          | —                      | Token           | Invalidate token                  |
| GET    | `/api/admin/me/`                              | —                      | Token           | Current staff user                |
| GET    | `/api/admin/applications/`                    | —                      | Token           | List applicants (`?search=`,`?page=`) |
| POST   | `/api/admin/applications/bulk/`               | `{ids,action}`         | Token           | Bulk select/reject/pending/delete |
| GET    | `/api/admin/applications/{id}/`               | —                      | Token           | Applicant detail + CV + decision  |
| PATCH  | `/api/admin/applications/{id}/`               | `{"decision": ""}`     | Token           | Set decision                      |
| DELETE | `/api/admin/applications/{id}/`               | —                      | Token           | Delete applicant                  |
| GET    | `/api/admin/applications/{id}/quiz/`          | —                      | Token           | Per-question breakdown            |

Admin endpoints require the `Authorization: Token <token>` header — see [section 4](#4-the-custom-admin-panel).
