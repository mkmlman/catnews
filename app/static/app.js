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
  var installReturnFocus = null;
  var helpReturnFocus = null;

  function closeInstallDialog() {
    if (!installDialog) return;
    var target = installReturnFocus;
    installReturnFocus = null;
    closeWithFade(installDialog, function () {
      installDialog.hidden = true;
      if (target && typeof target.focus === "function") target.focus();
    });
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
    paintStickyOffsets();
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
    installReturnFocus = document.activeElement;
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
  var previousScrollY = window.scrollY;
  var headerIsCompact = false;

  function paintStickyOffsets() {
    if (!headerEl) return;
    /* Both mobile headers occupy space while the filters stay sticky. */
    var h = headerEl.offsetHeight;
    document.documentElement.style.setProperty("--header-h", h + "px");
  }

  function setHeaderCompact(compact) {
    if (!headerEl || headerIsCompact === compact) return;
    headerIsCompact = compact;
    headerEl.classList.toggle("is-compact", compact);
    paintStickyOffsets();
    /* Keep the sticky bar aligned through the padding transition. */
    window.setTimeout(paintStickyOffsets, 280);
  }

  function paintHeaderScrim() {
    if (!headerEl) return;
    var y = window.scrollY;

    var design = document.documentElement.getAttribute("data-design-system");
    var isDesktopChrome =
      desktopMq.matches && (design === "departure" || design === "kami");
    var movingDown = y > previousScrollY + 2;
    if (isDesktopChrome && !headerEl.classList.contains("nav-open")) {
      if (y > 120 && movingDown) setHeaderCompact(true);
      /* Keep the compact reading chrome stable until the page is nearly home. */
      else if (y < 48) setHeaderCompact(false);
    } else {
      setHeaderCompact(false);
    }
    previousScrollY = y;
  }

  if (headerEl) {
    window.addEventListener("resize", function () {
      previousScrollY = window.scrollY;
      paintStickyOffsets();
      paintHeaderScrim();
    });
    window.addEventListener("load", paintStickyOffsets);
    window.addEventListener("scroll", paintHeaderScrim, { passive: true });
    paintStickyOffsets();
    paintHeaderScrim();
    if (window.MutationObserver) {
      new MutationObserver(function () {
        previousScrollY = window.scrollY;
        /* Theme CSS changes the masthead dimensions after the attribute flips. */
        window.requestAnimationFrame(function () {
          paintHeaderScrim();
          paintStickyOffsets();
          window.setTimeout(paintStickyOffsets, 280);
        });
        }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-design-system"] });
    }
    if (window.ResizeObserver) {
      new ResizeObserver(paintStickyOffsets).observe(headerEl);
    }
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
    helpReturnFocus = document.activeElement;
    helpDialog.hidden = false;
    if (helpDialogClose) helpDialogClose.focus();
  }

  function closeHelp() {
    if (!helpDialog) return;
    var target = helpReturnFocus;
    helpReturnFocus = null;
    closeWithFade(helpDialog, function () {
      helpDialog.hidden = true;
      if (target && typeof target.focus === "function") target.focus();
    });
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
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
    if (!el.hasAttribute("role")) el.setAttribute("role", "button");
    function endpointPath(v) {
      var m = String(v).match(/(\/(api\/\S*|feed\S*))/);
      return m ? m[1] : String(v).slice(0, 48);
    }
    var codeLabel = "Copy curl command for GET " + endpointPath(value);
    if (el.getAttribute("aria-label") === "Copy command" || !el.hasAttribute("aria-label")) {
      el.setAttribute("aria-label", codeLabel);
    }
    function copyCode() {
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
    }
    el.addEventListener("click", function (event) {
      if (event.target.closest("a")) return;
      copyCode();
    });
    el.addEventListener("keydown", function (event) {
      if (event.target !== el) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        copyCode();
      }
    });
  });

  document.querySelectorAll(".endpoint-copy").forEach(function (btn) {
    (function () {
      var li = btn.closest("li");
      var code = li ? li.querySelector(".endpoint-code") : null;
      var raw = code ? (code.getAttribute("data-copy") || code.textContent || "") : "";
      var m = String(raw).match(/(\/(api\/\S*|feed\S*))/);
      if (m && btn.getAttribute("aria-label") === "Copy command") {
        btn.setAttribute("aria-label", "Copy curl command for GET " + m[1]);
      }
    })();
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
    (function () {
      var path = btn.getAttribute("data-run") || "";
      if (path && btn.getAttribute("aria-label") === "Fetch and show the response") {
        btn.setAttribute("aria-label", "Fetch and show GET " + path + " response");
      }
    })();
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
      author: "",
    };
    if (by) meta.author = by.textContent.replace(/^by\s+/i, "").trim();
    return meta;
  }

  function toggleSaved(url) {
    var card = cardByUrl.get(url);
    var prevFocus = document.activeElement;
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
    /* Saved-only is a live view: removing the current card should remove it
       immediately instead of leaving a stale result on screen. */
    applyFilters();
    updateCounts();
    if (card && card.hidden && prevFocus && card.contains(prevFocus)) {
      var fallback = resetFiltersBtn || (filtersEl && filtersEl.querySelector('[data-source="All"]'));
      if (fallback && typeof fallback.focus === "function") fallback.focus();
    }
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
    if (top) {
      top.appendChild(btn);

      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "copy-toggle";
      copyBtn.title = "Copy link to this story";
      copyBtn.setAttribute("aria-label", "Copy link to this story");
      copyBtn.innerHTML =
        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="1.5" y="1.5" width="8" height="8" rx="1.5"/><path d="M5.5 5.5h6a1.5 1.5 0 0 1 1.5 1.5v6a1.5 1.5 0 0 1-1.5 1.5h-6A1.5 1.5 0 0 1 4 13.5v-6"/></svg>';
      copyBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var link =
          window.location.origin +
          window.location.pathname +
          "#" +
          card.id;
        var done = function () { showCopyToast("Copied link to story"); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(link).then(done, function () {
            fallbackCopy(link);
            done();
          });
        } else {
          fallbackCopy(link);
          done();
        }
      });
      top.insertBefore(copyBtn, btn);
    }

    var link = card.querySelector(".story-title a, .story-link");
    if (link) {
      link.addEventListener("click", function () {
        if (!read.has(url)) {
          read.add(url);
          saveSet(READ_KEY, read);
          paintCard(card, url);
          applyFilters();
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
  var noMatchesCopy = document.getElementById("no-matches-copy");
  var resetFiltersBtn = document.getElementById("reset-filters");
  var filterStatus = document.getElementById("filter-status");
  var filtersTouched = false;
  var hideRead = document.getElementById("hide-read");
  var loadMoreBtn = document.getElementById("load-more");
  var loadMoreCount = document.getElementById("load-more-count");
  var exportSavedBtn = document.getElementById("export-saved");
  var sourceRail = document.querySelector(".source-options");
  var filterScrollCue = document.querySelector(".filter-scroll-cue");
  var storiesEl = document.getElementById("stories");
  var viewBtns = filtersEl && filtersEl.querySelectorAll(".view-btn");
  var PAGE_SIZE = 12;
  var filterPrefs = loadObject(FILTER_KEY);
  function readFilterUrlState() {
    var params = new URLSearchParams(window.location.search);
    function boolParam(name) {
      return params.get(name) === "1" || params.get(name) === "true";
    }
    return {
      source: params.get("source"),
      sourcePresent: params.has("source"),
      view: params.get("view"),
      viewPresent: params.has("view"),
      saved: boolParam("saved"),
      savedPresent: params.has("saved"),
      hideRead: boolParam("hideRead"),
      hideReadPresent: params.has("hideRead"),
    };
  }

  var filterUrlState = readFilterUrlState();
  var preferredSource = filterUrlState.sourcePresent ? filterUrlState.source : filterPrefs.source;
  var viewPref = null;
  try {
    viewPref = localStorage.getItem(VIEW_KEY);
  } catch (e) {}
  if (filterUrlState.viewPresent) viewPref = filterUrlState.view;
  var state = {
    source: preferredSource === "All" || CFG.sourceTags[preferredSource] ? preferredSource : "All",
    savedOnly: filterUrlState.savedPresent ? filterUrlState.saved : filterPrefs.savedOnly === true,
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

  function syncFilterUrl() {
    if (!window.history || !window.history.replaceState) return;
    try {
      var url = new URL(window.location.href);
      var params = url.searchParams;
      if (state.source !== "All") params.set("source", state.source);
      else params.delete("source");
      if (state.view === "list") params.set("view", "list");
      else params.delete("view");
      if (state.savedOnly) params.set("saved", "1");
      else params.delete("saved");
      if (hideRead && hideRead.checked) params.set("hideRead", "1");
      else params.delete("hideRead");
      var query = params.toString();
      window.history.replaceState(
        window.history.state,
        "",
        url.pathname + (query ? "?" + query : "") + url.hash
      );
    } catch (e) {}
  }

  if (hideRead) {
    hideRead.checked = filterUrlState.hideReadPresent
      ? filterUrlState.hideRead
      : filterPrefs.hideRead === true;
  }

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
    if (noMatchesCopy && matched === 0) {
      if (state.savedOnly && saved.size === 0) {
        noMatchesCopy.textContent = "Nothing saved yet.";
      } else if (state.savedOnly) {
        noMatchesCopy.textContent = "No saved stories in this edition.";
      } else if (hideRead && hideRead.checked) {
        noMatchesCopy.textContent = "Everything here is read.";
      } else {
        noMatchesCopy.textContent = "No stories match.";
      }
    }
    if (resetFiltersBtn) {
      resetFiltersBtn.textContent = state.savedOnly && saved.size === 0
        ? "Browse all stories"
        : "Reset filters";
    }
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

  function resetFilters() {
    if (!filtersEl) return;
    filtersTouched = true;
    state.source = "All";
    state.savedOnly = false;
    state.loaded = PAGE_SIZE;
    if (hideRead) hideRead.checked = false;
    setActiveChips();
    persistFilterState();
    syncFilterUrl();
    applyFilters();
    var allChip = filtersEl.querySelector('[data-source="All"]');
    if (allChip) allChip.focus();
  }

  function announceFilterCount(matched, visible) {
    if (!filterStatus || !filtersTouched) return;
    filterStatus.textContent = "";
    (window.requestAnimationFrame || function (cb) { cb(); })(function () {
      filterStatus.textContent = matched === 0
        ? (noMatchesCopy ? noMatchesCopy.textContent + " Use the reset button to browse the full edition." : "No stories match the selected filters.")
        : "Showing " + visible + " of " + matched + (matched === 1 ? " story." : " stories.");
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
      syncFilterUrl();
      applyFilters();
    });
    if (hideRead) {
      hideRead.addEventListener("change", function () {
        filtersTouched = true;
        state.loaded = PAGE_SIZE;
        persistFilterState();
        syncFilterUrl();
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
  if (resetFiltersBtn) resetFiltersBtn.addEventListener("click", resetFilters);

  window.addEventListener("popstate", function () {
    if (!filtersEl) return;
    var next = readFilterUrlState();
    var prefs = loadObject(FILTER_KEY);
    var source = next.sourcePresent ? next.source : prefs.source;
    state.source = source === "All" || CFG.sourceTags[source] ? source : "All";
    state.savedOnly = next.savedPresent ? next.saved : prefs.savedOnly === true;
    state.loaded = PAGE_SIZE;
    if (hideRead) {
      hideRead.checked = next.hideReadPresent ? next.hideRead : prefs.hideRead === true;
    }
    setActiveChips();
    paintView();
    applyFilters();
  });

  var digestEdition = storiesEl ? storiesEl.getAttribute("data-digest-date") : "";

  var SHORT_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  function formatShortDate(iso) {
    if (!iso) return "";
    var parts = iso.split("-");
    var m = Number(parts[1]) - 1;
    return SHORT_MONTHS[m] + " " + Number(parts[2]) + ", " + parts[0];
  }
  function readRaw(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function writeRaw(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }

  function updateFilterScrollCue() {
    if (!sourceRail || !filterScrollCue) return;
    var atEnd = sourceRail.scrollLeft + sourceRail.clientWidth >= sourceRail.scrollWidth - 4;
    var hasMore = sourceRail.scrollWidth > sourceRail.clientWidth;
    filterScrollCue.classList.toggle("is-hidden", atEnd || !hasMore);
  }

  if (sourceRail) {
    sourceRail.addEventListener("scroll", updateFilterScrollCue, { passive: true });
    window.addEventListener("resize", updateFilterScrollCue);
    updateFilterScrollCue();
  }

  /* -------------------------------------------------------------
     Deep links: #story-… anchors scroll to and highlight a story card
     ------------------------------------------------------------- */
  function resetFiltersForTarget() {
    if (hideRead) hideRead.checked = false;
    state.source = "All";
    state.savedOnly = false;
    // Reveal the whole edition so a deep-linked story is never hidden by the
    // load-more cutoff, no matter where it sits in the digest.
    state.loaded = cards.length;
    setActiveChips();
    persistFilterState();
    applyFilters();
  }

  function focusStoryHash() {
    var id = (window.location.hash || "").replace(/^#/, "");
    if (id.indexOf("story-") !== 0) return;
    var target = document.getElementById(id);
    if (!target) return;
    if (target.hidden || target.hasAttribute("hidden")) {
      resetFiltersForTarget();
    }
    target.classList.remove("is-link-target");
    void target.offsetWidth;
    target.classList.add("is-link-target");
    var headerOffset = 0;
    var hProp = getComputedStyle(document.documentElement).getPropertyValue("--header-h");
    if (hProp) headerOffset = parseFloat(hProp) || 0;
    window.scrollTo({
      top: target.getBoundingClientRect().top + window.scrollY - headerOffset - 12,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }

  function initDeepLinks() {
    if (window.location.hash.indexOf("#story-") === 0) {
      var run = function () { window.setTimeout(focusStoryHash, 0); };
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", run);
      } else {
        run();
      }
    }
    window.addEventListener("hashchange", function () {
      if (window.location.hash.indexOf("#story-") === 0) focusStoryHash();
    });
  }
  initDeepLinks();

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
      list[index].scrollIntoView({
        block: "nearest",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      });
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
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
        var editionLink = document.querySelector(
          ".snapshot-nav-link[rel='" +
            (event.key === "ArrowLeft" ? "prev" : "next") +
            "']"
        );
        if (editionLink) {
          event.preventDefault();
          editionLink.click();
          return;
        }
      }
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
     Full-archive search over /api/search.json
     ------------------------------------------------------------- */
  var searchEl = document.getElementById("search");
  var searchInput = document.getElementById("search-input");
  var searchResults = document.getElementById("search-results");
  var storiesCache = null;
  var searchUnavailable = false;
  var searchSeq = 0;

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
    var seq = ++searchSeq;
    fetch(BASE + "/api/search.json")
      .then(function (res) {
        if (!res.ok) throw new Error("not available");
        return res.json();
      })
      .then(function (stories) {
        if (seq !== searchSeq) return;
        storiesCache = stories;
        searchUnavailable = false;
        cb(storiesCache);
      })
      .catch(function () {
        if (seq !== searchSeq) return;
        searchUnavailable = true;
        cb([]);
      });
  }

  function levenshteinOne(a, b) {
    if (a === b) return 0;
    if (Math.abs(a.length - b.length) > 1) return 2;
    var al = a.length, bl = b.length;
    var i = 0, j = 0, edits = 0;
    while (i < al && j < bl) {
      if (a[i] === b[j]) { i++; j++; }
      else {
        if (edits === 1) return 2;
        edits++;
        if (al > bl) i++;
        else if (bl > al) j++;
        else { i++; j++; }
      }
    }
    edits += (al - i) + (bl - j);
    return edits;
  }
  function tokenMatches(haystack, token) {
    if (haystack.indexOf(token) !== -1) return 2;
    if (token.length < 4) return 0;
    var words = haystack.split(/\s+/);
    for (var w = 0; w < words.length; w++) {
      if (Math.abs(words[w].length - token.length) > 1) continue;
      if (levenshteinOne(words[w], token) === 1) return 1;
    }
    return 0;
  }
  function excerptAround(text, tokens) {
    if (!text) return "";
    var lower = normalize(text);
    var best = -1;
    tokens.forEach(function (tk) {
      var idx = lower.indexOf(tk);
      if (idx !== -1 && (best === -1 || idx < best)) best = idx;
    });
    if (best === -1) return text.slice(0, 90);
    var start = Math.max(0, best - 35);
    var snippet = text.slice(start, start + 90);
    if (start > 0) snippet = "…" + snippet;
    if (start + 90 < text.length) snippet = snippet + "…";
    return snippet;
  }
  function searchStories(query) {
    var tokens = normalize(query)
      .split(/\s+/)
      .filter(Boolean);
    if (!tokens.length) return [];
    var cutOff = "";
    if (searchDays) {
      var t = new Date();
      t.setDate(t.getDate() - searchDays);
      cutOff = t.toISOString().slice(0, 10);
    }
    var results = [];
    (storiesCache || []).forEach(function (story) {
      if (searchSource !== "All" && story.source !== searchSource) return;
      if (cutOff) {
        if (!story.date || story.date < cutOff) return;
      }
      var haystack = [
        story.title,
        story.author,
        story.why_read,
        story.summary,
        story.snippet,
      ]
        .map(normalize)
        .join(" ");
      var titleLower = normalize(story.title);
      var score = 0;
      var ok = true;
      tokens.forEach(function (token) {
        var m = tokenMatches(haystack, token);
        if (!m) ok = false;
        else score += m;
        if (titleLower.indexOf(token) !== -1) score += 2;
        else if (token.length >= 4 && titleLower.split(/\s+/).some(function (w) { return levenshteinOne(w, token) === 1; })) score += 1;
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
  var searchSource = "All";
  var searchDays = 0;
  var searchDebounceTimer = null;
  var searchStatus = document.getElementById("search-status");
  if (!searchStatus && searchEl) {
    searchStatus = document.createElement("div");
    searchStatus.id = "search-status";
    searchStatus.className = "sr-only";
    searchStatus.setAttribute("aria-live", "polite");
    searchStatus.setAttribute("aria-atomic", "true");
    searchEl.appendChild(searchStatus);
  }

  function paintFacets() {
    if (!searchResults || !storiesCache) return;
    var old = searchResults.querySelector(".search-facets");
    if (old) old.remove();

    var bar = document.createElement("div");
    bar.className = "search-facets";

    var sources = ["All"];
    (storiesCache || []).forEach(function (story) {
      if (sources.indexOf(story.source) === -1) sources.push(story.source);
    });
    sources.forEach(function (key) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "facet-chip" + (searchSource === key ? " is-active" : "");
      chip.setAttribute("aria-pressed", searchSource === key ? "true" : "false");
      chip.textContent = key === "All" ? "All" : (CFG.sourceTags[key] || key);
      chip.addEventListener("click", function () {
        searchSource = key;
        paintFacets();
        renderResults();
        searchInput.focus();
      });
      bar.appendChild(chip);
    });

    var select = document.createElement("select");
    select.className = "facet-select";
    select.setAttribute("aria-label", "Limit results by date");
    [["All time", 0], ["Last 30 days", 30], ["Last 7 days", 7]].forEach(function (opt) {
      var option = document.createElement("option");
      option.value = String(opt[1]);
      option.textContent = opt[0];
      select.appendChild(option);
    });
    select.value = String(searchDays);
    select.addEventListener("change", function () {
      searchDays = Number(select.value) || 0;
      renderResults();
    });
    bar.appendChild(select);

    if (searchResults.children.length) {
      searchResults.insertBefore(bar, searchResults.firstChild);
    } else {
      searchResults.appendChild(bar);
    }
  }

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
    if (searchEl) searchEl.classList.remove("has-results");
    if (headerEl) headerEl.classList.remove("search-open");
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
    if (searchEl) searchEl.classList.add("has-results");
    if (headerEl) headerEl.classList.add("search-open");
    searchInput.setAttribute("aria-expanded", "true");
  }
  function debouncedRender() {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(renderResults, 150);
  }

  function renderResults() {
    var query = searchInput.value.trim();
    var tokens = normalize(query).split(/\s+/).filter(Boolean);
    searchResults.innerHTML = "";
    activeSearchIndex = -1;
    paintFacets();
    if (!query) {
      var hint = document.createElement("div");
      hint.className = "search-result search-result--none";
      var total = storiesCache ? storiesCache.length : "";
      hint.textContent = total ? "Type to search " + total + " stories — try python, llm, hugging face" : "Type to search the archive…";
      hint.id = "search-result-hint";
      searchResults.appendChild(hint);
      paintActiveResult();
      if (searchStatus) searchStatus.textContent = "";
      showSearchResults();
      return;
    }
    var hits = searchStories(query);
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
        var idx = Array.prototype.indexOf.call(hits, story);
        var a = document.createElement("a");
        a.className = "search-result";
        a.id = "search-result-" + idx;
        a.style.setProperty("--i", idx);
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
        var authorPart = story.author ? markText(story.author, tokens) : "";
        var whyPart = story.why_read ? markText(excerptAround(story.why_read, tokens), tokens) : "";
        sub.innerHTML = whyPart ? (authorPart ? authorPart + " · " : "") + whyPart : authorPart;
        if (whyPart && story.why_read && story.why_read.length > 92) sub.title = story.why_read;
        a.appendChild(tag);
        a.appendChild(text);
        a.appendChild(sub);
        a.addEventListener("mouseover", function () {
          activeSearchIndex = Array.prototype.indexOf.call(
            searchResults.querySelectorAll("a.search-result"),
            a
          );
          paintActiveResult();
        });
        a.addEventListener("click", function () {
          hideSearchResults();
        });
        searchResults.appendChild(a);
      });
    }
    paintActiveResult();
    if (searchStatus) {
      if (!query) searchStatus.textContent = "";
      else if (!hits.length) searchStatus.textContent = searchUnavailable ? "Search unavailable" : "No matches for " + query;
      else searchStatus.textContent = hits.length + (hits.length === 1 ? " result for " : " results for ") + query;
    }
    showSearchResults();
  }

  if (searchEl && searchInput && searchResults) {
    searchInput.addEventListener("focus", function () {
      if (!storiesCache) renderLoadingRow();
      loadStories(function () {
        renderResults();
      });
    });
    searchInput.addEventListener("input", debouncedRender);
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
        var anchors = searchResults.querySelectorAll("a.search-result");
        var active = activeSearchIndex >= 0
          ? anchors[activeSearchIndex]
          : searchResults.querySelector("a.search-result");
        if (active && active.tagName === "A") {
          event.preventDefault();
          active.click();
        }
      } else if (event.key === "Escape") {
        if (searchResults && !searchResults.hidden) {
          hideSearchResults();
          activeSearchIndex = -1;
        } else {
          searchInput.value = "";
          activeSearchIndex = -1;
          searchInput.blur();
        }
      }
    });
    document.addEventListener("click", function (event) {
      if (!searchEl.contains(event.target)) {
        hideSearchResults();
      }
    });
    searchInput.addEventListener("transitionend", function (e) {
      if (e.propertyName === "width") paintStickyOffsets();
    });
  }
  if (headerEl) {
    headerEl.addEventListener("transitionend", function (e) {
      if (e.propertyName === "padding-top" || e.propertyName === "padding-bottom" || e.propertyName === "background-color") paintStickyOffsets();
    });
  }

  /* -------------------------------------------------------------
     Search deep links: #q=… runs a search on load (the SearchAction target
     the site advertises in its structured data)
     ------------------------------------------------------------- */
  function runSearchHash() {
    var hash = window.location.hash || "";
    if (hash.indexOf("#q=") !== 0) return;
    var q;
    try {
      q = decodeURIComponent(hash.slice(3).replace(/\+/g, " ")).trim();
    } catch (e) {
      return;
    }
    if (!q || !searchInput) return;
    searchInput.value = q;
    searchInput.focus();
    loadStories(function () {
      renderResults();
    });
  }

  function initSearchHash() {
    var run = function () { window.setTimeout(runSearchHash, 0); };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", run);
    } else {
      run();
    }
    window.addEventListener("hashchange", function () {
      if ((window.location.hash || "").indexOf("#q=") === 0) runSearchHash();
    });
  }
  initSearchHash();

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
        (story.author || "unknown"),
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
          author: m.author || "unknown",
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

  /* -------------------------------------------------------------
     “A new edition is live” toast — a returning tab notices a newer
     digest.json (served network-first by the service worker) and offers
     to refresh instead of silently showing stale content.
     ------------------------------------------------------------- */
  var editionToast = document.getElementById("edition-toast");
  var editionToastText = document.getElementById("edition-toast-text");
  var editionToastRefresh = document.getElementById("edition-toast-refresh");
  var editionToastClose = document.getElementById("edition-toast-close");
  var TOAST_KEY = "catnews:toast-dismissed";
  var toastTimer = null;
  var latestEditionSeen = null;

  function showEditionToast() {
    if (!editionToast) return;
    editionToast.classList.add("is-visible");
    editionToast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      editionToast.classList.remove("is-visible");
      setTimeout(function () { editionToast.hidden = true; }, 180);
    }, 12000);
  }

  function hideEditionToast() {
    clearTimeout(toastTimer);
    if (editionToast) {
      editionToast.classList.remove("is-visible");
      editionToast.hidden = true;
    }
  }

  function checkForNewEdition() {
    if (!digestEdition) return;
    fetch(BASE + "/api/digest.json")
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.date) return;
        var latest = String(data.date);
        latestEditionSeen = latest;
        if (latest <= digestEdition) {
          hideEditionToast();
          return;
        }
        if (readRaw(TOAST_KEY) === latest) return;
        if (editionToastText) {
          editionToastText.textContent = "New edition " + formatShortDate(latest) + " is live";
        }
        showEditionToast();
      })
      .catch(function () {});
  }

  if (editionToastRefresh) {
    editionToastRefresh.addEventListener("click", function () {
      window.location.reload();
    });
  }
  if (editionToastClose) {
    editionToastClose.addEventListener("click", function () {
      hideEditionToast();
      writeRaw(TOAST_KEY, latestEditionSeen || digestEdition);
    });
  }
  if (editionToast) {
    // Fired at the document (and propagated to window); one listener is enough.
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) checkForNewEdition();
    });
    window.addEventListener("pageshow", function () {
      window.setTimeout(checkForNewEdition, 1500);
    });
  }

  /* Printing an archive should include collapsed sections: open every
     <details> for the printout and restore the reader's state afterwards. */
  var openedForPrint = [];
  window.addEventListener("beforeprint", function () {
    openedForPrint = [];
    document.querySelectorAll("details:not([open])").forEach(function (d) {
      openedForPrint.push(d);
      d.setAttribute("open", "");
    });
  });
  window.addEventListener("afterprint", function () {
    openedForPrint.forEach(function (d) {
      d.removeAttribute("open");
    });
    openedForPrint = [];
  });

  /* -------------------------------------------------------------
     Ocean background — a full-viewport WebGL sea for the Departure
     design system, built on afl_ext's MIT "ocean weaves" shader.
     Day water under light themes; night sky with stars over dark/pitch,
     cross-faded on theme flips. Clicks drop ripples into the water.
     Wave motion slows to a quiet drift under prefers-reduced-motion;
     rendering pauses in background tabs. Kami keeps solid paper.
     ------------------------------------------------------------- */
  (function () {
    var canvas = document.getElementById("ocean");
    if (!canvas || !canvas.getContext) return;
    var gl =
      canvas.getContext("webgl", { antialias: false }) ||
      canvas.getContext("experimental-webgl", { antialias: false });
    if (!gl) return;

    var root = document.documentElement;
    var reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

    /* Shared projection constants — JS mirrors them so pointer ripples
       land exactly where the shader puts the water. */
    var PROJECTION_DEPTH = 1.5;
    var BASE_TILT = 0.14;
    var WATER_DEPTH = 1.0;
    var CAMERA_HEIGHT = 1.5;

    var QUALITY_SETTINGS = {
      low: { scale: 0.25, lowDpiScale: 0.425, raymarchSteps: 20, waveIterRaymarch: 4, waveIterNormal: 16, fbmOctaves: 2 },
      medium: { scale: 0.35, lowDpiScale: 0.595, raymarchSteps: 24, waveIterRaymarch: 6, waveIterNormal: 16, fbmOctaves: 3 },
      high: { scale: 0.4, lowDpiScale: 0.68, raymarchSteps: 32, waveIterRaymarch: 8, waveIterNormal: 16, fbmOctaves: 4 }
    };
    var QUALITY_LEVELS = ["low", "medium", "high"];
    var LOW_DPI_THRESHOLD = 1.5;
    var LOW_DPI_NOISE_SCALE = 1.7;
    var AUTO_FPS_LOW = 28;
    var AUTO_FPS_HIGH = 55;
    var AUTO_SAMPLE_WINDOW = 2000;
    var AUTO_COOLDOWN = 4000;

    var currentQuality = "high";
    var fpsSamples = [];
    var lastQualityChange = 0;

    /* Reduced motion eases the sea toward a slow ambient drift rather than
       freezing mid-wave; grain barely matters so it only slows a little. */
    var REDUCED_WAVE_SPEED = 0.15;
    var REDUCED_GRAIN_SPEED = 0.75;
    var SPEED_EASE_DURATION = 3.0;

    var THEME_FADE_MS = 900;
    function ease(t) { return t * t * (3.0 - 2.0 * t); }

    function nightTarget() {
      var theme = root.getAttribute("data-theme");
      return theme === "dark" || theme === "pitch" ? 1.0 : 0.0;
    }
    function deepTarget() {
      return root.getAttribute("data-theme") === "pitch" ? 1.0 : 0.0;
    }

    var nightBlend = nightTarget();
    var nightFrom = nightBlend;
    var nightTo = nightBlend;
    var nightFadeStart = null;
    var deepBlend = deepTarget();
    var deepFrom = deepBlend;
    var deepTo = deepBlend;
    var deepFadeStart = null;

    function updateBlends(nowMs) {
      if (nightTo !== nightTarget()) {
        nightFrom = nightBlend; nightTo = nightTarget(); nightFadeStart = nowMs;
      }
      if (deepTo !== deepTarget()) {
        deepFrom = deepBlend; deepTo = deepTarget(); deepFadeStart = nowMs;
      }
      if (nightFadeStart !== null) {
        var p = Math.min((nowMs - nightFadeStart) / THEME_FADE_MS, 1);
        nightBlend = nightFrom + (nightTo - nightFrom) * ease(p);
        if (p >= 1) { nightFadeStart = null; nightBlend = nightTo; }
      }
      if (deepFadeStart !== null) {
        var q = Math.min((nowMs - deepFadeStart) / THEME_FADE_MS, 1);
        deepBlend = deepFrom + (deepTo - deepFrom) * ease(q);
        if (q >= 1) { deepFadeStart = null; deepBlend = deepTo; }
      }
    }

    var vertexSource = [
      "attribute vec2 position;",
      "void main() { gl_Position = vec4(position, 0.0, 1.0); }"
    ].join("\n");

    function fragmentSource(s) {
      return [
        "precision highp float;",
        "uniform vec2 iResolution;",
        "uniform float u_waveTime;",
        "uniform float u_grainTime;",
        "uniform float u_noiseScale;",
        "uniform float u_night;",
        "uniform float u_deep;",
        "uniform vec4 u_ripples[10];",
        "uniform int u_rippleCount;",
        // afl_ext 2017-2024 | MIT License (ocean weaves)
        "#define PI 3.14159265359",
        "#define DRAG_MULT 0.38",
        "#define WATER_DEPTH " + WATER_DEPTH.toFixed(1),
        "#define CAMERA_HEIGHT " + CAMERA_HEIGHT,
        "#define ITERATIONS_RAYMARCH " + s.waveIterRaymarch,
        "#define ITERATIONS_NORMAL " + s.waveIterNormal,
        "#define RAYMARCH_STEPS " + s.raymarchSteps,
        "#define FBM_OCTAVES " + s.fbmOctaves,

        "float hash21(vec2 p) {",
        "  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);",
        "}",
        "float noise21(vec2 p) {",
        "  vec2 i = floor(p);",
        "  vec2 f = fract(p);",
        "  f = f * f * (3.0 - 2.0 * f);",
        "  float a = hash21(i);",
        "  float b = hash21(i + vec2(1.0, 0.0));",
        "  float c = hash21(i + vec2(0.0, 1.0));",
        "  float d = hash21(i + vec2(1.0, 1.0));",
        "  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);",
        "}",
        "float fbm(vec2 p) {",
        "  float value = 0.0;",
        "  float amplitude = 0.5;",
        "  float frequency = 1.0;",
        "  for (int i = 0; i < FBM_OCTAVES; i++) {",
        "    value += amplitude * noise21(p * frequency);",
        "    frequency *= 2.0;",
        "    amplitude *= 0.5;",
        "  }",
        "  return value;",
        "}",

        "mat3 rotAxis(vec3 axis, float angle) {",
        "  float s = sin(angle);",
        "  float c = cos(angle);",
        "  float oc = 1.0 - c;",
        "  return mat3(",
        "    oc * axis.x * axis.x + c, oc * axis.x * axis.y - axis.z * s, oc * axis.z * axis.x + axis.y * s,",
        "    oc * axis.x * axis.y + axis.z * s, oc * axis.y * axis.y + c, oc * axis.y * axis.z - axis.x * s,",
        "    oc * axis.z * axis.x - axis.y * s, oc * axis.y * axis.z + axis.x * s, oc * axis.z * axis.z + c",
        "  );",
        "}",
        "vec3 getRay(vec2 fragCoord) {",
        "  vec2 uv = ((fragCoord.xy / iResolution.xy) * 2.0 - 1.0) * vec2(iResolution.x / iResolution.y, 1.0);",
        "  vec3 proj = normalize(vec3(uv.x, uv.y, " + PROJECTION_DEPTH + "));",
        "  return rotAxis(vec3(1.0, 0.0, 0.0), " + BASE_TILT + ") * proj;",
        "}",

        "float star(vec2 screenUv, vec2 cellId, vec2 grid) {",
        "  float rnd = hash21(cellId);",
        "  if (rnd > 0.8) return 0.0;",
        "  vec2 starPos = vec2(hash21(cellId + 0.1), hash21(cellId + 0.2));",
        "  vec2 starUv = (cellId + starPos) / grid;",
        "  vec2 deltaPx = (screenUv - starUv) * iResolution.xy;",
        "  float sizePx = 0.25 + hash21(cellId + 0.3) * 0.45;",
        "  float d = length(deltaPx);",
        "  float core = smoothstep(sizePx, sizePx * 0.2, d);",
        "  float phase = hash21(cellId + 0.4) * 6.28318;",
        "  float speed = 0.2 + hash21(cellId + 0.5) * 0.3;",
        "  float amount = mix(0.1, 0.35, hash21(cellId + 0.7));",
        "  float flicker = mix(1.0 - amount, 1.0 + amount, 0.5 + 0.5 * sin(u_waveTime * speed + phase));",
        "  float lumens = mix(1.0, 12.0, hash21(cellId + 0.6));",
        "  float brightness = mix(0.6, 1.4, lumens / 12.0);",
        "  return core * flicker * brightness;",
        "}",

        "vec2 wavedx(vec2 position, vec2 direction, float frequency, float timeshift) {",
        "  float x = dot(direction, position) * frequency + timeshift;",
        "  float wave = exp(sin(x) - 1.0);",
        "  float dx = wave * cos(x);",
        "  return vec2(wave, -dx);",
        "}",
        "float getripples(vec2 position) {",
        "  float rippleSum = 0.0;",
        "  for (int i = 0; i < 10; i++) {",
        "    if (i >= u_rippleCount) break;",
        "    vec4 ripple = u_ripples[i];",
        "    float age = u_waveTime - ripple.z;",
        "    if (age < 0.0 || age > 12.0) continue;",
        "    float dist = length(position - ripple.xy);",
        "    float phase = dist * 4.0 - age * 3.2;",
        "    float envelope = exp(-0.45 * age) * exp(-dist * 0.16);",
        "    float fadeIn = smoothstep(0.0, 0.3, age);",
        "    rippleSum += ripple.w * envelope * fadeIn * sin(phase);",
        "  }",
        "  return rippleSum;",
        "}",
        "float getwaves(vec2 position, int iterations, bool withRipples) {",
        "  float wavePhaseShift = length(position) * 0.1;",
        "  vec2 swellDir = normalize(vec2(-0.25, 1.0));",
        "  float swellBias = 0.35;",
        "  float iter = 0.0;",
        "  float frequency = 1.0;",
        "  float timeMultiplier = 2.0;",
        "  float weight = 1.0;",
        "  float sumOfValues = 0.0;",
        "  float sumOfWeights = 0.0;",
        "  for (int i = 0; i < 16; i++) {",
        "    if (i >= iterations) break;",
        "    vec2 p = normalize(mix(vec2(sin(iter), cos(iter)), swellDir, swellBias));",
        "    vec2 res = wavedx(position, p, frequency, u_waveTime * timeMultiplier + wavePhaseShift);",
        "    position += p * res.y * weight * DRAG_MULT;",
        "    sumOfValues += res.x * weight;",
        "    sumOfWeights += weight;",
        "    weight = mix(weight, 0.0, 0.2);",
        "    frequency *= 1.18;",
        "    timeMultiplier *= 1.07;",
        "    iter += 1232.399963;",
        "  }",
        "  float waves = sumOfValues / sumOfWeights;",
        "  float swellPhase = dot(position, swellDir) * 0.18 - u_waveTime * 0.08;",
        "  float swell = sin(swellPhase);",
        "  vec2 cameraPos = vec2(u_waveTime * 0.2, 1.0);",
        "  float swellFade = smoothstep(28.0, 4.0, length(position - cameraPos));",
        "  waves += swell * swellFade * 0.35;",
        "  if (withRipples) waves += getripples(position);",
        "  return waves;",
        "}",
        "float raymarchwater(vec3 camera, vec3 start, vec3 end, float depth) {",
        "  vec3 pos = start;",
        "  vec3 dir = normalize(end - start);",
        "  for (int i = 0; i < RAYMARCH_STEPS; i++) {",
        "    float height = getwaves(pos.xz, ITERATIONS_RAYMARCH, false) * depth - depth;",
        "    if (height + 0.01 > pos.y) {",
        "      return distance(pos, camera);",
        "    }",
        "    pos += dir * (pos.y - height);",
        "  }",
        "  return distance(start, camera);",
        "}",
        "vec3 normal(vec2 pos, float e, float depth) {",
        "  vec2 ex = vec2(e, 0);",
        "  float H = getwaves(pos.xy, ITERATIONS_NORMAL, true) * depth;",
        "  vec3 a = vec3(pos.x, H, pos.y);",
        "  return normalize(",
        "    cross(",
        "      a - vec3(pos.x - e, getwaves(pos.xy - ex.xy, ITERATIONS_NORMAL, true) * depth, pos.y),",
        "      a - vec3(pos.x, getwaves(pos.xy + ex.yx, ITERATIONS_NORMAL, true) * depth, pos.y + e)",
        "    )",
        "  );",
        "}",

        "float intersectPlane(vec3 origin, vec3 direction, vec3 point, vec3 nrm) {",
        "  return clamp(dot(point - origin, nrm) / dot(direction, nrm), -1.0, 9991999.0);",
        "}",
        "vec3 extra_cheap_atmosphere(vec3 raydir, vec3 sundir) {",
        "  float special_trick = 1.0 / (raydir.y * 1.0 + 0.1);",
        "  float special_trick2 = 1.0 / (sundir.y * 11.0 + 1.0);",
        "  float raysundt = pow(abs(dot(sundir, raydir)), 2.0);",
        "  float sundt = pow(max(0.0, dot(sundir, raydir)), 8.0);",
        "  vec3 suncolor = mix(vec3(1.0), max(vec3(0.0), vec3(1.0) - vec3(5.5, 13.0, 22.4) / 22.4), special_trick2);",
        "  vec3 bluesky = vec3(12.0, 12.0, 13.0) / 22.4 * suncolor;",
        "  vec3 bluesky2 = max(vec3(0.0), bluesky - vec3(12.0, 12.0, 13.0) * 0.002 * (special_trick + -6.0 * sundir.y * sundir.y));",
        "  bluesky2 *= special_trick * (0.24 + raysundt * 0.24);",
        "  return bluesky2 * (1.0 + 1.0 * pow(1.0 - raydir.y, 3.0));",
        "}",
        "vec3 getSunDirection() {",
        "  return normalize(vec3(-0.0773502691896258, 0.6, 0.5773502691896258));",
        "}",
        "vec3 getDaySky(vec3 dir) {",
        "  return extra_cheap_atmosphere(dir, getSunDirection()) * 0.62;",
        "}",
        "vec2 skyUV(vec3 dir) {",
        "  float u = atan(dir.z, dir.x) / (2.0 * PI) + 0.5;",
        "  float v = clamp(dir.y * 0.5 + 0.5, 0.0, 1.0);",
        "  return vec2(u, v);",
        "}",
        "vec3 getNightSky(vec3 dir) {",
        "  vec2 uv = skyUV(dir);",
        "  vec3 topColor = mix(vec3(0.015, 0.02, 0.04), vec3(0.008, 0.01, 0.02), u_deep);",
        "  vec3 bottomColor = mix(vec3(0.03, 0.035, 0.05), vec3(0.016, 0.015, 0.014), u_deep);",
        "  vec3 color = mix(bottomColor, topColor, uv.y);",
        "  vec2 screenUv = vec2(-1.0);",
        "  vec3 unrotated = rotAxis(vec3(1.0, 0.0, 0.0), -" + BASE_TILT + ") * dir;",
        "  if (unrotated.z > 0.0) {",
        "    vec2 p = (unrotated.xy / unrotated.z) * " + PROJECTION_DEPTH + ";",
        "    vec2 ndc = p / vec2(iResolution.x / iResolution.y, 1.0);",
        "    screenUv = ndc * 0.5 + 0.5;",
        "  }",
        "  if (screenUv.x >= 0.0 && screenUv.x <= 1.0 && screenUv.y > 0.35 && screenUv.y <= 1.0) {",
        "    float gridX = 40.0;",
        "    float gridY = 30.0;",
        "    vec2 grid = vec2(gridX, gridY);",
        "    vec2 baseCell = floor(vec2(screenUv.x * gridX, screenUv.y * gridY));",
        "    float s = 0.0;",
        "    for (int yi = -1; yi <= 1; yi++) {",
        "      for (int xi = -1; xi <= 1; xi++) {",
        "        vec2 cell = baseCell + vec2(float(xi), float(yi));",
        "        if (cell.y < 0.0 || cell.y >= gridY) continue;",
        "        cell.x = mod(cell.x + gridX, gridX);",
        "        s += star(screenUv, cell, grid);",
        "      }",
        "    }",
        "    float horizonFade = smoothstep(0.35, 0.55, screenUv.y);",
        "    color += vec3(1.0, 0.97, 0.9) * s * horizonFade;",
        "  }",
        "  return color;",
        "}",

        "vec3 aces_tonemap(vec3 color) {",
        "  mat3 m1 = mat3(0.59719, 0.07600, 0.02840, 0.35458, 0.90834, 0.13383, 0.04823, 0.01566, 0.83777);",
        "  mat3 m2 = mat3(1.60475, -0.10208, -0.00327, -0.53108, 1.10813, -0.07276, -0.07367, -0.00605, 1.07602);",
        "  vec3 v = m1 * color;",
        "  vec3 a = v * (v + 0.0245786) - 0.000090537;",
        "  vec3 b = v * (0.983729 * v + 0.4329510) + 0.238081;",
        "  return pow(clamp(m2 * (a / b), 0.0, 1.0), vec3(1.0 / 2.2));",
        "}",
        "float gaussian(float z, float u, float o) {",
        "  return (1.0 / (o * sqrt(2.0 * 3.1415))) * exp(-(((z - u) * (z - u)) / (2.0 * (o * o))));",
        "}",
        "vec4 applyFilmGrain(vec3 color, vec2 fragCoord) {",
        "  float gray = dot(color, vec3(0.299, 0.587, 0.114));",
        "  vec2 uv = fragCoord * u_noiseScale / iResolution;",
        "  float seed = dot(uv, vec2(12.9898, 78.233));",
        "  float noise = fract(sin(seed) * 43758.5453 + u_grainTime * 1.5);",
        "  float variance = mix(0.75, 0.6, u_night);",
        "  noise = gaussian(noise, 0.0, variance * variance);",
        "  float grainIntensity = mix(0.4, 0.065, u_night);",
        "  gray += noise * (1.0 - gray) * grainIntensity;",
        "  gray = clamp(gray, 0.0, 1.0);",
        "  vec3 dark = mix(vec3(0.62), vec3(0.05), u_night);",
        "  vec3 light = mix(vec3(0.97), vec3(1.0), u_night);",
        "  return vec4(mix(dark, light, gray), 1.0);",
        "}",

        "void mainImage(out vec4 fragColor, in vec2 fragCoord) {",
        "  vec3 ray = getRay(fragCoord);",
        "  if (ray.y >= 0.0) {",
        "    vec3 C;",
        "    float horizonFactor = smoothstep(0.02, 0.25, ray.y);",
        "    float nb = pow(u_night, mix(0.35, 1.0, horizonFactor));",
        "    C = mix(getDaySky(ray), getNightSky(ray), nb);",
        "    fragColor = vec4(aces_tonemap(C * 2.0), 1.0);",
        "    return;",
        "  }",
        "  vec3 waterPlaneHigh = vec3(0.0, 0.0, 0.0);",
        "  vec3 waterPlaneLow = vec3(0.0, -WATER_DEPTH, 0.0);",
        "  vec3 origin = vec3(u_waveTime * 0.2, CAMERA_HEIGHT, 1.0);",
        "  float highHit = intersectPlane(origin, ray, waterPlaneHigh, vec3(0.0, 1.0, 0.0));",
        "  float lowHit = intersectPlane(origin, ray, waterPlaneLow, vec3(0.0, 1.0, 0.0));",
        "  vec3 highHitPos = origin + ray * highHit;",
        "  vec3 lowHitPos = origin + ray * lowHit;",
        "  float dist = raymarchwater(origin, highHitPos, lowHitPos, WATER_DEPTH);",
        "  vec3 waterHitPos = origin + ray * dist;",
        "  float eps = max(0.01, dist * 0.004);",
        "  vec3 N = normal(waterHitPos.xz, eps, WATER_DEPTH);",
        "  N = mix(N, vec3(0.0, 1.0, 0.0), 0.6 * min(1.0, sqrt(dist * 0.01) * 1.1));",
        "  float fresnelSharp = 0.04 + 0.96 * pow(1.0 - max(0.0, dot(-N, ray)), 5.0);",
        "  float fresnelFlat = 0.04 + 0.96 * pow(1.0 - max(0.0, dot(vec3(0.0, 1.0, 0.0), -ray)), 5.0);",
        "  float fresnel = mix(fresnelSharp, fresnelFlat, min(1.0, sqrt(dist * 0.01) * 1.1));",
        "  vec3 R = normalize(reflect(ray, N));",
        "  R.y = abs(R.y);",
        "  float rh = smoothstep(0.02, 0.25, R.y);",
        "  float rb = pow(u_night, mix(0.35, 1.0, rh));",
        "  vec3 reflection = mix(getDaySky(R), getNightSky(R), rb);",
        "  vec3 scatteringBase = mix(vec3(0.055, 0.065, 0.08), vec3(0.02, 0.02, 0.03), u_night);",
        "  vec3 scattering = scatteringBase * (0.2 + (waterHitPos.y + WATER_DEPTH) / WATER_DEPTH);",
        "  vec3 C = fresnel * reflection + scattering;",
        "  vec3 fogColor = mix(vec3(0.55, 0.55, 0.58), vec3(0.03, 0.035, 0.05), u_night);",
        "  fogColor = mix(fogColor, fogColor * 0.72, u_deep);",
        "  float fogAmount = 1.0 - exp(-dist * 0.02);",
        "  C = mix(C, fogColor, fogAmount);",
        "  float waveBrightness = mix(1.55, 1.9, u_night);",
        "  fragColor = vec4(aces_tonemap(C * waveBrightness), 1.0);",
        "}",
        "void main() {",
        "  vec4 sceneColor;",
        "  mainImage(sceneColor, gl_FragCoord.xy);",
        "  gl_FragColor = applyFilmGrain(sceneColor.rgb * mix(1.0, 0.82, u_deep), gl_FragCoord.xy);",
        "}"
      ].join("\n");
    }

    function compile(type, source) {
      var shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        if (window.console) console.warn("catnews ocean:", gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    }

    var vs = compile(gl.VERTEX_SHADER, vertexSource);
    var fs = compile(gl.FRAGMENT_SHADER, fragmentSource(QUALITY_SETTINGS[currentQuality]));
    var program = null;
    var uniforms = {};
    function linkProgram() {
      if (program) gl.deleteProgram(program);
      program = gl.createProgram();
      gl.attachShader(program, vs);
      gl.attachShader(program, fs);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        if (window.console) console.warn("catnews ocean:", gl.getProgramInfoLog(program));
        program = null;
        return false;
      }
      ["iResolution", "u_waveTime", "u_grainTime", "u_noiseScale", "u_night",
        "u_deep", "u_ripples", "u_rippleCount"].forEach(function (name) {
          uniforms[name] = gl.getUniformLocation(program, name);
        });
      uniforms.position = gl.getAttribLocation(program, "position");
      return true;
    }
    if (!vs || !fs || !linkProgram()) return;

    var quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);

    function setQuality(next) {
      if (QUALITY_LEVELS.indexOf(next) < 0 || next === currentQuality) return;
      currentQuality = next;
      fs = compile(gl.FRAGMENT_SHADER, fragmentSource(QUALITY_SETTINGS[currentQuality]));
      if (!fs || !linkProgram()) return;
      resize();
    }
    function updateAutoQuality(nowMs, fps) {
      fpsSamples.push({ t: nowMs, fps: fps });
      var cutoff = nowMs - AUTO_SAMPLE_WINDOW;
      while (fpsSamples.length && fpsSamples[0].t < cutoff) fpsSamples.shift();
      if (fpsSamples.length < 3 || nowMs - lastQualityChange < AUTO_COOLDOWN) return;
      var avg = fpsSamples.reduce(function (sum, s) { return sum + s.fps; }, 0) / fpsSamples.length;
      var idx = QUALITY_LEVELS.indexOf(currentQuality);
      if (avg < AUTO_FPS_LOW && idx > 0) {
        setQuality(QUALITY_LEVELS[idx - 1]);
        fpsSamples = [];
        lastQualityChange = nowMs;
      } else if (avg > AUTO_FPS_HIGH && idx < QUALITY_LEVELS.length - 1) {
        setQuality(QUALITY_LEVELS[idx + 1]);
        fpsSamples = [];
        lastQualityChange = nowMs;
      }
    }

    /* Ripples — clicks anywhere project through the camera onto the water. */
    var MAX_RIPPLES = 10;
    var RIPPLE_LIFETIME = 12;
    var ripples = [];
    var rippleData = new Float32Array(MAX_RIPPLES * 4);
    document.addEventListener("click", function (event) {
      if (!oceanVisible()) return;
      var target = event.target;
      if (target && target.closest && target.closest("a, button, summary, input, select, textarea, [role='button']")) return;
      var ndcX = (event.clientX / window.innerWidth) * 2 - 1;
      var ndcY = -((event.clientY / window.innerHeight) * 2 - 1);
      var aspect = Math.max(canvas.width, 1) / Math.max(canvas.height, 1);
      var rx = ndcX * aspect, ry = ndcY, rz = PROJECTION_DEPTH;
      var len = Math.sqrt(rx * rx + ry * ry + rz * rz) || 1;
      rx /= len; ry /= len; rz /= len;
      var tilt = BASE_TILT;
      var cy = ry * Math.cos(tilt) + rz * Math.sin(tilt);
      var cz = -ry * Math.sin(tilt) + rz * Math.cos(tilt);
      if (cy >= 0) return;
      var camX = waveTime * 0.2;
      var t = -CAMERA_HEIGHT / cy;
      ripples.push({ x: camX + rx * t, z: 1.0 + cz * t, t: waveTime, amp: 0.18 });
      if (ripples.length > MAX_RIPPLES) ripples.shift();
    }, false);
    function rippleUniforms() {
      while (ripples.length && waveTime - ripples[0].t > RIPPLE_LIFETIME) ripples.shift();
      for (var i = 0; i < ripples.length; i++) {
        rippleData[i * 4] = ripples[i].x;
        rippleData[i * 4 + 1] = ripples[i].z;
        rippleData[i * 4 + 2] = ripples[i].t;
        rippleData[i * 4 + 3] = ripples[i].amp;
      }
      return rippleData;
    }

    function resize() {
      var width = window.innerWidth;
      var height = window.innerHeight;
      if (!width || !height) return;
      var settings = QUALITY_SETTINGS[currentQuality];
      var dpi = window.devicePixelRatio || 1;
      var scale = (dpi < LOW_DPI_THRESHOLD ? settings.lowDpiScale : settings.scale);
      canvas.width = Math.round(width * dpi * scale);
      canvas.height = Math.round(height * dpi * scale);
    }

    var waveTime = 0;
    var grainTime = 0;
    var lastFrame = null;
    var waveSpeed = reduceQuery.matches ? REDUCED_WAVE_SPEED : 1.0;
    var grainSpeed = reduceQuery.matches ? REDUCED_GRAIN_SPEED : 1.0;
    var waveSpeedFrom = waveSpeed, waveSpeedTo = waveSpeed;
    var grainSpeedFrom = grainSpeed, grainSpeedTo = grainSpeed;
    var speedEaseElapsed = SPEED_EASE_DURATION;
    var frameCount = 0;
    var lastFpsAt = 0;
    var rafId = null;

    function updateClocks(nowMs) {
      if (lastFrame === null) {
        waveTime = nowMs * 0.001;
        grainTime = nowMs * 0.001;
        lastFrame = nowMs;
        return;
      }
      var delta = Math.max(0, (nowMs - lastFrame) * 0.001);
      var reduced = reduceQuery.matches;
      var targetWave = reduced ? REDUCED_WAVE_SPEED : 1.0;
      var targetGrain = reduced ? REDUCED_GRAIN_SPEED : 1.0;
      if (waveSpeedTo !== targetWave || grainSpeedTo !== targetGrain) {
        speedEaseElapsed = 0;
        waveSpeedFrom = waveSpeed; waveSpeedTo = targetWave;
        grainSpeedFrom = grainSpeed; grainSpeedTo = targetGrain;
      }
      if (speedEaseElapsed < SPEED_EASE_DURATION) {
        speedEaseElapsed += delta;
        var p = ease(Math.min(speedEaseElapsed / SPEED_EASE_DURATION, 1));
        waveSpeed = waveSpeedFrom + (waveSpeedTo - waveSpeedFrom) * p;
        grainSpeed = grainSpeedFrom + (grainSpeedTo - grainSpeedFrom) * p;
      }
      waveTime += delta * waveSpeed;
      grainTime += delta * grainSpeed;
      lastFrame = nowMs;
    }

    function render(nowMs) {
      updateClocks(nowMs);
      updateBlends(nowMs);
      frameCount++;
      if (nowMs - lastFpsAt >= 1000) {
        updateAutoQuality(nowMs, frameCount);
        frameCount = 0;
        lastFpsAt = nowMs;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.useProgram(program);
      gl.enableVertexAttribArray(uniforms.position);
      gl.bindBuffer(gl.ARRAY_BUFFER, quad);
      gl.vertexAttribPointer(uniforms.position, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(uniforms.iResolution, canvas.width, canvas.height);
      gl.uniform1f(uniforms.u_waveTime, waveTime);
      gl.uniform1f(uniforms.u_grainTime, grainTime);
      gl.uniform1f(uniforms.u_noiseScale,
        (window.devicePixelRatio || 1) < LOW_DPI_THRESHOLD ? LOW_DPI_NOISE_SCALE : 1.0);
      gl.uniform1f(uniforms.u_night, nightBlend);
      gl.uniform1f(uniforms.u_deep, deepBlend);
      gl.uniform4fv(uniforms.u_ripples, rippleUniforms());
      gl.uniform1i(uniforms.u_rippleCount, ripples.length);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      canvas.classList.add("shader-ready");
      rafId = requestAnimationFrame(render);
    }

    function running() { return rafId !== null; }
    function stop() {
      if (running()) { cancelAnimationFrame(rafId); rafId = null; }
    }
    /* The canvas is display:none under kami, when toggled off, and before
       first paint — never burn GPU raymarching an invisible sea. */
    function oceanVisible() {
      if (canvas.hidden || canvas.style.display === "none") return false;
      if (root.getAttribute("data-design-system") === "kami") return false;
      return true;
    }
    function sync() {
      if (document.hidden || !oceanVisible()) { stop(); }
      else if (!running()) {
        lastFrame = null; /* avoid a time jump after a long pause */
        rafId = requestAnimationFrame(render);
      }
    }
    document.addEventListener("visibilitychange", sync);
    if (window.MutationObserver) {
      var oceanVisibility = new MutationObserver(sync);
      oceanVisibility.observe(canvas, { attributes: true, attributeFilter: ["hidden", "style", "class"] });
      oceanVisibility.observe(root, { attributes: true, attributeFilter: ["data-design-system"] });
    }

    var reduceHandler = reduceQuery.addEventListener
      ? function () { sync(); }
      : null;
    if (reduceHandler) reduceQuery.addEventListener("change", reduceHandler);
    else if (reduceQuery.addListener) reduceQuery.addListener(sync);

    window.addEventListener("resize", resize);
    resize();
    sync();
  })();
  (function () {
    var btn = document.getElementById("ocean-toggle");
    var ocean = document.getElementById("ocean");
    var fluid = document.getElementById("fluid");
    if (!btn || !ocean || !fluid) return;
    var key = "catnews:background";
    var legacyKey = "catnews:ocean";
    var saveData = (navigator.connection && navigator.connection.saveData) || false;
    var reducePref = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function isForcedOff() { return saveData || reducePref; }
    function read() {
      try {
        var v = localStorage.getItem(key);
        if (v === "ocean" || v === "fluid" || v === "off") return v;
        var legacy = localStorage.getItem(legacyKey);
        if (legacy === "off") return "off";
        if (legacy === "on") return "ocean";
      } catch (e) {}
      // default: ocean, off if forced
      if (isForcedOff()) return "off";
      return "ocean";
    }
    function apply(state) {
      var showOcean = state === "ocean";
      var showFluid = state === "fluid";
      ocean.hidden = !showOcean; ocean.style.display = showOcean ? "" : "none";
      if (window.catnewsFluid) {
        if (showFluid) window.catnewsFluid.show(); else window.catnewsFluid.hide();
      } else {
        fluid.hidden = !showFluid; if (showFluid) fluid.classList.add("is-visible"); else fluid.classList.remove("is-visible");
        fluid.style.display = showFluid ? "" : "none";
      }
      var label = showOcean ? "Ocean" : showFluid ? "Fluid" : "Off";
      var next = showOcean ? "fluid" : showFluid ? "off" : "ocean";
      btn.textContent = showOcean ? "◐" : showFluid ? "≈" : "○";
      btn.setAttribute("aria-pressed", state !== "off" ? "true" : "false");
      btn.setAttribute("aria-label", "Background: " + label + " — switch to " + next);
      btn.title = "Background: " + label + " — click for " + next + "";
      try { localStorage.setItem(key, state); localStorage.setItem(legacyKey, showOcean ? "on" : "off"); } catch (e) {}
    }
    var cur = read();
    apply(cur);
    // Keep background visibility in sync when design system flips to/from kami
    if (window.MutationObserver) {
      new MutationObserver(function () {
        try {
          var v = localStorage.getItem(key);
          if (v !== "ocean" && v !== "fluid" && v !== "off") v = cur;
          apply(v);
        } catch (e) { apply(cur); }
      }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-design-system"] });
    }
    btn.addEventListener("click", function () {
      var curState;
      try { curState = localStorage.getItem(key); } catch (e) { curState = null; }
      if (curState !== "ocean" && curState !== "fluid" && curState !== "off") curState = !ocean.hidden ? "ocean" : !fluid.hidden ? "fluid" : "off";
      var next = curState === "ocean" ? "fluid" : curState === "fluid" ? "off" : "ocean";
      apply(next);
    });
  })();
})();
