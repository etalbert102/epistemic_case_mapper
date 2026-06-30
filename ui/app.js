let uiData = null;
let activeCaseKey = null;
let query = "";

const elements = {
  caseTabs: document.getElementById("caseTabs"),
  reviewStatus: document.getElementById("reviewStatus"),
  searchInput: document.getElementById("searchInput"),
  heroEyebrow: document.getElementById("heroEyebrow"),
  heroTitle: document.getElementById("judgeModeTitle"),
  heroBody: document.getElementById("heroBody"),
  heroLinks: document.getElementById("heroLinks"),
  heroCards: document.getElementById("heroCards"),
  caseTitle: document.getElementById("caseTitle"),
  caseQuestion: document.getElementById("caseQuestion"),
  metricGrid: document.getElementById("metricGrid"),
  clusterGrid: document.getElementById("clusterGrid"),
  claimList: document.getElementById("claimList"),
  cruxList: document.getElementById("cruxList"),
  spotlightTable: document.getElementById("spotlightTable"),
  lossList: document.getElementById("lossList"),
  taskList: document.getElementById("taskList"),
  fullMapLink: document.getElementById("fullMapLink"),
  workedMapLink: document.getElementById("workedMapLink"),
  auditLink: document.getElementById("auditLink"),
  bestRegionsLink: document.getElementById("bestRegionsLink"),
  fullBaselineLink: document.getElementById("fullBaselineLink"),
  workedBaselineLink: document.getElementById("workedBaselineLink"),
  multiModelAuditLink: document.getElementById("multiModelAuditLink"),
  taskQueueLink: document.getElementById("taskQueueLink"),
  reviewPacketLink: document.getElementById("reviewPacketLink"),
  reviewChecklistLink: document.getElementById("reviewChecklistLink"),
  qualityPanel: document.getElementById("qualityPanel"),
  qualitySummary: document.getElementById("qualitySummary"),
  qualityWarningList: document.getElementById("qualityWarningList"),
  qualityScorecardLink: document.getElementById("qualityScorecardLink"),
};

async function boot() {
  const response = await fetch("data.json");
  uiData = await response.json();
  activeCaseKey = uiData.cases[0].caseKey;
  elements.searchInput.addEventListener("input", (event) => {
    query = event.target.value.trim().toLowerCase();
    renderCase();
  });
  renderTabs();
  renderHero();
  renderCase();
}

function renderHero() {
  const hero = uiData.hero || {};
  elements.heroEyebrow.textContent = hero.eyebrow || "Inspection Mode";
  elements.heroTitle.textContent = hero.title || uiData.package?.packageLabel || "Epistemic Case Mapper";
  elements.heroBody.textContent = hero.body || "";
  elements.heroLinks.innerHTML = (hero.links || [])
    .map((link) => {
      const primary = link.primary ? " primary" : "";
      return `<a class="action-link${primary}" href="${artifactHref(link.path)}" target="_blank" rel="noreferrer">${escapeHtml(link.label)}</a>`;
    })
    .join("");
  elements.heroCards.innerHTML = (hero.cards || [])
    .map(
      (card) => `
        <div>
          <span>${escapeHtml(card.label)}</span>
          <p>${formatInline(card.text || "")}</p>
        </div>
      `,
    )
    .join("");
}

function renderTabs() {
  elements.caseTabs.innerHTML = uiData.cases
    .map((caseItem) => {
      const active = caseItem.caseKey === activeCaseKey ? "is-active" : "";
      return `
        <button class="case-tab ${active}" data-case-key="${escapeHtml(caseItem.caseKey)}">
          <span>${escapeHtml(caseItem.shortLabel)}</span>
          <span>${caseItem.sources.length} sources</span>
        </button>
      `;
    })
    .join("");
  elements.caseTabs.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeCaseKey = button.dataset.caseKey;
      renderTabs();
      renderCase();
    });
  });
}

