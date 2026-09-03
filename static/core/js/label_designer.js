// Perfect Jewel ERP — Irys-aware label designer.
// Drag fields on a paper outline (tail / front / back), edit properties,
// save as LabelTemplate + LabelField. See apps/hardware/zpl.py for ZPL.
(function () {
  var cfg = window.HARDWARE_DESIGNER;
  if (!cfg) return;

  var canvas = document.getElementById('labelCanvas');
  var canvasWrap = document.getElementById('labelCanvasWrap');
  var propEmpty = document.getElementById('propEmpty');
  var propForm = document.getElementById('propForm');
  var sizeLabel = document.getElementById('canvasSizeLabel');
  var zoomLabel = document.getElementById('zoomLabel');
  var selectedId = null;
  var nextTempId = -1;
  var zoom = cfg.zoom || 2; // CSS px per printer dot — Irys tags are tiny

  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  function mmToDots(mm, dpi) {
    return Math.round(mm * (dpi || 300) / 25.4);
  }

  function scaleDot(value, fromDpi, toDpi) {
    fromDpi = fromDpi || 300;
    toDpi = toDpi || 300;
    if (fromDpi === toDpi) return Math.round(value || 0);
    return Math.round((value || 0) * toDpi / fromDpi);
  }

  /** Rebuild Irys / blank geometry at an arbitrary printer DPI (matches media.py). */
  function buildMediaProfile(profileId, dpi, widthDots, heightDots) {
    dpi = parseInt(dpi, 10) || 300;
    if (profileId === 'irys_standard') {
      var tailW = mmToDots(50, dpi);
      var faceW = mmToDots(25, dpi);
      var faceH = mmToDots(13, dpi);
      var width = tailW + faceW;
      var height = faceH * 2;
      var tailH = mmToDots(4, dpi);
      var tailY = Math.floor((faceH - tailH) / 2);
      var tipW = mmToDots(6, dpi);
      var base = {
        id: 'irys_standard',
        label: 'Irys Standard RFID (25×13 mm closed + 50 mm tail)',
        dpi: dpi,
        width_mm: Math.round(width * 25.4 / dpi * 10) / 10,
        height_mm: Math.round(height * 25.4 / dpi * 10) / 10,
        width_dots: width,
        height_dots: height,
        regions: [
          { id: 'tail', label: 'Tail', hint: 'On the front face only', x: 0, y: tailY, w: tailW, h: tailH },
          { id: 'front', label: 'Front', hint: 'Tail attached', x: tailW, y: 0, w: faceW, h: faceH },
          { id: 'back', label: 'Back', hint: 'No tail', x: tailW, y: faceH, w: faceW, h: faceH },
        ],
        outline: [
          [0, tailY + Math.floor(tailH / 2)],
          [tipW, tailY],
          [tailW, tailY],
          [tailW, 0],
          [width, 0],
          [width, height],
          [tailW, height],
          [tailW, tailY + tailH],
          [tipW, tailY + tailH],
        ],
        fold_y: faceH,
      };
      if (widthDots && heightDots && (widthDots !== width || heightDots !== height)) {
        var sx = widthDots / width;
        var sy = heightDots / height;
        base.width_dots = widthDots;
        base.height_dots = heightDots;
        base.width_mm = Math.round(widthDots * 25.4 / dpi * 10) / 10;
        base.height_mm = Math.round(heightDots * 25.4 / dpi * 10) / 10;
        base.regions = base.regions.map(function (r) {
          return {
            id: r.id, label: r.label, hint: r.hint,
            x: Math.round(r.x * sx), y: Math.round(r.y * sy),
            w: Math.round(r.w * sx), h: Math.round(r.h * sy),
          };
        });
        base.outline = base.outline.map(function (p) {
          return [Math.round(p[0] * sx), Math.round(p[1] * sy)];
        });
        base.fold_y = Math.round(base.fold_y * sy);
      }
      return base;
    }
    var w = widthDots || mmToDots(75, dpi);
    var h = heightDots || mmToDots(26, dpi);
    return {
      id: 'blank',
      label: 'Blank rectangle (free design)',
      dpi: dpi,
      width_mm: Math.round(w * 25.4 / dpi * 10) / 10,
      height_mm: Math.round(h * 25.4 / dpi * 10) / 10,
      width_dots: w,
      height_dots: h,
      regions: [{ id: 'body', label: 'Label', hint: 'Full printable area', x: 0, y: 0, w: w, h: h }],
      outline: [[0, 0], [w, 0], [w, h], [0, h]],
      fold_y: null,
    };
  }

  function refreshMediaCatalog(dpi) {
    cfg.mediaProfiles = {
      irys_standard: buildMediaProfile('irys_standard', dpi),
      blank: buildMediaProfile('blank', dpi),
    };
  }

  function applyDpi(newDpi, opts) {
    opts = opts || {};
    newDpi = parseInt(newDpi, 10) || 300;
    var oldDpi = cfg.dpi || 300;
    if (newDpi === oldDpi && !opts.force) return;
    if (oldDpi !== newDpi) {
      cfg.fields.forEach(function (f) {
        f.x = scaleDot(f.x, oldDpi, newDpi);
        f.y = scaleDot(f.y, oldDpi, newDpi);
        f.font_size = Math.max(8, scaleDot(f.font_size, oldDpi, newDpi));
        f.box_width = Math.max(10, scaleDot(f.box_width, oldDpi, newDpi));
      });
      var ox = document.getElementById('tplOffsetX');
      var oy = document.getElementById('tplOffsetY');
      if (ox) ox.value = scaleDot(parseInt(ox.value, 10) || 0, oldDpi, newDpi);
      if (oy) oy.value = scaleDot(parseInt(oy.value, 10) || 0, oldDpi, newDpi);
    }
    cfg.dpi = newDpi;
    refreshMediaCatalog(newDpi);
    var preset = cfg.mediaProfiles[cfg.mediaProfile] || cfg.mediaProfiles.irys_standard;
    if (opts.keepSize) {
      cfg.geometry = buildMediaProfile(cfg.mediaProfile, newDpi, cfg.widthDots, cfg.heightDots);
    } else {
      cfg.widthDots = preset.width_dots;
      cfg.heightDots = preset.height_dots;
      cfg.geometry = JSON.parse(JSON.stringify(preset));
    }
    syncSizeInputs();
    applyZoom();
    renderProps();
  }

  function fieldById(id) {
    return cfg.fields.find(function (f) { return f.id === id; });
  }

  function labelForField(f) {
    if (f.field_key === 'static_text') {
      return f.static_text || '(empty text)';
    }
    if (f.field_key === 'horizontal_line') {
      return '';
    }
    var base = cfg.fieldLabels[f.field_key] || f.field_key;
    var sample = cfg.sampleValues[f.field_key] || '';
    if (f.field_key === 'barcode_image') {
      return '▮▮ ' + (sample || 'BARCODE');
    }
    return f.static_text ? (f.static_text + sample) : sample || base;
  }

  function regionAt(x, y) {
    var regions = (cfg.geometry && cfg.geometry.regions) || [];
    for (var i = 0; i < regions.length; i++) {
      var r = regions[i];
      if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
        return r;
      }
    }
    return null;
  }

  function applyZoom() {
    var w = cfg.widthDots;
    var h = cfg.heightDots;
    canvas.style.width = (w * zoom) + 'px';
    canvas.style.height = (h * zoom) + 'px';
    canvas.style.setProperty('--dot-scale', String(zoom));
    if (zoomLabel) zoomLabel.textContent = zoom.toFixed(1) + '×';
    if (sizeLabel) {
      var mmW = cfg.geometry && cfg.geometry.width_mm;
      var mmH = cfg.geometry && cfg.geometry.height_mm;
      sizeLabel.textContent = w + '×' + h + ' dots'
        + (mmW && mmH ? ' · ~' + mmW + '×' + mmH + ' mm' : '')
        + ' · ' + (cfg.dpi || 300) + ' dpi';
    }
    renderCanvas();
  }

  function buildOutline() {
    var geo = cfg.geometry || {};
    var outline = document.createElement('div');
    outline.className = 'label-paper-outline';
    outline.setAttribute('aria-hidden', 'true');

    (geo.regions || []).forEach(function (r) {
      var zone = document.createElement('div');
      zone.className = 'label-zone label-zone-' + r.id;
      zone.style.left = (r.x * zoom) + 'px';
      zone.style.top = (r.y * zoom) + 'px';
      zone.style.width = (r.w * zoom) + 'px';
      zone.style.height = (r.h * zoom) + 'px';
      var tag = document.createElement('span');
      tag.className = 'label-zone-tag';
      tag.textContent = r.label;
      zone.appendChild(tag);
      if (r.hint) zone.title = r.hint;
      outline.appendChild(zone);
    });

    if (geo.fold_y != null) {
      var fold = document.createElement('div');
      fold.className = 'label-fold-line';
      fold.style.top = (geo.fold_y * zoom) + 'px';
      fold.style.left = ((geo.regions.find(function (r) { return r.id === 'front' || r.id === 'back'; }) || { x: 0 }).x * zoom) + 'px';
      fold.style.width = ((geo.regions.find(function (r) { return r.id === 'front'; }) || { w: geo.width_dots }).w * zoom) + 'px';
      outline.appendChild(fold);
    }

    // Clip silhouette using CSS clip-path from outline polygon.
    if (geo.outline && geo.outline.length) {
      var pts = geo.outline.map(function (p) {
        return (p[0] * zoom) + 'px ' + (p[1] * zoom) + 'px';
      }).join(', ');
      outline.style.clipPath = 'polygon(' + pts + ')';
      // Soft shadow layer behind (unclipped wrapper handled by parent).
    }

    return outline;
  }

  function renderCanvas() {
    canvas.innerHTML = '';
    canvas.appendChild(buildOutline());

    cfg.fields.forEach(function (f) {
      var box = document.createElement('div');
      var isLine = f.field_key === 'horizontal_line';
      var isBarcode = f.field_key === 'barcode_image';
      box.className = 'label-field-box'
        + (f.id === selectedId ? ' selected' : '')
        + (!f.visible ? ' hidden-field' : '')
        + (isLine ? ' is-line' : '')
        + (isBarcode ? ' is-barcode' : '');
      box.style.left = (f.x * zoom) + 'px';
      box.style.top = (f.y * zoom) + 'px';
      box.style.width = (f.box_width * zoom) + 'px';
      if (!isLine) {
        var fs = Math.max(8, Math.round(f.font_size * zoom * 0.55));
        box.style.fontSize = fs + 'px';
        box.style.fontWeight = f.bold ? '700' : '400';
        box.style.textAlign = f.align === 'C' ? 'center' : (f.align === 'R' ? 'right' : 'left');
        box.textContent = labelForField(f);
      } else {
        box.style.height = Math.max(1, Math.round((f.font_size / 10 || 1) * zoom)) + 'px';
      }
      box.dataset.id = String(f.id);
      box.title = (cfg.fieldLabels[f.field_key] || f.field_key)
        + ' @ ' + f.x + ',' + f.y
        + (regionAt(f.x, f.y) ? ' (' + regionAt(f.x, f.y).label + ')' : '');
      box.addEventListener('pointerdown', onBoxPointerDown);
      canvas.appendChild(box);
    });

    updateRegionHint();
  }

  function updateRegionHint() {
    var el = document.getElementById('regionHint');
    if (!el) return;
    var f = fieldById(selectedId);
    if (!f) {
      el.textContent = 'Click a zone or add a field. Drag to position.';
      return;
    }
    var r = regionAt(f.x, f.y);
    el.textContent = r
      ? ('On ' + r.label + (r.hint ? ' — ' + r.hint : ''))
      : 'Outside marked print zones — may miss the die-cut.';
  }

  function highlightSelected() {
    canvas.querySelectorAll('.label-field-box').forEach(function (el) {
      var id = parseInt(el.dataset.id, 10);
      if (id === selectedId) el.classList.add('selected');
      else el.classList.remove('selected');
    });
  }

  function selectField(id, opts) {
    selectedId = id;
    if (opts && opts.rebuild) renderCanvas();
    else highlightSelected();
    renderProps();
    updateRegionHint();
  }

  function renderProps() {
    var f = fieldById(selectedId);
    if (!f) {
      propEmpty.style.display = 'block';
      propForm.style.display = 'none';
      return;
    }
    propEmpty.style.display = 'none';
    propForm.style.display = 'block';
    document.getElementById('propKeyLabel').textContent =
      cfg.fieldLabels[f.field_key] || f.field_key;
    document.getElementById('propText').value = f.static_text || '';
    document.getElementById('propX').value = f.x;
    document.getElementById('propY').value = f.y;
    document.getElementById('propFont').value = f.font_size;
    document.getElementById('propBoxWidth').value = f.box_width;
    document.getElementById('propAlign').value = f.align;
    document.getElementById('propBold').checked = !!f.bold;
    document.getElementById('propVisible').checked = !!f.visible;
    var isLine = f.field_key === 'horizontal_line';
    document.getElementById('propText').disabled = isLine;
    document.getElementById('propAlign').disabled = isLine;
    document.getElementById('propBold').disabled = isLine;
  }

  function bindProp(inputId, key, transform) {
    document.getElementById(inputId).addEventListener('input', function () {
      var f = fieldById(selectedId);
      if (!f) return;
      var val = this.type === 'checkbox' ? this.checked : this.value;
      f[key] = transform ? transform(val) : val;
      renderCanvas();
      updateRegionHint();
    });
  }

  bindProp('propText', 'static_text');
  bindProp('propX', 'x', function (v) { return parseInt(v, 10) || 0; });
  bindProp('propY', 'y', function (v) { return parseInt(v, 10) || 0; });
  bindProp('propFont', 'font_size', function (v) { return parseInt(v, 10) || 10; });
  bindProp('propBoxWidth', 'box_width', function (v) { return parseInt(v, 10) || 50; });
  bindProp('propAlign', 'align');
  bindProp('propBold', 'bold');
  bindProp('propVisible', 'visible');

  document.getElementById('propDelete').addEventListener('click', function () {
    if (selectedId === null) return;
    cfg.fields = cfg.fields.filter(function (f) { return f.id !== selectedId; });
    selectedId = null;
    renderCanvas();
    renderProps();
  });

  function addField(key, x, y) {
    var id = nextTempId--;
    var isBarcodeImage = key === 'barcode_image';
    var isLine = key === 'horizontal_line';
    var dropX = typeof x === 'number' ? x : 20;
    var dropY = typeof y === 'number' ? y : (20 + (cfg.fields.length * 8) % Math.max(40, cfg.heightDots - 40));
    var defaultW = isLine ? Math.min(180, cfg.widthDots - dropX - 4)
      : (isBarcodeImage ? 160 : 90);
      // Prefer dropping into the front panel for Irys if no coords given.
    if (typeof x !== 'number' && cfg.geometry && cfg.geometry.regions) {
      var front = cfg.geometry.regions.find(function (r) { return r.id === 'front'; });
      var tail = cfg.geometry.regions.find(function (r) { return r.id === 'tail'; });
      if ((key === 'supplier_code' || key === 'subcategory') && tail) {
        dropX = tail.x + 40;
        dropY = tail.y + Math.max(1, Math.floor((tail.h - 12) / 2));
        defaultW = Math.max(40, tail.w - 50);
      } else if (front) {
        dropX = front.x + 6;
        dropY = front.y + 6 + (cfg.fields.length * 10) % Math.max(20, front.h - 24);
        defaultW = Math.min(defaultW, front.w - 12);
      }
    }
    cfg.fields.push({
      id: id,
      field_key: key,
      static_text: '',
      x: dropX,
      y: dropY,
      font_size: isLine ? 12 : (isBarcodeImage ? 18 : 16),
      bold: false,
      align: key === 'supplier_code' ? 'C' : 'L',
      box_width: defaultW,
      visible: true,
      order: cfg.fields.length,
    });
    selectField(id, { rebuild: true });
  }

  document.querySelectorAll('[data-add-field]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      addField(btn.dataset.addField);
    });
    // Drag from palette onto canvas
    btn.setAttribute('draggable', 'true');
    btn.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('text/field-key', btn.dataset.addField);
      e.dataTransfer.effectAllowed = 'copy';
    });
  });

  canvas.addEventListener('dragover', function (e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });

  canvas.addEventListener('drop', function (e) {
    e.preventDefault();
    var key = e.dataTransfer.getData('text/field-key');
    if (!key) return;
    var rect = canvas.getBoundingClientRect();
    var x = Math.max(0, Math.round((e.clientX - rect.left) / zoom));
    var y = Math.max(0, Math.round((e.clientY - rect.top) / zoom));
    addField(key, x, y);
  });

  /* -------- Drag placed fields (don't rebuild DOM on pick — that killed the drag) -------- */
  var dragging = null, dragOffsetX = 0, dragOffsetY = 0, didDrag = false;

  function onBoxPointerDown(e) {
    if (e.button != null && e.button !== 0) return;
    var box = e.currentTarget;
    var id = parseInt(box.dataset.id, 10);
    selectField(id);
    dragging = box;
    didDrag = false;
    var rect = box.getBoundingClientRect();
    dragOffsetX = e.clientX - rect.left;
    dragOffsetY = e.clientY - rect.top;
    box.classList.add('dragging');
    try { box.setPointerCapture(e.pointerId); } catch (err) {}
    e.preventDefault();
    e.stopPropagation();
  }

  function onPointerMove(e) {
    if (!dragging) return;
    var canvasRect = canvas.getBoundingClientRect();
    var id = parseInt(dragging.dataset.id, 10);
    var f = fieldById(id);
    var boxW = f ? f.box_width : 40;
    var x = Math.round((e.clientX - canvasRect.left - dragOffsetX) / zoom);
    var y = Math.round((e.clientY - canvasRect.top - dragOffsetY) / zoom);
    x = Math.max(0, Math.min(cfg.widthDots - 4, x));
    y = Math.max(0, Math.min(cfg.heightDots - 4, y));
    if (f && x + boxW > cfg.widthDots) x = Math.max(0, cfg.widthDots - boxW);
    dragging.style.left = (x * zoom) + 'px';
    dragging.style.top = (y * zoom) + 'px';
    if (f) {
      if (f.x !== x || f.y !== y) didDrag = true;
      f.x = x;
      f.y = y;
    }
    if (f && id === selectedId) {
      document.getElementById('propX').value = x;
      document.getElementById('propY').value = y;
      updateRegionHint();
    }
  }

  function onPointerUp(e) {
    if (!dragging) return;
    dragging.classList.remove('dragging');
    try { dragging.releasePointerCapture(e.pointerId); } catch (err) {}
    dragging = null;
  }

  document.addEventListener('pointermove', onPointerMove);
  document.addEventListener('pointerup', onPointerUp);
  document.addEventListener('pointercancel', onPointerUp);

  /* -------- Zoom -------- */
  var zoomIn = document.getElementById('zoomIn');
  var zoomOut = document.getElementById('zoomOut');
  if (zoomIn) zoomIn.addEventListener('click', function () {
    zoom = Math.min(6, Math.round((zoom + 0.25) * 100) / 100);
    applyZoom();
  });
  if (zoomOut) zoomOut.addEventListener('click', function () {
    zoom = Math.max(1, Math.round((zoom - 0.25) * 100) / 100);
    applyZoom();
  });

  /* -------- Paper / size -------- */
  var mediaSelect = document.getElementById('tplMedia');
  var widthInput = document.getElementById('tplWidth');
  var heightInput = document.getElementById('tplHeight');

  function syncSizeInputs() {
    if (widthInput) widthInput.value = cfg.widthDots;
    if (heightInput) heightInput.value = cfg.heightDots;
  }

  if (mediaSelect) {
    mediaSelect.addEventListener('change', function () {
      var pid = mediaSelect.value;
      refreshMediaCatalog(cfg.dpi || 300);
      var preset = cfg.mediaProfiles[pid];
      if (!preset) return;
      if (!confirm('Switch paper to "' + (preset.label || pid) + '" and resize the canvas to match? Field positions stay as-is.')) {
        mediaSelect.value = cfg.mediaProfile;
        return;
      }
      cfg.mediaProfile = pid;
      cfg.widthDots = preset.width_dots;
      cfg.heightDots = preset.height_dots;
      cfg.geometry = JSON.parse(JSON.stringify(preset));
      syncSizeInputs();
      applyZoom();
    });
  }

  function onSizeChange() {
    cfg.widthDots = parseInt(widthInput.value, 10) || cfg.widthDots;
    cfg.heightDots = parseInt(heightInput.value, 10) || cfg.heightDots;
    cfg.geometry = buildMediaProfile(cfg.mediaProfile, cfg.dpi || 300, cfg.widthDots, cfg.heightDots);
    applyZoom();
  }

  if (widthInput) widthInput.addEventListener('change', onSizeChange);
  if (heightInput) heightInput.addEventListener('change', onSizeChange);

  var dpiSelect = document.getElementById('tplDpi');
  if (dpiSelect) {
    dpiSelect.addEventListener('change', function () {
      var next = parseInt(dpiSelect.value, 10) || 300;
      if (next === (cfg.dpi || 300)) return;
      if (!confirm('Switch to ' + next + ' DPI? Field positions will be rescaled to keep the same physical layout. Jewellery RFID Zebras are usually 300.')) {
        dpiSelect.value = String(cfg.dpi || 300);
        return;
      }
      applyDpi(next);
    });
  }

  document.getElementById('fitIrysBtn') && document.getElementById('fitIrysBtn').addEventListener('click', function () {
    refreshMediaCatalog(cfg.dpi || 300);
    if (mediaSelect) mediaSelect.value = 'irys_standard';
    cfg.mediaProfile = 'irys_standard';
    var preset = cfg.mediaProfiles.irys_standard;
    cfg.widthDots = preset.width_dots;
    cfg.heightDots = preset.height_dots;
    cfg.geometry = JSON.parse(JSON.stringify(preset));
    syncSizeInputs();
    applyZoom();
  });

  /* -------- Sample jewellery layout -------- */
  document.getElementById('loadSampleBtn') && document.getElementById('loadSampleBtn').addEventListener('click', function () {
    if (!confirm('Replace current fields with the Irys jewellery sample layout (front / back / tail)?')) return;
    refreshMediaCatalog(cfg.dpi || 300);
    var preset = cfg.mediaProfiles.irys_standard;
    cfg.mediaProfile = 'irys_standard';
    if (mediaSelect) mediaSelect.value = 'irys_standard';
    cfg.widthDots = preset.width_dots;
    cfg.heightDots = preset.height_dots;
    cfg.geometry = JSON.parse(JSON.stringify(preset));
    // Typical Zebra jewellery RFID needs a small downward nudge onto the die-cut.
    var ox = document.getElementById('tplOffsetX');
    var oy = document.getElementById('tplOffsetY');
    if (ox) ox.value = '0';
    if (oy && !(parseInt(oy.value, 10) || 0)) oy.value = '35';
    syncSizeInputs();

    var front = preset.regions.find(function (r) { return r.id === 'front'; });
    var back = preset.regions.find(function (r) { return r.id === 'back'; });
    var tail = preset.regions.find(function (r) { return r.id === 'tail'; });
    // Tuned for 300 DPI faces (~295×154); scale if the template DPI differs.
    var s = (cfg.dpi || 300) / 300;
    function ds(n) { return Math.max(1, Math.round(n * s)); }
    var id = -1;
    function F(key, x, y, opts) {
      opts = opts || {};
      return {
        id: id--,
        field_key: key,
        static_text: opts.static_text || '',
        x: x, y: y,
        font_size: opts.font_size || ds(20),
        bold: !!opts.bold,
        align: opts.align || 'L',
        box_width: opts.box_width || ds(120),
        visible: true,
        order: 0,
      };
    }
    cfg.fields = [
      F('subcategory', tail.x + ds(70), tail.y + ds(6), {
        font_size: ds(24), bold: true, align: 'C', box_width: Math.max(ds(80), tail.w - ds(100)),
      }),
      F('reference_id', front.x + ds(8), front.y + ds(6), {
        font_size: ds(22), bold: true, box_width: front.w - ds(16),
      }),
      F('price_rated', front.x + ds(8), front.y + ds(40), {
        font_size: ds(26), bold: true, align: 'C', box_width: front.w - ds(16),
      }),
      F('horizontal_line', front.x + ds(8), front.y + ds(76), {
        font_size: ds(12), box_width: front.w - ds(16),
      }),
      F('barcode_number', back.x + ds(8), back.y + ds(8), {
        font_size: ds(22), bold: true, box_width: back.w - ds(16),
      }),
      F('barcode_image', back.x + ds(8), back.y + ds(36), {
        font_size: ds(22), box_width: back.w - ds(16),
      }),
      F('category_code', back.x + ds(8), back.y + ds(84), {
        font_size: ds(16), box_width: ds(60),
      }),
      F('company_name', back.x + ds(8), back.y + ds(101), {
        font_size: ds(15), bold: true, align: 'C', box_width: back.w - ds(16),
      }),
    ];
    selectedId = null;
    applyZoom();
    renderProps();
  });

  /* -------- Save -------- */
  document.getElementById('saveBtn').addEventListener('click', function () {
    var status = document.getElementById('saveStatus');
    status.textContent = 'Saving…';

    var payload = {
      name: document.getElementById('tplName').value,
      category: document.getElementById('tplCategory').value,
      is_default: document.getElementById('tplIsDefault').checked,
      media_profile: cfg.mediaProfile,
      width_dots: cfg.widthDots,
      height_dots: cfg.heightDots,
      dpi: cfg.dpi || 300,
      offset_x: parseInt((document.getElementById('tplOffsetX') || {}).value, 10) || 0,
      offset_y: parseInt((document.getElementById('tplOffsetY') || {}).value, 10) || 0,
      fields: cfg.fields.map(function (f) {
        return {
          id: f.id > 0 ? f.id : null,
          field_key: f.field_key,
          static_text: f.static_text,
          x: f.x,
          y: f.y,
          font_size: f.font_size,
          bold: f.bold,
          align: f.align,
          box_width: f.box_width,
          visible: f.visible,
        };
      }),
    };

    fetch(cfg.saveUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.ok) {
          status.textContent = 'Saved.';
          if (data.fields) cfg.fields = data.fields;
          if (data.geometry) cfg.geometry = data.geometry;
          if (data.width_dots) cfg.widthDots = data.width_dots;
          if (data.height_dots) cfg.heightDots = data.height_dots;
          if (data.media_profile) cfg.mediaProfile = data.media_profile;
          if (typeof data.dpi === 'number') {
            cfg.dpi = data.dpi;
            if (dpiSelect) dpiSelect.value = String(data.dpi);
            refreshMediaCatalog(data.dpi);
          }
          if (typeof data.offset_x === 'number' && document.getElementById('tplOffsetX')) {
            document.getElementById('tplOffsetX').value = data.offset_x;
          }
          if (typeof data.offset_y === 'number' && document.getElementById('tplOffsetY')) {
            document.getElementById('tplOffsetY').value = data.offset_y;
          }
          syncSizeInputs();
          applyZoom();
          setTimeout(function () { status.textContent = ''; }, 2000);
        } else {
          status.textContent = 'Error: ' + (data.error || 'save failed');
        }
      })
      .catch(function () {
        status.textContent = 'Save failed — check your connection.';
      });
  });

  refreshMediaCatalog(cfg.dpi || 300);
  syncSizeInputs();
  applyZoom();
  renderProps();
})();
