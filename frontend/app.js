const DATA_URL = "/data/instagram_reviews_rag.csv";
const BACKLOG_URL = "/data/backlog_recommendations.json";

const SENTIMENT_COLORS = {
  negative: "#d14f45",
  neutral: "#ad741f",
  positive: "#187d69",
};

const CATEGORY_COLORS = [
  "#3157d5",
  "#5675dc",
  "#7189df",
  "#8ea1e7",
  "#2748b4",
  "#536eb9",
  "#7e8fbd",
  "#415b9d",
  "#7584a7",
  "#9da8c1",
];

const state = {
  rows: [],
  filtered: [],
  backlogItems: [],
  backlogMetadata: null,
  category: "All",
  sentiment: "All",
  priority: "All",
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
  clearFilters: getElement("#clearFilters"),
  criticalCount: getElement("#criticalCount"),
  criticalShare: getElement("#criticalShare"),
  topIssue: getElement("#topIssue"),
  topIssueShare: getElement("#topIssueShare"),
  avgRating: getElement("#avgRating"),
  ratingContext: getElement("#ratingContext"),
  categoryTotal: getElement("#categoryTotal"),
  categoryPanelTitle: getElement("#categoryPanelTitle"),
  categoryPanelSubtitle: getElement("#categoryPanelSubtitle"),
  categoryChart: getElement("#categoryChart"),
  sentimentChart: getElement("#sentimentChart"),
  sourceReviewCount: getElement("#sourceReviewCount"),
  aiSummaryList: getElement("#aiSummaryList"),
  sentimentCategoryChart: getElement("#sentimentCategoryChart"),
  backlogLanes: getElement("#backlogLanes"),
};

const navLinks = document.querySelectorAll("[data-nav-target]");

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
  state.filtered = state.rows.filter((row) => {
    const categoryOk =
      state.category === "All" || row.category === state.category;
    const sentimentOk =
      state.sentiment === "All" || row.sentiment === state.sentiment;
    const priorityOk =
      state.priority === "All" ||
      (row.sentiment === "negative" && row.user_rating <= 2);

    return categoryOk && sentimentOk && priorityOk;
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
    state.priority = "All";
    render();
  });
  els.sentimentFilter.addEventListener("change", (event) => {
    state.sentiment = event.target.value;
    state.priority = "All";
    render();
  });
  els.clearFilters.addEventListener("click", () => {
    resetFilters();
  });

  setupNavigationState();
}

function resetFilters() {
  state.category = "All";
  state.sentiment = "All";
  state.priority = "All";
  els.categoryFilter.value = state.category;
  els.sentimentFilter.value = state.sentiment;
  render();
}

