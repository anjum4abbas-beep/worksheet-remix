// ---- Server config (does this deployment need a visitor-supplied API key /
// access code, or does the operator supply the API key server-side?) ----
const KEY_STORAGE = "worksheet-remix-api-key";
const CODE_STORAGE = "worksheet-remix-access-code";
const CONSENT_STORAGE = "worksheet-remix-consent-ack";

let siteConfig = { requires_client_key: true, requires_access_code: false };

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    siteConfig = await res.json();
  } catch (e) {
    // If /api/config isn't reachable, fall back to the safest assumption
    // (ask the visitor for their own key) rather than silently failing.
    siteConfig = { requires_client_key: true, requires_access_code: false };
  }
  document.getElementById("settings-apikey-block").style.display = siteConfig.requires_client_key ? "block" : "none";
  document.getElementById("settings-access-block").style.display = siteConfig.requires_access_code ? "block" : "none";
  settingsBtn.style.display = (siteConfig.requires_client_key || siteConfig.requires_access_code) ? "inline-block" : "none";
}

const settingsBtn = document.getElementById("settings-btn");
const settingsDialog = document.getElementById("settings-dialog");
const apiKeyInput = document.getElementById("api-key-input");
const accessCodeInput = document.getElementById("access-code-input");

settingsBtn.addEventListener("click", () => {
  apiKeyInput.value = localStorage.getItem(KEY_STORAGE) || "";
  accessCodeInput.value = localStorage.getItem(CODE_STORAGE) || "";
  settingsDialog.showModal();
});
document.getElementById("settings-cancel").addEventListener("click", () => settingsDialog.close());
document.getElementById("settings-save").addEventListener("click", () => {
  localStorage.setItem(KEY_STORAGE, apiKeyInput.value.trim());
  localStorage.setItem(CODE_STORAGE, accessCodeInput.value.trim());
  settingsDialog.close();
  setStatus("Settings saved.", "ok");
});

function getApiKey() {
  return localStorage.getItem(KEY_STORAGE) || "";
}
function getAccessCode() {
  return localStorage.getItem(CODE_STORAGE) || "";
}

// ---- First-visit pilot consent notice ----
const consentDialog = document.getElementById("consent-dialog");
if (!localStorage.getItem(CONSENT_STORAGE)) {
  consentDialog.showModal();
}
document.getElementById("consent-ack").addEventListener("click", () => {
  localStorage.setItem(CONSENT_STORAGE, "1");
  consentDialog.close();
});

loadConfig();

// ---- Tabs (paste vs upload) ----
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-paste").style.display = btn.dataset.tab === "paste" ? "block" : "none";
    document.getElementById("tab-upload").style.display = btn.dataset.tab === "upload" ? "block" : "none";
  });
});

// ---- Theme chips ----
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.getElementById("theme").value = chip.dataset.theme;
  });
});

// ---- Status line ----
const statusLine = document.getElementById("status-line");
function setStatus(msg, cls) {
  statusLine.textContent = msg || "";
  statusLine.className = "status-line" + (cls ? " " + cls : "");
}

// ---- Generate ----
const generateBtn = document.getElementById("generate-btn");
const printBtn = document.getElementById("print-btn");

