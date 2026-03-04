const METRICS = {
  total: { label: "综合榜单", key: "total", unit: "score" },
  velocity: { label: "升星最快", key: "velocity", unit: "stars/day" },
  interesting: { label: "有趣度", key: "interesting", unit: "score" },
  advanced: { label: "先进性", key: "advanced", unit: "score" },
  productive: { label: "生产力", key: "productive", unit: "score" },
};

const LEADERBOARD_LABELS = {
  fastest: "升星最快",
  interesting: "最有趣",
  advanced: "最先进",
  productive: "最高生产力",
  overall: "综合最佳",
};

const state = {
  payload: null,
  metric: "total",
  language: "all",
  segment: "all",
  search: "",
  minStars: 0,
};

function formatNumber(value, digits = 0) {
  return Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatDate(value) {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function textIncludes(target, keyword) {
  if (!keyword) {
    return true;
  }
  return target.toLowerCase().includes(keyword);
}

function scoreClass(segment) {
  if (segment === "Trend") {
    return "segment-trend";
  }
  if (segment === "Frontier") {
    return "segment-frontier";
  }
  return "segment-builder";
}

function applyFilters(rows) {
  const query = state.search.trim().toLowerCase();
  return rows.filter((row) => {
    if (state.language !== "all" && (row.language || "Unknown") !== state.language) {
      return false;
    }
    if (state.segment !== "all" && row.segment !== state.segment) {
      return false;
    }
    if ((row.stars || 0) < state.minStars) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = [
      row.full_name || "",
      row.description || "",
      (row.topics || []).join(" "),
      row.language || "",
    ].join(" ").toLowerCase();
    return textIncludes(haystack, query);
  });
}

function sortRows(rows) {
  const metricKey = METRICS[state.metric].key;
  return [...rows].sort((a, b) => {
    const diff = (b[metricKey] || 0) - (a[metricKey] || 0);
    if (diff !== 0) {
      return diff;
    }
    return (b.stars || 0) - (a.stars || 0);
  });
}

function renderSummary(payload) {
  const candidateCount = payload.candidate_count || 0;
  const topRepo = (payload.leaderboards?.overall || [])[0];
  const segmentCounts = payload.site_meta?.segment_counts || {};

  document.getElementById("capturedAt").textContent = formatDate(payload.captured_at);
  document.getElementById("previousAt").textContent = formatDate(payload.previous_snapshot);
  document.getElementById("candidateCount").textContent = formatNumber(candidateCount);
  document.getElementById("medianVelocity").textContent = formatNumber(payload.median_velocity || 0, 2);
  document.getElementById("topRepoName").textContent = topRepo ? topRepo.full_name : "-";
  document.getElementById("topRepoScore").textContent = topRepo ? `Score: ${formatNumber(topRepo.total, 2)}` : "Score: -";
  document.getElementById("segmentOverview").textContent =
    `Trend ${segmentCounts.Trend || 0} / Frontier ${segmentCounts.Frontier || 0} / Builder ${segmentCounts.Builder || 0}`;
}

function renderSpotlight(payload) {
  const grid = document.getElementById("spotlightGrid");
  grid.innerHTML = "";
  const leaderboards = payload.leaderboards || {};
  Object.entries(LEADERBOARD_LABELS).forEach(([key, label]) => {
    const top = (leaderboards[key] || [])[0];
    const card = document.createElement("article");
    card.className = "spotlight-card";
    if (!top) {
      card.innerHTML = `<h3>${label}</h3><p class="spotlight-meta">暂无数据</p>`;
      grid.appendChild(card);
      return;
    }
    const metricValue = key === "fastest" ? formatNumber(top.velocity, 2) : formatNumber(top.total || top[key], 2);
    card.innerHTML = `
      <h3>${label}</h3>
      <a href="${top.url}" target="_blank" rel="noopener">${top.full_name}</a>
      <p class="spotlight-meta">Stars ${formatNumber(top.stars)} · ${
        key === "fastest" ? `${metricValue} stars/day` : `Score ${metricValue}`
      }</p>
    `;
    grid.appendChild(card);
  });
}

function createBadge(text, strong = false, extraClass = "") {
  const span = document.createElement("span");
  span.className = `badge ${strong ? "badge-strong" : ""} ${extraClass}`.trim();
  span.textContent = text;
  return span;
}

function renderRows(payload) {
  const rows = payload.rows || [];
  const filtered = sortRows(applyFilters(rows));
  const grid = document.getElementById("repoGrid");
  const title = document.getElementById("listTitle");
  const resultCount = document.getElementById("resultCount");
  const template = document.getElementById("repoCardTemplate");

  title.textContent = METRICS[state.metric].label;
  resultCount.textContent = `${formatNumber(filtered.length)} 项`;
  grid.innerHTML = "";

  if (filtered.length === 0) {
    const empty = document.createElement("article");
    empty.className = "repo-card";
    empty.innerHTML = "<p class=\"repo-desc\">没有符合条件的项目，试试放宽筛选条件。</p>";
    grid.appendChild(empty);
    return;
  }

  filtered.slice(0, 120).forEach((row) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const link = node.querySelector(".repo-name");
    const segment = node.querySelector(".badge-segment");
    const desc = node.querySelector(".repo-desc");
    const metricWrap = node.querySelector(".repo-metrics");
    const tagsWrap = node.querySelector(".repo-tags");

    link.textContent = row.full_name;
    link.href = row.url;
    segment.textContent = row.segment || "Builder";
    segment.classList.add(scoreClass(row.segment));
    desc.textContent = row.description || "No description";

    metricWrap.append(
      createBadge(`Stars ${formatNumber(row.stars)}`, true),
      createBadge(`Trend ${formatNumber(row.interesting, 1)}`),
      createBadge(`Frontier ${formatNumber(row.advanced, 1)}`),
      createBadge(`Builder ${formatNumber(row.productive, 1)}`),
      createBadge(`Velocity ${formatNumber(row.velocity, 2)}/day`)
    );

    tagsWrap.append(createBadge(row.language || "Unknown"));
    (row.topics || []).slice(0, 3).forEach((topic) => tagsWrap.append(createBadge(`#${topic}`)));
    grid.appendChild(node);
  });
}

function setupFilters(payload) {
  const languages = payload.filters?.languages || [];
  const languageSelect = document.getElementById("languageSelect");
  languages.forEach((language) => {
    const option = document.createElement("option");
    option.value = language;
    option.textContent = language;
    languageSelect.appendChild(option);
  });

  const starsRange = document.getElementById("starsRange");
  const maxStars = Math.max(...(payload.rows || []).map((row) => row.stars || 0), 500);
  starsRange.max = String(Math.ceil(maxStars / 100) * 100);
  document.getElementById("starsValue").textContent = "0";
}

function bindEvents() {
  document.getElementById("metricTabs").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-metric]");
    if (!button) {
      return;
    }
    state.metric = button.dataset.metric;
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");
    renderRows(state.payload);
  });

  document.getElementById("searchInput").addEventListener("input", (event) => {
    state.search = event.target.value || "";
    renderRows(state.payload);
  });

  document.getElementById("languageSelect").addEventListener("change", (event) => {
    state.language = event.target.value || "all";
    renderRows(state.payload);
  });

  document.getElementById("segmentSelect").addEventListener("change", (event) => {
    state.segment = event.target.value || "all";
    renderRows(state.payload);
  });

  document.getElementById("starsRange").addEventListener("input", (event) => {
    state.minStars = Number(event.target.value || 0);
    document.getElementById("starsValue").textContent = formatNumber(state.minStars);
    renderRows(state.payload);
  });
}

function setupReveal() {
  const nodes = [...document.querySelectorAll(".reveal")];
  nodes.forEach((node, index) => {
    node.style.animationDelay = `${index * 70}ms`;
  });
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });
  nodes.forEach((node) => observer.observe(node));
}

async function loadPayload() {
  const response = await fetch(`./data/latest.json?t=${Date.now()}`);
  if (!response.ok) {
    throw new Error(`Failed to load report: ${response.status}`);
  }
  return response.json();
}

async function main() {
  setupReveal();
  try {
    const payload = await loadPayload();
    state.payload = payload;
    setupFilters(payload);
    bindEvents();
    renderSummary(payload);
    renderSpotlight(payload);
    renderRows(payload);
  } catch (error) {
    const grid = document.getElementById("repoGrid");
    grid.innerHTML = `<article class="repo-card"><p class="repo-desc">数据加载失败：${error.message}</p></article>`;
  }
}

main();
