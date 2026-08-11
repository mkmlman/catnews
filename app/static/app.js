/* catnews client-side enhancements: source/saved/read filters,
   keyboard navigation, save-for-later, and full-archive search. */
(function () {
  "use strict";

  var CFG = window.CATNEWS || { basePath: "", sourceTags: {} };
  var BASE = CFG.basePath;
  var SAVED_KEY = "catnews:saved";
  var READ_KEY = "catnews:read";

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

  var saved = loadSet(SAVED_KEY);
  var read = loadSet(READ_KEY);

  /* -------------------------------------------------------------
     PWA install button + help dialog
     ------------------------------------------------------------- */
  var installBtn = document.getElementById("install-btn");
  var installDialog = document.getElementById("install-dialog");
  var installDialogClose = document.getElementById("install-dialog-close");
  var deferredPrompt = null;

  function showInstallDialog() {
    if (installDialog) installDialog.hidden = false;
  }

  if (installDialogClose) {
    installDialogClose.addEventListener("click", function () {
      installDialog.hidden = true;
    });
  }
  if (installDialog) {
    installDialog.addEventListener("click", function (event) {
      if (event.target === installDialog) installDialog.hidden = true;
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
  var keywordFilter = document.getElementById("keyword-filter");
  var loadMoreBtn = document.getElementById("load-more");
  var PAGE_SIZE = 12;
  var state = { source: "All", savedOnly: false, loaded: PAGE_SIZE };

  function keywordTokens() {
    if (!keywordFilter) return [];
    return normalize(keywordFilter.value)
      .split(/\s+/)
      .filter(Boolean);
  }

  function cardText(card) {
    return normalize(card.textContent || "");
  }

  function applyFilters() {
    if (!filtersEl) return;
    var tokens = keywordTokens();
    var visible = 0;
    var matched = 0;
    cards.forEach(function (card, index) {
      var url = card.getAttribute("data-url");
      var sourceMatch =
        state.source === "All" || card.getAttribute("data-source") === state.source;
      var savedMatch = !state.savedOnly || (url && saved.has(url));
      var readMatch = !hideRead || !hideRead.checked || !url || !read.has(url);
      var textMatch = true;
      if (tokens.length) {
        var haystack = cardText(card);
        textMatch = tokens.every(function (token) {
          return haystack.indexOf(token) !== -1;
        });
      }
      var match = sourceMatch && savedMatch && readMatch && textMatch;
      if (match) matched++;
      var show = match && index < state.loaded;
      card.hidden = !show;
      if (show) visible++;
    });
    if (noMatches) noMatches.hidden = matched !== 0;
    if (loadMoreBtn) loadMoreBtn.hidden = matched <= state.loaded;
  }

  function setActiveChips() {
    var chips = filtersEl.querySelectorAll(".chip");
    chips.forEach(function (chip) {
      if (chip.dataset.source !== undefined) {
        chip.classList.toggle("is-active", chip.dataset.source === state.source);
      } else if (chip.dataset.saved !== undefined) {
        chip.classList.toggle("is-active", state.savedOnly);
      }
    });
  }

  function updateCounts() {
    var savedChip = filtersEl && filtersEl.querySelector('[data-saved="saved"]');
    if (savedChip && saved.size) {
      savedChip.textContent = "Saved (" + saved.size + ")";
    } else if (savedChip) {
      savedChip.textContent = "Saved";
    }
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
      applyFilters();
    });
    if (hideRead) {
      hideRead.addEventListener("change", applyFilters);
    }
    if (keywordFilter) {
      keywordFilter.addEventListener("input", applyFilters);
    }
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", function () {
        state.loaded += PAGE_SIZE;
        applyFilters();
      });
    }
    updateCounts();
    applyFilters();
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
    fetchFrom(BASE + "/api/stories.json");
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
        searchInput.blur();
      }
    });
    document.addEventListener("click", function (event) {
      if (!searchEl.contains(event.target)) {
        searchResults.hidden = true;
      }
    });
  }
})();