generateBtn.addEventListener("click", async () => {
  const apiKey = getApiKey();
  const accessCode = getAccessCode();

  if (siteConfig.requires_client_key && !apiKey) {
    setStatus("Add your Anthropic API key in Settings first.", "error");
    settingsDialog.showModal();
    return;
  }
  if (siteConfig.requires_access_code && !accessCode) {
    setStatus("Enter the beta access code in Settings first.", "error");
    settingsDialog.showModal();
    return;
  }

  const activeTab = document.querySelector(".tab-btn.active").dataset.tab;
  const theme = document.getElementById("theme").value.trim();
  const notes = document.getElementById("notes").value.trim();

  const formData = new FormData();
  formData.append("theme", theme);
  formData.append("notes", notes);

  if (activeTab === "upload") {
    const fileInput = document.getElementById("worksheet_file");
    if (!fileInput.files.length) {
      setStatus("Choose a file to upload, or switch to Paste text.", "error");
      return;
    }
    formData.append("file", fileInput.files[0]);
  } else {
    const text = document.getElementById("worksheet_text").value.trim();
    if (!text) {
      setStatus("Paste the worksheet text first.", "error");
      return;
    }
    formData.append("worksheet_text", text);
  }

  if (!theme) {
    setStatus("Enter the child's special interest / theme.", "error");
    return;
  }

  generateBtn.disabled = true;
  setStatus("Rewriting your worksheet... this can take 10-20 seconds.", "");

  try {
    const headers = {};
    if (apiKey) headers["X-Api-Key"] = apiKey;
    if (accessCode) headers["X-Access-Code"] = accessCode;
    const res = await fetch("/api/rewrite", {
      method: "POST",
      headers,
      body: formData,
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      setStatus(data.error || "Something went wrong.", "error");
      return;
    }
    setStatus("Done.", "ok");
    renderWorksheet(data, activeTab === "paste" ? document.getElementById("worksheet_text").value : null);
  } catch (e) {
    setStatus("Network error talking to the local server: " + e.message, "error");
  } finally {
    generateBtn.disabled = false;
  }
});

// ---- Rendering ----
function renderWorksheet(data, originalText) {
  const dyslexia = document.getElementById("opt-dyslexia").checked;
  const large = document.getElementById("opt-large").checked;
  const showOriginal = document.getElementById("opt-original").checked;

  const output = document.getElementById("output-content");
  output.innerHTML = "";
  output.appendChild(buildWorksheetEl(data, { dyslexia, large }));

  if (showOriginal && originalText) {
    const origWrap = document.createElement("div");
    origWrap.style.marginTop = "18px";
    origWrap.innerHTML = `<div class="meta" style="margin-bottom:6px;">Original, for comparison:</div>
      <div class="worksheet" style="background:#faf9f7;"><pre style="white-space:pre-wrap; font-family:inherit; margin:0;">${escapeHtml(originalText)}</pre></div>`;
    output.appendChild(origWrap);
  }

  printBtn.style.display = "inline-block";
}

function buildWorksheetEl(data, opts) {
  const div = document.createElement("div");
  div.className = "worksheet" + (opts.dyslexia ? " dyslexia-font" : "");
  if (opts.large) div.style.fontSize = "1.15rem";

  let html = `<div class="meta">${escapeHtml(data.subject || "")} · themed on ${escapeHtml(data.theme_used || "")}</div>`;
  html += `<h3>${escapeHtml(data.title || "Worksheet")}</h3>`;
  if (data.intro_note) html += `<div class="intro">${escapeHtml(data.intro_note)}</div>`;
  if (data.passage) html += `<div class="passage">${escapeHtml(data.passage)}</div>`;

  html += "<ol>";
  (data.items || []).forEach((item) => {
    html += `<li><div>${escapeHtml(item.rewritten_text || "")}</div>`;
    if (item.answer) html += `<div class="answer">Answer: ${escapeHtml(item.answer)}</div>`;
    html += "</li>";
  });
  html += "</ol>";

  if (data.teacher_note) {
    html += `<div class="teacher-note">Note for the adult: ${escapeHtml(data.teacher_note)}</div>`;
  }

  div.innerHTML = html;
  return div;
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str == null ? "" : String(str);
  return d.innerHTML;
}

printBtn.addEventListener("click", () => window.print());

// ---- Example gallery (see examples.js for WORKSHEET_EXAMPLES) ----
const exampleList = document.getElementById("example-list");
(window.WORKSHEET_EXAMPLES || []).forEach((ex, i) => {
  const card = document.createElement("div");
  card.className = "example-card";
  card.innerHTML = `<div class="info"><strong>${escapeHtml(ex.label)}</strong><span>${escapeHtml(ex.subtitle)}</span></div>`;
  const btn = document.createElement("button");
  btn.className = "icon-btn";
  btn.type = "button";
  btn.textContent = "View";
  btn.addEventListener("click", () => {
    document.getElementById("output-content").innerHTML = "";
    document.getElementById("output-content").appendChild(buildWorksheetEl(ex.result, {
      dyslexia: document.getElementById("opt-dyslexia").checked,
      large: document.getElementById("opt-large").checked,
    }));
    printBtn.style.display = "inline-block";
    setStatus(`Showing pre-generated example: ${ex.label}`, "ok");
  });
  card.appendChild(btn);
  exampleList.appendChild(card);
});
