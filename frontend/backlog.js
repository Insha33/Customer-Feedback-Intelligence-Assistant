const BACKLOG_URL = "/data/backlog_recommendations.json";

const lanes = ["Must implement", "Should have", "Nice to have"];
const laneClasses = {
  "Must implement": "must",
  "Should have": "should",
  "Nice to have": "nice",
};

const meta = document.querySelector("#backlogMeta");
const container = document.querySelector("#backlogDetailLanes");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderBacklog(data) {
  const recommendations = data.recommendations || [];
  const metadata = data.metadata || {};

  meta.textContent = `${metadata.total_reviews?.toLocaleString() || "-"} reviews analyzed · generated from ${metadata.source_csv || "review dataset"}`;

  container.innerHTML = lanes
    .map((lane) => {
      const items = recommendations.filter((item) => item.lane === lane);
      const cards = items
        .map(
          (item) => `
            <article class="backlog-detail-card">
              <div class="backlog-detail-card-header">
                <h3>${escapeHtml(item.action)}</h3>
                <span class="lane-count ${laneClasses[lane]}">${escapeHtml(item.confidence || "medium")}</span>
              </div>
              <dl>
                <div>
                  <dt>Evidence</dt>
                  <dd>${escapeHtml(item.evidence)}</dd>
                </div>
                <div>
                  <dt>Expected impact</dt>
                  <dd>${escapeHtml(item.impact)}</dd>
                </div>
              </dl>
              <div class="backlog-meta">
                ${(item.categories || [])
                  .map(
                    (category) =>
                      `<span class="chip">${escapeHtml(category)}</span>`,
                  )
                  .join("")}
              </div>
            </article>
          `,
        )
        .join("");

      return `
        <section class="backlog-detail-lane">
          <div class="lane-title">
            <span>${lane}</span>
            <span class="lane-count ${laneClasses[lane]}">${items.length}</span>
          </div>
          <div class="backlog-detail-stack">${cards}</div>
        </section>
      `;
    })
    .join("");
}

async function init() {
  try {
    const response = await fetch(BACKLOG_URL, {
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`Could not load ${BACKLOG_URL}: HTTP ${response.status}`);
    }

    renderBacklog(await response.json());
  } catch (error) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

init();
