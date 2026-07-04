const DATA_URL = "/data/instagram_reviews_rag.csv";

const CATEGORY_ACTIONS = {
  "Account Suspension":
    "Fix false-positive suspension and appeal recovery flows",
  "Performance Issues":
    "Stabilize crashes, update regressions, and load failures",
  "Feature Requests": "Evaluate repeated feature asks for roadmap fit",
  "Reels & Feed Algorithm":
    "Tune feed ranking, reels visibility, and recommendation quality",
  "Authentication Issues": "Repair login, 2FA, and account recovery paths",
  "Content Moderation": "Improve moderation accuracy and explanation quality",
  "Messaging & DMs": "Fix message delivery, notification, and DM reliability",
  "Privacy Concerns": "Clarify privacy controls and reduce trust-risk reports",
  "Customer Support": "Shorten support response paths and escalation loops",
  "Creator Tools": "Improve creator workflows, analytics, and publishing tools",
  "General Feedback": "Monitor broad satisfaction themes",
};

const SENTIMENT_COLORS = {
  negative: "#d84a4a",
  neutral: "#c9861a",
  positive: "#258f67",
};

const CATEGORY_COLORS = [
  "#0f9f8f",
  "#3b6eea",
  "#d84a4a",
  "#c9861a",
  "#7c5cff",
  "#258f67",
  "#e56b8f",
  "#3aa6b9",
  "#8b6f47",
  "#6b7280",
];

const state = {
  rows: [],
  filtered: [],
  category: "All",
  sentiment: "All",
  query: "",
};

function getElement(selector) {
  const element = document.querySelector(selector);

  if (!element) {
    throw new Error(`Required dashboard element is missing: ${selector}`);
  }

  return element;
}

const els = {
  categoryFilter: getElement("#categoryFilter"),
  sentimentFilter: getElement("#sentimentFilter"),
  searchInput: getElement("#searchInput"),
  clearFilters: getElement("#clearFilters"),
  criticalCount: getElement("#criticalCount"),
  criticalShare: getElement("#criticalShare"),
  topIssue: getElement("#topIssue"),
  topIssueShare: getElement("#topIssueShare"),
  avgRating: getElement("#avgRating"),
  ratingContext: getElement("#ratingContext"),
  categoryTotal: getElement("#categoryTotal"),
  categoryChart: getElement("#categoryChart"),
  sentimentChart: getElement("#sentimentChart"),
  backlogLanes: getElement("#backlogLanes"),
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (char === '"' && inQuotes && next === '"') {
      cell += '"';
      index += 1;
      continue;
    }

    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }

    if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") {
        index += 1;
      }
      row.push(cell);
      if (row.some((value) => value.length > 0)) {
        rows.push(row);
      }
      row = [];
      cell = "";
      continue;
    }

    cell += char;
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  const headers = rows.shift() || [];
  return rows.map((values) =>
    Object.fromEntries(
      headers.map((header, index) => [header, values[index] ?? ""]),
    ),
  );
}

function normalizeRow(row) {
  return {
    ...row,
    user_rating: Number(row.user_rating) || 0,
    quality_score: Number(row.quality_score) || 0,
    sentiment: (row.sentiment || "unknown").toLowerCase(),
  };
}

function countBy(rows, key) {
  return rows.reduce((acc, row) => {
    const value = row[key] || "Unknown";
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {});
}

function pct(value, total) {
  if (!total) return "0%";
  return `${Math.round((value / total) * 100)}%`;
}

function average(rows, key) {
  if (!rows.length) return 0;
  return (
    rows.reduce((sum, row) => sum + (Number(row[key]) || 0), 0) / rows.length
  );
}

function topEntries(counts, limit = 10) {
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

function applyFilters() {
  const query = state.query.trim().toLowerCase();
  state.filtered = state.rows.filter((row) => {
    const categoryOk =
      state.category === "All" || row.category === state.category;
    const sentimentOk =
      state.sentiment === "All" || row.sentiment === state.sentiment;
    const queryOk =
      !query ||
      [row.review_text, row.category, row.source, row.review_date]
        .join(" ")
        .toLowerCase()
        .includes(query);

    return categoryOk && sentimentOk && queryOk;
  });
}

function setupFilters() {
  const categories = [
    "All",
    ...Object.keys(countBy(state.rows, "category")).sort(),
  ];
  const sentiments = [
    "All",
    ...Object.keys(countBy(state.rows, "sentiment")).sort(),
  ];

  els.categoryFilter.innerHTML = categories
    .map(
      (category) =>
        `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`,
    )
    .join("");
  els.sentimentFilter.innerHTML = sentiments
    .map(
      (sentiment) =>
        `<option value="${escapeHtml(sentiment)}">${escapeHtml(sentiment)}</option>`,
    )
    .join("");

  els.categoryFilter.addEventListener("change", (event) => {
    state.category = event.target.value;
    render();
  });
  els.sentimentFilter.addEventListener("change", (event) => {
    state.sentiment = event.target.value;
    render();
  });
  els.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
  });
  els.clearFilters.addEventListener("click", () => {
    state.category = "All";
    state.sentiment = "All";
    state.query = "";
    els.categoryFilter.value = state.category;
    els.sentimentFilter.value = state.sentiment;
    els.searchInput.value = "";
    render();
  });
}

