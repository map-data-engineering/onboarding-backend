// Applicant journey: Details -> Eligibility -> Experience -> Honesty check ->
// Knowledge check -> Your work -> Submit.
//
// Every step is persisted server-side as it is completed, so a reload resumes
// from the record rather than from anything the browser remembers. localStorage
// holds only the application id, and even that is validated on load.

const STEPS = ["Details", "Eligibility", "Experience", "Honesty check",
               "Knowledge check", "Your work", "Submit"];

const LS = {
  get appId()  { return localStorage.getItem("application_id"); },
  set appId(v) { v ? localStorage.setItem("application_id", v) : localStorage.removeItem("application_id"); },
};

const stage = document.getElementById("stage");
const stepsEl = document.getElementById("steps");

let step = 0;
let claimFunctions = [];   // honesty-check rows, as ordered by the server
// Not persisted: /status/ hands the session back on reload, so the record stays
// the single source of truth for where the applicant is.
let sessionId = null;

/* ------------------------------------------------------------------ helpers */
function renderSteps(visible = true) {
  stepsEl.innerHTML = visible
    ? STEPS.map((s, i) =>
        `<li class="${i === step ? "on" : i < step ? "done" : ""}">${i + 1}. ${s}</li>`).join("")
    : "";
}

function show(templateId, atStep) {
  if (atStep !== undefined) step = atStep;
  const tpl = document.getElementById(templateId);
  stage.replaceChildren(tpl.content.cloneNode(true));
  renderSteps(atStep !== undefined);
  window.scrollTo({ top: 0, behavior: "smooth" });
  return stage;
}

const $ = (sel) => stage.querySelector(sel);
const $$ = (sel) => [...stage.querySelectorAll(sel)];

function alertBox(message) {
  const box = $("[data-alert]");
  if (!box) return;
  box.textContent = message;
  box.classList.toggle("hidden", !message);
}

function clearErrors() {
  $$("[data-error]").forEach((el) => (el.textContent = ""));
  alertBox("");
}

// Render DRF's {field: [messages]} map against the fields on screen, falling
// back to the summary box for anything with nowhere to go.
function showErrors(data) {
  clearErrors();
  if (!data || typeof data !== "object") {
    alertBox("Something went wrong. Please try again.");
    return;
  }
  const leftovers = [];
  Object.entries(data).forEach(([field, messages]) => {
    const text = Array.isArray(messages) ? messages.join(" ") : String(messages);
    const target = stage.querySelector(`[data-error="${field}"]`);
    if (target) target.textContent = text;
    else leftovers.push(field === "detail" ? text : `${field}: ${text}`);
  });
  if (leftovers.length) alertBox(leftovers.join(" "));
}

function busy(button, label) {
  button.disabled = true;
  button.dataset.label = button.textContent;
  button.innerHTML = `<span class="spin"></span>${label}`;
  return () => {
    button.disabled = false;
    button.textContent = button.dataset.label;
  };
}

function values(names) {
  const out = {};
  names.forEach((n) => {
    const field = stage.querySelector(`[name="${n}"]`);
    out[n] = field ? field.value.trim() : "";
  });
  return out;
}

// Build a labelled <select> block for the eligibility/experience steps.
function questionBlock(name, text, options, hint) {
  return `
    <label>${text} <span class="req">*</span></label>
    <select name="${name}">
      <option value="">Choose…</option>
      ${options.map((o) => `<option>${o}</option>`).join("")}
    </select>
    ${hint ? `<p class="hint">${hint}</p>` : ""}
    <div class="field-error" data-error="${name}"></div>`;
}

/* ------------------------------------------------------- step 1: details */
const DETAIL_FIELDS = ["first_name", "last_name", "email", "phone", "country_of_residence",
  "nationality", "gender", "education", "institution", "institution_type", "role",
  "r_experience", "bayesian_knowledge"];

function stepDetails() {
  show("tpl-details", 0);
  $("[data-next]").addEventListener("click", async (e) => {
    clearErrors();
    const done = busy(e.currentTarget, "Saving…");
    try {
      const app = await apiJson("POST", "/applications/", values(DETAIL_FIELDS));
      LS.appId = app.id;
      stepEligibility();
    } catch (err) {
      showErrors(err.data);
    } finally {
      done();
    }
  });
}

/* --------------------------------------------------- step 2: eligibility */
const ELIGIBILITY = [
  ["elig_attend", "Can you attend in person for all four days?",
   ["Yes, all four days", "Only part of the period", "No"]],
  ["elig_laptop", "Will you bring a laptop on which you can install software (R, RStudio, INLA)?",
   ["Yes", "No", "I am not sure"]],
  ["elig_data", "Do you have access to spatial data you could analyse?",
   ["Yes, I work with it now", "Not yet, but I expect to within six months", "No"]],
  ["elig_funding", "Travel and accommodation are not funded by the workshop. How will yours be covered?",
   ["My institution has agreed to cover it", "I will cover it myself",
    "Likely covered, but not yet confirmed", "I could not attend without financial support"]],
];

