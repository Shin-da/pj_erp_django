// Perfect Jewel ERP — customizable label designer (Tag Printing).
// Drag fields on a canvas, edit their properties, save the layout as a
// LabelTemplate + LabelField set. See apps/hardware/zpl.py for how a saved
// template turns into real ZPL sent to a Zebra printer.
(function () {
  var cfg = window.HARDWARE_DESIGNER;
  if (!cfg) return;

  var canvas = document.getElementById('labelCanvas');
  var propEmpty = document.getElementById('propEmpty');
  var propForm = document.getElementById('propForm');
  var selectedId = null;
  var nextTempId = -1;

  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  function fieldById(id) {
    return cfg.fields.find(function (f) { return f.id === id; });
  }

  function labelForField(f) {
    if (f.field_key === 'static_text') {
      return f.static_text || '(empty text)';
    }
    var base = cfg.fieldLabels[f.field_key] || f.field_key;
    var sample = cfg.sampleValues[f.field_key] || '';
    return f.static_text ? (f.static_text + sample) : (base + ': ' + sample);
  }

  function renderCanvas() {
    canvas.innerHTML = '';
    cfg.fields.forEach(function (f) {
      var box = document.createElement('div');
      box.className = 'label-field-box'
        + (f.id === selectedId ? ' selected' : '')
        + (!f.visible ? ' hidden-field' : '');
      box.style.left = f.x + 'px';
      box.style.top = f.y + 'px';
      box.style.maxWidth = f.box_width + 'px';
      box.style.fontWeight = f.bold ? '700' : '400';
      box.style.textAlign = f.align === 'C' ? 'center' : (f.align === 'R' ? 'right' : 'left');
      box.textContent = labelForField(f);
      box.dataset.id = f.id;
      box.addEventListener('mousedown', onBoxMouseDown);
      canvas.appendChild(box);
    });
  }

  function selectField(id) {
    selectedId = id;
    renderCanvas();
    renderProps();
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
    document.getElementById('propText').value = f.static_text || '';
    document.getElementById('propX').value = f.x;
    document.getElementById('propY').value = f.y;
    document.getElementById('propFont').value = f.font_size;
    document.getElementById('propBoxWidth').value = f.box_width;
    document.getElementById('propAlign').value = f.align;
    document.getElementById('propBold').checked = !!f.bold;
    document.getElementById('propVisible').checked = !!f.visible;
  }

  function bindProp(inputId, key, transform) {
    document.getElementById(inputId).addEventListener('input', function () {
      var f = fieldById(selectedId);
      if (!f) return;
      var val = this.type === 'checkbox' ? this.checked : this.value;
      f[key] = transform ? transform(val) : val;
      renderCanvas();
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

  document.querySelectorAll('[data-add-field]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var key = btn.dataset.addField;
      var id = nextTempId--;
      var isBarcodeImage = key === 'barcode_image';
      cfg.fields.push({
        id: id,
        field_key: key,
        static_text: '',
        x: 20,
        y: 20 + (cfg.fields.length * 6) % 200,
        font_size: isBarcodeImage ? 20 : 24,
        bold: false,
        align: 'L',
        box_width: isBarcodeImage ? 200 : 300,
        visible: true,
        order: cfg.fields.length,
      });
      selectField(id);
    });
  });

  /* -------- Drag -------- */
  var dragging = null, dragOffsetX = 0, dragOffsetY = 0;

  function onBoxMouseDown(e) {
    var id = parseInt(e.currentTarget.dataset.id, 10);
    selectField(id);
    dragging = e.currentTarget;
    var rect = dragging.getBoundingClientRect();
    dragOffsetX = e.clientX - rect.left;
    dragOffsetY = e.clientY - rect.top;
    e.preventDefault();
  }

  document.addEventListener('mousemove', function (e) {
    if (!dragging) return;
    var canvasRect = canvas.getBoundingClientRect();
    var x = Math.max(0, Math.round(e.clientX - canvasRect.left - dragOffsetX));
    var y = Math.max(0, Math.round(e.clientY - canvasRect.top - dragOffsetY));
    dragging.style.left = x + 'px';
    dragging.style.top = y + 'px';
    var f = fieldById(parseInt(dragging.dataset.id, 10));
    if (f) { f.x = x; f.y = y; }
    if (parseInt(dragging.dataset.id, 10) === selectedId) {
      document.getElementById('propX').value = x;
      document.getElementById('propY').value = y;
    }
  });

  document.addEventListener('mouseup', function () {
    dragging = null;
  });

  /* -------- Save -------- */
  document.getElementById('saveBtn').addEventListener('click', function () {
    var status = document.getElementById('saveStatus');
    status.textContent = 'Saving…';

    var payload = {
      name: document.getElementById('tplName').value,
      category: document.getElementById('tplCategory').value,
      is_default: document.getElementById('tplIsDefault').checked,
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
          if (data.fields) {
            cfg.fields = data.fields;
            renderCanvas();
          }
          setTimeout(function () { status.textContent = ''; }, 2000);
        } else {
          status.textContent = 'Error: ' + (data.error || 'save failed');
        }
      })
      .catch(function () {
        status.textContent = 'Save failed — check your connection.';
      });
  });

  renderCanvas();
  renderProps();
})();