function renderMetrics(rows) {
  const total = rows.length;
  const categoryCounts = countBy(rows, "category");
  const topCategory = topEntries(categoryCounts, 1)[0] || ["-", 0];
  const criticalRows = rows.filter(
    (row) => row.sentiment === "negative" && row.user_rating <= 2,
  );
  const avg = average(rows, "user_rating");

  els.criticalCount.textContent = criticalRows.length.toLocaleString();
  els.criticalShare.textContent = `${pct(criticalRows.length, total)} require product or support action`;
  els.topIssue.textContent = topCategory[0];
  els.topIssueShare.textContent = `${topCategory[1].toLocaleString()} reviews, ${pct(
    topCategory[1],
    total,
  )}`;
  els.avgRating.textContent = avg ? avg.toFixed(1) : "-";
  els.ratingContext.textContent = "average app-store rating";
  els.categoryTotal.textContent = `${total.toLocaleString()} reviews`;
}

function renderCategoryChart(rows) {
  const entries = topEntries(countBy(rows, "category"), 10);
  const total = rows.length;
  const max = entries[0]?.[1] || 1;

  els.categoryChart.innerHTML = entries
    .map(([category, count], index) => {
      const width = Math.max(4, (count / max) * 100);
      const color = CATEGORY_COLORS[index % CATEGORY_COLORS.length];
      const isActive = state.category === category;

      return `
        <button class="bar-row ${isActive ? "active" : ""}" type="button" data-category="${escapeHtml(category)}">
          <span class="bar-label" title="${escapeHtml(category)}">${escapeHtml(category)}</span>
          <span class="bar-track" aria-hidden="true">
            <span class="bar-fill" style="width:${width}%; background:${color}"></span>
          </span>
          <span class="bar-value">${pct(count, total)}</span>
        </button>
      `;
    })
    .join("");

  els.categoryChart.querySelectorAll("[data-category]").forEach((button) => {
    button.addEventListener("click", () => {
      const selectedCategory = button.dataset.category;
      state.category =
        state.category === selectedCategory ? "All" : selectedCategory;
      els.categoryFilter.value = state.category;
      render();
    });
  });
}

function renderDonut(rows) {
  const counts = countBy(rows, "sentiment");
  const total = rows.length || 1;
  const segments = ["negative", "neutral", "positive"].map((name) => ({
    name,
    value: counts[name] || 0,
    color: SENTIMENT_COLORS[name],
  }));
  let offset = 25;
  const radius = 46;
  const circumference = 2 * Math.PI * radius;

  const circles = segments
    .map((segment) => {
      const length = (segment.value / total) * circumference;
      const circle = `
        <circle
          r="${radius}"
          cx="74"
          cy="74"
          fill="none"
          stroke="${segment.color}"
          stroke-width="20"
          stroke-dasharray="${length} ${circumference - length}"
          stroke-dashoffset="${offset}"
          transform="rotate(-90 74 74)"
        ></circle>`;
      offset -= length;
      return circle;
    })
    .join("");

  const negativeShare = pct(counts.negative || 0, rows.length);
  const legend = segments
    .map(
      (segment) => `
        <button class="legend-item ${state.sentiment === segment.name ? "active" : ""}" type="button" data-sentiment="${segment.name}">
          <span class="legend-name">
            <span class="swatch" style="background:${segment.color}"></span>
            ${escapeHtml(segment.name)}
          </span>
          <span>${pct(segment.value, rows.length)}</span>
        </button>
      `,
    )
    .join("");

  els.sentimentChart.innerHTML = `
    <svg class="donut" viewBox="0 0 148 148" role="img" aria-label="Sentiment distribution">
      <circle r="${radius}" cx="74" cy="74" fill="none" stroke="#edf2f7" stroke-width="20"></circle>
      ${circles}
      <text x="74" y="70">${negativeShare}</text>
      <text x="74" y="90" style="font-size:11px;fill:#667085">negative</text>
    </svg>
    <div class="legend">${legend}</div>
  `;

  els.sentimentChart.querySelectorAll("[data-sentiment]").forEach((button) => {
    button.addEventListener("click", () => {
      const selectedSentiment = button.dataset.sentiment;
      state.sentiment =
        state.sentiment === selectedSentiment ? "All" : selectedSentiment;
      els.sentimentFilter.value = state.sentiment;
      render();
    });
  });
}

