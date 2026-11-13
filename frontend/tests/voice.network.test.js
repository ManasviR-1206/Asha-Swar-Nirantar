/**
 * Network-disconnection test.
 *
 * Requires a backend configured for a verified live Gnani language and
 * browser microphone permission. Demo mode selects browser speech instead of
 * opening the provider socket, so this test does not apply there.
 *
 * Starts a recording, then simulates the speech service disappearing while
 * capture is still running. The session must report a clear connection error.
 */
export default async function runNetworkDropTest() {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = [];

  const ctx = new AudioContext();
  const osc = ctx.createOscillator();
  const dest = ctx.createMediaStreamDestination();
  const gain = ctx.createGain();
  gain.gain.value = 0.4;
  osc.frequency.value = 300;
  osc.connect(gain);
  gain.connect(dest);
  osc.start();
  const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
    configurable: true,
    value: async () => dest.stream,
  });

  const restore = () => {
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: orig,
    });
    try {
      osc.stop();
      ctx.close();
    } catch {}
  };

  try {
    const { createVoiceSession } = await import("/src/lib/voice.js");

    // Install the socket spy BEFORE the session opens its socket.
    const sockets = [];
    const OrigWS = window.WebSocket;
    const spy = function (...args) {
      const ws = new OrigWS(...args);
      sockets.push(ws);
      return ws;
    };
    spy.prototype = OrigWS.prototype;
    Object.assign(spy, OrigWS);
    window.WebSocket = spy;

    let reported = null;
    const session = createVoiceSession({
      language: "en",
      onError: (err) => {
        reported = err?.kind || null;
      },
    });

    try {
      await session.start();
    } finally {
      window.WebSocket = OrigWS;
    }
    await wait(900);

    // Simulate the speech service going away mid-recording.
    sockets.forEach((s) => {
      try {
        s.close();
      } catch {}
    });

    await wait(1500);
    log.push({
      step: "socket-dropped",
      ok: reported === "socket-closed",
      reportedKind: reported,
      sockets: sockets.length,
    });

    // Pressing stop after the drop must also fail cleanly.
    let stopKind = null;
    try {
      await session.stop();
    } catch (e) {
      stopKind = e?.kind || null;
    }
    log.push({
      step: "stop-after-drop",
      ok: stopKind === "socket-closed" || stopKind === "empty-audio",
      stopKind,
    });

    return log;
  } catch (err) {
    log.push({ step: "exception", ok: false, error: String((err && err.message) || err) });
    return log;
  } finally {
    restore();
  }
}
