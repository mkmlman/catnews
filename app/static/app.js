/* catnews client-side enhancements: source/saved/read filters,
   keyboard navigation, save-for-later, and full-archive search. */
(function () {
  "use strict";

  var CFG = window.CATNEWS || { basePath: "", sourceTags: {} };
  var BASE = CFG.basePath;
  var SAVED_KEY = "catnews:saved";
  var READ_KEY = "catnews:read";
  var FILTER_KEY = "catnews:filters";
  var VIEW_KEY = "catnews:view";

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
  var SAVED_META_KEY = "catnews:saved-meta";
  var savedMeta = loadObject(SAVED_META_KEY);

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
    closeWithFade(installDialog, function () {
      installDialog.hidden = true;
    });
    if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
    }
    lastFocusedElement = null;
  }

  var EASE_MS = 160;
  /* Fade an element out (opacity + list of transition:...), then run `done`.
     Honors prefers-reduced-motion by hiding immediately. */
  function closeWithFade(el, done) {
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !el) {
      if (done) done();
      return;
    }
    el.classList.add("is-closing");
    setTimeout(function () {
      if (done) done();
      el.classList.remove("is-closing");
    }, EASE_MS);
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

  function trapDialogFocus(dialog, event) {
    if (!dialog || dialog.hidden || event.key !== "Tab") return;
    var focusable = dialog.querySelectorAll(
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
      trapDialogFocus(installDialog, event);
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
     Sticky frosted header: measure height for the filters bar and
     deepen the scrim once the page scrolls.
     ------------------------------------------------------------- */
  var headerEl = document.querySelector(".site-header");
  var desktopMq = window.matchMedia("(min-width: 861px)");

  function paintStickyOffsets() {
    if (!headerEl) return;
    var h = desktopMq.matches ? headerEl.offsetHeight : 0;
    document.documentElement.style.setProperty("--header-h", h + "px");
  }

  function paintHeaderScrim() {
    if (headerEl) headerEl.classList.toggle("is-scrolled", window.scrollY > 8);
  }

  if (headerEl) {
    window.addEventListener("resize", paintStickyOffsets);
    window.addEventListener("load", paintStickyOffsets);
    window.addEventListener("scroll", paintHeaderScrim, { passive: true });
    paintStickyOffsets();
    paintHeaderScrim();
  }

  /* -------------------------------------------------------------
     Reading progress hairline
     ------------------------------------------------------------- */
  var progressBar = document.getElementById("scroll-progress");

  function paintProgress() {
    if (!progressBar) return;
    var max = document.documentElement.scrollHeight - window.innerHeight;
    progressBar.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
  }
  window.addEventListener("scroll", paintProgress, { passive: true });
  window.addEventListener("resize", paintProgress);
  paintProgress();

  /* -------------------------------------------------------------
     Footer: back to top + keyboard-shortcuts help dialog
     ------------------------------------------------------------- */
  var footerToTop = document.getElementById("footer-to-top");
  if (footerToTop) {
    footerToTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  var helpToggle = document.getElementById("help-toggle");
  var helpDialog = document.getElementById("help-dialog");
  var helpDialogClose = document.getElementById("help-dialog-close");

  function openHelp() {
    if (!helpDialog) return;
    lastFocusedElement = document.activeElement;
    helpDialog.hidden = false;
    if (helpDialogClose) helpDialogClose.focus();
  }

  function closeHelp() {
    if (!helpDialog) return;
    closeWithFade(helpDialog, function () {
      helpDialog.hidden = true;
    });
    if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
    }
    lastFocusedElement = null;
  }

  if (helpToggle) helpToggle.addEventListener("click", openHelp);
  if (helpDialogClose) helpDialogClose.addEventListener("click", closeHelp);
  if (helpDialog) {
    helpDialog.addEventListener("click", function (event) {
      if (event.target === helpDialog) closeHelp();
    });
    document.addEventListener("keydown", function (event) {
      if (helpDialog.hidden) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closeHelp();
        return;
      }
      trapDialogFocus(helpDialog, event);
    });
  }

  /* -------------------------------------------------------------
     Click-to-copy on API endpoints
     ------------------------------------------------------------- */
  var copyToast = document.getElementById("copy-toast");
  var copyTimer = null;
  var toastHidden = false;

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  }

  function scheduleCopyToastHide() {
    if (!copyToast) return;
    clearTimeout(copyTimer);
    if (toastHidden) return;
    copyTimer = setTimeout(function () {
      copyToast.classList.remove("is-visible");
    }, 1400);
  }

  function showCopyToast(text) {
    if (!copyToast) return;
    toastHidden = false;
    copyToast.textContent = text;
    copyToast.classList.add("is-visible");
    scheduleCopyToastHide();
  }

  if (copyToast) {
    copyToast.addEventListener("mouseenter", function () {
      toastHidden = true;
      clearTimeout(copyTimer);
    });
    copyToast.addEventListener("mouseleave", function () {
      toastHidden = false;
      scheduleCopyToastHide();
    });
  }

  document.querySelectorAll(".endpoint-code").forEach(function (el) {
    var value = el.getAttribute("data-copy") || null;
    if (!value) {
      var anchor = el.querySelector("a");
      value = anchor ? anchor.getAttribute("href") : null;
    }
    if (!value) {
      var clean = (el.textContent || "").replace(/^GET\s+/, "").trim();
      if (clean && clean.indexOf("<") === -1) value = clean;
    }
    if (!value) return;
    el.setAttribute("data-copyable", "1");
    el.addEventListener("click", function (event) {
      if (event.target.closest("a")) return;
      var done = function () {
        showCopyToast("Copied " + value);
        el.classList.add("is-copied");
        setTimeout(function () { el.classList.remove("is-copied"); }, 900);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(done, function () {
          fallbackCopy(value);
          done();
        });
      } else {
        fallbackCopy(value);
        done();
      }
    });
  });

  document.querySelectorAll(".endpoint-copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var code = btn.closest("li") ? btn.closest("li").querySelector(".endpoint-code") : null;
      var value = code ? (code.getAttribute("data-copy") || "") : "";
      if (!value) return;
      var done = function () {
        showCopyToast("Copied " + value);
        btn.classList.add("is-copied");
        setTimeout(function () { btn.classList.remove("is-copied"); }, 900);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(done, function () {
          fallbackCopy(value);
          done();
        });
      } else {
        fallbackCopy(value);
        done();
      }
    });
  });

  /* -------------------------------------------------------------
     API Run buttons — execute the endpoint and show its response
     ------------------------------------------------------------- */
  var RUN_MAX = 4000;

  function apiRunText(text, path) {
    if (path.indexOf(".json") !== -1) {
      try {
        return JSON.stringify(JSON.parse(text), null, 2);
      } catch (e) { /* fall through to raw */ }
    }
    return text || "";
  }

  document.querySelectorAll(".endpoint-run").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var li = btn.closest("li");
      var out = li ? li.querySelector(".endpoint-output") : null;
      var path = btn.getAttribute("data-run") || "";
      if (!out || !path) return;

      var full = new URL(path, window.location.origin).toString();
      out.hidden = false;
      out.textContent = "… fetching " + full;
      btn.disabled = true;

      fetch(full)
        .then(function (res) {
          return res.text().then(function (body) {
            return { ok: res.ok, status: res.status, body: body };
          });
        })
        .then(function (data) {
          var text = data.ok
            ? apiRunText(data.body, path)
            : "HTTP " + data.status + "\n" + (data.body || "").slice(0, 300);
          if (text.length > RUN_MAX) {
            text = text.slice(0, RUN_MAX) + "\n… (truncated)";
          }
          out.textContent = text;
        })
        .catch(function (err) {
          out.textContent = "Error: " + err.message;
        })
        .then(function () {
          btn.disabled = false;
        });
    });
  });

  /* -------------------------------------------------------------
     Back to top
     ------------------------------------------------------------- */
  var toTopBtn = document.getElementById("to-top");

  function paintToTop() {
    if (!toTopBtn) return;
    var show = window.scrollY > 480;
    toTopBtn.hidden = !show;
    toTopBtn.classList.toggle("is-visible", show);
  }

  if (toTopBtn) {
    window.addEventListener("scroll", paintToTop, { passive: true });
    window.addEventListener("resize", paintToTop);
    toTopBtn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    paintToTop();
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
    if (!card) return;
    card.classList.toggle("is-read", read.has(url));
    card.classList.toggle("is-saved", saved.has(url));
    var btn = card.querySelector(".save-toggle");
    if (btn) {
      btn.setAttribute("aria-pressed", saved.has(url) ? "true" : "false");
      btn.setAttribute(
        "aria-label",
        saved.has(url) ? "Remove from saved" : "Save for later"
      );
    }
  }

  function collectCardMeta(card) {
    var link = card.querySelector(".story-title a, .story-link");
    var by = card.querySelector(".story-by");
    var meta = {
      title: link ? link.textContent.trim() : "",
      source: card.getAttribute("data-source") || "",
      byline: "",
    };
    if (by) meta.byline = by.textContent.replace(/^by\s+/i, "").trim();
    return meta;
  }

  function toggleSaved(url) {
    var card = cardByUrl.get(url);
    if (saved.has(url)) {
      saved.delete(url);
      delete savedMeta[url];
    } else {
      saved.add(url);
      if (card) savedMeta[url] = collectCardMeta(card);
    }
    saveSet(SAVED_KEY, saved);
    saveObject(SAVED_META_KEY, savedMeta);
    paintCard(card, url);
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
    btn.innerHTML =
      '<svg class="save-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 2.6h8v10.8l-4-2.7-4 2.7Z"/></svg>';
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      toggleSaved(url);
    });
    var top = card.querySelector(".story-top");
    if (top) top.appendChild(btn);

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
  var filterStatus = document.getElementById("filter-status");
  var filtersTouched = false;
  var hideRead = document.getElementById("hide-read");
  var loadMoreBtn = document.getElementById("load-more");
  var loadMoreCount = document.getElementById("load-more-count");
  var exportSavedBtn = document.getElementById("export-saved");
  var sourceFilterRow = document.querySelector(".filter-row--sources");
  var filterScrollCue = document.querySelector(".filter-scroll-cue");
  var storiesEl = document.getElementById("stories");
  var viewBtns = filtersEl && filtersEl.querySelectorAll(".view-btn");
  var PAGE_SIZE = 12;
  var filterPrefs = loadObject(FILTER_KEY);
  var preferredSource = filterPrefs.source;
  var viewPref = null;
  try {
    viewPref = localStorage.getItem(VIEW_KEY);
  } catch (e) {}
  var state = {
    source: preferredSource === "All" || CFG.sourceTags[preferredSource] ? preferredSource : "All",
    savedOnly: filterPrefs.savedOnly === true,
    loaded: PAGE_SIZE,
    view: viewPref === "list" ? "list" : "grid",
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
    cards.forEach(function (card) {
      var url = card.getAttribute("data-url");
      var sourceMatch =
        state.source === "All" || card.getAttribute("data-source") === state.source;
      var savedMatch = !state.savedOnly || (url && saved.has(url));
      var readMatch = !hideRead || !hideRead.checked || !url || !read.has(url);
      var match = sourceMatch && savedMatch && readMatch;
      if (match) matched++;
      var show = match && matched <= state.loaded;
      card.hidden = !show;
      if (show) visible++;
    });
    if (noMatches) noMatches.hidden = matched !== 0;
    if (loadMoreBtn) {
      var hasMore = matched > state.loaded;
      loadMoreBtn.hidden = !hasMore;
      if (loadMoreCount) {
        loadMoreCount.hidden = !hasMore;
        if (hasMore) loadMoreCount.textContent = visible + " of " + matched;
      }
    }
    announceFilterCount(matched, visible);
  }

  function announceFilterCount(matched, visible) {
    if (!filterStatus || !filtersTouched || matched === 0) return;
    filterStatus.textContent = "";
    (window.requestAnimationFrame || function (cb) { cb(); })(function () {
      filterStatus.textContent =
        "Showing " + visible + " of " + matched + (matched === 1 ? " story." : " stories.");
    });
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

  function paintView() {
    if (storiesEl) storiesEl.classList.toggle("view-list", state.view === "list");
    if (viewBtns) {
      viewBtns.forEach(function (btn) {
        var active = btn.getAttribute("data-view") === state.view;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }
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
    paintPersonalFooter();
  }

  function paintPersonalFooter() {
    var el = document.getElementById("footer-personal");
    if (!el) return;
    var parts = [];
    if (saved.size) parts.push(saved.size + " saved");
    if (read.size) parts.push(read.size + " read");
    el.textContent = parts.join(" · ");
    el.hidden = parts.length === 0;
  }

  if (filtersEl) {
    filtersEl.addEventListener("click", function (event) {
      var chip = event.target.closest(".chip");
      if (!chip) return;
      if (chip.dataset.source !== undefined) {
        filtersTouched = true;
        state.source = chip.dataset.source;
        if (state.source !== "All") state.savedOnly = false;
        state.loaded = PAGE_SIZE;
      } else if (chip.dataset.saved !== undefined) {
        filtersTouched = true;
        state.savedOnly = !state.savedOnly;
        if (state.savedOnly) state.source = "All";
        state.loaded = PAGE_SIZE;
      } else if (chip.dataset.view !== undefined) {
        state.view = chip.dataset.view;
        try {
          localStorage.setItem(VIEW_KEY, state.view);
        } catch (e) {}
        paintView();
      }
      setActiveChips();
      persistFilterState();
      applyFilters();
    });
    if (hideRead) {
      hideRead.addEventListener("change", function () {
        filtersTouched = true;
        state.loaded = PAGE_SIZE;
        persistFilterState();
        applyFilters();
      });
    }
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", function () {
        filtersTouched = true;
        var previouslyHidden = [];
        cards.forEach(function (card) {
          if (card.hidden || card.hasAttribute("hidden")) previouslyHidden.push(card);
        });
        state.loaded += PAGE_SIZE;
        applyFilters();
        previouslyHidden.forEach(function (card) {
          if (!card.hidden && !card.hasAttribute("hidden")) {
            card.style.animation = "none";
            void card.offsetWidth;
            card.style.animation = "";
          }
        });
      });
    }
    updateCounts();
    setActiveChips();
    applyFilters();
    paintView();
  }

  function updateFilterScrollCue() {
    if (!sourceFilterRow || !filterScrollCue) return;
    var atEnd = sourceFilterRow.scrollLeft + sourceFilterRow.clientWidth >= sourceFilterRow.scrollWidth - 4;
    var hasMore = sourceFilterRow.scrollWidth > sourceFilterRow.clientWidth;
    filterScrollCue.classList.toggle("is-hidden", atEnd || !hasMore);
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
    // Let native controls keep their default keys: the shortcut layer must not
    // hijack Enter on buttons/links/<details>, tab from form fields, etc.
    var target = event.target;
    if (
      target &&
      (target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.closest(
          "button, a, summary, [role='button'], [contenteditable='true']"
        ))
    ) {
      return;
    }

    var list = visibleCards();
    if (event.key === "/") {
      event.preventDefault();
      var input = document.getElementById("search-input");
      if (input) input.focus();
      return;
    }
    if (event.key === "?") {
      event.preventDefault();
      openHelp();
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
  var searchUnavailable = false;

  function normalize(s) {
    return (s || "").toLowerCase();
  }

  function renderLoadingRow() {
    if (!searchResults) return;
    searchResults.innerHTML = "";
    var row = document.createElement("div");
    row.className = "search-result search-result--loading";
    row.textContent = "Searching the archive…";
    searchResults.appendChild(row);
    showSearchResults();
  }

  function loadStories(cb) {
    if (storiesCache) {
      cb(storiesCache);
      return;
    }
    fetch(BASE + "/api/search.json")
      .then(function (res) {
        if (!res.ok) throw new Error("not available");
        return res.json();
      })
      .then(function (stories) {
        storiesCache = stories;
        searchUnavailable = false;
        cb(storiesCache);
      })
      .catch(function () {
        searchUnavailable = true;
        cb([]);
      });
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

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      }[c];
    });
  }

  function markText(text, tokens) {
    if (!text) return "";
    var lower = text.toLowerCase();
    var out = "";
    var i = 0;
    tokens.forEach(function (tk) {
      if (!tk) return;
      var idx = lower.indexOf(tk, i);
      while (idx !== -1) {
        out += escapeHtml(text.slice(i, idx));
        out += "<mark>" + escapeHtml(text.slice(idx, idx + tk.length)) + "</mark>";
        i = idx + tk.length;
        idx = lower.indexOf(tk, i);
      }
    });
    out += escapeHtml(text.slice(i));
    return out;
  }

  var activeSearchIndex = -1;

  function paintActiveResult() {
    var items = searchResults.querySelectorAll("a.search-result");
    items.forEach(function (el, i) {
      el.classList.toggle("is-active", i === activeSearchIndex);
      el.setAttribute("aria-selected", i === activeSearchIndex ? "true" : "false");
    });
    if (activeSearchIndex >= 0 && items[activeSearchIndex]) {
      items[activeSearchIndex].scrollIntoView({ block: "nearest" });
      searchInput.setAttribute("aria-activedescendant", items[activeSearchIndex].id);
    } else {
      searchInput.removeAttribute("aria-activedescendant");
    }
  }

  var searchHideTimer = null;
  function hideSearchResults() {
    if (!searchResults) return;
    searchResults.classList.add("is-closing");
    clearTimeout(searchHideTimer);
    searchHideTimer = setTimeout(function () {
      searchResults.hidden = true;
      searchResults.classList.remove("is-closing");
    }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : EASE_MS);
    searchInput.setAttribute("aria-expanded", "false");
  }
  function showSearchResults() {
    if (!searchResults) return;
    clearTimeout(searchHideTimer);
    searchResults.classList.remove("is-closing");
    searchResults.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");
    searchInput.classList.add("is-typing");
  }

  function renderResults() {
    var query = searchInput.value.trim();
    if (!query) {
      hideSearchResults();
      activeSearchIndex = -1;
      return;
    }
    var tokens = normalize(query).split(/\s+/).filter(Boolean);
    var hits = searchStories(query);
    searchResults.innerHTML = "";
    activeSearchIndex = -1;
    if (!hits.length) {
      var none = document.createElement("div");
      none.className = "search-result search-result--none";
      none.textContent = searchUnavailable
        ? "Search unavailable — try again later."
        : "No matches.";
      none.id = "search-result-" + 0;
      none.style.setProperty("--i", 0);
      searchResults.appendChild(none);
    } else {
      hits.forEach(function (story) {
        var a = document.createElement("a");
        a.className = "search-result";
        a.id = "search-result-" + Array.prototype.indexOf.call(hits, story);
        a.style.setProperty("--i", Array.prototype.indexOf.call(hits, story));
        a.href = story.url;
        a.target = "_blank";
        a.rel = "noopener";
        a.setAttribute("role", "option");
        var tag = document.createElement("span");
        tag.className = "badge badge-" + (story.source || "");
        tag.textContent = CFG.sourceTags[story.source] || story.source || "";
        var text = document.createElement("span");
        text.className = "search-result-title";
        text.innerHTML = markText(story.title, tokens);
        var sub = document.createElement("span");
        sub.className = "search-result-sub";
        sub.innerHTML = markText(story.byline || story.author || "", tokens);
        a.appendChild(tag);
        a.appendChild(text);
        a.appendChild(sub);
        a.addEventListener("mouseover", function () {
          activeSearchIndex = Array.prototype.indexOf.call(
            searchResults.children,
            a
          );
          paintActiveResult();
        });
        searchResults.appendChild(a);
      });
    }
    paintActiveResult();
    showSearchResults();
  }

  if (searchEl && searchInput && searchResults) {
    searchInput.addEventListener("focus", function () {
      if (!storiesCache) renderLoadingRow();
      loadStories(function () {
        renderResults();
      });
    });
    searchInput.addEventListener("input", renderResults);
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        var next = activeSearchIndex;
        var count = searchResults.querySelectorAll("a.search-result").length;
        if (!count) return;
        activeSearchIndex = next < count - 1 ? next + 1 : 0;
        paintActiveResult();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        var count2 = searchResults.querySelectorAll("a.search-result").length;
        if (!count2) return;
        activeSearchIndex = activeSearchIndex > 0 ? activeSearchIndex - 1 : count2 - 1;
        paintActiveResult();
      } else if (event.key === "Enter") {
        var active = activeSearchIndex >= 0
          ? searchResults.children[activeSearchIndex]
          : searchResults.querySelector("a.search-result");
        if (active && active.tagName === "A") {
          event.preventDefault();
          window.open(active.href, "_blank", "noopener");
        }
      } else if (event.key === "Escape") {
        searchInput.value = "";
        hideSearchResults();
        activeSearchIndex = -1;
        searchInput.blur();
      }
    });
    document.addEventListener("click", function (event) {
      if (!searchEl.contains(event.target)) {
        hideSearchResults();
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
      var have = {};
      savedStories.forEach(function (s) {
        have[s.url] = true;
      });
      var meta = loadObject(SAVED_META_KEY);
      saved.forEach(function (url) {
        if (have[url]) return;
        var m = meta[url];
        if (!m || !m.title) return;
        savedStories.push({
          url: url,
          title: m.title,
          source: m.source || "unknown",
          byline: m.byline || "unknown",
        });
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

  /* -------------------------------------------------------------
     Heatmap tooltip (GitHub-style) on the stats page
     ------------------------------------------------------------- */
  var heatTip = document.getElementById("heat-tip");
  var heatTipShown = false;

  var HEAT_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
  ];

  function heatTipText(dateStr, count) {
    var parts = dateStr.split("-");
    var label = HEAT_MONTHS[Number(parts[1]) - 1] + " " + Number(parts[2]) + ", " + parts[0];
    if (count > 0) {
      return count + " " + (count === 1 ? "story" : "stories") + " on " + label;
    }
    return "No data on " + label;
  }

  function showHeatTip(cell) {
    if (!heatTip) return;
    heatTip.textContent = heatTipText(cell.getAttribute("data-date"), Number(cell.getAttribute("data-count") || 0));
    heatTip.hidden = false;
    heatTipShown = true;
    var cellRect = cell.getBoundingClientRect();
    var tipRect = heatTip.getBoundingClientRect();
    var x = cellRect.left + cellRect.width / 2;
    x = Math.max(tipRect.width / 2, Math.min(x, window.innerWidth - tipRect.width / 2));
    var y = cellRect.top - tipRect.height - 8;
    if (y < 0) y = cellRect.bottom + 8;
    heatTip.style.left = x + "px";
    heatTip.style.top = y + "px";
  }

  function hideHeatTip() {
    if (!heatTip) return;
    heatTip.hidden = true;
    heatTipShown = false;
  }

  var heatmap = document.querySelector(".trend-chart.heatmap");
  if (heatmap && heatTip) {
    document.body.appendChild(heatTip);
    heatmap.addEventListener("mouseover", function (event) {
      var cell = event.target.closest("rect.heat");
      if (cell) showHeatTip(cell);
    });
    heatmap.addEventListener("mouseout", function (event) {
      if (event.target.closest("rect.heat")) hideHeatTip();
    });
    heatmap.addEventListener("focusin", function (event) {
      var cell = event.target.closest("rect.heat");
      if (cell) showHeatTip(cell);
    });
    heatmap.addEventListener("focusout", function (event) {
      if (event.target.closest("rect.heat")) hideHeatTip();
    });
    heatmap.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        var cell = event.target.closest("rect.heat");
        if (cell) showHeatTip(cell);
      }
    });
    window.addEventListener("resize", hideHeatTip);
    window.addEventListener("scroll", hideHeatTip, { passive: true });
  }

  /* -------------------------------------------------------------
     Stats: share/rank bars grow in from zero when scrolled into view
     ------------------------------------------------------------- */
  var statBars = document.querySelectorAll(".share-fill, .rank-fill");
  if (statBars.length && "IntersectionObserver" in window) {
    statBars.forEach(function (bar) {
      var target = bar.style.width;
      bar.style.width = "0%";
      var io = new IntersectionObserver(
        function (entries, obs) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              bar.style.width = target;
              obs.disconnect();
            }
          });
        },
        { threshold: 0.2 }
      );
      io.observe(bar);
    });
  }
})();
