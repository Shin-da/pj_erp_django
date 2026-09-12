// Perfect Jewel ERP — returns counter.
//
// Resolve each pasted barcode against the server, build one row per piece
// showing who had it and what the system currently thinks it is, and let
// the operator pick an outcome per row. Rows the transition table can't
// accept are shown greyed with the reason rather than hidden, because an
// operator holding a physical pile needs to know which ones didn't take.
//
// Nothing here decides eligibility on its own — the allowed outcomes for
// each row come from the server, which derives them from
// inventory.VALID_TRANSITIONS. The submit is re-validated server-side
// regardless.
(function () {
  var input = document.getElementById('retInput');
  if (!input) return;

  var lookupUrl = input.dataset.lookupUrl;
  var rowsBody = document.getElementById('retRows');
  var emptyRow = document.getElementById('retEmpty');
  var submitBtn = document.getElementById('retSubmit');
  var footNote = document.getElementById('retFootNote');
  var busy = document.getElementById('retBusy');
  var countReady = document.getElementById('retCountReady');
  var countBlocked = document.getElementById('retCountBlocked');

  var rows = [];   // {barcode, data, tr}
  var seen = {};   // lowercase barcode -> true, so a double scan is ignored

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function parseBarcodes(text) {
    return text.split(/[\r\n,]+/).map(function (s) { return s.trim(); }).filter(Boolean);
  }

  function refreshTotals() {
    var ready = rows.filter(function (r) { return r.data.ok; }).length;
    var blocked = rows.length - ready;
    countReady.textContent = ready;
    countBlocked.textContent = blocked;
    submitBtn.disabled = ready === 0;

    if (!rows.length) {
      footNote.textContent = 'Scan some barcodes to begin.';
    } else if (!ready) {
      footNote.textContent = 'None of these can be returned.';
    } else {
      footNote.textContent = ready + ' piece' + (ready === 1 ? '' : 's') +
        ' will be processed' + (blocked ? ', ' + blocked + ' skipped' : '') + '.';
    }
    emptyRow.style.display = rows.length ? 'none' : '';
  }

  function outcomeCell(data) {
    var allowed = data.allowed_outcomes || [];
    if (!data.ok || !allowed.length) {
      return '<span class="cell-muted">' + esc(data.error || 'Not returnable') + '</span>';
    }
    var opts = allowed.map(function (o) {
      return '<option value="' + esc(o.value) + '">' + esc(o.label) + '</option>';
    }).join('');
    return '<select name="outcome" class="field" style="width:100%; min-width:170px;">' + opts + '</select>';
  }

  function addRow(data) {
    var tr = document.createElement('tr');
    if (!data.ok) tr.className = 'is-blocked';

    var invoiceCell = data.invoice
      ? '<span class="mono">' + esc(data.invoice) + '</span>' +
        (data.invoice_cancelled ? ' <span class="pill pill-danger">Cancelled</span>' : '')
      : '<span class="cell-muted">—</span>';

    tr.innerHTML =
      '<td class="mono cell-strong">' + esc(data.barcode) +
        '<input type="hidden" name="barcode" value="' + esc(data.barcode) + '"></td>' +
      '<td>' + esc(data.product || '—') + '</td>' +
      '<td>' + esc(data.status || '—') + '</td>' +
      '<td>' + (data.holder ? esc(data.holder) : '<span class="cell-muted">—</span>') + '</td>' +
      '<td>' + invoiceCell + '</td>' +
      '<td>' + outcomeCell(data) + '</td>' +
      '<td><button type="button" class="ret-remove" title="Remove from batch">&times;</button></td>';

    // A blocked row must not submit a barcode with no matching outcome —
    // the POST pairs the two lists by position, so an unpaired barcode
    // would shift every outcome after it onto the wrong piece.
    if (!data.ok) {
      var hidden = tr.querySelector('input[name="barcode"]');
      if (hidden) hidden.removeAttribute('name');
    }

    var entry = { barcode: data.barcode, data: data, tr: tr };
    tr.querySelector('.ret-remove').addEventListener('click', function () {
      rows = rows.filter(function (r) { return r !== entry; });
      delete seen[data.barcode.toLowerCase()];
      tr.remove();
      refreshTotals();
    });

    rowsBody.appendChild(tr);
    rows.push(entry);
  }

  function lookup(barcode) {
    return fetch(lookupUrl + '?barcode=' + encodeURIComponent(barcode), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) {
          return { ok: false, barcode: barcode, error: 'Lookup failed — check the connection and try again.' };
        }
        if (!data.barcode) data.barcode = barcode;
        return data;
      })
      .catch(function () {
        return { ok: false, barcode: barcode, error: 'Lookup failed — check the connection and try again.' };
      });
  }

  function resolveAll() {
    var codes = parseBarcodes(input.value).filter(function (b) {
      return !seen[b.toLowerCase()];
    });
    if (!codes.length) return;

    codes.forEach(function (b) { seen[b.toLowerCase()] = true; });
    busy.style.display = 'inline-flex';

    // Sequential rather than parallel: a hundred simultaneous requests
    // from one paste is unkind to a dev server, and the operator is
    // watching rows appear anyway.
    var i = 0;
    function next() {
      if (i >= codes.length) {
        busy.style.display = 'none';
        input.value = '';
        refreshTotals();
        return;
      }
      lookup(codes[i++]).then(function (data) {
        addRow(data);
        refreshTotals();
        next();
      });
    }
    next();
  }

  document.getElementById('retResolve').addEventListener('click', resolveAll);

  input.addEventListener('keydown', function (e) {
    // A barcode gun types the code then sends Enter — resolve on the spot
    // rather than making someone reach for the button between pieces.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      resolveAll();
    }
  });

  document.getElementById('retClear').addEventListener('click', function () {
    input.value = '';
    rows.forEach(function (r) { r.tr.remove(); });
    rows = [];
    seen = {};
    refreshTotals();
    input.focus();
  });

  var bulkSeg = document.getElementById('retBulkSeg');
  if (bulkSeg) {
    bulkSeg.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var wanted = btn.dataset.outcome;
        rows.forEach(function (r) {
          var sel = r.tr.querySelector('select[name="outcome"]');
          if (!sel) return;
          // Only apply where that outcome is actually offered for this
          // row; a reserved piece has no "sold" option to select.
          var match = Array.prototype.slice.call(sel.options).some(function (o) { return o.value === wanted; });
          if (match) sel.value = wanted;
        });
      });
    });
  }

  refreshTotals();
  input.focus();
})();
