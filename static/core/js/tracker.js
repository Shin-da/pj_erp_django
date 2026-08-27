// Perfect Jewel ERP — Product Tracker: live barcode validation + live gauge.
(function () {
  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  var box = document.getElementById('barcodeInput');
  if (!box) return; // not on this page

  var validatingNote = document.getElementById('barcodeValidatingNote');
  var removedPanel = document.getElementById('liveRemovedPanel');
  var url = box.dataset.validateUrl;

  var form = document.getElementById('scanForm');
  var expectedUrl = form ? form.dataset.expectedUrl : null;
  var gaugeEntered = document.getElementById('gaugeEntered');
  var gaugeExpected = document.getElementById('gaugeExpected');
  var gaugeBadge = document.getElementById('gaugeBadge');
  var scanTypeSelect = document.getElementById('scanType');
  var scanLocationSelect = document.getElementById('scanLocation');
  var parentSelect = document.getElementById('parentSelect');

  var currentEntered = gaugeEntered ? (parseInt(gaugeEntered.textContent, 10) || 0) : 0;

  var debounceHandle = null;
  var lastSentValue = null;
  var inFlight = false;

  function renderRemoved(removedPrefix, removedNotFound) {
    if (!removedPrefix.length && !removedNotFound.length) {
      removedPanel.innerHTML = '<div class="cell-muted">Removed barcodes will appear here</div>';
      return;
    }
    var html = '';
    if (removedPrefix.length) {
      html += '<div style="margin-bottom:8px;"><b>' + removedPrefix.length + '</b> barcode(s) that don\'t start with "PJ":</div>';
      removedPrefix.forEach(function (code) {
        html += '<div class="mono" style="padding:2px 0;">' + code + '</div>';
      });
    }
    if (removedNotFound.length) {
      html += '<div style="margin:8px 0;"><b>' + removedNotFound.length + '</b> barcode(s) not found in the system:</div>';
      removedNotFound.forEach(function (code) {
        html += '<div class="mono" style="padding:2px 0;">' + code + '</div>';
      });
    }
    removedPanel.innerHTML = html;
  }

  /* -------- Live gauge -------- */

  function setBadge(entered, expected, hasExpected) {
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

  function refreshExpected(entered) {
    var mode = scanTypeSelect ? scanTypeSelect.value : '';

    if (mode === 'CLOSING') {
      var opt = parentSelect && parentSelect.selectedOptions[0];
      var hasParent = !!(opt && opt.value !== '');
      var expected = hasParent ? (parseInt(opt.dataset.itemCount, 10) || 0) : 0;
      setBadge(entered, expected, hasParent);
      return;
    }

    if (mode === 'CHECK') {
      setBadge(entered, entered, entered > 0);
      return;
    }

    // OPENING (default)
    var locationId = scanLocationSelect ? scanLocationSelect.value : '';
    if (!locationId || !expectedUrl) {
      setBadge(entered, 0, false);
      return;
    }
    fetch(expectedUrl + '?location_id=' + encodeURIComponent(locationId))
      .then(function (res) { return res.json(); })
      .then(function (data) {
        setBadge(entered, data.expected || 0, true);
      })
      .catch(function () {
        setBadge(entered, 0, false);
      });
  }

  function updateGauge(entered) {
    currentEntered = entered;
    if (gaugeEntered) gaugeEntered.textContent = entered;
    refreshExpected(entered);
  }

  if (scanTypeSelect) scanTypeSelect.addEventListener('change', function () { refreshExpected(currentEntered); });
  if (scanLocationSelect) scanLocationSelect.addEventListener('change', function () { refreshExpected(currentEntered); });
  if (parentSelect) parentSelect.addEventListener('change', function () { refreshExpected(currentEntered); });

  /* -------- Validation (existing) -------- */

  function runValidation() {
    var currentValue = box.value;
    if (currentValue === lastSentValue) return;
    if (currentValue.trim() === '') {
      lastSentValue = currentValue;
      renderRemoved([], []);
      validatingNote.style.display = 'none';
      updateGauge(0);
      return;
    }
    if (inFlight) return;

    lastSentValue = currentValue;
    inFlight = true;
    validatingNote.style.display = 'inline-flex';

    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ raw: currentValue }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        inFlight = false;
        validatingNote.style.display = 'none';
        if (box.value !== currentValue) return; // stale response, box changed since
        box.value = data.normalized_text;
        lastSentValue = data.normalized_text;
        renderRemoved(data.removed_prefix, data.removed_not_found);
        var enteredCount = data.normalized_text ? data.normalized_text.split('\n').filter(Boolean).length : 0;
        updateGauge(enteredCount);
      })
      .catch(function () {
        inFlight = false;
        validatingNote.style.display = 'none';
        removedPanel.innerHTML = '<div class="cell-muted">Validation failed — try again.</div>';
      });
  }

  box.addEventListener('input', function () {
    if (debounceHandle) clearTimeout(debounceHandle);
    debounceHandle = setTimeout(runValidation, 500);
  });
})();