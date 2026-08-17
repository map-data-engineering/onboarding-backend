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
- **The final submission → `multipart/form-data`** (the CV file is uploaded there).
- **Everything else → `application/json`**. (Creating an application accepts either.)

### Authentication
- **Applicant** endpoints are **open** — no login, no token. Don't build a login for the portal.
- **Admin** endpoints are **staff-only, token-authenticated** — see [section 4](#4-the-custom-admin-panel).

---

## 2. The applicant flow (end to end)

The journey has **eight steps**, and every one after the first is persisted server-side as it is
completed. The **written answers and CV are collected at the very end**, and only from applicants who
score at least the pass mark (**8** of the 14 drawn, `PASS_MARK`). The motivation and expectations are
mandatory, and the CV must be a PDF (max 2 pages, 5MB).

```
Step 0  GET  /config/                                    -> preparation screen: limits, deadline, countries
Step 1  POST /applications/                              -> create the applicant (details only)
Step 2  POST /applications/{id}/eligibility/             -> four practical questions; may END the journey
Step 3  POST /applications/{id}/experience/              -> experience and plans (8 answers)
Step 4  GET  /applications/{id}/claims/                  -> the honesty-check function names
        POST /applications/{id}/claims/                  -> their answers
Step 5  POST /applications/{id}/quiz/start/              -> begin the timed check, get question #1
        (loop) POST /quiz/{session_id}/answer/           -> submit answer, receive next question
        GET  /quiz/{session_id}/result/                  -> final score + `passed`
Step 6  POST /applications/{id}/finalize/                -> written answers + CV
        (only if `passed` is true — the server returns 403 otherwise)
Step 7  (no call) confirmation screen
```

One ID to keep in app state: **`application_id`**, returned by Step 1 — you need it through Step 6.
The `session_id` comes back from Step 5 and from `/status/`, so there's no need to persist it
separately.

> **Nothing is decided in the browser.** Which option strings are valid, which honesty-check names
> are invented, whether an eligibility answer ends the journey, whether the final step is unlocked,
> and the composite score are all computed server-side from the stored record.

> **The gate is enforced server-side.** Hiding the final form in your UI is a convenience, not the
> control. `POST /finalize/` independently checks that the quiz is finished and that
> `score >= pass_mark`.

---

### Step 0 — Before you begin

`GET /api/config/` — no auth, no application id. Fetch it **before rendering anything**; it holds the
copy and limits that must match what the API enforces:

```json
{
  "contact_email": "cmyalla@ihi.or.tz",
  "deadline": "Friday 28 August 2026",
  "duration": "about 15 minutes",
  "funding_gate": true,
  "limits": { "cv_max_mb": 5.0, "cv_max_pages": 2, "max_words": 300 },
  "quiz": { "questions": 14, "bank_size": 24, "seconds_min": 25, "seconds_max": 25, "pass_mark": 8 },
  "countries": [{ "label": "Tanzania and neighbours", "countries": ["Tanzania", "Kenya", "…"] },
                { "label": "All countries", "countries": ["Afghanistan", "…"] }]
}
```

Render a preparation screen listing what the applicant needs to have ready — a PDF CV within
`cv_max_pages`/`cv_max_mb`, a dataset they analysed and 5–15 lines of their own R, their motivation
within `max_words` — with **a tickbox per item** and the start button disabled until all are ticked.
Word the tickboxes specifically ("My CV is a PDF, no more than 2 pages"): the point is to make people
go and check the file, which "I have read the requirements" does not. Add a **Print this list**
button; a meaningful share of applicants read this on a phone and draft their answers elsewhere.

State the funding position here too, before anyone invests fifteen minutes: there is no travel,
accommodation or subsistence support.

Nothing is stored by this step — it exists to raise the quality of what you receive.

---

### Step 1 — Submit the details form

`POST /api/applications/` — send as `application/json` (or `multipart/form-data`; both are accepted).
The submit button on this screen should read **"Next"**, not "Submit" — the application isn't
submitted yet.

**Fields to collect** (all required):

| Field                  | Type        | Notes                                    |
|------------------------|-------------|------------------------------------------|
| `first_name`           | text        |                                          |
| `last_name`            | text        |                                          |
| `email`                | email       | validated by the server                  |
| `phone`                | text        | **must start with `+` and a country code** — 8–15 digits; spaces, hyphens and brackets are fine. A local `07…` number is rejected, because it cannot be dialled from abroad |
| `nationality`          | text        | **dropdown** — one of `countries` from `GET /config/`; anything else is a 400 |
| `country_of_residence` | text        | **dropdown**, same list. Free text produced three spellings of Tanzania in one export, and the panel's Tanzania-based floor matches on the stored string |
| `gender`               | text        | use a dropdown on your side              |
| `institution`          | text        |                                          |
| `institution_type`     | text        | e.g. University / NGO / Government        |
| `role`                 | text        |                                          |
| `education`            | text        | e.g. BSc / MSc / PhD                      |
| `r_experience`         | text        | self-rated, e.g. Beginner/Intermediate   |
| `bayesian_knowledge`   | text        | self-rated                               |

> **Do not put the written answers or `cv` on this form.** The endpoint ignores them entirely —
> they belong to [Step 6](#step-6--final-submission-their-own-work--cv).

**Example:**

```js
const res = await fetch(`${API}/applications/`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ first_name: "Ada", last_name: "Lovelace", email: "ada@example.org", /* … */ }),
});

if (res.status === 201) {
  const app = await res.json();
  const applicationId = app.id;   // <-- save this; you need it through Step 6
}
```

**Success:** `201 Created` with the application JSON (`id`, `created_at`, and the staff-review fields
`decision` (defaults to `"PENDING"`) and `decision_at` (`null`) — the applicant UI can ignore those
two). The written answers and `cv` are **not** in this response; they don't exist yet.

**Validation errors:** `400 Bad Request` with a field→messages map:

```json
{ "email": ["Enter a valid email address."] }
```

---

### Step 2 — Eligibility

`POST /api/applications/{application_id}/eligibility/` — JSON, all four required:

| Field | Options |
|-------|---------|
| `elig_attend` | `Yes, all four days` · `Only part of the period` · `No` |
| `elig_laptop` | `Yes` · `No` · `I am not sure` |
| `elig_data` | `Yes, I work with it now` · `Not yet, but I expect to within six months` · `No` |
| `elig_funding` | `My institution has agreed to cover it` · `I will cover it myself` · `Likely covered, but not yet confirmed` · `I could not attend without financial support` |

Send the option strings **exactly**; anything else is a `400` on that field.

```json
{ "eligible": false, "reason": "We have no funding for participant travel …" }
```

**`eligible: false` ends the journey** — show `reason` and stop. The answer is stored, every later
step returns 403, and `/status/` reports `ineligible_reason` so a reload doesn't resurrect them.
Which answers rule someone out is a server-side rule (`assessment.eligibility_problem`), not
something to reimplement in the client.

---

### Step 3 — Experience and plans

`POST /api/applications/{application_id}/experience/` — JSON, all eight required:
`exp_rfreq`, `exp_rself`, `exp_bayes`, `exp_glm`, `exp_dtype`, `exp_when`, `exp_share`, `exp_use`.
Options are listed in `assessment.EXPERIENCE_QUESTIONS`; again, send the strings exactly.
Returns `{"saved": true}`.

---

### Step 4 — Honesty check

`GET /api/applications/{application_id}/claims/` → `{"functions": ["st_read", "raster_scale2", …]}`

Render one row per name with three choices: `used`, `heard`, `no`. **Some of the names are
invented** — that is what the step measures — but the API never says which, so nothing in the page
source gives it away.

`POST` back `{"claims": {"st_read": "used", "raster_scale2": "no", …}}`, covering **every** name
returned by the GET; a partial map is a `400`. The response is just `{"saved": true}` — deliberately
no feedback about which were fake, so answers can't circulate.

---

### Step 5 — Start the quiz

`POST /api/applications/{application_id}/quiz/start/` — no body needed.
Returns **403** if the applicant was ruled out at Step 2.

**Success:** `201 Created` with the first question:

```json
{
  "session": "90adba6d-7418-452a-9b44-1298ff409270",
  "position": 0,
  "total": 14,
  "question": {
    "id": 5,
    "text": "A data frame d has 100 rows and two columns: district (10 unique values) and cases. How many rows does the result have?",
    "code": "d %>% group_by(district) %>% mutate(total = sum(cases))",
    "category": "R",
    "options": ["110", "100", "1", "10"],
    "time_limit_seconds": 25
  },
  "time_limit_seconds": 25,
  "deadline": "2026-07-28T12:10:29.840351Z"
}
```

Save `session` → that is your `session_id`. (`time_limit_seconds` appears both at the top level and
inside `question` — same value, provided in both places for convenience.)

> **The quiz can only be started once per applicant.** Calling this twice returns `400`
> `"A quiz session already exists for this application."` Don't offer a "restart" button — the
> backend forbids it (it would hand out a fresh timer).

---

### Step 5 (continued) — The timer, and answering questions

**The clock is server-authoritative.** Every question payload carries **`remaining_seconds`** — how
much time is actually left, computed server-side and clamped to `0 … time_limit_seconds`. Count down
from that.

```js
// Amount of time from the server; ticking from performance.now(), which is monotonic.
const total = payload.remaining_seconds;            // already clamped to the limit
const startedAt = performance.now();
const left = () => Math.max(0, total - (performance.now() - startedAt) / 1000);
```

> **Do not compute the remainder from `deadline` and `Date.now()`.** That makes the applicant's device
> clock part of the grading, and it fails silently in both directions: a phone a few minutes **fast**
> reports a negative remainder on the first tick, so the page auto-submits a blank answer for every
> question and the applicant scores zero with nothing on screen to explain it; a phone a few minutes
> **slow** shows a long countdown and then has every answer discarded as late. `deadline` is still in
> the payload for debugging and for older clients, but `remaining_seconds` is the field to render.

Use a **monotonic** source for the ticking too (`performance.now()`, not `Date.now()`): it is
unaffected by the system clock being corrected mid-question, and it stays accurate after a background
tab has had its timers throttled or the laptop has slept — both of which are common on a phone.

- The `question` object **never** contains the correct answer — don't look for it.
- Re-fetching the current question does **not** reset the timer (safe on page reload) — the
  `remaining_seconds` you get back is simply smaller.
- Show `position + 1` of `total` as progress ("Question 1 of 14").
- **`options` are shuffled per applicant** and frozen for the session. Render them in the order you
  receive them and submit the option *string* — never an index or letter, which mean nothing
  server-side.
- **`code`** is an optional snippet (often R) to show under the question text. Render it in a
  monospaced block with whitespace preserved, using `textContent` rather than `innerHTML`. It is
  `""` for most questions.
- **`time_limit_seconds` is per question** (25s for every question in the current bank) — read it
  rather than hard-coding, since a single long question can be given more room.

**When the clock reaches zero, submit whatever is selected — including nothing.**
`{"answer": ""}` (or omitting the field) is a valid request: the server records the question as
unanswered, and the response carries the **next** question with its own fresh clock, so the applicant
moves on. Give that automatic submission a **retry and then a resync** (`GET /quiz/{id}/current/`) if
the request fails: a single dropped POST at the moment the clock hits zero would otherwise leave the
applicant on a dead screen with a stopped timer, and the quiz cannot be restarted.

A manual submit is different — there is still time on the clock, so surface the error and let them
press the button again rather than spending their remaining seconds on retries.

`POST /api/quiz/{session_id}/answer/` — send JSON:

```js
const res = await fetch(`${API}/quiz/${sessionId}/answer/`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ answer: selectedOptionString }),  // an option string, or "" for no answer
});
const data = await res.json();
```

**Response:**

```json
{
  "timed_out": false,
  "accepted": true,
  "finished": false,
  "next": { "session": "…", "position": 1, "total": 14, "question": { … },
            "remaining_seconds": 25.0, "time_limit_seconds": 25, "deadline": "…" },
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

### Step 5 (continued) — Show the result

`GET /api/quiz/{session_id}/result/` (the same object also arrives as `result` on the final answer):

```json
{
  "id": "90adba6d-…",
  "application": "f9ce179f-…",
  "score": 9,
  "total": 14,
  "completed_at": "2026-07-28T12:10:29.840Z",
  "passed": true,
  "pass_mark": 8,
  "final_submitted": false
}
```

- `completed_at` is `null` if the quiz isn't finished yet.
- **`passed`** — `true` once the quiz is complete with `score >= pass_mark`. This is what unlocks
  Step 5. Read the flag; don't hard-code `7` in the frontend.
- **`final_submitted`** — `true` once Step 5 has been completed, so a reload doesn't offer the form
  again.
- `application` is the applicant's id — handy for Step 5 if you lost it.

Drive the results screen from these:

```js
const unlocked = result.passed && !result.final_submitted;
// unlocked -> show a "Continue to final step" button
// !result.passed -> "A score of at least ${result.pass_mark} is needed to continue." and stop here
```

---

### Step 6 — Final submission (their own work + CV)

`POST /api/applications/{application_id}/finalize/` — send as `multipart/form-data`.

| Field                 | Type     | Notes                                        |
|-----------------------|----------|----------------------------------------------|
| `written_dataset`     | textarea | required — a dataset they analysed (≥25 chars) |
| `written_code`        | textarea | required — 5–15 lines of their own R, or `none` |
| `written_why_not_ols` | textarea | required — why OLS would be a poor choice (≥15 chars) |
| `written_other`       | textarea | optional                                     |
| `motivation`          | textarea | required (max 300 words)                     |
| `expectations`        | textarea | required (max 300 words)                     |
| `cv`                  | **file** | required — **PDF only** (max 2 pages, 5MB)   |

```js
const form = new FormData();
form.append("written_dataset", datasetEl.value);
form.append("written_code", codeEl.value);
form.append("written_why_not_ols", whyEl.value);
form.append("written_other", otherEl.value);
form.append("cv", fileInput.files[0]);

const res = await fetch(`${API}/applications/${applicationId}/finalize/`, {
  method: "POST",
  body: form,   // do NOT set Content-Type — the browser sets the multipart boundary
});
```

Render `written_code` in a monospaced textarea — it is code, and staff read it as such. Whether real
code was supplied is machine-checked and feeds both the composite score and the `NO-CODE` flag, so
`none` is an honest answer rather than a disqualifying one.

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Submitted. Body: `{ id, submitted_at, …the written fields…, cv }`. Show the "application submitted" screen and clear the saved id. |
| `403` | The quiz isn't finished, or the score is below the pass mark. `{"detail": "…"}` |
| `400` | Validation errors (field→messages), or `{"detail": "This application has already been submitted."}` |
| `404` | Unknown `application_id` — clear stored state and send them back to Step 1. |

> **One submission only.** There is no edit/resubmit endpoint; a second `POST` returns `400`.

---

### Resuming after a reload

Persist only `application_id` in `localStorage` — and **validate it with the server before
resuming**, or a deleted/stale record leaves the user stranded on a screen they can't get out of.

`GET /api/applications/{application_id}/status/`:

```json
{
  "id": "f9ce179f-…",
  "final_submitted": false,
  "ineligible_reason": "",
  "completed": { "eligibility": true, "experience": true, "claims": false },
  "quiz": null
}
```

`completed` says which steps are already answered, so a reload picks up where the applicant left off
instead of asking everything again. `quiz` is `null` until the check is started, and carries the
session id once it is. A **`404` means the stored id is stale** — clear it and start over at Step 1.
The shipped `applicant.js` boots like this:

```
no application_id            -> details form
GET /status/ 404             -> clear state, details form
ineligible_reason            -> "thank you for your interest" screen
final_submitted              -> "submitted" screen
quiz.completed_at            -> results screen (which may unlock Step 6)
quiz in progress             -> GET /quiz/{id}/current/ and render the current question
otherwise                    -> first step in `completed` that is still false
```

---

## 3. Suggested applicant-portal screens

A step rail across the top (`1. Details … 7. Submit`) with the current step highlighted and completed
ones marked — the shipped portal renders it from one `STEPS` array in `applicant.js`.

1. **Details** → Step 1. Button reads **"Continue"**. On success store `application_id`.
2. **Eligibility** → Step 2. If the response says `eligible: false`, replace the whole card with the
   reason and clear the step rail — do not offer a way onwards.
3. **Experience** → Step 3, grouped under three subheadings.
4. **Honesty check** → Step 4, one row per function with three radios.
5. **Quiz intro then questions** → Step 5. One question, countdown, shuffled options, auto-advance.
6. **Results** → shows the score. If `passed && !final_submitted`, offer "Continue to your own work";
   otherwise the journey ends here.
7. **Your work** → the written answers + CV form. The button says **"Submit application"** → Step 6,
   then the confirmation screen.

### Styling

The shipped pages use no CSS framework — one stylesheet, `static/css/styles.css`, holding the
Malaria Atlas Project tile as custom properties (`--gold #EBBC40`, `--black #111010`, `--charcoal`,
`--warm`, `--light`), Lato for headings and Nunito Sans for body text. Reuse those variables rather
than hard-coding hex values, and note the comment at the top: `--warm #9E9C97` fails contrast for
body text, so it is used only for rules, borders and dividers.

Persist in `localStorage`: `application_id`, `session_id` — validate them via `/status/` on load
(see [Resuming after a reload](#resuming-after-a-reload)).

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

**Who am I** — `GET /api/admin/me/` → `{ username, email, is_superuser, role, can_review, can_export }`
(validate a saved token on load). The same object is returned as `user` by login.

- **`role`** is `"reviewer"` or `"viewer"`. A **viewer** is a staff account restricted to reading:
  applicant counts, the list, details, CV downloads and quiz breakdowns.
- **`can_review`** — false for viewers. Use it to hide the decision buttons, delete button, bulk
  toolbar and row checkboxes.
- **`can_export`** — false for viewers; hide the CSV export button.

> Treat these as *display* hints only. Every write endpoint plus `/export/` re-checks server-side and
> returns **403** `{"detail": "Your account has view-only access to applicants."}`, so a viewer who
> crafts the request by hand still gets nowhere.

**Logout** — `POST /api/admin/logout/` → `204`, invalidates the current token.

**List applicants** — `GET /api/admin/applications/` (paginated, 25/page):
```
?search=<text>   filter by first/last name, email, or institution
?status=<value>  pass | fail | pending  (400 on anything else)
?page=<n>        page number
```
```json
{
  "count": 42, "next": "…?page=2", "previous": null,
  "results": [
    { "id": "…", "first_name": "Ada", "last_name": "Lovelace", "email": "…",
      "institution": "…", "country_of_residence": "…", "created_at": "…",
      "status": "PASS", "decision": "PENDING", "quiz_status": "completed",
      "score": 12, "total": 14 }
  ]
}
```
- **`status`** is the knowledge-check outcome: `"PASS"` (score ≥ pass mark), `"FAIL"` (finished
  below it), or `"PENDING"` (quiz not finished). Derived from the score server-side — read-only, and
  there is no endpoint to set it.
- `decision` is one of `"PENDING" | "SELECTED" | "REJECTED"` — the **staff's** review outcome, and a
  separate thing from `status`. Show both; don't conflate them.
- `quiz_status` is one of `"not_started" | "in_progress" | "completed"`. `score`/`total` are `null`
  until a quiz exists.

**Export CSV** — `GET /api/admin/applications/export/` — **reviewers only** (403 for viewers).

Takes the *same* `?search=` and `?status=` params as the list, so the download contains exactly the
filtered rows. Responds with `text/csv` and a `Content-Disposition` filename
(`applicants-<YYYYMMDD-HHMM>.csv`), 27 columns including contact details, status, score, decision and
an absolute CV URL.

A plain `<a href>` **cannot** download it — the link carries no `Authorization` header. Fetch it and
hand the browser a blob:

```js
const res = await fetch(`${API}/admin/applications/export/?status=pass`, {
  headers: { Authorization: `Token ${token}` },
});
const url = URL.createObjectURL(await res.blob());
const a = Object.assign(document.createElement("a"), { href: url, download: "applicants.csv" });
a.click();
URL.revokeObjectURL(url);
```

> Values that begin with `=`, `+`, `-` or `@` are prefixed with `'` in the file. Applicants write the
> motivation and expectations fields themselves, and spreadsheets execute cells starting with those
> characters — the prefix keeps the text readable and inert. The file also carries a UTF-8 BOM so
> Excel renders accented names correctly.

**Applicant detail** — `GET /api/admin/applications/{id}/` → all profile fields + an absolute `cv`
URL + `status`, `pass_mark`, `decision`, `decision_at`, `final_submitted_at`, and quiz summary
(`quiz_status`, `score`, `total`, `completed_at`).

> Applicants with `status: "FAIL"` never reach the final step, so their `cv` is `null` and
> `motivation`/`expectations` are empty, with `final_submitted_at: null`. Handle that in the UI —
> the shipped panel hides the "Download CV" link and shows "Not submitted".

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
  "session": "…", "score": 12, "total": 14, "completed_at": "…",
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
2. **Applicants table** → `GET /admin/applications/` with search (`?search=`), a **status filter**
   (`?status=pass|fail|pending`) and pagination. Add row checkboxes + a bulk toolbar (Mark selected /
   Mark rejected / Reset to pending / Delete) wired to `POST /admin/applications/bulk/`. Show
   `status` and `decision` as two separate colored badges.
3. **Applicant detail** → `GET /admin/applications/{id}/` (fields + "Download CV" link).
   Show the `status` badge with `score`/`total` and `pass_mark` next to it, so the outcome is
   self-explanatory. Add Select / Reject / Pending buttons (`PATCH`) and a Delete button (`DELETE`).
4. **Quiz breakdown** (tab on the detail page) → `GET /admin/applications/{id}/quiz/`.
5. **Shortlist** → `POST /admin/shortlist/` with the floors, then `POST /admin/shortlist/export/`.

### The shortlist builder

`GET`/`POST /api/admin/shortlist/` — ranks every application on the composite (recomputed
server-side from the stored answers) and allocates seats. Body, all optional:

| Field | Default | Meaning |
|---|---|---|
| `seats` | `25` | how many places there are |
| `min_women` | `10` | floor, filled before the open seats |
| `min_tanzania` | `12` | floor, matched on the stored country string |
| `max_per_institution` | `3` | cap, applied to the seats (not to the waitlist) |
| `waitlist` | `10` | how many reserves to mark |
| `travel` | `"prefer"` | `prefer` \| `only` \| `ignore` — see the main README |
| `drop_bluff` | `true` | exclude applicants who claimed an invented function |
| `pool` | `"submitted"` | `submitted` \| `scored` \| `all` |

Returns `{settings, floors, stats, rows}`. Every row carries `rank`, `shortlisted`, `waitlisted`, the
score components and the `flags`; **render the whole ranking with the picks marked**, not just the
picks — the applications a human most needs to read are the ones either side of the cut line.

`floors` is what the status pills show (`women` / `women_required` / `women_met`, the same for
Tanzania-based, plus `travel_unconfirmed`, `largest_institution` and the shortlist's median score). An
unmeetable floor comes back `*_met: false` rather than being quietly fudged — show it in red.

`stats.advice` is a sentence worth displaying verbatim: it warns when the median applicant is near the
ceiling of the knowledge check, which means the questions have stopped discriminating and the ranking
is being driven by the other components.

`POST /api/admin/shortlist/export/` takes the same body plus `only_shortlist` and streams a CSV whose
first three columns are `Rank`, `Shortlisted`, `Waitlisted`. **Reviewers only** (403 for viewers,
who can still build a shortlist — it computes a ranking and records nothing).

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
| GET    | `/api/config/`                                | —                      | —               | Deadline, limits, countries, quiz shape |
| POST   | `/api/applications/`                          | JSON (details only)    | —               | Create applicant — no CV/free text |
| GET    | `/api/applications/{id}/status/`              | —                      | —               | Resume state (404 = stale id)     |
| POST   | `/api/applications/{id}/eligibility/`         | JSON (4 answers)       | —               | Step 2 — may end the journey      |
| POST   | `/api/applications/{id}/experience/`          | JSON (8 answers)       | —               | Step 3 — experience and plans     |
| GET    | `/api/applications/{id}/claims/`              | —                      | —               | Step 4 — honesty-check names      |
| POST   | `/api/applications/{id}/claims/`              | `{"claims": {…}}`      | —               | Step 4 — their answers            |
| POST   | `/api/applications/{id}/quiz/start/`          | —                      | —               | Start quiz, get question #1       |
| GET    | `/api/quiz/{session}/current/`                | —                      | —               | Current question (or result)      |
| POST   | `/api/quiz/{session}/answer/`                 | `{"answer": ""}`       | —               | Submit answer, get next question  |
| GET    | `/api/quiz/{session}/result/`                 | —                      | —               | Final score + `passed`/`pass_mark` |
| POST   | `/api/applications/{id}/finalize/`            | multipart form         | —               | Final submit: motivation, expectations, CV (403 if not passed) |
| POST   | `/api/admin/login/`                           | `{username,password}`  | —               | Staff login → token               |
| POST   | `/api/admin/logout/`                          | —                      | Token           | Invalidate token                  |
| GET    | `/api/admin/me/`                              | —                      | Token           | Current staff user                |
| GET    | `/api/admin/applications/`                    | —                      | Token           | List applicants (`?search=`,`?status=`,`?page=`) |
| GET    | `/api/admin/applications/export/`             | —                      | Token (reviewer) | CSV of the filtered applicants    |
| POST   | `/api/admin/applications/bulk/`               | `{ids,action}`         | Token           | Bulk select/reject/pending/delete |
| GET    | `/api/admin/applications/{id}/`               | —                      | Token           | Applicant detail + CV + decision  |
| PATCH  | `/api/admin/applications/{id}/`               | `{"decision": ""}`     | Token           | Set decision                      |
| DELETE | `/api/admin/applications/{id}/`               | —                      | Token           | Delete applicant                  |
| GET    | `/api/admin/applications/{id}/quiz/`          | —                      | Token           | Per-question breakdown            |
| GET/POST | `/api/admin/shortlist/`                     | JSON (floors)          | Token           | Ranking + seat allocation         |
| POST   | `/api/admin/shortlist/export/`                | JSON (floors)          | Token (reviewer) | CSV with Rank/Shortlisted/Waitlisted |

Admin endpoints require the `Authorization: Token <token>` header — see [section 4](#4-the-custom-admin-panel).
