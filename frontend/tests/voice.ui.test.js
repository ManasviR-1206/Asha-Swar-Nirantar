/**
 * End-to-end UI test for the Voice Visit page.
 *
 * Drives the real page with mocked browser speech and TTS events, then checks
 * that the structured record, Tara's read-back and confirmation controls appear.
 * Saving is opt-in because it writes a test visit to the active database.
 *
 * Imported by the browser test harness: await import('/tests/voice.ui.test.js')
 */
export default async function runVoiceUiTest({ save = false } = {}) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = [];

  const originalRecognition = window.SpeechRecognition;
  const originalWebkitRecognition = window.webkitSpeechRecognition;
  const originalSpeechSynthesis = Object.getOwnPropertyDescriptor(window, "speechSynthesis");
  const originalUtterance = window.SpeechSynthesisUtterance;
  const transcript =
    "I visited Lakshmi today. She is 28 weeks pregnant. Her weight is 53 kilograms and her blood pressure is 120 over 80.";
  window.SpeechRecognition = class {
    start() {
      this.onstart?.();
      this.onresult?.({
        resultIndex: 0,
        results: [{ 0: { transcript }, isFinal: true }],
      });
    }

    stop() {
      this.onend?.();
    }
  };
  window.webkitSpeechRecognition = undefined;
  Object.defineProperty(window, "speechSynthesis", {
    configurable: true,
    value: {
      cancel() {},
      speak(utterance) {
        setTimeout(() => utterance.onend?.(), 0);
      },
    },
  });
  window.SpeechSynthesisUtterance = class {
    constructor(text) {
      this.text = text;
    }
  };

  const findButton = (label) =>
    Array.from(document.querySelectorAll("button")).find(
      (b) =>
        (b.getAttribute("aria-label") || "").toLowerCase().includes(label) ||
        b.textContent.trim() === label
    );

  try {
    // ---- click Record ----
    const recordBtn = findButton("record");
    if (!recordBtn) return [{ step: "record-button", ok: false, error: "not found" }];
    recordBtn.click();
    await wait(2500);
    log.push({
      step: "recording",
      ok: true,
      statusChip: document.body.innerText.match(/Ready|Listening|Processing|Speaking/)?.[0],
      hasTranscript: /Visited|weeks pregnant|Blood pressure/.test(document.body.innerText),
    });

    // ---- click Stop (same button, aria-label changes to stop) ----
    const stopBtn = findButton("stop");
    if (!stopBtn) return [{ step: "stop-button", ok: false, error: "not found" }, ...log];
    stopBtn.click();

    // ---- wait for extraction + read-back ----
    let ready = false;
    for (let i = 0; i < 40; i++) {
      await wait(400);
      const text = document.body.innerText;
      if (/Confirm\s*&\s*Save/i.test(text)) {
        ready = true;
        break;
      }
    }
    const text = document.body.innerText;
    log.push({
      step: "after-stop",
      ok: ready,
      statusChip: text.match(/Ready|Listening|Processing|Speaking|Awaiting confirmation|Saved/)?.[0],
      hasStructured: /Structured Record/.test(text),
      hasPreviewFields: /Weeks pregnant|Blood pressure|Weight/i.test(text),
      hasTara: /Tara says/i.test(text),
      hasConfirm: /Confirm\s*&\s*Save/i.test(text),
      hasCorrection: /Correct by voice/i.test(text),
      // the visit must NOT be saved before confirmation
      savedEarly: /Visit saved|Record saved/i.test(text),
    });

    if (!ready || !save) return log;

    // ---- press Confirm & Save ----
    const confirmBtn = Array.from(document.querySelectorAll("button")).find((b) =>
      /Confirm\s*&\s*Save/i.test(b.textContent.trim())
    );
    if (confirmBtn) {
      confirmBtn.click();
      for (let i = 0; i < 30; i++) {
        await wait(300);
        if (/Open Pulse Thread|Record Another Visit/i.test(document.body.innerText)) break;
      }
      const after = document.body.innerText;
      log.push({
        step: "confirm-save",
        ok: /Open Pulse Thread|Record Another Visit/i.test(after),
        savedPanel: /Open Pulse Thread|Record Another Visit/i.test(after),
        body: after.slice(0, 400),
      });
    }

    return log;
  } catch (err) {
    log.push({ step: "exception", ok: false, error: String(err && err.message || err), name: err?.name });
    return log;
  } finally {
    window.SpeechRecognition = originalRecognition;
    window.webkitSpeechRecognition = originalWebkitRecognition;
    if (originalSpeechSynthesis) {
      Object.defineProperty(window, "speechSynthesis", originalSpeechSynthesis);
    } else {
      delete window.speechSynthesis;
    }
    window.SpeechSynthesisUtterance = originalUtterance;
  }
}
