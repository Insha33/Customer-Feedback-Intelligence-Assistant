const chatMessages = document.querySelector("#chatMessages");
const chatPanel = document.querySelector(".chat-panel");
const chatForm = document.querySelector("#chatForm");
const questionInput = document.querySelector("#questionInput");
const sendQuestion = document.querySelector("#sendQuestion");
const chatError = document.querySelector("#chatError");
const contextReviewCount = document.querySelector("#contextReviewCount");
const BACKLOG_URL = "/data/backlog_recommendations.json";
const WORKING_STATES = [
  "Reading the question",
  "Checking review metrics",
  "Retrieving matching reviews",
  "Drafting a concise answer",
];

function resizeComposer() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 132)}px`;
}

function appendInlineMarkdown(parent, text) {
  const boldPattern = /\*\*(.+?)\*\*/g;
  let cursor = 0;
  let match;

  while ((match = boldPattern.exec(text)) !== null) {
    parent.append(document.createTextNode(text.slice(cursor, match.index)));
    const strong = document.createElement("strong");
    strong.textContent = match[1];
    parent.append(strong);
    cursor = match.index + match[0].length;
  }

  parent.append(document.createTextNode(text.slice(cursor)));
}

function renderAssistantContent(content) {
  const container = document.createElement("div");
  container.className = "message-content";
  const lines = String(content || "").replace(/\r\n/g, "\n").split("\n");
  let list = null;

  lines.forEach((rawLine) => {
    const line = rawLine.trim();

    if (!line) {
      list = null;
      return;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (!list) {
        list = document.createElement("ul");
        container.append(list);
      }
      const item = document.createElement("li");
      appendInlineMarkdown(item, bullet[1]);
      list.append(item);
      return;
    }

    list = null;
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, line.replace(/^#{1,3}\s+/, ""));
    container.append(paragraph);
  });

  return container;
}

function appendMessage(role, content, sources = []) {
  chatPanel.classList.add("chat-active");
  const wrapper = document.createElement("div");
  wrapper.className = `message-wrap ${role}`;

  const title = document.createElement("div");
  title.className = "message-author";
  title.textContent = role === "user" ? "You" : "ReviewLens AI";

  const article = document.createElement("article");
  article.className = `message ${role}`;

  const body =
    role === "assistant"
      ? renderAssistantContent(content)
      : document.createElement("p");

  if (role !== "assistant") {
    body.textContent = content;
  }

  article.append(body);

  if (sources.length) {
    const sourceList = document.createElement("div");
    sourceList.className = "source-list";
    sources.slice(0, 5).forEach((source) => {
      const item = document.createElement("span");
      item.textContent = [
        source.review_id,
        source.category || "Uncategorized",
        source.sentiment,
      ]
        .filter(Boolean)
        .join(" · ");
      sourceList.append(item);
    });
    article.append(sourceList);
  }

  wrapper.append(title, article);
  chatMessages.append(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendWorkingMessage() {
  chatPanel.classList.add("chat-active");
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrap assistant";

  const title = document.createElement("div");
  title.className = "message-author";
  title.textContent = "ReviewLens AI";

  const article = document.createElement("article");
  article.className = "message assistant thinking-message";
  article.setAttribute("aria-live", "polite");

  const status = document.createElement("span");
  status.className = "thinking-text";
  status.textContent = WORKING_STATES[0];

  const dots = document.createElement("span");
  dots.className = "thinking-dots";
  dots.setAttribute("aria-hidden", "true");
  dots.innerHTML = "<span></span><span></span><span></span>";

  article.append(status, dots);
  wrapper.append(title, article);
  chatMessages.append(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  let index = 0;
  const intervalId = window.setInterval(() => {
    index = (index + 1) % WORKING_STATES.length;
    status.textContent = WORKING_STATES[index];
  }, 1400);

  return {
    remove() {
      window.clearInterval(intervalId);
      wrapper.remove();
    },
  };
}

function setLoading(isLoading) {
  sendQuestion.disabled = isLoading;
  questionInput.disabled = isLoading;
  chatForm.setAttribute("aria-busy", String(isLoading));
}

async function loadContextMetadata() {
  try {
    const response = await fetch(BACKLOG_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const total = data.metadata?.total_reviews;
    contextReviewCount.textContent = total
      ? `${Number(total).toLocaleString()} reviews indexed`
      : "Review index available";
  } catch {
    contextReviewCount.textContent = "Review index available";
  }
}

async function readApiResponse(response) {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  const preview = text.replace(/\s+/g, " ").trim().slice(0, 120);

  throw new Error(
    [
      "The Ask AI API returned HTML instead of JSON.",
      "Start the app with `npm run start:dashboard`, not `python3 -m http.server`.",
      preview ? `Server response started with: ${preview}` : "",
    ]
      .filter(Boolean)
      .join(" "),
  );
}

async function askQuestion(question) {
  setLoading(true);
  chatError.textContent = "";
  const workingMessage = appendWorkingMessage();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    });
    const data = await readApiResponse(response);

    if (!response.ok) {
      throw new Error(data.error || "The chatbot request failed.");
    }

    workingMessage.remove();
    appendMessage("assistant", data.answer, data.sources || []);
  } catch (error) {
    workingMessage.remove();
    chatError.textContent = `Could not complete the request. ${error.message}`;
  } finally {
    setLoading(false);
    questionInput.focus();
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();

  if (!question) {
    return;
  }

  appendMessage("user", question);
  questionInput.value = "";
  resizeComposer();
  askQuestion(question);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.prompt;
    resizeComposer();
    questionInput.focus();
  });
});

questionInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey) {
    return;
  }

  event.preventDefault();
  chatForm.requestSubmit();
});

questionInput.addEventListener("input", resizeComposer);

loadContextMetadata();
