// Perfect Jewel ERP — global nav search.
//
// Behaviour:
//   - Typing (2+ chars, debounced) fetches grouped suggestions and shows a
//     dropdown under the search box.
//   - An exact barcode match is pinned to the top and pre-selected, so a
//     barcode scanner — which types the code then sends Enter — lands
//     straight on that piece with zero clicks.
//   - Arrow keys move through results, Enter opens the highlighted one,
//     Escape closes. Enter with nothing highlighted opens the full
//     results page.
//   - "/" anywhere on the page focuses the box (unless you're already
//     typing in a field).
(function () {
  var box = document.querySelector('.topbar-search .search-box');
  if (!box) return;
  var input = box.querySelector('input');
  if (!input) return;

  var suggestUrl = box.dataset.suggestUrl;
  var searchUrl = box.dataset.searchUrl;
  if (!suggestUrl || !searchUrl) return;

  // ---- dropdown element ----
  var dd = document.createElement('div');
  dd.className = 'search-dd';
  dd.style.display = 'none';
  box.appendChild(dd);

  var flat = [];      // flat list of {url, el} for keyboard nav
  var cursor = -1;
  var timer = null;
  var lastQuery = '';
  var seq = 0;        // guards against out-of-order responses

  function close() {
    dd.style.display = 'none';
    dd.innerHTML = '';
    flat = [];
    cursor = -1;
  }

  function highlight(i) {
    flat.forEach(function (r, n) { r.el.classList.toggle('active', n === i); });
    cursor = i;
    if (flat[i]) flat[i].el.scrollIntoView({ block: 'nearest' });
  }

  function rowHtml(label, sub) {
    return '<div class="sd-label">' + esc(label) + '</div>' +
           (sub ? '<div class="sd-sub">' + esc(sub) + '</div>' : '');
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function addRow(container, label, sub, url, extraClass) {
    var el = document.createElement('a');
    el.className = 'sd-row' + (extraClass ? ' ' + extraClass : '');
    el.href = url;
    el.innerHTML = rowHtml(label, sub);
    el.addEventListener('mouseenter', function () { highlight(flat.indexOf(entry)); });
    container.appendChild(el);
    var entry = { url: url, el: el };
    flat.push(entry);
    return entry;
  }

  function render(data) {
    dd.innerHTML = '';
    flat = [];
    cursor = -1;

    if (data.exact) {
      var head = document.createElement('div');
      head.className = 'sd-group';
      head.innerHTML = '<div class="sd-group-title"><i class="fa-solid fa-crosshairs"></i> Exact barcode</div>';
      dd.appendChild(head);
      addRow(
        head,
        data.exact.barcode,
        data.exact.product + ' · ' + data.exact.location + ' · ' + data.exact.status,
        data.exact.url,
        'sd-exact'
      );
    }

    (data.groups || []).forEach(function (group) {
      var g = document.createElement('div');
      g.className = 'sd-group';
      g.innerHTML = '<div class="sd-group-title"><i class="fa-solid ' + esc(group.icon) + '"></i> ' + esc(group.title) + '</div>';
      dd.appendChild(g);
      group.results.forEach(function (r) { addRow(g, r.label, r.sub, r.url); });
    });

    if (!flat.length) {
      dd.innerHTML = '<div class="sd-empty">No matches for &ldquo;' + esc(data.q) + '&rdquo;</div>';
    } else {
      var foot = document.createElement('a');
      foot.className = 'sd-foot';
      foot.href = searchUrl + '?q=' + encodeURIComponent(data.q);
      foot.textContent = 'See all results';
      dd.appendChild(foot);
    }

    dd.style.display = 'block';
    if (data.exact) highlight(0);
  }

  function fetchSuggestions(q) {
    var mine = ++seq;
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
      .catch(function () { /* offline / 500 — just leave the dropdown closed */ });
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
        // item if the query turns out to be an exact barcode.
        window.location.href = searchUrl + '?q=' + encodeURIComponent(input.value.trim());
      }
    } else if (e.key === 'Escape') {
      close();
      input.blur();
    }
  });

  document.addEventListener('click', function (e) {
    if (!box.contains(e.target)) close();
  });

  input.addEventListener('focus', function () {
    if (flat.length) dd.style.display = 'block';
  });

  // "/" to focus, matching the <kbd>/</kbd> hint already in the markup.
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/') return;
    var t = e.target;
    var typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
    if (typing) return;
    e.preventDefault();
    input.focus();
    input.select();
  });
})();
