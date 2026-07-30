// Custom admin panel (README section 4). Token auth; token lives in
// sessionStorage (not localStorage) to reduce XSS exposure.
const TOKEN = {
  get()   { return sessionStorage.getItem("admin_token"); },
  set(v)  { v ? sessionStorage.setItem("admin_token", v) : sessionStorage.removeItem("admin_token"); },
};

const views = {
  login:  document.getElementById("view-login"),
  list:   document.getElementById("view-list"),
  detail: document.getElementById("view-detail"),
};
const navUser = document.getElementById("nav-user");

function showView(name) {
  Object.entries(views).forEach(([k, el]) => el.classList.toggle("d-none", k !== name));
  navUser.classList.toggle("d-none", name === "login");
}

// Any admin call that 401s means the token is bad -> back to login.
async function adminCall(method, path, body) {
  try {
    return await apiJson(method, path, body, TOKEN.get());
  } catch (err) {
    if (err.status === 401) { TOKEN.set(null); showView("login"); }
    throw err;
  }
}

// ------------------------------------------------------------------ Login
const loginForm = document.getElementById("login-form");
const loginAlert = document.getElementById("login-alert");

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginAlert.classList.add("d-none");
  const btn = document.getElementById("login-btn");
  btn.disabled = true;
  const fd = new FormData(loginForm);
  try {
    const data = await apiJson("POST", "/admin/login/", {
      username: fd.get("username"),
      password: fd.get("password"),
    });
    TOKEN.set(data.token);
    setNavUser(data.user);
    loginForm.reset();
    loadList();
  } catch (err) {
    loginAlert.textContent = (err.data && err.data.detail) || "Sign in failed.";
    loginAlert.classList.remove("d-none");
  } finally {
    btn.disabled = false;
  }
});

function setNavUser(user) {
  document.getElementById("nav-username").textContent =
    user.username + (user.is_superuser ? " (superuser)" : "");
}

document.getElementById("logout-btn").addEventListener("click", async () => {
  try { await adminCall("POST", "/admin/logout/"); } catch { /* ignore */ }
  TOKEN.set(null);
  showView("login");
});

// ------------------------------------------------------------------ List
let currentPage = 1;
let currentSearch = "";
let pageState = { next: null, previous: null, count: 0 };

const searchInput = document.getElementById("search-input");
const applicantsBody = document.getElementById("applicants-body");

const QUIZ_BADGE = {
  not_started: '<span class="badge bg-secondary">Not started</span>',
  in_progress: '<span class="badge bg-warning text-dark">In progress</span>',
  completed:   '<span class="badge bg-success">Completed</span>',
};

async function loadList() {
  showView("list");
  applicantsBody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">Loading…</td></tr>`;
  const params = new URLSearchParams();
  if (currentSearch) params.set("search", currentSearch);
  if (currentPage > 1) params.set("page", currentPage);
  const qs = params.toString() ? `?${params}` : "";
  try {
    const data = await adminCall("GET", `/admin/applications/${qs}`);
    pageState = { next: data.next, previous: data.previous, count: data.count };
    renderList(data.results);
    updatePager();
  } catch (err) {
    if (err.status !== 401) {
      applicantsBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">Failed to load applicants.</td></tr>`;
    }
  }
}

