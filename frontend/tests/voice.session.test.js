/**
 * Browser tests for the voice session using mocked SpeechRecognition events.
 * Run from a page served by Vite; these tests do not access a microphone or
 * claim to test the browser's real speech service.
 */
export default async function runVoiceSessionTests() {
  const { createVoiceSession, VoiceErrorKind } = await import("/src/lib/voice.js");
  const originalRecognition = window.SpeechRecognition;
  const originalWebkitRecognition = window.webkitSpeechRecognition;
  const results = [];

  const check = (label, ok, detail = {}) => results.push({ label, ok, ...detail });
  const makeResult = (transcript, isFinal) => ({
    0: { transcript },
    isFinal,
  });

  try {
    let activeRecognition;
    class MockRecognition {
      constructor() {
        activeRecognition = this;
      }

      start() {
        this.onstart?.();
        this.onresult?.({
          resultIndex: 0,
          results: [makeResult("I visited Lakshmi", false)],
        });
        this.onresult?.({
          resultIndex: 0,
          results: [
            makeResult("I visited Lakshmi", true),
            makeResult("She is 28 weeks pregnant", false),
          ],
        });
        this.onresult?.({
          resultIndex: 1,
          results: [
            makeResult("I visited Lakshmi", true),
            makeResult("She is 28 weeks pregnant", true),
          ],
        });
      }

      stop() {
        this.onend?.();
      }

      abort() {
        this.onend?.();
      }
    }

    window.SpeechRecognition = MockRecognition;
    window.webkitSpeechRecognition = undefined;

    const partials = [];
    let finalized = "";
    const session = createVoiceSession({
      language: "kn",
      preferBrowser: true,
      onPartial: (text) => partials.push(text),
      onFinal: (text) => {
        finalized = text;
      },
    });
    await session.start();
    const result = await session.stop();
    const expected = "I visited Lakshmi She is 28 weeks pregnant";
    check("accumulates browser final results", result.transcript === expected, {
      transcript: result.transcript,
    });
    check("maps Kannada locale", activeRecognition.lang === "kn-IN", {
      locale: activeRecognition.lang,
    });
    check("emits partial and one final", partials.length >= 2 && finalized === expected, {
      partials,
      finalized,
    });
    check("labels mocked browser provider", result.stats.provider === "Browser Speech Recognition", {
      provider: result.stats.provider,
    });

    class ErrorRecognition extends MockRecognition {
      constructor(error) {
        super();
        this.error = error;
      }

      start() {
        this.onstart?.();
        this.onerror?.({ error: this.error });
      }
    }

    window.SpeechRecognition = class extends ErrorRecognition {
      constructor() {
        super("not-allowed");
      }
    };
    const denied = createVoiceSession({ language: "en", preferBrowser: true });
    await denied.start();
    try {
      await denied.stop();
      check("reports permission denial", false);
    } catch (error) {
      check("reports permission denial", error.kind === VoiceErrorKind.MIC_PERMISSION_DENIED, {
        kind: error.kind,
      });
    }

    window.SpeechRecognition = class extends ErrorRecognition {
      constructor() {
        super("language-not-supported");
      }
    };
    const unsupportedLocale = createVoiceSession({ language: "kn", preferBrowser: true });
    await unsupportedLocale.start();
    try {
      await unsupportedLocale.stop();
      check("reports unsupported speech locale", false);
    } catch (error) {
      check("reports unsupported speech locale", error.kind === VoiceErrorKind.SPEECH_LANGUAGE_UNSUPPORTED, {
        kind: error.kind,
      });
    }

    class SilentRecognition {
      start() {
        this.onstart?.();
      }

      stop() {
        this.onend?.();
      }
    }
    window.SpeechRecognition = SilentRecognition;
    const silent = createVoiceSession({ language: "en", preferBrowser: true });
    await silent.start();
    try {
      await silent.stop();
      check("reports no speech instead of inventing a transcript", false);
    } catch (error) {
      check("reports no speech instead of inventing a transcript", error.kind === VoiceErrorKind.NO_SPEECH, {
        kind: error.kind,
      });
    }

    window.SpeechRecognition = MockRecognition;
    let abortedFinals = 0;
    const aborted = createVoiceSession({
      language: "en",
      preferBrowser: true,
      onFinal: () => {
        abortedFinals++;
      },
    });
    await aborted.start();
    aborted.abort();
    check("abort does not finalize a cancelled recording", abortedFinals === 0, {
      finalized: abortedFinals,
    });

    window.SpeechRecognition = undefined;
    window.webkitSpeechRecognition = undefined;
    const unsupported = createVoiceSession({ language: "en", preferBrowser: true });
    try {
      await unsupported.start();
      check("reports missing browser speech API", false);
    } catch (error) {
      check("reports missing browser speech API", error.kind === VoiceErrorKind.SPEECH_UNSUPPORTED, {
        kind: error.kind,
      });
    }
  } finally {
    window.SpeechRecognition = originalRecognition;
    window.webkitSpeechRecognition = originalWebkitRecognition;
  }

  return results;
}