function stepEligibility() {
  show("tpl-eligibility", 1);
  $("[data-questions]").innerHTML =
    ELIGIBILITY.map(([n, t, o]) => questionBlock(n, t, o)).join("");

  $("[data-next]").addEventListener("click", async (e) => {
    clearErrors();
    const payload = values(ELIGIBILITY.map(([n]) => n));
    if (Object.values(payload).some((v) => !v)) {
      alertBox("Please answer all four questions.");
      return;
    }
    const done = busy(e.currentTarget, "Saving…");
    try {
      const res = await apiJson("POST", `/applications/${LS.appId}/eligibility/`, payload);
      if (!res.eligible) { stopped(res.reason); return; }
      stepExperience();
    } catch (err) {
      showErrors(err.data);
    } finally {
      done();
    }
  });
}

function stopped(reason, title) {
  show("tpl-stopped");
  renderSteps(false);
  if (title) $("[data-title]").textContent = title;
  $("[data-message]").textContent = reason;
  LS.appId = null;   // nothing further to resume
}

/* ---------------------------------------------------- step 3: experience */
const EXPERIENCE = [
  ["Working with R", [
    ["exp_rfreq", "How often do you currently write or run R code yourself?",
     ["Most weeks", "Most months", "A few times a year", "Rarely or never"]],
    ["exp_rself", "How would you describe your own R skills?",
     ["Beginner — I can run scripts others have written",
      "Intermediate — I write my own analysis scripts",
      "Advanced — I write functions and packages"]],
    ["exp_bayes", "How would you describe your familiarity with Bayesian methods?",
     ["None", "Beginner", "Intermediate", "Advanced"]],
    ["exp_glm", "Have you fitted a regression or GLM yourself in the past two years?",
     ["Yes, several times", "Yes, once or twice", "No"]],
  ]],
  ["Your data", [
    ["exp_dtype", "Which best describes the spatial data you work with, or expect to?",
     ["Survey or sampling points with coordinates",
      "Counts or rates aggregated to districts, wards or facilities",
      "Raster or gridded environmental data",
      "Locations of events or cases (point patterns)",
      "A mixture of these", "None yet"]],
    ["exp_when", "When would you next apply these methods to your own data?",
     ["I have an analysis waiting for these methods now", "Within six months",
      "Within a year", "No specific plan yet"]],
  ]],
  ["Afterwards", [
    ["exp_share", "Would you run an internal session to pass on what you learn to colleagues?",
     ["Yes, and I have a specific team in mind", "Yes, in principle", "Possibly", "No"]],
    ["exp_use", "Does your current role involve producing analyses that other people use for decisions?",
     ["Yes, regularly", "Sometimes", "No"]],
  ]],
];

function stepExperience() {
  show("tpl-experience", 2);
  $("[data-questions]").innerHTML = EXPERIENCE.map(([heading, questions]) =>
    `<h2>${heading}</h2>` + questions.map(([n, t, o]) => questionBlock(n, t, o)).join("")
  ).join("");

  const names = EXPERIENCE.flatMap(([, qs]) => qs.map(([n]) => n));
  $("[data-next]").addEventListener("click", async (e) => {
    clearErrors();
    const payload = values(names);
    if (Object.values(payload).some((v) => !v)) {
      alertBox("Please answer every question.");
      return;
    }
    const done = busy(e.currentTarget, "Saving…");
    try {
      await apiJson("POST", `/applications/${LS.appId}/experience/`, payload);
      stepClaims();
    } catch (err) {
      showErrors(err.data);
    } finally {
      done();
    }
  });
}

/* ------------------------------------------------- step 4: honesty check */
async function stepClaims() {
  show("tpl-claims", 3);
  const body = $("[data-rows]");
  body.innerHTML = `<tr><td colspan="4" class="muted">Loading…</td></tr>`;

  try {
    // The server decides the order, and never says which names are invented.
    const data = await apiJson("GET", `/applications/${LS.appId}/claims/`);
    claimFunctions = data.functions;
  } catch (err) {
    alertBox("Could not load this step. Please reload the page.");
    return;
  }

  body.innerHTML = claimFunctions.map((fn, i) => `
    <tr>
      <td>${fn}()</td>
      ${["used", "heard", "no"].map((v) =>
        `<td><input type="radio" name="c${i}" value="${v}"
                    aria-label="${fn}: ${v}"></td>`).join("")}
    </tr>`).join("");

  $("[data-next]").addEventListener("click", async (e) => {
    clearErrors();
    const claims = {};
    let missing = false;
    claimFunctions.forEach((fn, i) => {
      const picked = stage.querySelector(`input[name="c${i}"]:checked`);
      if (!picked) missing = true;
      else claims[fn] = picked.value;
    });
    if (missing) {
      alertBox("Please answer for every function.");
      return;
    }
    const done = busy(e.currentTarget, "Saving…");
    try {
      await apiJson("POST", `/applications/${LS.appId}/claims/`, { claims });
      stepQuizIntro();
    } catch (err) {
      showErrors(err.data);
    } finally {
      done();
    }
  });
}

