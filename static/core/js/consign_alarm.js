/* Consignment due reminder — modal + chime. Warn only; does not change stock. */
(function () {
  var overlay = document.getElementById("consignAlarmModal");
  if (!overlay) return;

  var TODAY_KEY = "pj-consign-alarm-dismissed";
  var SESSION_KEY = "pj-consign-alarm-closed";
  var MUTE_KEY = "pj-consign-alarm-mute";
  var played = false;

  function todayStamp() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function storageGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function storageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
  }
  function sessionGet(key) {
    try { return sessionStorage.getItem(key); } catch (e) { return null; }
  }
  function sessionSet(key, value) {
    try { sessionStorage.setItem(key, value); } catch (e) { /* ignore */ }
  }

  function isMuted() {
    return storageGet(MUTE_KEY) === "1";
  }

  function playChime() {
    if (played || isMuted() || !window.AlertSounds) return;
    AlertSounds.unlock();
    AlertSounds.play("reminder");
    played = true;
  }

  function closeSession() {
    sessionSet(SESSION_KEY, "1");
    overlay.classList.remove("open");
  }

  function dismissToday() {
    storageSet(TODAY_KEY, todayStamp());
    sessionSet(SESSION_KEY, "1");
    overlay.classList.remove("open");
  }

  function shouldAutoOpen() {
    if (sessionGet(SESSION_KEY)) return false;
    if (storageGet(TODAY_KEY) === todayStamp()) return false;
    return overlay.getAttribute("data-consign-alarm") === "1";
  }

  overlay.querySelectorAll("[data-consign-snooze]").forEach(function (btn) {
    btn.addEventListener("click", function () { closeSession(); });
  });
  overlay.querySelectorAll("[data-consign-today]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      dismissToday();
    });
  });

  var mute = document.getElementById("consignAlarmMute");
  if (mute) {
    mute.checked = isMuted();
    mute.addEventListener("change", function () {
      storageSet(MUTE_KEY, mute.checked ? "1" : "0");
    });
  }

  document.addEventListener("click", function playOnce() {
    if (overlay.classList.contains("open")) playChime();
  }, { once: true });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay.classList.contains("open")) closeSession();
  });

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeSession();
  });

  if (shouldAutoOpen()) {
    overlay.classList.add("open");
    // Don't call playChime() here — the page has had no user gesture yet,
    // so the AudioContext would just be suspended. The click listener
    // above catches the user's first click on the page and plays it then.
  }
})();
