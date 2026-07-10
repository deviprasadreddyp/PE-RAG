const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#questionInput");
const sendBtn = document.querySelector("#sendBtn");
const clearBtn = document.querySelector("#clearBtn");
const metricsToggle = document.querySelector("#metricsToggle");
const metricsPanel = document.querySelector("#metricsPanel");
const evidenceToggle = document.querySelector("#evidenceToggle");
const evidenceDrawer = document.querySelector("#evidenceDrawer");
const closeEvidence = document.querySelector("#closeEvidence");
const debugToggle = document.querySelector("#debugToggle");
const sourceList = document.querySelector("#sourceList");
const traceOutput = document.querySelector("#traceOutput");

const progressSteps = [
  "Parsing the question",
  "Applying metadata filters",
  "Running hybrid retrieval",
  "Reranking evidence",
  "Building cited context",
  "Making the single LLM call",
  "Resolving source citations",
];

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(E\d+)\]/g, "<span class=\"citation-pill\">[$1]</span>");
}

function renderTable(lines) {
  const rows = lines
    .filter((line) => line.trim().startsWith("|"))
    .map((line) => line.trim().slice(1, -1).split("|").map((cell) => inlineMarkdown(cell.trim())));
  if (rows.length < 2) return `<p>${inlineMarkdown(lines.join(" "))}</p>`;
  const header = rows[0];
  const body = rows.slice(2);
  return `
    <table class="answer-table">
      <thead><tr>${header.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>
      <tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>
  `;
}

function renderMarkdown(markdown) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      html.push(`<h3>${inlineMarkdown(line.slice(3))}</h3>`);
      i += 1;
      continue;
    }
    if (line.trim().startsWith("|")) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        tableLines.push(lines[i]);
        i += 1;
      }
      html.push(renderTable(tableLines));
      continue;
    }
    if (line.startsWith("- ")) {
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(`<li>${inlineMarkdown(lines[i].slice(2))}</li>`);
        i += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    const paragraph = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].startsWith("## ") &&
      !lines[i].startsWith("- ") &&
      !lines[i].trim().startsWith("|")
    ) {
      paragraph.push(lines[i]);
      i += 1;
    }
    html.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
  }
  return html.join("");
}

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function greetingHtml() {
  return `
    <article class="message assistant">
      <div class="bubble intro">
        <p class="kicker">Hello</p>
        <h2>Which filing question should we diligence today?</h2>
        <div class="sample-grid">
          <button type="button" data-sample="Compare Apple, Tesla, and JPMorgan risk factors">Compare risk exposure</button>
          <button type="button" data-sample="How has NVIDIA's revenue and growth outlook changed?">Review NVIDIA growth</button>
          <button type="button" data-sample="What regulatory risks do UnitedHealth and Johnson & Johnson disclose?">Check regulatory risk</button>
        </div>
      </div>
    </article>
  `;
}

function attachSampleHandlers(root = document) {
  root.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.sample;
      resizeInput();
      input.focus();
    });
  });
}

function resetConversation() {
  document.body.classList.add("is-empty");
  messages.innerHTML = greetingHtml();
  attachSampleHandlers(messages);
  renderSources([]);
  renderTrace({});
  scrollToBottom();
}

