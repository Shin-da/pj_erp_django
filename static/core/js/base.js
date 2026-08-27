// Perfect Jewel ERP — base JS. Empty for now; add site-wide behavior here.
/* =========================================================================
   2) COLLAPSIBLE SIDEBAR GROUPS
   ========================================================================= */
document.querySelectorAll('[data-toggle-section]').forEach(function(btn){
  btn.addEventListener('click', function(){
    btn.closest('[data-collapsible]').classList.toggle('collapsed');
  });
});

/* =========================================================================
   3) THEME TOGGLE — persisted via localStorage, wrapped so a blocked/absent
      storage API never breaks the toggle itself (it just won't persist).
   ========================================================================= */
function applyTheme(mode){
  document.documentElement.setAttribute('data-theme', mode);
  try { localStorage.setItem('pj-theme', mode); } catch(e) { /* storage unavailable — toggle still works this session */ }
}
document.getElementById('themeToggle').addEventListener('click', function(){
  var current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  applyTheme(current === 'dark' ? 'light' : 'dark');
});

/* =========================================================================
   4) DROPDOWN MENUS (user account, notifications) — click to open,
      click outside or Escape to close, only one open at a time.
   ========================================================================= */
document.querySelectorAll('[data-menu]').forEach(function(wrap){
  var trigger = wrap.querySelector('[data-menu-trigger]');
  trigger.addEventListener('click', function(e){
    e.stopPropagation();
    var willOpen = !wrap.classList.contains('open');
    document.querySelectorAll('[data-menu].open').forEach(function(w){ w.classList.remove('open'); });
    if(willOpen) wrap.classList.add('open');
  });
});
document.addEventListener('click', function(){
  document.querySelectorAll('[data-menu].open').forEach(function(w){ w.classList.remove('open'); });
});
document.addEventListener('keydown', function(e){
  if(e.key === 'Escape'){
    document.querySelectorAll('[data-menu].open').forEach(function(w){ w.classList.remove('open'); });
    closeAllModals();
  }
});

/* =========================================================================
   5) MODALS
   ========================================================================= */
function openModal(id){
  var m = document.getElementById(id);
  if(m) m.classList.add('open');
}
function closeAllModals(){
  document.querySelectorAll('.modal-overlay.open').forEach(function(m){ m.classList.remove('open'); });
}
document.querySelectorAll('[data-open-modal]').forEach(function(btn){
  btn.addEventListener('click', function(){ openModal(btn.getAttribute('data-open-modal')); });
});
document.querySelectorAll('[data-close-modal]').forEach(function(btn){
  btn.addEventListener('click', function(){ btn.closest('.modal-overlay').classList.remove('open'); });
});
document.querySelectorAll('.modal-overlay').forEach(function(overlay){
  overlay.addEventListener('click', function(e){ if(e.target === overlay) overlay.classList.remove('open'); });
});

/* =========================================================================
   6) FILTER BAR SEGMENTED CONTROLS — visual state only in this mock
   ========================================================================= */
document.querySelectorAll('.seg').forEach(function(seg){
  seg.querySelectorAll('button').forEach(function(btn){
    btn.addEventListener('click', function(){
      seg.querySelectorAll('button').forEach(function(b){ b.classList.remove('active'); });
      btn.classList.add('active');
    });
  });
});

/* =========================================================================
   7) SIDEBAR — three states via the one hamburger button.
      - Narrow screens (<=900px, phones/tablets): off-canvas. Hidden by
        default; hamburger slides it in over a backdrop (`nav-open`).
      - Wider screens (>900px): never fully hides. Hamburger instead
        toggles between fully open and a collapsed icon-only rail
        (`sb-collapsed`), persisted across visits like the theme toggle.
   ========================================================================= */
var shell = document.getElementById('appShell');
var DESKTOP_MQ = window.matchMedia('(min-width: 901px)');

function applySidebarCollapsed(collapsed){
  shell.classList.toggle('sb-collapsed', collapsed);
  try { localStorage.setItem('pj-sidebar', collapsed ? 'collapsed' : 'open'); } catch(e) { /* storage unavailable — toggle still works this session */ }
}
try {
  if (DESKTOP_MQ.matches && localStorage.getItem('pj-sidebar') === 'collapsed') {
    shell.classList.add('sb-collapsed');
  }
} catch(e) { /* storage unavailable — default to open */ }

document.getElementById('hamburgerBtn').addEventListener('click', function(){
  if (DESKTOP_MQ.matches) {
    applySidebarCollapsed(!shell.classList.contains('sb-collapsed'));
  } else {
    shell.classList.toggle('nav-open');
  }
});
document.getElementById('sbBackdrop').addEventListener('click', closeMobileNav);
function closeMobileNav(){ shell.classList.remove('nav-open'); }