/* ----------------------------------------------- step 5: knowledge check */
function stepQuizIntro() {
  show("tpl-quiz-intro", 4);
  $("[data-next]").addEventListener("click", async (e) => {
    alertBox("");
    const done = busy(e.currentTarget, "Starting…");
    try {
      const question = await apiJson("POST", `/applications/${LS.appId}/quiz/start/`);
      renderQuestion(question);
    } catch (err) {
      if (err.status === 404) { reset("We couldn't find your application. Please start again."); return; }
      alertBox((err.data && (err.data.detail || JSON.stringify(err.data))) ||
               "Could not start the knowledge check.");
      done();
    }
  });
}

let countdownTimer = null;
let selectedAnswer = null;
let submitting = false;

function stopCountdown() {
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
}

// Server-authoritative countdown: tick against the ISO `deadline`, never a local
// timer we started -- the two drift, and only the server's opinion counts.
//
// `deadline` includes the server's network grace. We count down to the advertised
// limit instead, so someone told "25 seconds" sees 25 and the grace quietly covers
// the round trip of the answer we auto-submit at zero.
function startCountdown(deadlineIso, limitSeconds, graceSeconds = 0) {
  stopCountdown();
  const deadline = new Date(deadlineIso).getTime() - graceSeconds * 1000;
  const el = $("[data-countdown]");
  const bar = $("[data-bar]");
  const barWrap = bar.parentElement;

  const tick = () => {
    const remaining = Math.max(0, (deadline - Date.now()) / 1000);
    el.textContent = `${Math.ceil(remaining)}s`;
    const fraction = Math.max(0, Math.min(1, remaining / limitSeconds));
    bar.style.width = `${fraction * 100}%`;

    const low = remaining <= limitSeconds * 0.4, crit = remaining <= 5;
    el.classList.toggle("low", low && !crit);
    el.classList.toggle("crit", crit);
    barWrap.classList.toggle("low", low && !crit);
    barWrap.classList.toggle("crit", crit);

    if (remaining <= 0) {
      stopCountdown();
      $("[data-status]").textContent = "Time's up — submitting…";
      submitAnswer();
    }
  };
  tick();
  countdownTimer = setInterval(tick, 250);
}

function renderQuestion(payload) {
  show("tpl-question", 4);
  selectedAnswer = null;
  sessionId = payload.session;

  const q = payload.question;
  const shown = payload.position + 1;
  $("[data-progress]").textContent = `Question ${shown} of ${payload.total}`;
  $("[data-category]").textContent = q.category_label || q.category || "";
  $("[data-stem]").textContent = q.text;

  const code = $("[data-code]");
  code.textContent = q.code || "";
  code.classList.toggle("hidden", !q.code);

  // Options arrive already shuffled for this applicant; render as received and
  // submit the option *string*, never an index.
  const box = $("[data-options]");
  box.innerHTML = q.options.map((opt, i) => `
    <label class="opt">
      <input type="radio" name="answer" value="${i}">
      <span></span>
    </label>`).join("");
  box.querySelectorAll(".opt").forEach((label, i) => {
    label.querySelector("span").textContent = q.options[i];
    label.addEventListener("change", () => {
      selectedAnswer = q.options[i];
      box.querySelectorAll(".opt").forEach((o) => o.classList.remove("sel"));
      label.classList.add("sel");
      $("[data-submit]").disabled = false;
    });
  });

  $("[data-submit]").addEventListener("click", () => submitAnswer());
  startCountdown(payload.deadline, payload.time_limit_seconds, payload.grace_seconds || 0);
}

async function submitAnswer() {
  if (submitting) return;
  submitting = true;
  stopCountdown();
  const button = $("[data-submit]");
  if (button) button.disabled = true;

  try {
    const res = await apiJson("POST", `/quiz/${sessionId}/answer/`, { answer: selectedAnswer || "" });
    if (res.finished) showResult(res.result);
    else renderQuestion(res.next);
  } catch (err) {
    const status = $("[data-status]");
    if (status) status.textContent = "Could not submit. Retrying is disabled to protect the timer.";
    console.error(err);
  } finally {
    submitting = false;
  }
}

