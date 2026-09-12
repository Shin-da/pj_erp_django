/**
 * alertSounds.js
 * ----------------------------------------------------------------
 * Zero-dependency alert/notification sound module using the Web
 * Audio API. No audio files — every sound is synthesized on the fly.
 *
 * USAGE
 *   <script src="alertSounds.js"></script>
 *   <script>
 *     AlertSounds.play('scanHit');
 *     AlertSounds.play('scanMiss');
 *     AlertSounds.play('scanMatch');
 *     AlertSounds.play('success');
 *   </script>
 *
 * Or as an ES module:
 *   import AlertSounds from './alertSounds.js';
 *   AlertSounds.play('error');
 *
 * NOTES
 *   - Browsers require a user gesture (click/tap) before audio can
 *     play. Call AlertSounds.unlock() once on the first click/tap
 *     of your app (e.g. on the scanner "Start" button) to avoid the
 *     first sound being silently dropped.
 *   - Volume: pass a second arg 0.0–1.0 to scale peak volume, e.g.
 *     AlertSounds.play('scanHit', 0.5) for a quieter tick.
 *   - All sounds are defined declaratively in the SOUND_DEFS table
 *     below — edit frequencies/durations there without touching
 *     the playback engine.
 * ----------------------------------------------------------------
 */

