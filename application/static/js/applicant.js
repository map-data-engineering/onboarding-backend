// Applicant journey state machine (README section 2).
// Persisted state lets us resume a quiz across reloads / tab close.
const LS = {
  get appId()  { return localStorage.getItem("application_id"); },
  set appId(v) { v ? localStorage.setItem("application_id", v) : localStorage.removeItem("application_id"); },
  get sessId() { return localStorage.getItem("session_id"); },
  set sessId(v){ v ? localStorage.setItem("session_id", v) : localStorage.removeItem("session_id"); },
};

const screens = {
  form:     document.getElementById("screen-form"),
  intro:    document.getElementById("screen-intro"),
  question: document.getElementById("screen-question"),
  result:   document.getElementById("screen-result"),
  final:    document.getElementById("screen-final"),
  done:     document.getElementById("screen-done"),
};

function showScreen(name) {
  Object.entries(screens).forEach(([k, el]) => el.classList.toggle("d-none", k !== name));
  // "done" has no badge of its own -- keep the final step lit.
  const active = name === "done" ? "final" : name;
  document.querySelectorAll("#steps [data-step]").forEach((b) => {
    b.classList.toggle("bg-primary", b.dataset.step === active);
    b.classList.toggle("bg-secondary", b.dataset.step !== active);
  });
}

// ---------------------------------------------------------------- Step 1: details
const form = document.getElementById("application-form");
const formAlert = document.getElementById("form-alert");
const finalAlert = document.getElementById("final-alert");

function clearFieldErrors() {
  document.querySelectorAll("[data-error]").forEach((el) => (el.textContent = ""));
  formAlert.classList.add("d-none");
  finalAlert.classList.add("d-none");
}

