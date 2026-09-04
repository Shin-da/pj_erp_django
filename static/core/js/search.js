// Perfect Jewel ERP — global nav search.
//
// Behaviour:
//   - Typing (2+ chars, debounced) fetches grouped suggestions and shows a
//     dropdown under the search box.
//   - An exact barcode/EPC match is pinned to the top and pre-selected, so a
//     barcode scanner — which types the code then sends Enter — lands
//     straight on that piece with zero clicks.
//   - Arrow keys move through results, Enter opens the highlighted one,
//     Escape closes. Enter with nothing highlighted opens the full
//     results page.
//   - "/" anywhere on the page focuses the box (unless you're already
//     typing in a field).
//   - On narrow screens the search box is revealed via a toggle button.
(function () {
  var box = document.querySelector('.topbar-search .search-box');
  if (!box) return;
  var input = box.querySelector('input');
  if (!input) return;
  var topbarSearch = document.querySelector('.topbar-search');
  var toggleBtn = document.getElementById('searchToggle');
  var closeBtn = document.getElementById('searchClose');

  var suggestUrl = box.dataset.suggestUrl;
  var searchUrl = box.dataset.searchUrl;
  if (!suggestUrl || !searchUrl) return;

  // ---- dropdown element ----
  var dd = document.createElement('div');
  dd.className = 'search-dd';
  dd.style.display = 'none';
  dd.setAttribute('role', 'listbox');
  box.appendChild(dd);

  var flat = [];      // flat list of {url, el} for keyboard nav
  var cursor = -1;
  var timer = null;
  var lastQuery = '';
  var seq = 0;        // guards against out-of-order responses
  var loading = false;

  function close() {
    dd.style.display = 'none';
    dd.innerHTML = '';
    flat = [];
    cursor = -1;
  }

  function openMobileSearch() {
    if (!topbarSearch) return;
    topbarSearch.classList.add('is-open');
    document.body.classList.add('search-mobile-open');
    input.focus();
    input.select();
  }

  function closeMobileSearch() {
    if (!topbarSearch) return;
    topbarSearch.classList.remove('is-open');
    document.body.classList.remove('search-mobile-open');
    close();
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function (e) {
      e.preventDefault();
      if (topbarSearch && topbarSearch.classList.contains('is-open')) {
        closeMobileSearch();
      } else {
        openMobileSearch();
      }
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', function (e) {
      e.preventDefault();
      closeMobileSearch();
    });
  }

  function highlight(i) {
    flat.forEach(function (r, n) { r.el.classList.toggle('active', n === i); });
    cursor = i;
    if (flat[i]) flat[i].el.scrollIntoView({ block: 'nearest' });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function markMatch(text, q) {
    var safe = esc(text);
    if (!q || q.length < 2) return safe;
    var lower = text.toLowerCase();
    var needle = q.toLowerCase();
    var idx = lower.indexOf(needle);
    if (idx < 0) return safe;
    return esc(text.slice(0, idx))
      + '<mark>' + esc(text.slice(idx, idx + q.length)) + '</mark>'
      + esc(text.slice(idx + q.length));
  }

  function rowHtml(label, sub, q) {
    return '<div class="sd-label">' + markMatch(label, q) + '</div>' +
           (sub ? '<div class="sd-sub">' + markMatch(sub, q) + '</div>' : '');
  }

  function addRow(container, label, sub, url, q, extraClass) {
    var el = document.createElement('a');
    el.className = 'sd-row' + (extraClass ? ' ' + extraClass : '');
    el.href = url;
    el.setAttribute('role', 'option');
    el.innerHTML = rowHtml(label, sub, q);
    var entry = { url: url, el: el };
    el.addEventListener('mouseenter', function () { highlight(flat.indexOf(entry)); });
    container.appendChild(el);
    flat.push(entry);
    return entry;
  }

  function showLoading(q) {
    loading = true;
    dd.innerHTML = '<div class="sd-loading"><i class="fa-solid fa-spinner fa-spin"></i> Searching…</div>';
    dd.style.display = 'block';
  }

  function render(data) {
    loading = false;
    dd.innerHTML = '';
    flat = [];
    cursor = -1;
    var q = data.q || '';

    if (data.exact) {
      var head = document.createElement('div');
      head.className = 'sd-group';
      head.innerHTML = '<div class="sd-group-title"><i class="fa-solid fa-crosshairs"></i> Exact match</div>';
      dd.appendChild(head);
      addRow(
        head,
        data.exact.barcode,
        data.exact.product + ' · ' + data.exact.location + ' · ' + data.exact.status,
        data.exact.url,
        q,
        'sd-exact'
      );
    }

    (data.groups || []).forEach(function (group) {
      var g = document.createElement('div');
      g.className = 'sd-group';
      var count = (group.results || []).length;
      g.innerHTML = '<div class="sd-group-title"><i class="fa-solid ' + esc(group.icon) + '"></i> '
        + esc(group.title)
        + '<span class="sd-group-count">' + count + '</span></div>';
      dd.appendChild(g);
      group.results.forEach(function (r) { addRow(g, r.label, r.sub, r.url, q); });
    });

    if (!flat.length) {
      dd.innerHTML = '<div class="sd-empty">No matches for &ldquo;' + esc(data.q) + '&rdquo;'
        + '<div class="sd-empty-hint">Try a barcode, invoice (RE…), product, or location</div></div>';
    } else {
      var foot = document.createElement('div');
      foot.className = 'sd-foot-wrap';
      foot.innerHTML =
        '<a class="sd-foot" href="' + searchUrl + '?q=' + encodeURIComponent(data.q) + '">See all results</a>'
        + '<div class="sd-kbd-hint"><kbd>↑</kbd><kbd>↓</kbd> navigate <kbd>↵</kbd> open <kbd>esc</kbd> close</div>';
      dd.appendChild(foot);
    }

    dd.style.display = 'block';
    if (data.exact) highlight(0);
  }

  function fetchSuggestions(q) {
    var mine = ++seq;
    showLoading(q);
    fetch(suggestUrl + '?q=' + encodeURIComponent(q), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || mine !== seq) return;   // a newer keystroke already won
        if (input.value.trim() !== data.q) return;
        render(data);
      })
      .catch(function () {
        if (mine !== seq) return;
        loading = false;
        dd.innerHTML = '<div class="sd-empty">Couldn’t reach search. Try again.</div>';
        dd.style.display = 'block';
      });
  }

  input.addEventListener('input', function () {
    var q = input.value.trim();
    if (q === lastQuery) return;
    lastQuery = q;
    clearTimeout(timer);
    if (q.length < 2) { close(); return; }
    timer = setTimeout(function () { fetchSuggestions(q); }, 180);
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') {
      if (!flat.length) return;
      e.preventDefault();
      highlight((cursor + 1) % flat.length);
    } else if (e.key === 'ArrowUp') {
      if (!flat.length) return;
      e.preventDefault();
      highlight((cursor - 1 + flat.length) % flat.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (cursor >= 0 && flat[cursor]) {
        window.location.href = flat[cursor].url;
      } else if (input.value.trim()) {
        // No highlight — let the server decide. It redirects straight to the
        // item if the query turns out to be an exact barcode/EPC.
        window.location.href = searchUrl + '?q=' + encodeURIComponent(input.value.trim());
      }
    } else if (e.key === 'Escape') {
      if (topbarSearch && topbarSearch.classList.contains('is-open')) {
        closeMobileSearch();
      } else {
        close();
        input.blur();
      }
    }
  });

  document.addEventListener('click', function (e) {
    if (!box.contains(e.target) && !(toggleBtn && toggleBtn.contains(e.target))) {
      close();
      // Don't auto-close mobile overlay on outside click into topbar-search itself
      if (topbarSearch && topbarSearch.classList.contains('is-open')
          && !topbarSearch.contains(e.target) && !(toggleBtn && toggleBtn.contains(e.target))) {
        closeMobileSearch();
      }
    }
  });

  input.addEventListener('focus', function () {
    if (flat.length || loading) dd.style.display = 'block';
  });

  // "/" to focus, matching the <kbd>/</kbd> hint already in the markup.
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/') return;
    var t = e.target;
    var typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
    if (typing) return;
    e.preventDefault();
    if (window.matchMedia('(max-width: 900px)').matches) {
      openMobileSearch();
    } else {
      input.focus();
      input.select();
    }
  });
})();