/* ------------------------------------------------------ result + step 6 */
function showResult(result) {
  stopCountdown();
  show("tpl-result", 4);
  $("[data-score]").textContent = result.score;
  $("[data-total]").textContent = result.total;

  const unlocked = result.passed && !result.final_submitted;
  $("[data-continue-wrap]").classList.toggle("hidden", !unlocked);

  if (result.final_submitted) {
    $("[data-message]").textContent = "Your application has already been submitted.";
  } else if (result.passed) {
    $("[data-message]").textContent =
      "You've met the required score. One step left: your own work and your CV.";
  } else {
    $("[data-title]").textContent = "Thank you for taking the knowledge check";
    $("[data-message]").textContent =
      `A score of at least ${result.pass_mark} is needed to continue with this application.`;
  }
  $("[data-completed]").textContent = result.completed_at
    ? `Completed ${new Date(result.completed_at).toLocaleString()}` : "";

  if (unlocked) $("[data-next]").addEventListener("click", stepWritten);
  else LS.appId = null;
}

const WRITTEN_FIELDS = ["written_dataset", "written_code", "written_why_not_ols",
                        "written_other", "motivation", "expectations"];

// Same rule as the server (validators.count_words): whitespace-delimited.
const countWords = (text) => (text.match(/\S+/g) || []).length;

function wireWordCounters() {
  $$("[data-words]").forEach((field) => {
    const limit = Number(field.dataset.words);
    const readout = stage.querySelector(`[data-counter-for="${field.name}"]`);
    if (!readout) return;
    const update = () => {
      const words = countWords(field.value);
      readout.textContent = `${words} / ${limit} words`;
      // Colour only once they are over -- a counter that shouts at 250 is noise.
      readout.style.color = words > limit ? "var(--bad)" : "";
      readout.style.fontWeight = words > limit ? "600" : "";
    };
    field.addEventListener("input", update);
    update();
  });
}

const CV_MAX_BYTES = 5 * 1024 * 1024;

function localChecksPass(file) {
  let ok = true;
  const fail = (field, message) => {
    const box = stage.querySelector(`[data-error="${field}"]`);
    if (box) box.textContent = message;
    ok = false;
  };

  $$("[data-words]").forEach((field) => {
    const limit = Number(field.dataset.words);
    const words = countWords(field.value);
    if (words > limit) fail(field.name, `${words} words — please shorten to ${limit} or fewer.`);
  });

  if (!file) fail("cv", "Please attach your CV.");
  else if (!file.name.toLowerCase().endsWith(".pdf"))
    fail("cv", "Your CV must be a PDF. Export from Word rather than renaming the file.");
  else if (file.size > CV_MAX_BYTES)
    fail("cv", `That file is ${(file.size / 1048576).toFixed(1)} MB. The limit is 5 MB.`);

  if (!ok) alertBox("Please correct the highlighted answers.");
  return ok;
}

function stepWritten() {
  show("tpl-written", 5);
  wireWordCounters();
  $("[data-next]").addEventListener("click", async (e) => {
    clearErrors();
    const form = new FormData();
    WRITTEN_FIELDS.forEach((n) => form.append(n, stage.querySelector(`[name="${n}"]`).value.trim()));
    const file = stage.querySelector('[name="cv"]').files[0];
    if (file) form.append("cv", file);

    // Fail fast on the two things we can see without a round trip. The server
    // re-checks all of it (and the page count, which we can't check here).
    if (!localChecksPass(file)) return;

    const done = busy(e.currentTarget, "Submitting…");
    try {
      await apiForm("POST", `/applications/${LS.appId}/finalize/`, form);
      show("tpl-done", 6);
      LS.appId = null;
    } catch (err) {
      showErrors(err.data);
      done();
    }
  });
}

/* ------------------------------------------------------------ resume/boot */
function reset(message) {
  LS.appId = null;
  stepDetails();
  if (message) alertBox(message);
}

(async function boot() {
  if (!LS.appId) { stepDetails(); return; }

  let state;
  try {
    state = await apiJson("GET", `/applications/${LS.appId}/status/`);
  } catch {
    reset();          // stale or deleted -> start a fresh application
    return;
  }

  if (state.ineligible_reason) { stopped(state.ineligible_reason); return; }
  if (state.final_submitted) { LS.appId = null; show("tpl-done", 6); return; }

  if (state.quiz) {
    sessionId = state.quiz.id;
    if (state.quiz.completed_at) { showResult(state.quiz); return; }
    try {
      const data = await apiJson("GET", `/quiz/${state.quiz.id}/current/`);
      if (data.question) { renderQuestion(data); return; }
      if (typeof data.score === "number") { showResult(data); return; }
    } catch { /* fall through to the intro */ }
    stepQuizIntro();
    return;
  }

  // No quiz yet: pick up at the first unanswered step.
  if (!state.completed.eligibility) stepEligibility();
  else if (!state.completed.experience) stepExperience();
  else if (!state.completed.claims) stepClaims();
  else stepQuizIntro();
})();
