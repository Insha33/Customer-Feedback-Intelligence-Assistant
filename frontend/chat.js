const chatMessages = document.querySelector("#chatMessages");
const chatPanel = document.querySelector(".chat-panel");
const chatForm = document.querySelector("#chatForm");
const questionInput = document.querySelector("#questionInput");
const sendQuestion = document.querySelector("#sendQuestion");
const WORKING_STATES = [
  "Reading the question",
  "Checking review metrics",
  "Retrieving matching reviews",
  "Drafting a concise answer",
];

function appendMessage(role, content, sources = []) {
  chatPanel.classList.add("chat-active");
  const wrapper = document.createElement("div");
  wrapper.className = `message-wrap ${role}`;

  const title = document.createElement("div");
  title.className = "message-author";
  title.textContent = role === "user" ? "You" : "ReviewLens AI";

  const article = document.createElement("article");
  article.className = `message ${role}`;

  const body = document.createElement("p");
  body.textContent = content;

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
    appendMessage("assistant", `I could not answer that yet: ${error.message}`);
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
  askQuestion(question);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.prompt;
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
