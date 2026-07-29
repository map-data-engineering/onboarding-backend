# Frontend Developer Guide — Onboarding Portal

This is the guide for building the **two** front ends that talk to this Django API:

1. **The Applicant Portal** — the public page where people apply and take the timed quiz.
2. **The Custom Admin Panel** — the internal dashboard where staff review applicants and scores.

You do **not** need to know Python or Django. You only need this document and the running API.

---

## 1. Talking to the backend

### Base URL
Every endpoint lives under `/api/`. In local development the backend runs at:

```
http://127.0.0.1:8000/api/
```

> ⚠️ Port 8000 may already be taken on this machine by another project. If so the backend
> dev will start it on another port (e.g. `http://127.0.0.1:8077`). Always read the base URL
> from an environment variable in your app — never hard-code it.
>
> ```env
> # .env  (Vite example — use VITE_ prefix; CRA uses REACT_APP_)
> VITE_API_BASE_URL=http://127.0.0.1:8000/api
> ```

### Data formats
- **Creating an application → `multipart/form-data`** (because a CV file is uploaded).
- **Everything else → `application/json`**.

### Authentication
The **applicant** endpoints have **no login, no token, no API key** — they are open. Do not build
a login screen for the applicant portal. (The **custom admin panel** is different — it uses token
auth; see [section 4](#4-the-custom-admin-panel).)

### CORS — read this before you write any fetch()
The backend does **not** yet allow cross-origin requests. Your dev server (e.g.
`http://localhost:5173`) is a *different origin* from the API (`http://127.0.0.1:8000`), so the
browser will block your requests with a CORS error until the backend enables it.

Ask the backend dev to install and configure `django-cors-headers` with your dev origin
allow-listed. Until that is done, your `fetch()` calls will fail in the browser even though
they work in Postman/curl. **This is the #1 thing that will trip you up on day one.**

---

## 2. The applicant flow (end to end)

The whole applicant journey is 3 stages. Here is the exact order of API calls:

```
Step 1  POST /applications/                              -> create the applicant + upload CV
Step 2  POST /applications/{application_id}/quiz/start/  -> begin the timed quiz, get question #1
Step 3  (loop) POST /quiz/{session_id}/answer/           -> submit answer, receive next question
Step 4  GET  /quiz/{session_id}/result/                  -> show final score
```

You will store two IDs in your app state as you go:
- `application_id` — returned by Step 1.
- `session_id` — returned by Step 2 (field name is `session`). Used by every quiz call after.

---

### Step 1 — Submit the application form

`POST /api/applications/` — send as `multipart/form-data`.

**Fields to collect on your form** (all required unless marked optional):

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

**Success:** `201 Created` with the full application JSON (includes `id`, a `cv` URL, and `created_at`).

**Validation errors:** `400 Bad Request` with a field→messages map. Render these next to your inputs:

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
    "options": ["sf", "randomForest", "shiny", "glm"]
  },
  "time_limit_seconds": 40,
  "deadline": "2026-07-28T12:10:29.840351Z"
}
```

Save `session` → that is your `session_id` for all later calls. (`time_limit_seconds` also appears
*inside* the `question` object — it's the same value, provided in both places for convenience.)

> **The quiz can only be started once per applicant.** If you call this twice you get
> `400` with `"A quiz session already exists for this application."` Do not offer a "restart"
> button — the backend intentionally forbids it (it would hand out a fresh timer).

---

### Step 3 — The timer, and answering questions

**The clock is server-authoritative.** Each question carries a `deadline` (ISO timestamp).
Render your countdown against that `deadline`, not against a local `setTimeout` you started —
the two will drift. The formula the server uses is `time_limit_seconds` + a 3s network grace.

- The `question` object **never** contains the correct answer — don't look for it.
- Re-fetching the current question does **not** reset the timer (safe to call on page reload).
- Show `position + 1` of `total` as progress (e.g. "Question 1 of 12").

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

How to drive your UI from this response:
- `timed_out: true` → their time ran out; the answer was not counted. Move on.
- `finished: false` → render `next` as the new current question (and restart the countdown to its `deadline`).
- `finished: true` → `next` is `null` and `result` holds the final score. Go to the results screen.

> **Correctness is hidden on purpose.** The response never tells the applicant whether they got
> it right — only at the very end (the score). Don't build per-question right/wrong feedback.

**If the applicant closes the tab / refreshes:** call
`GET /api/quiz/{session_id}/current/` to resume. It returns the current question, or — if the
quiz is already done — the result object instead. Persist `session_id` in `localStorage` so you
can resume.

---

### Step 4 — Show the result

`GET /api/quiz/{session_id}/result/`

```json
{ "id": "90adba6d-…", "score": 12, "total": 12, "completed_at": "2026-07-28T12:10:29.840Z" }
```

Display `score` / `total`. `completed_at` is `null` if somehow not finished yet.

---

## 3. Suggested applicant-portal screens

1. **Application form** → Step 1. On success, store `application_id`, go to (2).
2. **Quiz intro** ("You have 40s per question, no going back") → button calls Step 2.
3. **Quiz question** → renders one question + countdown + options; submit calls Step 3; auto-advances.
4. **Results** → Step 4.

State to persist in `localStorage`: `application_id`, `session_id`. That lets you resume a quiz.

---

## 4. The Custom Admin Panel

The admin panel is where staff **list applicants, open an applicant's details/CV, and see quiz
scores**. These endpoints **now exist** and are live under `/api/admin/`. They are **staff-only**
and protected by **token auth**.

### Auth model (token)
1. Staff log in with username + password → the API returns a **token**.
2. You send that token on **every** other admin request as a header:
   ```js
   fetch(`${API}/admin/applications/`, { headers: { Authorization: `Token ${token}` } });
   ```
3. Store the token in `sessionStorage` (not `localStorage`, to reduce XSS exposure). If any admin
   call returns **`401`**, the token is missing/expired/invalid → send the user back to the login
   screen. Call the logout endpoint to invalidate the token on sign-out.

Only accounts with `is_staff = true` can log in here. A backend dev creates staff accounts with
`manage.py createsuperuser` (or via Django admin).

### Admin endpoints

**Login** — `POST /api/admin/login/` (JSON, no token needed):
```js
const res = await fetch(`${API}/admin/login/`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password }),
});
// 200 -> { token, user: { username, email, is_superuser } }   (save token)
// 401 -> { detail: "Invalid credentials or not a staff account." }
```

**Who am I** — `GET /api/admin/me/` → `{ username, email, is_superuser }` (use to validate a saved token on app load).

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
      "quiz_status": "completed", "score": 12, "total": 12 }
  ]
}
```
`quiz_status` is one of `"not_started" | "in_progress" | "completed"`. `score`/`total` are `null`
until a quiz exists.