function renderCase() {
  const caseItem = uiData.cases.find((item) => item.caseKey === activeCaseKey);
  if (!caseItem) return;

  document.body.dataset.theme = caseItem.theme || "default";
  elements.reviewStatus.textContent =
    "Artifacts are inspectable but remain human-review-needed until packet decisions are recorded.";
  elements.caseTitle.textContent = caseItem.label;
  elements.caseQuestion.textContent = caseItem.question;
  setArtifactLink(elements.fullMapLink, caseItem.artifacts.fullMap);
  setArtifactLink(elements.workedMapLink, caseItem.artifacts.workedMap);
  setArtifactLink(elements.auditLink, caseItem.artifacts.erosionAudit);
  setArtifactLink(elements.bestRegionsLink, caseItem.artifacts.bestRegions);
  setArtifactLink(elements.fullBaselineLink, caseItem.artifacts.fullCaseBaseline);
  setArtifactLink(elements.workedBaselineLink, caseItem.artifacts.workedBaseline);
  setArtifactLink(elements.multiModelAuditLink, caseItem.artifacts.multiModelAudit);
  setArtifactLink(elements.taskQueueLink, caseItem.artifacts.taskQueue);
  setArtifactLink(elements.reviewPacketLink, caseItem.artifacts.reviewPacket);
  setArtifactLink(elements.reviewChecklistLink, caseItem.artifacts.reviewChecklist);
  setArtifactLink(elements.qualityScorecardLink, caseItem.artifacts.qualityScorecard);

  renderMetrics(caseItem);
  renderQuality(caseItem);
  renderClusters(caseItem);
  renderClaims(caseItem);
  renderSpotlights(caseItem);
  renderLosses(caseItem);
  renderTasks(caseItem);
}

function renderQuality(caseItem) {
  const warnings = caseItem.qualityWarnings || [];
  const quality = caseItem.quality || {};
  const hasQuality = quality.exists || warnings.length > 0;
  elements.qualityPanel.hidden = !hasQuality;
  if (!hasQuality) return;

  const overall = quality.overallResult || "not recorded";
  const riskCount = warnings.filter((warning) => ["risk", "fail"].includes(warning.severity)).length;
  elements.qualitySummary.innerHTML = `
    <div class="metric"><strong>${escapeHtml(overall)}</strong><span>Overall result</span></div>
    <div class="metric"><strong>${riskCount}</strong><span>Risk/fail warnings</span></div>
  `;
  elements.qualityWarningList.innerHTML = warnings.length
    ? warnings
        .slice(0, 8)
        .map(
          (warning) => `
            <article class="list-card quality-warning" data-severity="${escapeHtml(warning.severity)}">
              <h4>${escapeHtml(warning.severity)} · ${escapeHtml(warning.label)}</h4>
              <p>${escapeHtml(warning.evidence || "")}</p>
              <div class="tag-row">
                <span class="tag">${escapeHtml(warning.signal_type || "")}</span>
              </div>
            </article>
          `,
        )
        .join("")
    : emptyState("No quality warnings recorded.");
}

function renderMetrics(caseItem) {
  const metrics = [
    ["Sources", caseItem.sources.length],
    ["Full-case clusters", caseItem.clusters.length],
    ["Worked claims", caseItem.worked.claims.length],
    ["Task queue items", caseItem.tasks.length],
  ];
  elements.metricGrid.innerHTML = metrics
    .map(([label, value]) => `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`)
    .join("");
}

function renderClusters(caseItem) {
  const clusters = filterItems(caseItem.clusters, ["topic", "cluster_claim", "decision_space_preserved", "sources"]);
  elements.clusterGrid.innerHTML = clusters.length
    ? clusters
        .map(
          (cluster) => `
            <article class="cluster-card" data-status="${escapeHtml(cluster.map_status || "")}">
              <h4>${escapeHtml(cluster.topic || cluster.cluster_id)}</h4>
              <p>${escapeHtml(cluster.cluster_claim || cluster.decision_space_preserved || "")}</p>
              <div class="tag-row">
                <span class="tag">${escapeHtml(cluster.map_status || "broad scaffold")}</span>
                <span class="tag">${escapeHtml(cluster.cluster_id)}</span>
              </div>
            </article>
          `,
        )
        .join("")
    : emptyState("No clusters match the current filter.");
}

