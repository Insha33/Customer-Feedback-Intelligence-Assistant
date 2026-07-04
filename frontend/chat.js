const chatMessages = document.querySelector("#chatMessages");
const chatForm = document.querySelector("#chatForm");
const questionInput = document.querySelector("#questionInput");
const sendQuestion = document.querySelector("#sendQuestion");
const chatStatus = document.querySelector("#chatStatus");

function appendMessage(role, content, sources = []) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const title = document.createElement("strong");
  title.textContent = role === "user" ? "You" : "ReviewLens";

  const body = document.createElement("p");
  body.textContent = content;

  article.append(title, body);

  if (sources.length) {
    const sourceList = document.createElement("div");
    sourceList.className = "source-list";
    sources.slice(0, 5).forEach((source) => {
      const item = document.createElement("span");
      item.textContent = `${source.review_id} · ${source.category || "Uncategorized"}`;
      sourceList.append(item);
    });
    article.append(sourceList);
  }

  chatMessages.append(article);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setLoading(isLoading) {
  sendQuestion.disabled = isLoading;
  questionInput.disabled = isLoading;
  chatStatus.textContent = isLoading ? "Searching Qdrant..." : "Hybrid RAG";
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

    appendMessage("assistant", data.answer, data.sources || []);
  } catch (error) {
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