function renderFieldErrors(data, alertBox) {
  // data is a { field: [messages] } map (or {detail: "..."}).
  const box = alertBox || formAlert;
  const fail = (text) => { box.textContent = text; box.classList.remove("d-none"); };
  if (data && typeof data === "object" && !Array.isArray(data)) {
    let handledAny = false;
    Object.entries(data).forEach(([field, msgs]) => {
      const target = document.querySelector(`[data-error="${field}"]`);
      const text = Array.isArray(msgs) ? msgs.join(" ") : String(msgs);
      if (target) { target.textContent = text; handledAny = true; }
      else if (field === "detail") { fail(text); handledAny = true; }
    });
    if (!handledAny) fail(JSON.stringify(data));
  } else {
    fail("Something went wrong submitting your application.");
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFieldErrors();
  const btn = document.getElementById("submit-application");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving…`;
  try {
    const app = await apiForm("POST", "/applications/", new FormData(form));
    LS.appId = app.id;
    LS.sessId = null;
    showScreen("intro");
  } catch (err) {
    renderFieldErrors(err.data, formAlert);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `Next <i class="bi bi-arrow-right"></i>`;
  }
});

// ---------------------------------------------------------------- Step 2: start
const introAlert = document.getElementById("intro-alert");
document.getElementById("start-quiz").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  introAlert.classList.add("d-none");
  try {
    const q = await apiJson("POST", `/applications/${LS.appId}/quiz/start/`);
    LS.sessId = q.session;
    renderQuestion(q);
  } catch (err) {
    if (err.status === 404) {
      // The stored application no longer exists -- send them back to the form.
      resetJourney();
      showScreen("form");
      formAlert.textContent = "We couldn't find your application. Please fill in your details again.";
      formAlert.classList.remove("d-none");
      return;
    }
    // e.g. "A quiz session already exists" -> try to resume instead.
    const msg = err.data && (err.data.detail || JSON.stringify(err.data));
    introAlert.textContent = msg || "Could not start the quiz.";
    introAlert.classList.remove("d-none");
  } finally {
    btn.disabled = false;
  }
});

// -------------------------------------------------------- Step 3: question loop
let countdownTimer = null;
let selectedAnswer = null;
let currentDeadline = null;

const els = {
  progress:    document.getElementById("q-progress"),
  progressbar: document.getElementById("q-progressbar"),
  category:    document.getElementById("q-category"),
  countdown:   document.getElementById("q-countdown"),
  text:        document.getElementById("q-text"),
  options:     document.getElementById("q-options"),
  submit:      document.getElementById("submit-answer"),
  status:      document.getElementById("q-status"),
};

function stopCountdown() {
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
}

// Server-authoritative countdown: we tick against the ISO `deadline`, not a
// local timer we started -- the two would drift.
function startCountdown(deadlineIso) {
  stopCountdown();
  currentDeadline = new Date(deadlineIso).getTime();
  const tick = () => {
    const remaining = Math.max(0, Math.round((currentDeadline - Date.now()) / 1000));
    els.countdown.textContent = `${remaining}s`;
    els.countdown.classList.toggle("danger", remaining <= 5);
    if (remaining <= 0) {
      stopCountdown();
      els.status.textContent = "Time's up — submitting…";
      submitAnswer(true); // auto-submit; server will mark it timed_out
    }
  };
  tick();
  countdownTimer = setInterval(tick, 250);
}

function renderQuestion(payload) {
  showScreen("question");
  selectedAnswer = null;
  els.submit.disabled = true;
  els.status.textContent = "";

  const q = payload.question;
  const shown = payload.position + 1;
  els.progress.textContent = `Question ${shown} of ${payload.total}`;
  els.progressbar.style.width = `${(shown / payload.total) * 100}%`;
  els.category.textContent = (q.category || "").toLowerCase();
  els.text.textContent = q.text;

  els.options.innerHTML = "";
  q.options.forEach((opt) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn btn-outline-secondary quiz-option";
    b.textContent = opt;
    b.addEventListener("click", () => {
      selectedAnswer = opt;
      els.options.querySelectorAll(".quiz-option").forEach((o) => o.classList.remove("active"));
      b.classList.add("active");
      els.submit.disabled = false;
    });
    els.options.appendChild(b);
  });

  startCountdown(payload.deadline);
}

els.submit.addEventListener("click", () => submitAnswer(false));

let submitting = false;
async function submitAnswer(auto) {
  if (submitting) return;
  submitting = true;
  stopCountdown();
  els.submit.disabled = true;

  // On a manual submit we send the chosen option; on a timeout we send whatever
  // was selected (or empty) -- the server decides it timed out regardless.
  const answer = selectedAnswer || "";
  try {
    const res = await apiJson("POST", `/quiz/${LS.sessId}/answer/`, { answer });
    if (res.finished) {
      showResult(res.result);
    } else {
      renderQuestion(res.next);
    }
  } catch (err) {
    els.status.textContent = "Could not submit answer. Retrying is disabled to protect the timer.";
    console.error(err);
  } finally {
    submitting = false;
  }
}

// ---------------------------------------------------------------- Step 4: result
function showResult(result) {
  stopCountdown();
  showScreen("result");
  document.getElementById("r-score").textContent = result.score;
  document.getElementById("r-total").textContent = result.total;

  const icon = document.getElementById("r-icon");
  const message = document.getElementById("r-message");
  const continueWrap = document.getElementById("r-continue-wrap");

  // Only applicants at or above the pass mark get to finish the application.
  const unlocked = result.passed && !result.final_submitted;
  continueWrap.classList.toggle("d-none", !unlocked);

  if (result.final_submitted) {
    message.textContent = "Your application has already been submitted.";
  } else if (result.passed) {
    message.textContent =
      "You've met the required score. One last step: your motivation, expectations and CV.";
  } else {
    icon.className = "bi bi-info-circle-fill text-secondary";
    message.textContent =
      `A score of at least ${result.pass_mark} is needed to continue. ` +
      `Thank you for your interest.`;
  }

  document.getElementById("r-completed").textContent = result.completed_at
    ? `Completed ${new Date(result.completed_at).toLocaleString()}`
    : "";

  // Keep the resume state while the final step is still open (a reload re-fetches
  // /current/, which returns this same result payload). Otherwise the journey is
  // over -- clear it so a reload starts fresh.
  if (unlocked) {
    if (result.application) LS.appId = result.application;
    if (result.id) LS.sessId = result.id;
  } else {
    LS.sessId = null;
    LS.appId = null;
  }
}

// ------------------------------------------------- Step 5: final submission
document.getElementById("go-final").addEventListener("click", () => {
  clearFieldErrors();
  showScreen("final");
});

const finalForm = document.getElementById("final-form");
finalForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFieldErrors();
  const btn = document.getElementById("submit-final");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Submitting…`;
  try {
    await apiForm("POST", `/applications/${LS.appId}/finalize/`, new FormData(finalForm));
    showScreen("done");
    LS.appId = null;
    LS.sessId = null;
  } catch (err) {
    renderFieldErrors(err.data, finalAlert);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `Submit application <i class="bi bi-check2-circle"></i>`;
  }
});

// ---------------------------------------------------------------- Resume on load
function resetJourney() {
  LS.appId = null;
  LS.sessId = null;
}

(async function boot() {
  if (!LS.appId) { resetJourney(); showScreen("form"); return; }

  // Ask the server where this applicant actually is. Never trust the stored ids
  // on their own -- the record may have been deleted, leaving the browser stuck
  // on a journey that no longer exists.
  let state;
  try {
    state = await apiJson("GET", `/applications/${LS.appId}/status/`);
  } catch (err) {
    resetJourney();       // stale/unknown application -> start a fresh application
    showScreen("form");
    return;
  }

  if (state.final_submitted) { resetJourney(); showScreen("done"); return; }

  if (state.quiz) {
    LS.sessId = state.quiz.id;
    if (state.quiz.completed_at) { showResult(state.quiz); return; }
    // Mid-quiz: a response from /current/ is either a question payload (has
    // .question) or a result payload (has .score but no .question).
    try {
      const data = await apiJson("GET", `/quiz/${LS.sessId}/current/`);
      if (data.question) { renderQuestion(data); return; }
      if (typeof data.score === "number") { showResult(data); return; }
    } catch (err) {
      LS.sessId = null; // fall through to the intro screen
    }
  }

  showScreen("intro");
})();
