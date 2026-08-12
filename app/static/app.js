/* catnews client-side enhancements: source/saved/read filters,
   keyboard navigation, save-for-later, and full-archive search. */
(function () {
  "use strict";

  var CFG = window.CATNEWS || { basePath: "", sourceTags: {} };
  var BASE = CFG.basePath;
  var SAVED_KEY = "catnews:saved";
  var READ_KEY = "catnews:read";
  var FILTER_KEY = "catnews:filters";

  function loadSet(key) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch (e) {
      return new Set();
    }
  }

  function saveSet(key, set) {
    try {
      localStorage.setItem(key, JSON.stringify(Array.from(set)));
    } catch (e) {}
  }

  function loadObject(key) {
    try {
      var raw = localStorage.getItem(key);
      var value = raw ? JSON.parse(raw) : null;
      return value && typeof value === "object" ? value : {};
    } catch (e) {
      return {};
    }
  }

  function saveObject(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  var saved = loadSet(SAVED_KEY);
  var read = loadSet(READ_KEY);

  /* -------------------------------------------------------------
     PWA install button + help dialog
     ------------------------------------------------------------- */
  var installBtn = document.getElementById("install-btn");
  var installDialog = document.getElementById("install-dialog");
  var installDialogClose = document.getElementById("install-dialog-close");
  var deferredPrompt = null;
  var lastFocusedElement = null;

  function closeInstallDialog() {
    if (!installDialog) return;
    installDialog.hidden = true;
    if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
    }
    lastFocusedElement = null;
  }

  /* -------------------------------------------------------------
     Compact mobile navigation
     ------------------------------------------------------------- */
  var navToggle = document.getElementById("nav-toggle");
  var siteHeader = document.querySelector(".site-header");
  var primaryNav = document.getElementById("primary-nav");

  function setNavOpen(open) {
    if (!navToggle || !siteHeader || !primaryNav) return;
    siteHeader.classList.toggle("nav-open", open);
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    navToggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
  }

  if (navToggle) {
    navToggle.addEventListener("click", function () {
      setNavOpen(navToggle.getAttribute("aria-expanded") !== "true");
    });
    primaryNav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () { setNavOpen(false); });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setNavOpen(false);
    });
    document.addEventListener("click", function (event) {
      if (siteHeader && !siteHeader.contains(event.target)) setNavOpen(false);
    });
  }

  function showInstallDialog() {
    if (!installDialog) return;
    lastFocusedElement = document.activeElement;
    installDialog.hidden = false;
    if (installDialogClose) installDialogClose.focus();
  }

  if (installDialogClose) {
    installDialogClose.addEventListener("click", function () {
      closeInstallDialog();
    });
  }
  if (installDialog) {
    installDialog.addEventListener("click", function (event) {
      if (event.target === installDialog) closeInstallDialog();
    });
    document.addEventListener("keydown", function (event) {
      if (installDialog.hidden) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closeInstallDialog();
        return;
      }
      if (event.key !== "Tab") return;
      var focusable = installDialog.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  if (installBtn) {
    window.addEventListener("beforeinstallprompt", function (event) {
      event.preventDefault();
      deferredPrompt = event;
    });
    window.addEventListener("appinstalled", function () {
      installBtn.disabled = true;
      installBtn.setAttribute("aria-label", "App installed");
      installBtn.title = "App installed";
    });
    installBtn.addEventListener("click", function () {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function () {
          deferredPrompt = null;
          installBtn.disabled = true;
          installBtn.setAttribute("aria-label", "App installed");
          installBtn.title = "App installed";
        });
      } else {
        showInstallDialog();
      }
    });
  }

  /* -------------------------------------------------------------
     Story cards: read/saved state
     ------------------------------------------------------------- */
  var cards = Array.from(document.querySelectorAll(".story"));
  var cardByUrl = new Map();
  cards.forEach(function (card) {
    var url = card.getAttribute("data-url");
    if (url) cardByUrl.set(url, card);
  });

  function paintCard(card, url) {
    card.classList.toggle("is-read", read.has(url));
    card.classList.toggle("is-saved", saved.has(url));
    var btn = card.querySelector(".save-toggle");
    if (btn) {
      btn.setAttribute("aria-pressed", saved.has(url) ? "true" : "false");
      btn.textContent = saved.has(url) ? "\u2605" : "\u2606";
      btn.setAttribute(
        "aria-label",
        saved.has(url) ? "Remove from saved" : "Save for later"
      );
    }
  }

  function toggleSaved(url) {
    if (saved.has(url)) saved.delete(url);
    else saved.add(url);
    saveSet(SAVED_KEY, saved);
    paintCard(cardByUrl.get(url), url);
    updateCounts();
  }

  function toggleRead(url) {
    if (read.has(url)) read.delete(url);
    else read.add(url);
    saveSet(READ_KEY, read);
    paintCard(cardByUrl.get(url), url);
    applyFilters();
    updateCounts();
  }

  cards.forEach(function (card) {
    var url = card.getAttribute("data-url");
    if (!url) return;

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "save-toggle";
    btn.setAttribute("aria-pressed", "false");
    btn.title = "Save for later";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      toggleSaved(url);
    });
    card.querySelector(".story-top").appendChild(btn);

    var link = card.querySelector(".story-title a, .story-link");
    if (link) {
      link.addEventListener("click", function () {
        if (!read.has(url)) {
          read.add(url);
          saveSet(READ_KEY, read);
          paintCard(card, url);
          updateCounts();
        }
      });
    }
    paintCard(card, url);
  });

  /* -------------------------------------------------------------
     Filters: source chip + saved chip + hide-read
     ------------------------------------------------------------- */
  var filtersEl = document.getElementById("filters");
  var noMatches = document.getElementById("no-matches");
  var hideRead = document.getElementById("hide-read");
  var loadMoreBtn = document.getElementById("load-more");
  var exportSavedBtn = document.getElementById("export-saved");
  var sourceFilterRow = document.querySelector(".filter-row--sources");
  var filterScrollCue = document.querySelector(".filter-scroll-cue");
  var PAGE_SIZE = 12;
  var filterPrefs = loadObject(FILTER_KEY);
  var preferredSource = filterPrefs.source;
  var state = {
    source: preferredSource === "All" || CFG.sourceTags[preferredSource] ? preferredSource : "All",
    savedOnly: filterPrefs.savedOnly === true,
    loaded: PAGE_SIZE,
  };

  function persistFilterState() {
    saveObject(FILTER_KEY, {
      source: state.source,
      savedOnly: state.savedOnly,
      hideRead: Boolean(hideRead && hideRead.checked),
    });
  }

  if (hideRead && filterPrefs.hideRead === true) hideRead.checked = true;

  function applyFilters() {
    if (!filtersEl) return;
    var visible = 0;
    var matched = 0;
    cards.forEach(function (card, index) {
      var url = card.getAttribute("data-url");
      var sourceMatch =
        state.source === "All" || card.getAttribute("data-source") === state.source;
      var savedMatch = !state.savedOnly || (url && saved.has(url));
      var readMatch = !hideRead || !hideRead.checked || !url || !read.has(url);
      var match = sourceMatch && savedMatch && readMatch;
      if (match) matched++;
      var show = match && index < state.loaded;
      card.hidden = !show;
      if (show) visible++;
    });
    if (noMatches) noMatches.hidden = matched !== 0;
    if (loadMoreBtn) {
      loadMoreBtn.hidden = matched <= state.loaded;
      loadMoreBtn.textContent = visible < matched
        ? "Load more \u00B7 " + visible + " of " + matched
        : "Load more";
    }
  }

  function setActiveChips() {
    var chips = filtersEl.querySelectorAll(".chip");
    chips.forEach(function (chip) {
      if (chip.dataset.source !== undefined) {
        chip.classList.toggle("is-active", chip.dataset.source === state.source);
        chip.setAttribute("aria-pressed", chip.dataset.source === state.source ? "true" : "false");
      } else if (chip.dataset.saved !== undefined) {
        chip.classList.toggle("is-active", state.savedOnly);
        chip.setAttribute("aria-pressed", state.savedOnly ? "true" : "false");
      }
    });
  }

  function updateCounts() {
    var savedChip = filtersEl && filtersEl.querySelector('[data-saved="saved"]');
    var countEl = savedChip && savedChip.querySelector(".chip-count");
    if (savedChip && countEl) {
      countEl.textContent = saved.size ? saved.size : "";
      savedChip.setAttribute(
        "aria-label",
        saved.size ? "Show saved stories, " + saved.size + " saved" : "Show saved stories"
      );
    }
    if (exportSavedBtn) exportSavedBtn.hidden = saved.size === 0;
  }

  if (filtersEl) {
    filtersEl.addEventListener("click", function (event) {
      var chip = event.target.closest(".chip");
      if (!chip) return;
      if (chip.dataset.source !== undefined) {
        state.source = chip.dataset.source;
        if (state.source !== "All") state.savedOnly = false;
      } else if (chip.dataset.saved !== undefined) {
        state.savedOnly = !state.savedOnly;
        if (state.savedOnly) state.source = "All";
      }
      setActiveChips();
      persistFilterState();
      applyFilters();
    });
    if (hideRead) {
      hideRead.addEventListener("change", function () {
        persistFilterState();
        applyFilters();
      });
    }
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", function () {
        state.loaded += PAGE_SIZE;
        applyFilters();
      });
    }
    updateCounts();
    setActiveChips();
    applyFilters();
  }

  function updateFilterScrollCue() {
    if (!sourceFilterRow || !filterScrollCue) return;
    var atEnd = sourceFilterRow.scrollLeft + sourceFilterRow.clientWidth >= sourceFilterRow.scrollWidth - 4;
    filterScrollCue.hidden = atEnd || sourceFilterRow.scrollWidth <= sourceFilterRow.clientWidth;
  }

  if (sourceFilterRow) {
    sourceFilterRow.addEventListener("scroll", updateFilterScrollCue, { passive: true });
    window.addEventListener("resize", updateFilterScrollCue);
    updateFilterScrollCue();
  }

  /* -------------------------------------------------------------
     Keyboard shortcuts: j/k move, o/Enter open, s save, m read, / search
     ------------------------------------------------------------- */
  var selectedIndex = -1;

  function visibleCards() {
    return cards.filter(function (c) {
      return !c.hidden && !c.hasAttribute("hidden");
    });
  }

  function select(index, list) {
    list.forEach(function (c) {
      c.classList.remove("is-selected");
    });
    if (index >= 0 && list[index]) {
      selectedIndex = index;
      list[index].classList.add("is-selected");
      list[index].scrollIntoView({ block: "nearest", behavior: "smooth" });
    } else {
      selectedIndex = -1;
    }
  }

  document.addEventListener("keydown", function (event) {
    var target = event.target;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
      return;
    }

    var list = visibleCards();
    if (event.key === "/") {
      event.preventDefault();
      var input = document.getElementById("search-input");
      if (input) input.focus();
      return;
    }
    if (list.length === 0) return;

    if (event.key === "j" || event.key === "k") {
      event.preventDefault();
      var step = event.key === "j" ? 1 : -1;
      var next =
        selectedIndex < 0 ? (step === 1 ? 0 : list.length - 1) : selectedIndex + step;
      next = (next + list.length) % list.length;
      select(next, list);
    } else if (event.key === "o" || event.key === "Enter") {
      var current = list[selectedIndex];
      if (current) {
        event.preventDefault();
        var anchor = current.querySelector(".story-title a, .story-link");
        if (anchor) anchor.click();
      }
    } else if (event.key === "s") {
      var sCard = list[selectedIndex];
      if (sCard && sCard.getAttribute("data-url")) {
        event.preventDefault();
        toggleSaved(sCard.getAttribute("data-url"));
      }
    } else if (event.key === "m") {
      var mCard = list[selectedIndex];
      if (mCard && mCard.getAttribute("data-url")) {
        event.preventDefault();
        toggleRead(mCard.getAttribute("data-url"));
      }
    }
  });

  /* -------------------------------------------------------------
     Full-archive search over /api/stories.json
     ------------------------------------------------------------- */
  var searchEl = document.getElementById("search");
  var searchInput = document.getElementById("search-input");
  var searchResults = document.getElementById("search-results");
  var storiesCache = null;

  function normalize(s) {
    return (s || "").toLowerCase();
  }

  function loadStories(cb) {
    if (storiesCache) {
      cb(storiesCache);
      return;
    }
    var triedJson = false;
    function fetchFrom(path) {
      fetch(path)
        .then(function (res) {
          if (!res.ok) throw new Error("not available");
          return res.json();
        })
        .then(function (stories) {
          storiesCache = stories;
          cb(storiesCache);
        })
        .catch(function () {
          if (!triedJson) {
            triedJson = true;
            fetchFrom(BASE + "/api/stories");
          } else {
            cb([]);
          }
        });
    }
    fetchFrom(BASE + "/api/search.json");
  }

  function searchStories(query) {
    var tokens = normalize(query)
      .split(/\s+/)
      .filter(Boolean);
    if (!tokens.length) return [];
    var results = [];
    (storiesCache || []).forEach(function (story) {
      var haystack = [
        story.title,
        story.byline,
        story.author,
        story.summary,
        story.snippet,
      ]
        .map(normalize)
        .join(" ");
      var score = 0;
      var ok = true;
      tokens.forEach(function (token) {
        if (haystack.indexOf(token) === -1) ok = false;
        else score += 1;
        if (normalize(story.title).indexOf(token) !== -1) score += 2;
      });
      if (ok) results.push({ score: score, story: story });
    });
    results.sort(function (a, b) {
      return b.score - a.score;
    });
    return results.slice(0, 8).map(function (r) {
      return r.story;
    });
  }

  function renderResults() {
    var query = searchInput.value.trim();
    if (!query) {
      searchResults.hidden = true;
      searchInput.setAttribute("aria-expanded", "false");
      return;
    }
    var hits = searchStories(query);
    searchResults.innerHTML = "";
    if (!hits.length) {
      var none = document.createElement("div");
      none.className = "search-result search-result--none";
      none.textContent = "No matches.";
      searchResults.appendChild(none);
    } else {
      hits.forEach(function (story) {
        var a = document.createElement("a");
        a.className = "search-result";
        a.href = story.url;
        a.target = "_blank";
        a.rel = "noopener";
        var tag = document.createElement("span");
        tag.className = "badge badge-" + (story.source || "");
        tag.textContent = CFG.sourceTags[story.source] || story.source || "";
        var text = document.createElement("span");
        text.className = "search-result-title";
        text.textContent = story.title || "";
        var sub = document.createElement("span");
        sub.className = "search-result-sub";
        sub.textContent = story.byline || story.author || "";
        a.appendChild(tag);
        a.appendChild(text);
        a.appendChild(sub);
        searchResults.appendChild(a);
      });
    }
    searchResults.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");
  }

  if (searchEl && searchInput && searchResults) {
    searchInput.addEventListener("focus", function () {
      loadStories(function () {
        renderResults();
      });
    });
    searchInput.addEventListener("input", renderResults);
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        var first = searchResults.querySelector("a.search-result");
        if (first) {
          event.preventDefault();
          window.open(first.href, "_blank", "noopener");
        }
      } else if (event.key === "Escape") {
        searchInput.value = "";
        searchResults.hidden = true;
        searchInput.setAttribute("aria-expanded", "false");
        searchInput.blur();
      }
    });
    document.addEventListener("click", function (event) {
      if (!searchEl.contains(event.target)) {
        searchResults.hidden = true;
        searchInput.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* -------------------------------------------------------------
     Export saved stories as Markdown (personal digest)
     ------------------------------------------------------------- */
  function storyToMarkdown(story, index) {
    var lines = [
      "### " + index + ". " + (story.title || ""),
      "",
      "- **Source:** " +
        (story.source || "unknown") +
        " · **By:** " +
        (story.byline || story.author || "unknown"),
    ];
    if (story.why_read) lines.push("- **Why read:** " + story.why_read);
    if (story.summary) lines.push("- **Summary:** " + story.summary);
    lines.push("- **Link:** " + (story.url || ""));
    return lines.join("\n");
  }

  function downloadSavedDigest() {
    loadStories(function (stories) {
      var savedStories = stories.filter(function (s) {
        return saved.has(s.url);
      });
      if (!savedStories.length) return;
      var today = new Date().toISOString().slice(0, 10);
      var blocks = ["# " + (CFG.appName || "catnews") + " — personal digest", ""];
      savedStories.forEach(function (story, i) {
        blocks.push(storyToMarkdown(story, i + 1));
        blocks.push("");
      });
      var blob = new Blob([blocks.join("\n")], { type: "text/markdown;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "catnews-saved-" + today + ".md";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  if (exportSavedBtn) {
    exportSavedBtn.addEventListener("click", downloadSavedDigest);
  }
})();