function addMessage(role, html, { extraClass = "" } = {}) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    <div class="bubble ${extraClass}">${html}</div>
  `;
  messages.appendChild(article);
  scrollToBottom();
  return article.querySelector(".bubble");
}

function progressHtml(stepIndex, message) {
  const active = progressSteps[Math.min(stepIndex, progressSteps.length - 1)];
  const status = message || active;
  const displayStatus = status.endsWith("...") ? status : `${status}...`;
  return `
    <p class="kicker">Working</p>
    <p class="status-line" title="${escapeHtml(displayStatus)}">${escapeHtml(displayStatus)}</p>
  `;
}

function startProgress(bubble) {
  let step = 0;
  bubble.innerHTML = progressHtml(step);
  return window.setInterval(() => {
    step = Math.min(step + 1, progressSteps.length - 1);
    bubble.innerHTML = progressHtml(step);
    scrollToBottom();
  }, 850);
}

async function readStream(response, onEvent) {
  if (!response.body) {
    throw new Error("Streaming is not supported by this browser.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const line = frame.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      onEvent(JSON.parse(line.slice(6)));
    }
  }
  if (buffer.trim()) {
    const line = buffer.split("\n").find((item) => item.startsWith("data: "));
    if (line) onEvent(JSON.parse(line.slice(6)));
  }
}

async function revealAnswer(bubble, markdown, refused) {
  const chunks = [];
  for (let i = 0; i < markdown.length; i += 120) {
    chunks.push(markdown.slice(i, i + 120));
  }
  let current = "";
  bubble.classList.toggle("refusal", Boolean(refused));
  for (const chunk of chunks) {
    current += chunk;
    bubble.innerHTML = renderMarkdown(current);
    scrollToBottom();
    await new Promise((resolve) => window.setTimeout(resolve, 16));
  }
}

function renderLiveAnswer(bubble, markdown) {
  bubble.innerHTML = `${renderMarkdown(markdown)}<span class="typing-caret" aria-hidden="true"></span>`;
  scrollToBottom();
}

function renderSources(citations) {
  if (!citations || citations.length === 0) {
    sourceList.innerHTML = `<p class="empty">Sources will appear after an answer.</p>`;
    return;
  }
  sourceList.innerHTML = citations.map((source, index) => {
    const label = source.tag || `Source ${index + 1}`;
    const meta = [source.ticker, source.form, source.fiscal_period, source.section].filter(Boolean).join(" / ");
    const url = source.source_url
      ? `<p><a href="${escapeHtml(source.source_url)}" target="_blank" rel="noreferrer">Open SEC source</a></p>`
      : "";
    return `
      <article class="source-card">
        <strong>${escapeHtml(label)}</strong>
        <p>${escapeHtml(meta)}</p>
        ${url}
      </article>
    `;
  }).join("");
  evidenceToggle.classList.toggle("has-sources", citations.length > 0);
}

function renderTrace(trace) {
  traceOutput.textContent = JSON.stringify(trace || {}, null, 2);
}

async function ask(question) {
  document.body.classList.remove("is-empty");
  addMessage("user", `<p>${inlineMarkdown(question)}</p>`);
  const bubble = addMessage("assistant", progressHtml(0), { extraClass: "working" });
  const timer = startProgress(bubble);
  let timerActive = true;
  sendBtn.disabled = true;
  document.body.classList.add("is-streaming");

  try {
    let finalPayload = null;
    let answerBuffer = "";
    let answerStarted = false;
    const response = await fetch("/query-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, debug: debugToggle.checked }),
    });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    await readStream(response, (event) => {
      if (event.type === "progress" && !answerStarted) {
        bubble.innerHTML = progressHtml(event.step || 0, event.message);
        scrollToBottom();
      }
      if (event.type === "answer_start") {
        answerStarted = true;
        if (timerActive) {
          window.clearInterval(timer);
          timerActive = false;
        }
        bubble.classList.remove("working");
        bubble.classList.add("answering");
        bubble.classList.toggle("refusal", Boolean(event.refused));
        bubble.innerHTML = `<p class="status-line">Writing the grounded answer...</p>`;
        scrollToBottom();
      }
      if (event.type === "answer_delta") {
        answerStarted = true;
        answerBuffer += event.text || "";
        renderLiveAnswer(bubble, answerBuffer);
      }
      if (event.type === "error") {
        throw new Error(event.message || "Request failed.");
      }
      if (event.type === "done") {
        finalPayload = event.payload;
      }
    });
    if (!finalPayload) {
      throw new Error("The answer stream ended before a result was returned.");
    }
    if (timerActive) {
      window.clearInterval(timer);
      timerActive = false;
    }
    bubble.classList.remove("working", "answering");
    bubble.classList.toggle("refusal", Boolean(finalPayload.refused));
    if (answerBuffer) {
      bubble.innerHTML = renderMarkdown(finalPayload.answer || answerBuffer);
      scrollToBottom();
    } else {
      await revealAnswer(bubble, finalPayload.answer || "", finalPayload.refused);
    }
    renderSources(finalPayload.citations || []);
    renderTrace(finalPayload.trace || {});
  } catch (error) {
    if (timerActive) window.clearInterval(timer);
    bubble.classList.add("refusal");
    bubble.innerHTML = `<p>${inlineMarkdown(error.message || "Request failed.")}</p>`;
  } finally {
    sendBtn.disabled = false;
    document.body.classList.remove("is-streaming");
    input.focus();
  }
}

function resizeInput() {
  if (!input.value.trim()) {
    input.style.height = "40px";
    return;
  }
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 92)}px`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  resizeInput();
  ask(question);
});

input.addEventListener("input", resizeInput);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

clearBtn.addEventListener("click", () => {
  resetConversation();
  input.focus();
});

metricsToggle.addEventListener("click", () => {
  const shouldOpen = metricsPanel.hidden;
  metricsPanel.hidden = !shouldOpen;
  metricsToggle.setAttribute("aria-expanded", String(shouldOpen));
});

function setEvidenceDrawer(open) {
  evidenceDrawer.classList.toggle("open", open);
  evidenceDrawer.setAttribute("aria-hidden", String(!open));
  evidenceToggle.setAttribute("aria-expanded", String(open));
}

evidenceToggle.addEventListener("click", () => {
  setEvidenceDrawer(!evidenceDrawer.classList.contains("open"));
});

closeEvidence.addEventListener("click", () => setEvidenceDrawer(false));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setEvidenceDrawer(false);
});

attachSampleHandlers();
document.body.classList.add("is-empty");
resizeInput();
renderTrace({});
