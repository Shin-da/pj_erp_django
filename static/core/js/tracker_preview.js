// Perfect Jewel ERP — Product Tracker redesign PREVIEW.
// Everything here is demo/sample-data interaction for walking through the
// concept with Cylver/Tatay — no real barcode validation, no database
// writes, no real "expected" logic. See apps/tracker/views.scan_preview
// for the sample data this reads from.
(function () {
  var cfg = window.TRACKER_PREVIEW;
  if (!cfg) return;

  /* ---------------- Main tab switch (Scan / History) ---------------- */
  var mainTabSeg = document.getElementById('mainTabSeg');
  var tabScan = document.getElementById('tabScan');
  var tabHistory = document.getElementById('tabHistory');

  if (mainTabSeg) {
    mainTabSeg.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        mainTabSeg.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var tab = btn.dataset.tab;
        tabScan.style.display = tab === 'scan' ? 'block' : 'none';
        tabHistory.style.display = tab === 'history' ? 'block' : 'none';
      });
    });
  }

  /* ---------------- Reseller group -> client cascading pickers ---------------- */
  function populateGroupSelect(select) {
    if (!select) return;
    cfg.resellerGroups.forEach(function (group) {
      var opt = new Option(group.name, group.code);
      select.add(opt);
    });
  }

  function wireGroupClientPair(groupSelectId, clientSelectId) {
    var groupSelect = document.getElementById(groupSelectId);
    var clientSelect = document.getElementById(clientSelectId);
    if (!groupSelect || !clientSelect) return;

    populateGroupSelect(groupSelect);

    groupSelect.addEventListener('change', function () {
      clientSelect.innerHTML = '';
      var group = cfg.resellerGroups.find(function (g) { return g.code === groupSelect.value; });
      if (!group) {
        clientSelect.add(new Option('-- Select a group first --', ''));
        return;
      }
      clientSelect.add(new Option('-- Select client --', ''));
      group.clients.forEach(function (client) {
        clientSelect.add(new Option(client.name + ' (' + client.code + ')', client.code));
      });
    });
  }

  wireGroupClientPair('raGroupSelect', 'raClientSelect');
  wireGroupClientPair('consGroupSelect', 'consClientSelect');

  /* ---------------- Room Allotment: "Request invoicing" demo ---------------- */
  var raInvoicingToggle = document.getElementById('raInvoicingToggle');
  var raInvoicingDemo = document.getElementById('raInvoicingDemo');
  if (raInvoicingToggle && raInvoicingDemo) {
    raInvoicingToggle.addEventListener('click', function () {
      var showing = raInvoicingDemo.style.display !== 'none';
      raInvoicingDemo.style.display = showing ? 'none' : 'block';
    });
  }

  /* ---------------- Consignment: Person / Location toggle ---------------- */
  var consDestSeg = document.getElementById('consDestSeg');
  var consPersonFields = document.getElementById('consPersonFields');
  var consLocationFields = document.getElementById('consLocationFields');
  if (consDestSeg) {
    consDestSeg.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        consDestSeg.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var isPerson = btn.dataset.consDest === 'PERSON';
        consPersonFields.style.display = isPerson ? 'block' : 'none';
        consLocationFields.style.display = isPerson ? 'none' : 'block';
      });
    });
  }

  /* ---------------- Return to Supplier: supplier picker ---------------- */
  var supplierSelect = document.getElementById('supplierSelect');
  var supplierCards = document.getElementById('supplierCards');
  if (supplierSelect) {
    cfg.suppliers.forEach(function (s) {
      supplierSelect.add(new Option(s.name, s.code));
    });
    supplierSelect.addEventListener('change', function () {
      var supplier = cfg.suppliers.find(function (s) { return s.code === supplierSelect.value; });
      if (!supplier) {
        supplierCards.style.display = 'none';
        setGauge(currentEntered(), 0, false);
        return;
      }
      supplierCards.style.display = 'flex';
      supplierCards.innerHTML =
        '<div class="panel" style="font-size:11.5px; flex:1; min-width:140px;"><div class="cell-muted">Expected on this supplier</div><div style="font-size:18px; font-weight:700;">' + supplier.expected + '</div></div>' +
        '<div class="panel" style="font-size:11.5px; flex:1; min-width:140px;"><div class="cell-muted">Last return</div><div style="font-size:14px; font-weight:600;">' + supplier.last_return + '</div></div>';
      setGauge(currentEntered(), supplier.expected, true);
    });
  }

  /* ---------------- Inventory direction toggle ---------------- */
  var invDirectionSeg = document.getElementById('invDirectionSeg');
  var invDirectionNote = document.getElementById('invDirectionNote');
  var invDemoExpected = { OPENING: 62, CLOSING: 50 };
  var currentInvDirection = 'OPENING';
  if (invDirectionSeg) {
    invDirectionSeg.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        invDirectionSeg.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentInvDirection = btn.dataset.invDir;
        invDirectionNote.textContent = currentInvDirection === 'OPENING'
          ? 'Head Office → Showroom. Fixed pair per Tatay\'s rule — no location picker, direction sets it automatically.'
          : 'Showroom → Head Office. Fixed pair per Tatay\'s rule — no location picker, direction sets it automatically.';
        if (currentScanType === 'INVENTORY') {
          setGauge(currentEntered(), invDemoExpected[currentInvDirection], true);
        }
      });
    });
  }

  /* ---------------- Scan type switch ---------------- */
  var scanTypeSeg = document.getElementById('scanTypeSeg');
  var currentScanType = 'INVENTORY';

  // Demo "expected" numbers per type, purely illustrative.
  var demoExpectedByType = {
    INVENTORY: null, // handled via invDemoExpected + direction
    TRANSFER: null,  // no expected concept — free-form move
    ROOM_ALLOTMENT: 100,
    CONSIGNMENT: 20,
    RETURN_TO_SUPPLIER: null, // depends on selected supplier
  };

  function applyScanType(type) {
    currentScanType = type;
    document.querySelectorAll('[data-type-panel]').forEach(function (panel) {
      panel.style.display = panel.dataset.typePanel === type ? 'block' : 'none';
    });

    if (type === 'INVENTORY') {
      setGauge(currentEntered(), invDemoExpected[currentInvDirection], true);
    } else if (type === 'ROOM_ALLOTMENT' || type === 'CONSIGNMENT') {
      setGauge(currentEntered(), demoExpectedByType[type], true);
    } else if (type === 'RETURN_TO_SUPPLIER') {
      var supplier = cfg.suppliers.find(function (s) { return s.code === (supplierSelect ? supplierSelect.value : ''); });
      setGauge(currentEntered(), supplier ? supplier.expected : 0, !!supplier);
    } else {
      // TRANSFER — no expected concept
      setGauge(currentEntered(), 0, false);
    }
  }

  if (scanTypeSeg) {
    scanTypeSeg.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        scanTypeSeg.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        applyScanType(btn.dataset.scanType);
      });
    });
  }

  /* ---------------- Gauge (demo — client-side only) ---------------- */
  var gaugeEntered = document.getElementById('previewGaugeEntered');
  var gaugeExpected = document.getElementById('previewGaugeExpected');
  var gaugeBadge = document.getElementById('previewGaugeBadge');
  var barcodeInput = document.getElementById('previewBarcodeInput');

  function currentEntered() {
    return gaugeEntered ? (parseInt(gaugeEntered.textContent, 10) || 0) : 0;
  }

  function setGauge(entered, expected, hasExpected) {
    if (gaugeEntered) gaugeEntered.textContent = entered;
    if (!gaugeExpected || !gaugeBadge) return;
    gaugeExpected.textContent = hasExpected ? expected : 0;
    if (!hasExpected) {
      gaugeBadge.textContent = 'No expected count';
    } else if (entered === expected) {
      gaugeBadge.textContent = 'Match';
    } else if (entered < expected) {
      gaugeBadge.textContent = 'Short by ' + (expected - entered);
    } else {
      gaugeBadge.textContent = 'Over by ' + (entered - expected);
    }
  }

  if (barcodeInput) {
    barcodeInput.addEventListener('input', function () {
      var lines = barcodeInput.value.split(/[\r\n,]+/).map(function (s) { return s.trim(); }).filter(Boolean);
      var entered = lines.length;

      if (currentScanType === 'INVENTORY') {
        setGauge(entered, invDemoExpected[currentInvDirection], true);
      } else if (currentScanType === 'ROOM_ALLOTMENT' || currentScanType === 'CONSIGNMENT') {
        setGauge(entered, demoExpectedByType[currentScanType], true);
      } else if (currentScanType === 'RETURN_TO_SUPPLIER') {
        var supplier = cfg.suppliers.find(function (s) { return s.code === (supplierSelect ? supplierSelect.value : ''); });
        setGauge(entered, supplier ? supplier.expected : 0, !!supplier);
      } else {
        setGauge(entered, 0, false);
      }
    });
  }

  /* ---------------- History tab: filter + view toggle ---------------- */
  var historyFilterSeg = document.getElementById('historyFilterSeg');
  var historyViewSeg = document.getElementById('historyViewSeg');
  var historyCards = document.getElementById('historyCards');
  var historyTable = document.getElementById('historyTable');

  function applyHistoryFilter(mode) {
    document.querySelectorAll('#historyCards [data-item-count], #historyTable tbody tr[data-item-count]').forEach(function (el) {
      var count = parseInt(el.dataset.itemCount, 10) || 0;
      el.style.display = (mode === 'WITH_STOCK' && count === 0) ? 'none' : '';
    });
  }

  if (historyFilterSeg) {
    historyFilterSeg.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        historyFilterSeg.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        applyHistoryFilter(btn.dataset.histFilter);
      });
    });
  }

  if (historyViewSeg) {
    historyViewSeg.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        historyViewSeg.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var isCards = btn.dataset.histView === 'CARDS';
        historyCards.style.display = isCards ? 'grid' : 'none';
        historyTable.style.display = isCards ? 'none' : 'block';
      });
    });
  }

  // Initial state
  applyScanType('INVENTORY');
})();