(function (global) {
  'use strict';

  let audioCtx = null;

  function getContext() {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AC();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  /**
   * Schedules a single tone.
   * @param {AudioContext} ctx
   * @param {number} freq        starting frequency (Hz)
   * @param {number} startTime   AudioContext time to start at
   * @param {number} duration    seconds
   * @param {string} waveType    'sine' | 'square' | 'triangle' | 'sawtooth'
   * @param {number} peak        peak gain (0–1), pre volume-scale
   * @param {number} [glideTo]   optional end frequency for a pitch glide
   * @param {number} [volumeScale] overall volume multiplier
   */
  function scheduleTone(ctx, freq, startTime, duration, waveType, peak, glideTo, volumeScale) {
    const scale = volumeScale === undefined ? 1 : volumeScale;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = waveType || 'sine';
    osc.frequency.setValueAtTime(freq, startTime);
    if (glideTo !== undefined) {
      osc.frequency.exponentialRampToValueAtTime(glideTo, startTime + duration);
    }

    gain.gain.setValueAtTime(0, startTime);
    gain.gain.linearRampToValueAtTime((peak || 0.2) * scale, startTime + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);

    osc.connect(gain).connect(ctx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration + 0.02);
  }

  /**
   * SOUND_DEFS
   * Each entry is a list of notes: [freqStart, offsetFromStart, duration, waveType, peak, glideTo?]
   * offsetFromStart is in seconds, relative to when .play() is called.
   */
  const SOUND_DEFS = {
    // ---- General ERP alerts ----
    success:      [[660, 0,    0.12, 'sine',     0.18], [990, 0.10, 0.18, 'sine', 0.18]],
    error:        [[220, 0,    0.22, 'square',   0.10]],
    warning:      [[520, 0,    0.12, 'triangle', 0.15], [520, 0.18, 0.12, 'triangle', 0.15]],
    critical:     [[180, 0,    0.16, 'sawtooth', 0.12], [160, 0.20, 0.22, 'sawtooth', 0.12]],
    notification: [[880, 0,    0.15, 'sine',     0.14]],
    session:      [[440, 0,    0.10, 'triangle', 0.12], [370, 0.14, 0.10, 'triangle', 0.12], [440, 0.28, 0.14, 'triangle', 0.12]],

    // ---- ERP-specific extras ----
    sync:         [[500, 0,    0.10, 'sine',     0.12], [650, 0.08, 0.10, 'sine', 0.12], [800, 0.16, 0.14, 'sine', 0.14]],
    print:        [[700, 0,    0.08, 'triangle', 0.14], [700, 0.10, 0.16, 'triangle', 0.14]],
    denied:       [[300, 0,    0.10, 'square',   0.08], [250, 0.11, 0.14, 'square', 0.08]],
    mention:      [[740, 0,    0.09, 'sine',     0.14], [1100, 0.09, 0.10, 'sine', 0.10]],
    undo:         [[600, 0,    0.10, 'sine',     0.13], [480, 0.11, 0.14, 'sine', 0.13]],
    batchDone:    [[523, 0,    0.10, 'sine',     0.13], [659, 0.10, 0.10, 'sine', 0.13], [784, 0.20, 0.10, 'sine', 0.13], [1046, 0.30, 0.20, 'sine', 0.15]],

    // ---- Scanning (fires per item) ----
    scanHit:      [[1400, 0,   0.045, 'sine',    0.16]],           // fast tick, safe for rapid-fire scans
    scanMiss:     [[260, 0,    0.09,  'square',  0.10], [220, 0.10, 0.13, 'square', 0.10]], // item not found in system
    scanDuplicate:[[350, 0,    0.06,  'square',  0.09], [350, 0.07, 0.06, 'square', 0.09]],
    scanMatch:    [[523, 0,    0.10,  'sine',    0.14], [659, 0.10, 0.10, 'sine', 0.14], [784, 0.20, 0.10, 'sine', 0.14], [1046, 0.30, 0.28, 'sine', 0.17]], // expected count === scanned count

    // ---- System-wide ----
    login:        [[440, 0,    0.08, 'sine',     0.14], [660, 0.08, 0.14, 'sine', 0.15]],
    logout:       [[500, 0,    0.10, 'sine',     0.12, 300]],
    upload:       [[440, 0,    0.07, 'triangle', 0.12], [550, 0.07, 0.07, 'triangle', 0.12], [660, 0.14, 0.16, 'triangle', 0.14]],
    disconnect:   [[500, 0,    0.16, 'sawtooth', 0.10, 200]],
    reconnect:    [[300, 0,    0.10, 'sine',     0.13, 550]],
    chat:         [[700, 0,    0.05, 'sine',     0.13], [900, 0.06, 0.09, 'sine', 0.13]],
    reminder:     [[600, 0,    0.09, 'sine',     0.13], [600, 0.18, 0.09, 'sine', 0.13], [600, 0.36, 0.14, 'sine', 0.13]],
    milestone:    [[523, 0,    0.09, 'sine',     0.14], [659, 0.09, 0.09, 'sine', 0.14], [784, 0.18, 0.09, 'sine', 0.14], [988, 0.27, 0.10, 'sine', 0.14], [1318, 0.37, 0.30, 'sine', 0.18]],
    click:        [[1000, 0,   0.02, 'square',   0.06]],
    maintenance:  [[440, 0,    0.14, 'triangle', 0.11], [349, 0.16, 0.18, 'triangle', 0.11]]
  };

  /**
   * Plays a named sound.
   * @param {string} name         key from SOUND_DEFS
   * @param {number} [volume=1]   0.0–1.0 volume multiplier
   */
  function play(name, volume) {
    const def = SOUND_DEFS[name];
    if (!def) {
      console.warn('AlertSounds: unknown sound "' + name + '"');
      return;
    }
    const ctx = getContext();
    const now = ctx.currentTime;
    def.forEach(function (note) {
      const freq = note[0], offset = note[1], dur = note[2], wave = note[3], peak = note[4], glide = note[5];
      scheduleTone(ctx, freq, now + offset, dur, wave, peak, glide, volume);
    });
  }

  /**
   * Call once on a user gesture (click/tap) to unlock audio on
   * browsers/devices that require it before any sound can play.
   */
  function unlock() {
    const ctx = getContext();
    if (ctx.state === 'suspended') ctx.resume();
  }

  /**
   * Convenience: plays a sequence of named sounds, spaced by their
   * own durations. Useful for simulating a batch of scans.
   * @param {string[]} names
   * @param {number} [gapSeconds=0.22] gap between each sound
   */
  function playSequence(names, gapSeconds) {
    const gap = gapSeconds === undefined ? 0.22 : gapSeconds;
    names.forEach(function (name, i) {
      setTimeout(function () { play(name); }, i * gap * 1000);
    });
  }

  const AlertSounds = {
    play: play,
    unlock: unlock,
    playSequence: playSequence,
    sounds: Object.keys(SOUND_DEFS) // list of valid names, for reference/debugging
  };

  // Expose globally and as CommonJS/ESM-friendly export
  global.AlertSounds = AlertSounds;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AlertSounds;
  }
})(typeof window !== 'undefined' ? window : globalThis);
