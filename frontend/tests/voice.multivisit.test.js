/**
 * Browser test for the multi-beneficiary Voice Visit review UI.
 *
 * The demo transcriber always returns one fixed sentence, so the STT result
 * is stubbed here with a three-beneficiary recording. Everything else is
 * real: the app opens a session, renders one card per beneficiary with its
 * own identity resolution, and persists the confirmed visits through the
 * real save endpoint.
 */
export default async function runMultiVisitUiTest() {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = [];

  const TRANSCRIPT =
    "Today I visited Lakshmi. She is 28 weeks pregnant and her weight is 53 kg. " +
    "Then I visited Ravi, aged 65, for his blood pressure follow-up. " +
    "After that I visited Anu, aged two years, for her vaccination follow-up.";

  /* ---- stub the STT transcript: intercept the session POST ---- */
  const origFetch = window.fetch;
  let created = null;
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/api/voice/sessions") && init && init.method === "POST" && !url.endsWith("/extract")) {
      const body = JSON.parse(init.body || "{}");
      body.transcript = TRANSCRIPT;
      init = { ...init, body: JSON.stringify(body) };
      const res = await origFetch(input, init);
      const data = await res.json();
      created = data;
      return new Response(JSON.stringify(data), {
        status: res.status,
        headers: { "Content-Type": "application/json" },
      });
    }
    return origFetch(input, init);
  };

  /* ---- stub the STT result ----
   *
   * In demo mode the backend asks the client to use the browser's speech
   * recognition (Prisma is not configured), so the browser API is stubbed
   * here with a three-beneficiary recording. The application's own session
   * open / extract / save calls all run for real. */
  const origSpeech = window.SpeechRecognition || window.webkitSpeechRecognition;
  class FakeRecognition {
    constructor() {
      this.lang = "en-IN";
      this.continuous = true;
      this.interimResults = true;
    }
    start() {
      setTimeout(() => {
        this.onstart && this.onstart();
        const mk = (text, isFinal) => ({
          0: { transcript: text },
          isFinal,
          length: 1,
        });
        this.onresult &&
          this.onresult({
            resultIndex: 0,
            results: [mk(TRANSCRIPT, true)],
          });
      }, 300);
    }
    stop() {
      setTimeout(() => this.onend && this.onend(), 200);
    }
    abort() {
      setTimeout(() => this.onend && this.onend(), 100);
    }
  }
  window.SpeechRecognition = FakeRecognition;
  window.webkitSpeechRecognition = FakeRecognition;

  try {
    /* ---- synthetic microphone so the capture path really runs ---- */
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const dest = ctx.createMediaStreamDestination();
    const gain = ctx.createGain();
    gain.gain.value = 0.4;
    osc.frequency.value = 300;
    osc.connect(gain);
    gain.connect(dest);
    osc.start();
    const origGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: async () => dest.stream,
    });

    /* ---- press Record, then Stop ---- */
    const recordBtn = Array.from(document.querySelectorAll("button")).find(
      (b) => (b.getAttribute("aria-label") || "").toLowerCase().includes("record")
    );
    if (!recordBtn) {
      log.push({ step: "record-button", ok: false, error: "not found" });
      return log;
    }
    recordBtn.click();
    await wait(2600);

    const stopBtn = Array.from(document.querySelectorAll("button")).find(
      (b) => (b.getAttribute("aria-label") || "").toLowerCase().includes("stop")
    );
    if (!stopBtn) {
      log.push({ step: "stop-button", ok: false, error: "not found" });
      return log;
    }
    stopBtn.click();

    /* ---- wait for the review cards ---- */
    let cards = [];
    for (let i = 0; i < 40; i++) {
      await wait(400);
      const text = document.body.innerText;
      if (/Multiple Beneficiaries|Confirm All|Choose beneficiary|No beneficiary named/i.test(text)) {
        cards = Array.from(
          document.querySelectorAll('.rounded-2xl.bg-white.p-4')
        );
        break;
      }
    }
    const body = document.body.innerText;
    log.push({
      step: "review-cards",
      ok: /Multiple Beneficiaries|Confirm All/i.test(body),
      showsLakshmi: /Lakshmi/.test(body),
      showsRavi: /Ravi/.test(body),
      showsAnu: /Anu/.test(body),
      hasIdentityBadge: /Choose beneficiary|No beneficiary named|Matched/i.test(body),
      hasConfirmAll: /Confirm All/i.test(body),
      cardCount: cards.length,
    });

    /* ---- confirm all and save ---- */
    const confirmAll = Array.from(document.querySelectorAll("button")).find((b) =>
      /Confirm All/i.test(b.textContent)
    );
    if (confirmAll) {
      confirmAll.click();
      let saved = false;
      for (let i = 0; i < 40; i++) {
        await wait(400);
        if (/Pulse Thread|Record Another Visit|Saved/i.test(document.body.innerText)) {
          saved = true;
          break;
        }
      }
      log.push({
        step: "confirm-all-save",
        ok: saved,
        sessionId: created?.id ?? null,
        body: document.body.innerText.slice(0, 500),
      });
    } else {
      log.push({ step: "confirm-all-save", ok: false, error: "Confirm All button not found" });
    }

    return log;
  } catch (err) {
    log.push({ step: "exception", ok: false, error: String((err && err.message) || err) });
    return log;
  } finally {
    window.fetch = origFetch;
    window.SpeechRecognition = origSpeech;
    window.webkitSpeechRecognition = origSpeech;
    try {
      osc.stop();
      ctx.close();
    } catch {}
  }
}
