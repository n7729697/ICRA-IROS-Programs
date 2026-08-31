(() => {
  "use strict";

  const PAGE_SIZE = { sessions: 45, papers: 120, saved: 120 };
  const FAVORITES_KEY = "robotics-program-atlas:favorites";
  const cache = new Map();
  const state = {
    index: null,
    catalog: null,
    conferenceKey: "",
    query: "",
    day: "all",
    view: "sessions",
    visible: PAGE_SIZE.sessions,
    favorites: readFavorites(),
  };

  const elements = {
    tabs: document.querySelector("#conference-tabs"),
    freshness: document.querySelector("#data-freshness"),
    seriesBadge: document.querySelector("#series-badge"),
    sourceBadge: document.querySelector("#source-badge"),
    title: document.querySelector("#conference-title"),
    meta: document.querySelector("#conference-meta"),
    source: document.querySelector("#official-program"),
    stats: document.querySelector("#stats"),
    search: document.querySelector("#search-input"),
    day: document.querySelector("#day-select"),
    views: document.querySelector("#view-switcher"),
    savedCount: document.querySelector("#saved-count"),
    summary: document.querySelector("#result-summary"),
    clear: document.querySelector("#clear-filters"),
    loading: document.querySelector("#loading"),
    error: document.querySelector("#error-state"),
    results: document.querySelector("#results"),
    loadMore: document.querySelector("#load-more"),
    sourceNote: document.querySelector("#source-note"),
    emptyTemplate: document.querySelector("#empty-template"),
  };

  function readFavorites() {
    try {
      const stored = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
      return new Set(Array.isArray(stored) ? stored : []);
    } catch {
      return new Set();
    }
  }

  function saveFavorites() {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites]));
  }

  function escapeHTML(value = "") {
    return String(value).replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    })[character]);
  }

  function searchKey(value = "") {
    return String(value)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function formatNumber(value) {
    return new Intl.NumberFormat("en-US").format(value || 0);
  }

  function conferenceFromURL(index) {
    const requested = new URLSearchParams(location.search).get("conference");
    if (index.conferences.some((conference) => conference.key === requested)) return requested;
    return index.conferences.some((conference) => conference.key === "icra-2026")
      ? "icra-2026"
      : (index.conferences[0] && index.conferences[0].key);
  }

  function replaceURL() {
    const url = new URL(location.href);
    url.searchParams.set("conference", state.conferenceKey);
    history.replaceState({}, "", url);
  }

  async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
    return response.json();
  }

  async function initialize() {
    bindEvents();
    updateSavedCount();
    try {
      state.index = await fetchJSON("data/index.json");
      const generated = new Date(state.index.generated_at);
      elements.freshness.textContent = Number.isNaN(generated.getTime())
        ? "Static catalog"
        : `Catalog built ${generated.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}`;
      renderConferenceTabs();
      await selectConference(conferenceFromURL(state.index));
    } catch (error) {
      showError(error);
    }
  }

  function bindEvents() {
    let searchFrame = 0;
    elements.search.addEventListener("input", () => {
      cancelAnimationFrame(searchFrame);
      searchFrame = requestAnimationFrame(() => {
        state.query = elements.search.value.trim();
        resetVisible();
        renderResults();
      });
    });

    elements.day.addEventListener("change", () => {
      state.day = elements.day.value;
      resetVisible();
      renderResults();
    });

    elements.views.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-view]");
      if (!button) return;
      state.view = button.dataset.view;
      for (const item of elements.views.querySelectorAll("button")) {
        item.setAttribute("aria-pressed", String(item === button));
      }
      resetVisible();
      renderResults();
    });

    elements.clear.addEventListener("click", () => {
      state.query = "";
      state.day = "all";
      elements.search.value = "";
      elements.day.value = "all";
      resetVisible();
      renderResults();
      elements.search.focus();
    });

    elements.loadMore.addEventListener("click", () => {
      state.visible += PAGE_SIZE[state.view];
      renderResults();
    });

    elements.results.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-favorite]");
      if (!button) return;
      const id = button.dataset.favorite;
      if (state.favorites.has(id)) state.favorites.delete(id);
      else state.favorites.add(id);
      saveFavorites();
      updateSavedCount();
      if (state.view === "saved") renderResults();
      else {
        document.querySelectorAll(`[data-favorite="${CSS.escape(id)}"]`).forEach((item) => {
          const saved = state.favorites.has(id);
          item.setAttribute("aria-pressed", String(saved));
          item.setAttribute("aria-label", saved ? "Remove from saved program" : "Save to my program");
          item.textContent = saved ? "★" : "☆";
        });
      }
    });

    document.addEventListener("keydown", (event) => {
      const activeTag = document.activeElement && document.activeElement.tagName;
      const editable = /^(INPUT|TEXTAREA|SELECT)$/.test(activeTag || "");
      if (event.key === "/" && !editable) {
        event.preventDefault();
        elements.search.focus();
      }
      if (event.key === "Escape" && document.activeElement === elements.search && elements.search.value) {
        elements.search.value = "";
        state.query = "";
        resetVisible();
        renderResults();
      }
    });
  }

  function renderConferenceTabs() {
    elements.tabs.innerHTML = state.index.conferences.map((conference) => `
      <button
        class="conference-tab"
        type="button"
        role="tab"
        data-conference="${escapeHTML(conference.key)}"
        aria-selected="false"
      >
        <span><strong>${escapeHTML(conference.series)} ${conference.year}</strong><span>${formatNumber(conference.counts.papers)} papers</span></span>
      </button>
    `).join("");

    elements.tabs.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-conference]");
      if (button && button.dataset.conference !== state.conferenceKey) {
        selectConference(button.dataset.conference);
      }
    });
  }

  async function selectConference(key) {
    const metadata = state.index.conferences.find((conference) => conference.key === key);
    if (!metadata) return;
    state.conferenceKey = key;
    state.day = "all";
    elements.day.value = "all";
    resetVisible();
    replaceURL();
    showLoading();
    for (const tab of elements.tabs.querySelectorAll("[data-conference]")) {
      tab.setAttribute("aria-selected", String(tab.dataset.conference === key));
    }
    const activeTab = elements.tabs.querySelector(`[data-conference="${key}"]`);
    if (activeTab && window.matchMedia("(max-width: 680px)").matches) {
      activeTab.scrollIntoView({ block: "nearest", inline: "center" });
    }

    try {
      const catalog = cache.has(key) ? cache.get(key) : await fetchJSON(metadata.data_url);
      cache.set(key, catalog);
      prepareCatalog(catalog);
      state.catalog = catalog;
      renderOverview();
      renderDayOptions();
      renderResults();
      elements.loading.hidden = true;
      elements.results.hidden = false;
    } catch (error) {
      showError(error);
    }
  }

  function prepareCatalog(catalog) {
    catalog.paperById = new Map();
    for (const paper of catalog.papers) {
      paper._search = searchKey([
        paper.title,
        paper.code,
        paper.day,
        paper.keywords.join(" "),
        paper.authors.map((author) => `${author.name} ${author.affiliation}`).join(" "),
      ].join(" "));
      catalog.paperById.set(paper.id, paper);
    }
    for (const session of catalog.sessions) {
      session._search = searchKey([
        session.code,
        session.title,
        session.kind,
        session.room,
        session.chairs.map((chair) => `${chair.name} ${chair.affiliation}`).join(" "),
      ].join(" "));
    }
  }

  function renderOverview() {
    const { conference, counts } = state.catalog;
    elements.seriesBadge.textContent = `${conference.series} ${conference.year}`;
    const archivedSource = conference.root_url.includes("web.archive.org");
    elements.sourceBadge.textContent = archivedSource ? "Archived source" : "Live source";
    elements.title.textContent = conference.title;
    elements.meta.textContent = `${conference.dates} · ${conference.location}`;
    elements.source.href = conference.root_url;
    elements.sourceNote.textContent = conference.source_note;
    const stats = [
      [counts.papers, "Paper records"],
      [counts.sessions, "Sessions"],
      [counts.authors, "Authors"],
      [counts.keywords, "Keywords"],
    ];
    elements.stats.innerHTML = stats.map(([value, label]) => `
      <div class="stat"><strong>${formatNumber(value)}</strong><span>${label}</span></div>
    `).join("");
  }

  function renderDayOptions() {
    const hasProceedings = state.catalog.papers.some((paper) => paper.day_index === null);
    elements.day.innerHTML = [
      '<option value="all">All days</option>',
      ...state.catalog.days.map((day) => `<option value="${day.index}">${escapeHTML(day.label)}</option>`),
      ...(hasProceedings ? ['<option value="proceedings">Proceedings index</option>'] : []),
    ].join("");
    elements.day.value = state.day;
  }

  function showLoading() {
    elements.loading.hidden = false;
    elements.results.hidden = true;
    elements.error.hidden = true;
    elements.loadMore.hidden = true;
    elements.summary.textContent = "Loading program…";
  }

  function showError(error) {
    elements.loading.hidden = true;
    elements.results.hidden = true;
    elements.error.hidden = false;
    elements.error.innerHTML = `<div><strong>Program data could not be loaded.</strong><br>${escapeHTML(error.message || error)}</div>`;
    elements.summary.textContent = "Loading failed";
  }

  function resetVisible() {
    state.visible = PAGE_SIZE[state.view];
  }

  function dayMatches(item) {
    if (state.day === "all") return true;
    if (state.day === "proceedings") return item.day_index === null;
    return item.day_index === Number(state.day);
  }

  function queryTokens() {
    return searchKey(state.query).split(" ").filter(Boolean);
  }

  function textMatches(haystack, tokens) {
    return tokens.every((token) => haystack.includes(token));
  }

  function filteredPapers() {
    const tokens = queryTokens();
    return state.catalog.papers.filter((paper) => {
      if (!dayMatches(paper)) return false;
      if (state.view === "saved" && !state.favorites.has(paper.id)) return false;
      return !tokens.length || textMatches(paper._search, tokens);
    });
  }

  function filteredSessions() {
    const tokens = queryTokens();
    const output = [];
    for (const session of state.catalog.sessions) {
      if (!dayMatches(session)) continue;
      const allPapers = session.paper_ids.map((id) => state.catalog.paperById.get(id)).filter(Boolean);
      const sessionMatches = !tokens.length || textMatches(session._search, tokens);
      const matchingPapers = tokens.length
        ? allPapers.filter((paper) => textMatches(paper._search, tokens))
        : allPapers;
      if (sessionMatches || matchingPapers.length) {
        output.push({ session, papers: sessionMatches ? allPapers : matchingPapers });
      }
    }
    return output;
  }

  function renderResults() {
    if (!state.catalog) return;
    elements.clear.hidden = !state.query && state.day === "all";
    if (state.view === "sessions") renderSessions();
    else renderPaperGrid();
  }

  function renderSessions() {
    const matches = filteredSessions();
    const visible = matches.slice(0, state.visible);
    elements.summary.innerHTML = `<strong>${formatNumber(matches.length)}</strong> matching sessions`;
    elements.loadMore.hidden = visible.length >= matches.length;
    elements.loadMore.textContent = `Show more sessions (${formatNumber(matches.length - visible.length)} remaining)`;

    if (!matches.length) {
      renderEmpty();
      return;
    }

    const groups = new Map();
    for (const item of visible) {
      const day = item.session.day || "Program";
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(item);
    }

    elements.results.innerHTML = [...groups.entries()].map(([day, items]) => `
      <section class="day-group">
        <h3 class="day-heading">${escapeHTML(day)}</h3>
        ${items.map(({ session, papers }) => renderSession(session, papers)).join("")}
      </section>
    `).join("");
  }

  function renderSession(session, papers) {
    const context = [session.time, session.room, `${papers.length} ${papers.length === 1 ? "entry" : "entries"}`].filter(Boolean);
    const chairs = session.chairs.map((chair) => `${chair.role}: ${chair.name}`).join(" · ");
    const open = state.query ? " open" : "";
    return `
      <details class="session-card"${open}>
        <summary>
          <span class="session-code">${escapeHTML(session.code)}</span>
          <span class="session-title">
            <strong>${escapeHTML(session.title)}</strong>
            <span>${escapeHTML([session.kind, chairs].filter(Boolean).join(" · "))}</span>
          </span>
          <span class="session-side">${escapeHTML(context.join(" · "))}</span>
        </summary>
        <div class="paper-list">
          ${papers.length ? papers.map((paper) => renderPaper(paper)).join("") : '<div class="paper-item"><div class="paper-main"><p class="authors">No paper entries were listed for this session.</p></div></div>'}
        </div>
      </details>
    `;
  }

  function renderPaperGrid() {
    const matches = filteredPapers();
    const visible = matches.slice(0, state.visible);
    const label = state.view === "saved" ? "saved entries in this edition" : "matching paper records";
    elements.summary.innerHTML = `<strong>${formatNumber(matches.length)}</strong> ${label}`;
    elements.loadMore.hidden = visible.length >= matches.length;
    elements.loadMore.textContent = `Show more papers (${formatNumber(matches.length - visible.length)} remaining)`;

    if (!matches.length) {
      renderEmpty(state.view === "saved");
      return;
    }
    elements.results.innerHTML = `<div class="paper-grid">${visible.map((paper) => renderPaper(paper, true)).join("")}</div>`;
  }

  function renderPaper(paper, card = false) {
    const authors = paper.authors.map((author) => author.name).join(", ");
    const keywords = paper.keywords.slice(0, 6);
    const saved = state.favorites.has(paper.id);
    let status = "";
    if (paper.is_placeholder) status = "Title unavailable in the archived index";
    else if (paper.schedule_status === "index-reconstructed") status = "Schedule link reconstructed from the official index";
    else if (paper.schedule_status === "proceedings-only") status = "Proceedings metadata · session unavailable";
    const code = [paper.code, paper.time].filter(Boolean).join(" · ") || paper.day || "Paper";
    const doiLink = paper.doi
      ? `<a class="paper-link" href="https://doi.org/${escapeHTML(paper.doi)}" target="_blank" rel="noreferrer" aria-label="Open DOI">DOI</a>`
      : "";
    const sourceLink = paper.source_url
      ? `<a class="paper-link" href="${escapeHTML(paper.source_url)}" target="_blank" rel="noreferrer" aria-label="Open metadata source">↗</a>`
      : "";
    return `
      <article class="paper-item${card ? " paper-card" : ""}">
        <div class="paper-code">${escapeHTML(code)}${paper.page ? `<span>pp. ${escapeHTML(paper.page)}</span>` : ""}</div>
        <div class="paper-main">
          <h4 class="paper-title${paper.is_placeholder ? " placeholder" : ""}">${escapeHTML(paper.title)}</h4>
          ${authors ? `<p class="authors">${escapeHTML(authors)}</p>` : ""}
          ${keywords.length ? `<div class="keywords">${keywords.map((keyword) => `<span class="keyword">${escapeHTML(keyword)}</span>`).join("")}</div>` : ""}
          ${status ? `<span class="status-note">${escapeHTML(status)}</span>` : ""}
        </div>
        <div class="paper-actions">
          ${doiLink}${sourceLink}
          <button
            class="save-button"
            type="button"
            data-favorite="${escapeHTML(paper.id)}"
            aria-pressed="${saved}"
            aria-label="${saved ? "Remove from saved program" : "Save to my program"}"
            title="${saved ? "Remove from saved program" : "Save to my program"}"
          >${saved ? "★" : "☆"}</button>
        </div>
      </article>
    `;
  }

  function renderEmpty(saved = false) {
    const fragment = elements.emptyTemplate.content.cloneNode(true);
    if (saved) {
      fragment.querySelector("h3").textContent = "Nothing saved in this edition";
      fragment.querySelector("p").textContent = "Use the star beside any paper to build your personal program.";
    }
    elements.results.replaceChildren(fragment);
    elements.loadMore.hidden = true;
  }

  function updateSavedCount() {
    elements.savedCount.textContent = formatNumber(state.favorites.size);
  }

  initialize();
})();
