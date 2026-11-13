/**
 * End-to-end UI test for the Household Health page.
 *
 * The original "No speech captured — try Manual Entry." bug lived here, so
 * this drives the real page with mocked browser speech and TTS events: select
 * a household, record, stop, and verify the extracted observations and read-back.
 */
export default async function runHouseholdVoiceUiTest() {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = [];

  const originalRecognition = window.SpeechRecognition;
  const originalWebkitRecognition = window.webkitSpeechRecognition;
  const originalSpeechSynthesis = Object.getOwnPropertyDescriptor(window, "speechSynthesis");
  const originalUtterance = window.SpeechSynthesisUtterance;
  const transcript =
    "Visited household 24 today. They use borewell water. Water is stored in a covered container. " +
    "Toilet is available and used. Waste is collected twice a week. Drainage is open. " +
    "No stagnant water. Handwashing facility is available with soap. Follow up in 14 days.";
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
        (b.getAttribute("aria-label") || b.getAttribute("title") || "").toLowerCase().includes(label) ||
        b.textContent.trim() === label
    );

  try {
    // ---- choose a household ----
    // ---- choose a household (wait for the household list to load) ----
    let hhSelect = null;
    let opt = null;
    for (let i = 0; i < 30; i++) {
      hhSelect = Array.from(document.querySelectorAll("select")).find((s) =>
        Array.from(s.options).some((o) => /HN-/.test(o.textContent))
      );
      if (hhSelect) {
        opt = Array.from(hhSelect.options).find((o) => /HN-/.test(o.textContent));
        break;
      }
      await wait(300);
    }
    if (!hhSelect || !opt) {
      return [{ step: "household-select", ok: false, error: "not found" }];
    }
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
    setter.call(hhSelect, opt.value);
    hhSelect.dispatchEvent(new Event("change", { bubbles: true }));
    await wait(1200);
    log.push({
      step: "household-selected",
      ok: !!opt.value,
      selected: opt.textContent.trim(),
    });

    // ---- record ----
    const recordBtn = findButton("record");
    if (!recordBtn) return [{ step: "record-button", ok: false, error: "not found" }, ...log];
    recordBtn.click();
    await wait(2500);
    log.push({
      step: "recording",
      ok: true,
      statusChip: document.body.innerText.match(/Ready|Listening|Processing|Speaking/)?.[0],
      hasTranscript: /Visited|weeks pregnant|Blood pressure/i.test(document.body.innerText),
    });

    // ---- stop ----
    const stopBtn = findButton("stop");
    if (!stopBtn) return [{ step: "stop-button", ok: false, error: "not found" }, ...log];
    stopBtn.click();

    let ready = false;
    for (let i = 0; i < 40; i++) {
      await wait(400);
      if (/Save visit|Confirm|Save Record/i.test(document.body.innerText)) {
        ready = true;
        break;
      }
    }
    const text = document.body.innerText;
    log.push({
      step: "after-stop",
      ok: ready,
      statusChip: text.match(/Ready|Listening|Processing|Speaking|Awaiting confirmation|Saved/)?.[0],
      hasTranscript: /Visited|weeks pregnant/i.test(text),
      hasObservations: /Drinking water|Water source|Toilet|Waste|Drainage/i.test(text),
      hasReadBack: /Tara says|recorded|household/i.test(text),
      // must NOT claim "no speech captured" any more
      noSpeechError: /No speech captured/i.test(text),
      manualOpened: /Manual Entry/i.test(text),
      body: text.slice(0, 500),
    });

    return log;
  } catch (err) {
    log.push({
      step: "exception",
      ok: false,
      error: String((err && err.message) || err),
      name: err?.name,
    });
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