function categoryBacklog(rows) {
  const grouped = Object.entries(countBy(rows, "category")).map(
    ([category, count]) => {
      const categoryRows = rows.filter((row) => row.category === category);
      const negative = categoryRows.filter(
        (row) => row.sentiment === "negative",
      ).length;
      const lowRating = categoryRows.filter(
        (row) => row.user_rating <= 2,
      ).length;
      const quality = average(categoryRows, "quality_score");
      const score =
        count * 1.2 + negative * 1.4 + lowRating * 1.6 + quality * 8;

      let lane = "Nice to have";
      if (score >= 180 || (count >= 35 && lowRating / count >= 0.55)) {
        lane = "Must implement";
      } else if (score >= 70 || count >= 15) {
        lane = "Should have";
      }

      return {
        category,
        count,
        negative,
        lowRating,
        quality,
        score,
        lane,
        action:
          CATEGORY_ACTIONS[category] ||
          `Investigate recurring ${category} feedback`,
      };
    },
  );

  return grouped.sort((a, b) => b.score - a.score);
}

function renderBacklog(rows) {
  const lanes = ["Must implement", "Should have", "Nice to have"];
  const laneClasses = {
    "Must implement": "must",
    "Should have": "should",
    "Nice to have": "nice",
  };
  const items = categoryBacklog(rows);

  els.backlogLanes.innerHTML = lanes
    .map((lane) => {
      const laneItems = items.filter((item) => item.lane === lane);
      const list =
        laneItems
          .map(
            (item) => `
              <article class="backlog-item">
                <h3>${escapeHtml(item.action)}</h3>
                <p>${escapeHtml(item.category)} has ${item.count.toLocaleString()} reviews, ${pct(
                  item.negative,
                  item.count,
                )} negative sentiment, and ${pct(item.lowRating, item.count)} low ratings.</p>
                <div class="backlog-meta">
                  <span class="chip ${lane === "Must implement" ? "urgent" : ""}">${item.count} reviews</span>
                  <span class="chip">score ${Math.round(item.score)}</span>
                  <span class="chip">quality ${item.quality.toFixed(1)}</span>
                </div>
              </article>
            `,
          )
          .join("") ||
        `<div class="empty-state">No categories in this lane.</div>`;

      return `
        <section class="backlog-lane" aria-label="${lane}">
          <div class="lane-title">
            <span>${lane}</span>
            <span class="lane-count ${laneClasses[lane]}">${laneItems.length}</span>
          </div>
          <div class="backlog-stack">${list}</div>
        </section>
      `;
    })
    .join("");
}

function render() {
  applyFilters();
  renderMetrics(state.filtered);
  renderCategoryChart(state.filtered);
  renderDonut(state.filtered);
  renderBacklog(state.filtered);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function init() {
  try {
    const response = await fetch(DATA_URL, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Could not load ${DATA_URL}: HTTP ${response.status}`);
    }

    const csv = await response.text();
    state.rows = parseCsv(csv).map(normalizeRow);

    if (!state.rows.length) {
      throw new Error("The review CSV loaded but did not contain any rows.");
    }

    state.filtered = state.rows;
    setupFilters();
    render();
  } catch (error) {
    document.querySelector(".main").innerHTML = `
      <section class="panel">
        <h1>Unable to load review data</h1>
        <p class="empty-state">${escapeHtml(error.message)}</p>
      </section>
    `;
  }
}

init();