function renderClaims(caseItem) {
  const claims = filterItems(caseItem.worked.claims, ["claim", "role", "source_id"]).slice(0, 7);
  elements.claimList.innerHTML = claims.length
    ? claims
        .map(
          (claim) => `
            <article class="list-card">
              <h4>${escapeHtml(claim.claim_id)} · ${escapeHtml(claim.role || "claim")}</h4>
              <p>${escapeHtml(claim.claim || "")}</p>
              <div class="tag-row">
                <span class="tag">${escapeHtml(claim.source_id || "")}</span>
                <span class="tag">${escapeHtml(claim.entailed_by_excerpt || "unreviewed")}</span>
              </div>
            </article>
          `,
        )
        .join("")
    : emptyState("No claims match the current filter.");

  const cruxes = filterText(caseItem.worked.cruxes).slice(0, 4);
  elements.cruxList.innerHTML = cruxes.length
    ? cruxes.map((crux) => `<article class="list-card"><p>${formatInline(crux)}</p></article>`).join("")
    : emptyState("No cruxes match the current filter.");
}

function renderSpotlights(caseItem) {
  elements.spotlightTable.innerHTML = caseItem.spotlights
    .map(
      (row) => `
        <div class="comparison-row">
          <p><strong>Distinction</strong>${escapeHtml(row.distinction)}</p>
          <p><strong>Flat synthesis</strong>${escapeHtml(row.flat)}</p>
          <p><strong>Map surface</strong>${formatInline(row.map)}</p>
          <p><strong>Status</strong>${escapeHtml(row.status)}</p>
        </div>
      `,
    )
    .join("");
}

function renderLosses(caseItem) {
  const losses = filterItems(caseItem.erosion.losses, ["loss_id", "loss_type", "lost_item", "case_map_preserves"]);
  elements.lossList.innerHTML = losses.length
    ? losses
        .slice(0, 8)
        .map(
          (loss) => `
            <article class="list-card">
              <h4>${escapeHtml(loss.loss_id)} · ${escapeHtml(loss.loss_type || "")}</h4>
              <p>${escapeHtml(loss.lost_item || "")}</p>
              <div class="tag-row">
                <span class="tag">${escapeHtml(loss.adversarial_check || "human review needed")}</span>
              </div>
            </article>
          `,
        )
        .join("")
    : emptyState("No losses match the current filter.");
}

function renderTasks(caseItem) {
  const tasks = filterItems(caseItem.tasks, ["task_id", "task_type", "task", "realism_value", "cluster"]);
  elements.taskList.innerHTML = tasks.length
    ? tasks
        .map(
          (task) => `
            <article class="list-card">
              <h4>${escapeHtml(task.task_id)} · ${escapeHtml(task.priority || "priority")}</h4>
              <p>${escapeHtml(task.task || "")}</p>
              <div class="tag-row">
                <span class="tag">${escapeHtml(task.task_type || "")}</span>
                <span class="tag">${escapeHtml(task.cluster || "")}</span>
              </div>
            </article>
          `,
        )
        .join("")
    : emptyState("No tasks match the current filter.");
}

function filterItems(items, keys) {
  if (!query) return items;
  return items.filter((item) =>
    keys.some((key) =>
      String(item[key] || "")
        .toLowerCase()
        .includes(query),
    ),
  );
}

function filterText(items) {
  if (!query) return items;
  return items.filter((item) => String(item).toLowerCase().includes(query));
}

function artifactHref(path) {
  return `../${path}`;
}

function setArtifactLink(element, path) {
  if (!path) {
    element.hidden = true;
    element.removeAttribute("href");
    return;
  }
  element.hidden = false;
  element.href = artifactHref(path);
}

function emptyState(text) {
  return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function formatInline(text) {
  return escapeHtml(text).replace(/`([^`]+)`/g, "<code>$1</code>");
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

boot().catch((error) => {
  document.body.innerHTML = `<main class="dashboard"><section class="panel"><h1>Unable to load UI data</h1><p>${escapeHtml(
    error.message,
  )}</p></section></main>`;
});