function renderList(rows) {
  if (!rows.length) {
    applicantsBody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No applicants found.</td></tr>`;
    return;
  }
  applicantsBody.innerHTML = "";
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.className = "cursor-pointer";
    const score = r.score != null ? `${r.score} / ${r.total}` : "—";
    tr.innerHTML = `
      <td class="fw-semibold">${esc(r.first_name)} ${esc(r.last_name)}</td>
      <td>${esc(r.email)}</td>
      <td>${esc(r.institution || "")}</td>
      <td>${esc(r.country_of_residence || "")}</td>
      <td>${QUIZ_BADGE[r.quiz_status] || esc(r.quiz_status)}</td>
      <td class="text-center">${score}</td>
      <td class="text-end"><i class="bi bi-chevron-right text-muted"></i></td>`;
    tr.addEventListener("click", () => loadDetail(r.id));
    applicantsBody.appendChild(tr);
  });
}

function updatePager() {
  document.getElementById("list-count").textContent = `${pageState.count} applicant(s)`;
  document.getElementById("prev-page").disabled = !pageState.previous;
  document.getElementById("next-page").disabled = !pageState.next;
}

document.getElementById("prev-page").addEventListener("click", () => { currentPage--; loadList(); });
document.getElementById("next-page").addEventListener("click", () => { currentPage++; loadList(); });

// Debounced search
let searchTimer = null;
searchInput.addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentSearch = e.target.value.trim();
    currentPage = 1;
    loadList();
  }, 300);
});

// ------------------------------------------------------------------ Detail
const FIELD_LABELS = {
  phone: "Phone", nationality: "Nationality", country_of_residence: "Country of residence",
  gender: "Gender", institution: "Institution", institution_type: "Institution type",
  role: "Role", education: "Education", r_experience: "R experience",
  bayesian_knowledge: "Bayesian knowledge", motivation: "Motivation",
  expectations: "Expectations", created_at: "Applied at",
};

async function loadDetail(id) {
  showView("detail");
  switchTab("profile");
  document.getElementById("d-fields").innerHTML = `<p class="text-muted">Loading…</p>`;
  document.getElementById("quiz-body").innerHTML = "";
  document.getElementById("quiz-summary").innerHTML = "";
  try {
    const a = await adminCall("GET", `/admin/applications/${id}/`);
    renderDetail(a);
    loadQuizBreakdown(id);
  } catch (err) {
    if (err.status !== 401) {
      document.getElementById("d-fields").innerHTML = `<p class="text-danger">Failed to load applicant.</p>`;
    }
  }
}

function renderDetail(a) {
  document.getElementById("d-name").textContent = `${a.first_name} ${a.last_name}`;
  document.getElementById("d-email").textContent = a.email;

  const cv = document.getElementById("d-cv");
  if (a.cv) { cv.href = a.cv; cv.classList.remove("d-none"); }
  else { cv.classList.add("d-none"); }

  const dl = document.getElementById("d-fields");
  dl.innerHTML = "";
  Object.entries(FIELD_LABELS).forEach(([key, label]) => {
    if (!(key in a)) return;
    let val = a[key];
    if (key === "created_at" && val) val = new Date(val).toLocaleString();
    dl.insertAdjacentHTML("beforeend",
      `<dt class="col-sm-3 text-muted">${label}</dt>
       <dd class="col-sm-9">${val ? esc(String(val)) : "<span class='text-muted'>—</span>"}</dd>`);
  });
}

async function loadQuizBreakdown(id) {
  const summary = document.getElementById("quiz-summary");
  const body = document.getElementById("quiz-body");
  try {
    const q = await adminCall("GET", `/admin/applications/${id}/quiz/`);
    summary.innerHTML = `
      <div class="alert alert-info d-flex justify-content-between mb-0">
        <span><strong>Score:</strong> ${q.score} / ${q.total}</span>
        <span>${q.completed_at ? "Completed " + new Date(q.completed_at).toLocaleString() : "Not completed"}</span>
      </div>`;
    body.innerHTML = "";
    q.questions.forEach((item) => {
      const result = item.timed_out
        ? '<span class="badge bg-secondary">Timed out</span>'
        : item.is_correct
          ? '<span class="badge bg-success"><i class="bi bi-check-lg"></i></span>'
          : '<span class="badge bg-danger"><i class="bi bi-x-lg"></i></span>';
      body.insertAdjacentHTML("beforeend", `
        <tr>
          <td>${item.position + 1}</td>
          <td>${esc(item.question_text)}</td>
          <td><span class="badge bg-light text-dark border category-pill">${esc((item.category || "").toLowerCase())}</span></td>
          <td>${item.submitted_answer ? esc(item.submitted_answer) : "<span class='text-muted'>—</span>"}</td>
          <td>${esc(item.correct_answer)}</td>
          <td class="text-center">${result}</td>
        </tr>`);
    });
  } catch (err) {
    if (err.status === 404) {
      summary.innerHTML = `<div class="alert alert-secondary mb-0">This applicant has not started the quiz.</div>`;
    } else if (err.status !== 401) {
      summary.innerHTML = `<div class="alert alert-danger mb-0">Failed to load quiz breakdown.</div>`;
    }
  }
}

// Tabs
document.querySelectorAll("[data-tab]").forEach((btn) =>
  btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

function switchTab(name) {
  document.querySelectorAll("[data-tab]").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  document.getElementById("tab-profile").classList.toggle("d-none", name !== "profile");
  document.getElementById("tab-quiz").classList.toggle("d-none", name !== "quiz");
}

document.getElementById("back-to-list").addEventListener("click", () => loadList());

// ------------------------------------------------------------------ Helpers
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ------------------------------------------------------------------ Boot
(async function boot() {
  if (!TOKEN.get()) { showView("login"); return; }
  // Validate the saved token before showing anything staff-only.
  try {
    const user = await apiJson("GET", "/admin/me/", undefined, TOKEN.get());
    setNavUser(user);
    loadList();
  } catch {
    TOKEN.set(null);
    showView("login");
  }
})();