**Applicant detail** — `GET /api/admin/applications/{id}/` → all fields + an absolute `cv` URL +
quiz summary (`quiz_status`, `score`, `total`, `completed_at`).

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
Returns `404` if the applicant never started the quiz. (This endpoint exposes `correct_answer` —
it's staff-only, so that's fine.)

### Suggested admin-panel screens
1. **Login** → `POST /admin/login/`, store token, go to (2).
2. **Applicants table** → `GET /admin/applications/` with a search box (`?search=`) and pagination.
3. **Applicant detail** → `GET /admin/applications/{id}/` (show fields + a "Download CV" link to `cv`).
4. **Quiz breakdown** (tab on the detail page) → `GET /admin/applications/{id}/quiz/`.

> Django's built-in admin at **`/admin/`** also still exists (superuser login) if staff prefer a
> ready-made UI — but the custom panel above is what you're building.

---

## 5. Running the backend locally (so you can develop against it)

```bash
# from the project root
.venv/Scripts/python.exe manage.py migrate         # first time only
.venv/Scripts/python.exe manage.py seed_questions   # loads the 12 quiz questions
.venv/Scripts/python.exe manage.py runserver 8000   # or another port if 8000 is busy
```

- Applicant API: `http://127.0.0.1:8000/api/…`
- Custom admin API: `http://127.0.0.1:8000/api/admin/…` (token auth — see [section 4](#4-the-custom-admin-panel))
- Django's built-in admin: `http://127.0.0.1:8000/admin/` (needs a superuser:
  `manage.py createsuperuser`)
- Browsable API: open any GET endpoint in the browser to see it rendered by DRF.

For the exact request/response shapes and ready-to-run test commands, see
[`README_API_TESTING.md`](./README_API_TESTING.md).

---

## 6. Quick reference — all endpoints

| Method | Path                                          | Body            | Purpose                          |
|--------|-----------------------------------------------|-----------------|----------------------------------|
| POST   | `/api/applications/`                          | multipart form  | Create applicant + upload CV     |
| POST   | `/api/applications/{application_id}/quiz/start/` | —             | Start quiz, get question #1       |
| GET    | `/api/quiz/{session_id}/current/`             | —               | Current question (or result)      |
| POST   | `/api/quiz/{session_id}/answer/`              | `{"answer": ""}` | Submit answer, get next question |
| GET    | `/api/quiz/{session_id}/result/`              | —               | Final score                       |
| POST   | `/api/admin/login/`                           | `{username,password}` | Staff login → token         |
| POST   | `/api/admin/logout/`                          | — (token)       | Invalidate token                  |
| GET    | `/api/admin/me/`                              | — (token)       | Current staff user                |
| GET    | `/api/admin/applications/`                    | — (token)       | List applicants (`?search=`,`?page=`) |
| GET    | `/api/admin/applications/{id}/`               | — (token)       | Applicant detail + CV             |
| GET    | `/api/admin/applications/{id}/quiz/`          | — (token)       | Per-question breakdown            |

Admin endpoints require `Authorization: Token <token>` — see [section 4](#4-the-custom-admin-panel).