function setupNavigationState() {
  if (!("IntersectionObserver" in window)) {
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

      if (!visible) {
        return;
      }

      navLinks.forEach((link) => {
        const isActive = link.dataset.navTarget === visible.target.id;
        link.classList.toggle("active", isActive);
        if (isActive) {
          link.setAttribute("aria-current", "page");
        } else {
          link.removeAttribute("aria-current");
        }
      });
    },
    {
      rootMargin: "-20% 0px -55% 0px",
      threshold: [0.15, 0.35, 0.6],
    },
  );

  ["overview", "signals", "backlog"].forEach((id) => {
    const section = document.querySelector(`#${id}`);
    if (section) {
      observer.observe(section);
    }
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
  if (state.category !== "All") {
    renderCategoryDetail(rows);
    return;
  }

  const entries = topEntries(countBy(rows, "category"), 10);
  const total = rows.length;
  const max = entries[0]?.[1] || 1;

  els.categoryPanelTitle.textContent = "Issue Category Breakdown";
  els.categoryPanelSubtitle.textContent =
    "Click a bar to focus the dashboard on that theme.";
  els.categoryTotal.textContent = `${total.toLocaleString()} reviews`;
  els.categoryChart.innerHTML = entries
    .map(([category, count], index) => {
      const width = Math.max(4, (count / max) * 100);
      const color = CATEGORY_COLORS[index % CATEGORY_COLORS.length];
      const isActive = state.category === category;

      return `
        <button class="bar-row ${isActive ? "active" : ""}" type="button" data-category="${escapeHtml(category)}" aria-label="Focus ${escapeHtml(category)}, ${count.toLocaleString()} reviews, ${pct(count, total)} of current view">
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
      state.priority = "All";
      els.categoryFilter.value = state.category;
      render();
    });
  });
}

function renderCategoryDetail(rows) {
  const total = rows.length;
  const negativeCount = rows.filter(
    (row) => row.sentiment === "negative",
  ).length;
  const lowRatingCount = rows.filter((row) => row.user_rating <= 2).length;
  const avg = average(rows, "user_rating");
  const action = recommendedActionForCategory(state.category);
  const sampleReviews = [...rows]
    .sort((a, b) => {
      const aScore =
        (a.sentiment === "negative" ? 2 : 0) + (a.user_rating <= 2 ? 2 : 0);
      const bScore =
        (b.sentiment === "negative" ? 2 : 0) + (b.user_rating <= 2 ? 2 : 0);
      return bScore - aScore;
    })
    .slice(0, 3);

  els.categoryPanelTitle.textContent = "Category Deep Dive";
  els.categoryPanelSubtitle.textContent =
    "Focused evidence and action signals for the selected category.";
  els.categoryTotal.textContent = state.category;
  els.categoryChart.innerHTML = `
    <section class="category-detail" aria-label="${escapeHtml(state.category)} details">
      <div class="detail-hero">
        <div>
          <span class="detail-label">Selected category</span>
          <h3>${escapeHtml(state.category)}</h3>
          <p>${escapeHtml(action)}</p>
        </div>
        <button class="ghost-button compact" type="button" data-clear-category>
          Show all
        </button>
      </div>
      <div class="detail-metrics">
        <div>
          <strong>${total.toLocaleString()}</strong>
          <span>reviews</span>
        </div>
        <div>
          <strong>${pct(negativeCount, total)}</strong>
          <span>negative</span>
        </div>
        <div>
          <strong>${pct(lowRatingCount, total)}</strong>
          <span>1-2 star</span>
        </div>
        <div>
          <strong>${avg ? avg.toFixed(1) : "-"}</strong>
          <span>avg rating</span>
        </div>
      </div>
      <div class="review-samples">
        ${sampleReviews
          .map(
            (row) => `
              <article>
                <span>${escapeHtml(row.review_id)} · ${escapeHtml(row.source || "unknown")} · ${row.user_rating || "-"} star</span>
                <p>${escapeHtml(row.review_text || "")}</p>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;

  els.categoryChart
    .querySelector("[data-clear-category]")
    .addEventListener("click", () => {
      state.category = "All";
      state.priority = "All";
      els.categoryFilter.value = state.category;
      render();
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
        <button class="legend-item ${state.sentiment === segment.name ? "active" : ""}" type="button" data-sentiment="${segment.name}" aria-label="Filter to ${segment.name} sentiment, ${pct(segment.value, rows.length)} of current view">
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

function renderSentimentPerCategory(rows) {
  const entries = Object.entries(countBy(rows, "category"))
    .map(([category, total]) => {
      const categoryRows = rows.filter((row) => row.category === category);
      const counts = countBy(categoryRows, "sentiment");
      const positive = counts.positive || 0;
      const neutral = counts.neutral || 0;
      const negative = counts.negative || 0;
      const negativeRatio = total ? negative / total : 0;
      const averageRating = average(categoryRows, "user_rating");
      const severity =
        negativeRatio >= 0.8
          ? "Critical"
          : negativeRatio >= 0.55
            ? "Watch"
            : "Mixed";

      return {
        category,
        total,
        positive,
        neutral,
        negative,
        negativeRatio,
        averageRating,
        severity,
      };
    })
    .sort((a, b) => {
      const priorityOrder = { Critical: 0, Watch: 1, Mixed: 2 };
      const priorityDifference =
        priorityOrder[a.severity] - priorityOrder[b.severity];

      if (priorityDifference !== 0) {
        return priorityDifference;
      }

      if (b.negativeRatio !== a.negativeRatio) {
        return b.negativeRatio - a.negativeRatio;
      }

      return b.negative - a.negative;
    })
    .slice(0, 8);

  const rowsHtml = entries
    .map((entry) => {
      return `
        <button class="sentiment-row" type="button" data-category="${escapeHtml(entry.category)}" aria-label="Open ${escapeHtml(entry.category)} deep dive: ${entry.total.toLocaleString()} reviews, ${pct(entry.negative, entry.total)} negative, ${pct(entry.positive, entry.total)} positive, average rating ${entry.averageRating.toFixed(1)}, ${entry.severity} priority">
          <span class="sentiment-category">
            <strong>${escapeHtml(entry.category)}</strong>
            <small>${entry.total.toLocaleString()} reviews analyzed</small>
          </span>
          <span class="sentiment-value">${entry.total.toLocaleString()}</span>
          <span class="sentiment-value negative">${pct(entry.negative, entry.total)}</span>
          <span class="sentiment-value positive">${pct(entry.positive, entry.total)}</span>
          <span class="sentiment-value">${entry.averageRating.toFixed(1)}</span>
          <span class="severity-pill ${entry.severity.toLowerCase()}">${entry.severity}</span>
        </button>
      `;
    })
    .join("");

  els.sentimentCategoryChart.innerHTML = `
    <div class="sentiment-table-head" aria-hidden="true">
      <span>Issue category</span>
      <span>Total</span>
      <span>Negative share</span>
      <span>Positive share</span>
      <span>Avg rating</span>
      <span>Priority</span>
    </div>
    ${rowsHtml}
  `;

  els.sentimentCategoryChart
    .querySelectorAll("[data-category]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        state.category = button.dataset.category;
        state.priority = "All";
        els.categoryFilter.value = state.category;
        render();
        document.querySelector("#overview").scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    });
}

function productImplication(rows) {
  const lowRatingCount = rows.filter((row) => row.user_rating <= 2).length;
  const negativeCount = rows.filter(
    (row) => row.sentiment === "negative",
  ).length;

  if (!rows.length) {
    return "No product implication is available for the current filters.";
  }

  if (
    negativeCount / rows.length >= 0.7 ||
    lowRatingCount / rows.length >= 0.5
  ) {
    return "This view is dominated by high-severity dissatisfaction, so the product story should focus on reducing trust, access, or reliability pain before adding new features.";
  }

  return "This view has a mixed signal, so product teams should compare complaint severity with implementation effort before prioritizing roadmap work.";
}

function renderAiSummary(rows) {
  const categoryCounts = countBy(rows, "category");
  const topCategories = topEntries(categoryCounts, 3);
  const sentimentCounts = countBy(rows, "sentiment");
  const topNegativeCategories = topEntries(
    rows
      .filter((row) => row.sentiment === "negative")
      .reduce((acc, row) => {
        acc[row.category] = (acc[row.category] || 0) + 1;
        return acc;
      }, {}),
    3,
  );
  const positiveRows = rows.filter((row) => row.sentiment === "positive");
  const positiveTop = topEntries(countBy(positiveRows, "category"), 1)[0]?.[0];
  const negativeShare = pct(sentimentCounts.negative || 0, rows.length);
  const topCategoryText = topCategories
    .map(([category, count]) => `${category} (${pct(count, rows.length)})`)
    .join(", ");
  const negativeCategoryText = topNegativeCategories
    .map(([category]) => category)
    .join(", ");

  els.aiSummaryList.innerHTML = [
    `Most feedback in this view clusters around ${topCategoryText || "the selected filters"}.`,
    `${negativeShare} of the current review set is negative, with the strongest concentration in ${negativeCategoryText || "the leading issue categories"}.`,
    productImplication(rows),
    positiveTop
      ? `Positive reviews mainly cluster around ${positiveTop}, which is the best place to identify what users still value.`
      : "Positive review volume is low in this view, so the product story should focus on reducing pain before amplifying strengths.",
  ]
    .map(
      (insight) =>
        `<article><span></span><p>${escapeHtml(insight)}</p></article>`,
    )
    .join("");
}

function recommendedActionForCategory(category) {
  const item = state.backlogItems.find((backlogItem) =>
    (backlogItem.categories || []).includes(category),
  );

  return (
    item?.action ||
    `Use the backlog recommendations to investigate recurring ${category} feedback.`
  );
}

function itemMatchesCurrentFilters(item) {
  const categoryOk =
    state.category === "All" ||
    (item.categories || []).includes(state.category);
  const sentimentOk =
    state.sentiment === "All" ||
    state.sentiment === "negative" ||
    (item.evidence || "").toLowerCase().includes(state.sentiment);

  return categoryOk && sentimentOk;
}

function renderBacklog() {
  const lanes = ["Must implement", "Should have", "Nice to have"];
  const laneClasses = {
    "Must implement": "must",
    "Should have": "should",
    "Nice to have": "nice",
  };
  const items = state.backlogItems.filter(itemMatchesCurrentFilters);

  els.backlogLanes.innerHTML = lanes
    .map((lane) => {
      const laneItems = items.filter((item) => item.lane === lane);
      const previewItems = laneItems.slice(0, 1);
      const list =
        previewItems
          .map(
            (item) => `
              <article class="backlog-item backlog-preview-item">
                <h4>${escapeHtml(item.action)}</h4>
                <p>${escapeHtml(item.evidence || "")}</p>
                <div class="backlog-meta">
                  ${(item.categories || [])
                    .slice(0, 2)
                    .map(
                      (category) =>
                        `<span class="chip ${lane === "Must implement" ? "urgent" : ""}">${escapeHtml(category)}</span>`,
                    )
                    .join("")}
                  <a class="chip chip-link" href="./backlog.html">View details</a>
                </div>
              </article>
            `,
          )
          .join("") ||
        `<div class="empty-state">No categories in this lane.</div>`;

      return `
        <section class="backlog-lane" aria-label="${lane}">
          <div class="lane-title">
            <h3>${lane}</h3>
            <span class="lane-count ${laneClasses[lane]}">${laneItems.length}</span>
          </div>
          <div class="backlog-stack">${list}</div>
        </section>
      `;
    })
    .join("");

  els.backlogLanes.querySelectorAll("[data-category]").forEach((button) => {
    button.addEventListener("click", () => {
      state.category = button.dataset.category;
      state.priority = "All";
      els.categoryFilter.value = state.category;
      document.querySelector("#overview").scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
      render();
    });
  });
}

function render() {
  applyFilters();
  renderMetrics(state.filtered);
  renderCategoryChart(state.filtered);
  renderDonut(state.filtered);
  renderAiSummary(state.filtered);
  renderSentimentPerCategory(state.filtered);
  renderBacklog();
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
    const [response, backlogResponse] = await Promise.all([
      fetch(DATA_URL, {
        cache: "no-store",
      }),
      fetch(BACKLOG_URL, {
        cache: "no-store",
      }),
    ]);
    if (!response.ok) {
      throw new Error(`Could not load ${DATA_URL}: HTTP ${response.status}`);
    }
    if (!backlogResponse.ok) {
      throw new Error(
        `Could not load ${BACKLOG_URL}: HTTP ${backlogResponse.status}`,
      );
    }

    const csv = await response.text();
    const backlogData = await backlogResponse.json();
    state.rows = parseCsv(csv).map(normalizeRow);
    state.backlogItems = backlogData.recommendations || [];
    state.backlogMetadata = backlogData.metadata || null;

    if (!state.rows.length) {
      throw new Error("The review CSV loaded but did not contain any rows.");
    }

    els.sourceReviewCount.textContent = `${state.rows.length.toLocaleString()} reviews`;
    state.filtered = state.rows;
    setupFilters();
    render();
    document.body.classList.remove("is-loading");
  } catch (error) {
    document.body.classList.remove("is-loading");
    document.querySelector(".main").innerHTML = `
      <section class="panel">
        <h1>Unable to load review data</h1>
        <p class="empty-state">${escapeHtml(error.message)}</p>
      </section>
    `;
  }
}

init();
