/**
 * Microphone capture + streaming STT client for the Voice Assistant.
 *
 * The pipeline is unchanged:
 *   mic -> 16 kHz mono PCM16 -> WebSocket -> backend -> Gnani Prisma v3.0
 *        -> stt_partial / stt_final -> Tara read-back -> confirmation
 *
 * What this module fixes compared to the previous inline implementation:
 *
 *  1. RESAMPLING. The AudioContext runs at the hardware rate (44.1/48 kHz),
 *     but Gnani Prisma expects 16 kHz mono PCM16. The old code copied the
 *     Float32 samples straight into an Int16Array, so the provider received
 *     audio ~3x too slow. We now box-filter down to 16 kHz properly.
 *  2. FEEDBACK. The old code connected the ScriptProcessor straight to the
 *     destination, which plays the microphone through the speakers. We now
 *     route it through a zero-gain node so the graph is pulled silently.
 *  3. SUSPENDED CONTEXT. An AudioContext can start "suspended" under the
 *     autoplay policy, in which case no audio is ever produced. We resume it
 *     and verify it is running.
 *  4. FINALISATION. The client used to close the socket the instant the mic
 *     stopped, which discarded the in-flight final transcript. We now stop
 *     the mic, ask the backend to finalise, and wait for `stt_final`.
 *  5. ERROR CLASSIFICATION. Permission denied, no device, socket failure,
 *     provider failure, empty audio, no speech and timeout are distinct
 *     conditions with distinct messages.
 *
 * Diagnostics never include transcript text (it can contain health
 * information) — only counts, byte sizes and event names.
 */

const TARGET_SAMPLE_RATE = 16000;
const DEFAULT_CONNECT_TIMEOUT_MS = 8000;
const DEFAULT_FINALIZE_TIMEOUT_MS = 6000;
const LOG_EVERY_N_CHUNKS = 20;

/**
 * URL of the AudioWorklet capture processor (served verbatim from public/).
 * `addModule()` loads it as a classic worker script, so it must not be
 * processed by the bundler.
 */
const WORKLET_URL = "/pcm-worklet.js";

/** Stable error kinds so the UI can show a specific, honest message. */
export const VoiceErrorKind = {
  MIC_PERMISSION_DENIED: "mic-permission-denied",
  MIC_NO_DEVICE: "mic-no-device",
  MIC_BUSY: "mic-busy",
  MIC_INSECURE_CONTEXT: "mic-insecure-context",
  MIC_FAILED: "mic-failed",
  SOCKET_FAILED: "socket-failed",
  SOCKET_CLOSED: "socket-closed",
  STT_PROVIDER: "stt-provider-error",
  SPEECH_UNSUPPORTED: "speech-recognition-unsupported",
  SPEECH_LANGUAGE_UNSUPPORTED: "speech-language-unsupported",
  SPEECH_NETWORK: "speech-network-error",
  EMPTY_AUDIO: "empty-audio",
  NO_SPEECH: "no-speech",
  TIMEOUT: "timeout",
};

export class VoiceError extends Error {
  constructor(kind, message, cause) {
    super(message || kind);
    this.name = "VoiceError";
    this.kind = kind;
    this.cause = cause;
  }
}

/**
 * Box-filter decimator: converts Float32 samples at the context rate into
 * Float32 samples at `dstRate`. Averaging a whole window before dropping
 * samples keeps the high frequencies from folding back into the speech
 * band (which is what a naive "copy the samples" resampler does).
 */
export class Pcm16Downsampler {
  constructor(srcRate, dstRate = TARGET_SAMPLE_RATE) {
    this.srcRate = srcRate;
    this.dstRate = dstRate;
    this.sum = 0;
    this.count = 0;
    this.carry = 0;
  }

  /** @param {Float32Array} input @returns {number[]} downsampled samples */
  process(input) {
    const out = [];
    if (this.srcRate === this.dstRate) {
      for (let i = 0; i < input.length; i++) out.push(input[i]);
      return out;
    }
    if (this.srcRate < this.dstRate) {
      // Upsampling is not expected (targets are always <= 16 kHz), but keep
      // it sane with nearest-neighbour rather than dropping the difference.
      const step = this.srcRate / this.dstRate;
      for (let i = 0; i < input.length; i++) out.push(input[Math.floor(i * step)]);
      return out;
    }
    for (let i = 0; i < input.length; i++) {
      this.sum += input[i];
      this.count += 1;
      this.carry += this.dstRate;
      if (this.carry >= this.srcRate) {
        this.carry -= this.srcRate;
        out.push(this.sum / this.count);
        this.sum = 0;
        this.count = 0;
      }
    }
    return out;
  }
}

/** Float32 -> Int16 PCM, clamped. */
export function toInt16(samples) {
  const buf = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const v = samples[i];
    const scaled = v < -1 ? -1 : v > 1 ? 1 : v;
    buf[i] = Math.round(scaled * 32767);
  }
  return buf;
}

/** Classifies a getUserMedia rejection into a specific VoiceError. */
function micErrorFor(err) {
  const name = err?.name || "";
  const msg = err?.message || String(err);
  if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") {
    return new VoiceError(
      VoiceErrorKind.MIC_PERMISSION_DENIED,
      "Microphone permission was denied.",
      err
    );
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return new VoiceError(
      VoiceErrorKind.MIC_NO_DEVICE,
      "No microphone was found on this device.",
      err
    );
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return new VoiceError(
      VoiceErrorKind.MIC_BUSY,
      "The microphone is already in use by another application.",
      err
    );
  }
  return new VoiceError(VoiceErrorKind.MIC_FAILED, msg, err);
}

/**
 * Creates a voice session: microphone capture -> WebSocket -> final transcript.
 *
 * Usage:
 *   const session = createVoiceSession({ language, onPartial, onFinal, onLog });
 *   await session.start();          // throws VoiceError on failure
 *   const { transcript } = await session.stop();   // resolves after stt_final
 *   session.abort();                // tear down without waiting
 */
export function createVoiceSession({
  language = "en",
  socketUrl,
  onPartial,
  onFinal,
  onStatus,
  onProvider,
  onLevel,
  onError,
  onLog,
  preferBrowser = false,
  connectTimeoutMs = DEFAULT_CONNECT_TIMEOUT_MS,
  finalizeTimeoutMs = DEFAULT_FINALIZE_TIMEOUT_MS,
} = {}) {
  let ws = null;
  let stream = null;
  let ctx = null;
  let captureNode = null;
  let captureKind = null;
  let source = null;
  let silentGain = null;
  let stopped = false;
  let aborted = false;

  const stats = {
    chunks: 0,
    bytes: 0,
    sampleRate: 0,
    peakInt16: 0,
    durationMs: 0,
    mode: null,
    provider: null,
    captureKind: null,
  };

  let partialText = "";
  let finalText = "";
  let settle = null; // { resolve, reject }
  let finalizeTimer = null;
  let sessionError = null; // first fatal error seen during the session
  let recognition = null;
  let recognitionEnded = false;
  let browserFinalParts = [];
  let browserStopResolve = null;
  let browserStopReject = null;
  let browserStopTimer = null;
  let providerState = null;
  const providerWaiters = [];

  const announceProvider = (state, reason = "") => {
    if (providerState) return;
    providerState = state;
    stats.mode = state === "browser" ? "browser" : "live";
    stats.provider =
      state === "browser"
        ? `Browser Speech Recognition${reason === "provider_auth" ? " (Gnani authentication failed)" : ""}`
        : "Gnani Prisma";
    try {
      onProvider?.(stats.provider, reason);
    } catch {}
    providerWaiters.splice(0).forEach((resolve) => resolve(state));
  };

  const waitForProvider = () => {
    if (providerState) return Promise.resolve(providerState);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const index = providerWaiters.indexOf(onProviderReady);
        if (index >= 0) providerWaiters.splice(index, 1);
        reject(new VoiceError(VoiceErrorKind.TIMEOUT, "The speech provider did not respond."));
      }, connectTimeoutMs);
      const onProviderReady = (state) => {
        clearTimeout(timer);
        resolve(state);
      };
      providerWaiters.push(onProviderReady);
    });
  };

  const browserTranscript = () => {
    const final = browserFinalParts.join(" ").trim();
    return final || partialText.trim();
  };

  const finishBrowserStop = () => {
    if (!stopped || !browserStopResolve) return;
    if (browserStopTimer) {
      clearTimeout(browserStopTimer);
      browserStopTimer = null;
    }
    const resolve = browserStopResolve;
    const reject = browserStopReject;
    browserStopResolve = null;
    browserStopReject = null;
    if (sessionError) {
      reject(sessionError);
      return;
    }
    const transcript = browserTranscript();
    if (!transcript) {
      reject(new VoiceError(VoiceErrorKind.NO_SPEECH, "No speech was detected."));
      return;
    }
    finalText = transcript;
    try {
      onFinal?.(transcript);
    } catch {}
    resolve({ transcript, partial: partialText, fromPartial: !browserFinalParts.length, stats });
  };

  const browserRecognitionError = (error) => {
    const code = error?.error || "";
    if (code === "not-allowed" || code === "service-not-allowed") {
      return new VoiceError(VoiceErrorKind.MIC_PERMISSION_DENIED, "Microphone permission was denied.");
    }
    if (code === "audio-capture") {
      return new VoiceError(VoiceErrorKind.MIC_NO_DEVICE, "No microphone was found on this device.");
    }
    if (code === "language-not-supported") {
      return new VoiceError(
        VoiceErrorKind.SPEECH_LANGUAGE_UNSUPPORTED,
        "This browser does not support speech recognition for the selected language."
      );
    }
    if (code === "network") {
      return new VoiceError(VoiceErrorKind.SPEECH_NETWORK, "Browser speech recognition could not reach its service.");
    }
    if (code === "no-speech") {
      return new VoiceError(VoiceErrorKind.NO_SPEECH, "No speech was detected.");
    }
    return new VoiceError(VoiceErrorKind.STT_PROVIDER, "Browser speech recognition failed.");
  };

  const startBrowserRecognition = () =>
    new Promise((resolve, reject) => {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) {
        reject(
          new VoiceError(
            VoiceErrorKind.SPEECH_UNSUPPORTED,
            "Speech recognition is not available in this browser."
          )
        );
        return;
      }

      const locales = { en: "en-IN", kn: "kn-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN" };
      recognition = new Recognition();
      recognition.lang = locales[language] || language;
      recognition.continuous = true;
      recognition.interimResults = true;
      browserFinalParts = [];
      recognitionEnded = false;

      recognition.onstart = () => {
        stats.mode = "browser";
        stats.provider = "Browser Speech Recognition";
        stats.startedAt = Date.now();
        emitStatus("listening");
        try {
          onProvider?.(stats.provider);
        } catch {}
        log("recording.start", { provider: stats.provider, language: recognition.lang });
        resolve(stats);
      };

      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const text = event.results[i][0]?.transcript?.trim();
          if (!text) continue;
          if (event.results[i].isFinal) browserFinalParts.push(text);
          else interim += `${interim ? " " : ""}${text}`;
        }
        partialText = [...browserFinalParts, interim].filter(Boolean).join(" ").trim();
        try {
          onPartial?.(partialText);
        } catch {}
      };

      recognition.onerror = (event) => {
        if (aborted || (stopped && event?.error === "aborted")) return;
        const error = browserRecognitionError(event);
        sessionError = error;
        log("speech-recognition.error", { code: event?.error || "unknown" });
        try {
          onError?.(error);
        } catch {}
        if (!stats.startedAt) reject(error);
        finishBrowserStop();
      };

      recognition.onend = () => {
        recognitionEnded = true;
        finishBrowserStop();
      };

      try {
        recognition.start();
      } catch (error) {
        reject(browserRecognitionError({ error: error?.name === "NotAllowedError" ? "not-allowed" : "" }));
      }
    });

  const log = (event, data = {}) => {
    try {
      onLog?.({ event, ...data });
    } catch {
      /* diagnostics must never break the capture path */
    }
  };

  const emitStatus = (stage) => {
    try {
      onStatus?.(stage);
    } catch {
      /* ignore */
    }
  };

  const cleanupCapture = () => {
    try {
      if (captureNode?.port) captureNode.port.onmessage = null;
      captureNode?.disconnect();
    } catch {}
    try {
      source?.disconnect();
    } catch {}
    try {
      silentGain?.disconnect();
    } catch {}
    captureNode = null;
    source = null;
    silentGain = null;
    try {
      stream?.getTracks().forEach((track) => track.stop());
    } catch {}
    stream = null;
    try {
      ctx?.close();
    } catch {}
    ctx = null;
  };

  const closeSocket = () => {
    try {
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close();
      }
    } catch {}
    ws = null;
  };

  const settleWith = (fn, value) => {
    if (!settle) return;
    const s = settle;
    settle = null;
    if (finalizeTimer) {
      clearTimeout(finalizeTimer);
      finalizeTimer = null;
    }
    fn(s, value);
  };

  /** Sends the "finalize" instruction and waits for the final transcript. */
  const requestFinal = () =>
    new Promise((resolve, reject) => {
      // The provider may already have delivered a final (it does so on its
      // own after enough audio). Do not wait for a second one.
      if (finalText.trim()) {
        log("stt.final.already-received", { length: finalText.length });
        resolve({ transcript: finalText.trim(), partial: partialText, fromPartial: false });
        return;
      }

      settle = { resolve, reject };

      finalizeTimer = setTimeout(() => {
        finalizeTimer = null;
        log("stt.final.timeout", { hasPartial: partialText.length > 0 });
        // A missing final is not necessarily fatal: a progressive partial is
        // still a usable transcript. Only fail when we have nothing at all.
        if (partialText.trim()) {
          settleWith((s) => s.resolve({ transcript: partialText.trim(), partial: partialText, fromPartial: true }));
        } else {
          settleWith((s) =>
            s.reject(
              new VoiceError(
                VoiceErrorKind.NO_SPEECH,
                "No speech was detected before the recording finished."
              )
            )
          );
        }
      }, finalizeTimeoutMs);

      try {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "finalize" }));
          log("stt.finalize.sent");
        } else {
          log("stt.finalize.socket-not-open", { readyState: ws ? ws.readyState : null });
          settleWith((s) =>
            s.reject(
              new VoiceError(VoiceErrorKind.SOCKET_CLOSED, "The speech connection closed before the recording finished.")
            )
          );
        }
      } catch (err) {
        settleWith((s) =>
          s.reject(new VoiceError(VoiceErrorKind.SOCKET_FAILED, "Could not reach the speech service.", err))
        );
      }
    });

  const handleSocketMessage = (msg) => {
    if (!msg || !msg.type) return;
    log("stt.event", { type: msg.type, code: msg.code || null });

    if (msg.mode) stats.mode = msg.mode;

    if (msg.type === "stt_partial") {
      const text = msg.text || "";
      partialText = text;
      try {
        onPartial?.(text);
      } catch {}
      emitStatus("listening");
      return;
    }

    if (msg.type === "stt_final") {
      const text = msg.text || "";
      finalText = text;
      try {
        onFinal?.(text);
      } catch {}
      settleWith((s) => s.resolve({ transcript: text, partial: partialText, fromPartial: false }));
      return;
    }

    if (msg.type === "error") {
      const code = msg.code || "";
      const kind =
        code === "empty_audio"
          ? VoiceErrorKind.EMPTY_AUDIO
          : code === "no_final"
            ? VoiceErrorKind.STT_PROVIDER
            : VoiceErrorKind.STT_PROVIDER;
      log("stt.error", { code });
      settleWith((s) =>
        s.reject(new VoiceError(kind, msg.message || "The speech service could not produce a transcript.", null))
      );
      return;
    }

    if (msg.type === "status") {
      if (msg.stage === "browser_fallback") {
        announceProvider("browser", msg.reason);
        return;
      }
      if (msg.stage === "listening") {
        if (msg.mode === "live") announceProvider("gnani");
        emitStatus("listening");
      }
      else if (msg.stage === "finalizing") emitStatus("finalizing");
      // The backend sends "processing" right after a final transcript. While
      // the microphone is still running that must not interrupt the recording
      // state, so only surface it once we have asked to stop.
      else if (msg.stage === "processing" && stopped) emitStatus("processing");
    }
  };

  /** Handles one captured PCM frame: level, counters, send to the socket. */
  const onFrame = (pcmBuffer, rms) => {
    if (stopped || aborted) return;
    try {
      onLevel?.(rms || 0);
    } catch {}
    if (!pcmBuffer || pcmBuffer.byteLength === 0) return;
    // Track the loudest sample so we can tell "microphone was silent" apart
    // from "nothing was captured at all".
    const view = new Int16Array(pcmBuffer);
    for (let i = 0; i < view.length; i++) {
      const abs = view[i] < 0 ? -view[i] : view[i];
      if (abs > stats.peakInt16) stats.peakInt16 = abs;
    }
    stats.chunks += 1;
    stats.bytes += pcmBuffer.byteLength;
    if (stats.chunks % LOG_EVERY_N_CHUNKS === 0) {
      log("audio.chunk", { chunks: stats.chunks, bytes: stats.bytes });
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(pcmBuffer);
    } else {
      log("audio.dropped", { readyState: ws ? ws.readyState : null });
    }
  };

  const start = async () => {
    if (preferBrowser) return startBrowserRecognition();

    // Determine the real STT provider before requesting microphone access.
    let wsToken = "";
    try {
      wsToken = await fetchVoiceWsToken();
    } catch (err) {
      throw err instanceof VoiceError ? err : new VoiceError(VoiceErrorKind.SOCKET_FAILED, "Could not authenticate the voice session.", err);
    }
    const url = socketUrl || buildSocketUrl(language, undefined, wsToken);
    await new Promise((resolve, reject) => {
      let wsRef;
      try {
        wsRef = new WebSocket(url);
      } catch (err) {
        reject(new VoiceError(VoiceErrorKind.SOCKET_FAILED, "Could not open the speech connection.", err));
        return;
      }
      ws = wsRef;
      const timer = setTimeout(() => {
        try {
          wsRef.close();
        } catch {}
        reject(new VoiceError(VoiceErrorKind.SOCKET_FAILED, "The speech service did not respond in time."));
      }, connectTimeoutMs);

      wsRef.onopen = () => {
        clearTimeout(timer);
        log("socket.open", { url: url.replace(/\?.*$/, "?…") });
        resolve();
      };
      wsRef.onmessage = (ev) => {
        if (typeof ev.data !== "string") return;
        try {
          handleSocketMessage(JSON.parse(ev.data));
        } catch {}
      };
      wsRef.onerror = () => {
        clearTimeout(timer);
        log("socket.error");
        reject(new VoiceError(VoiceErrorKind.SOCKET_FAILED, "Could not reach the speech service."));
      };
      wsRef.onclose = (ev) => {
        clearTimeout(timer);
        log("socket.close", { code: ev?.code ?? null });
        if (providerState === "browser") return;
        if (!stopped) {
          const err = new VoiceError(
            VoiceErrorKind.SOCKET_CLOSED,
            "The speech connection dropped while recording."
          );
          sessionError = err;
          try {
            onError?.(err);
          } catch {}
          settleWith((s) => s.reject(err));
        }
      };
    }).catch((err) => {
      closeSocket();
      throw err instanceof VoiceError ? err : new VoiceError(VoiceErrorKind.SOCKET_FAILED, String(err), err);
    });

    const selectedProvider = await waitForProvider();
    if (selectedProvider === "browser") {
      closeSocket();
      return startBrowserRecognition();
    }

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      closeSocket();
      throw new VoiceError(
        VoiceErrorKind.MIC_INSECURE_CONTEXT,
        "Microphone capture needs a secure (https) connection."
      );
    }

    // ---- 1. microphone ----
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (err) {
      const voiceErr = micErrorFor(err);
      log("mic.error", { kind: voiceErr.kind });
      closeSocket();
      throw voiceErr;
    }
    log("mic.granted", { tracks: stream.getAudioTracks().length });

    // ---- 2. audio graph ----
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
      cleanupCapture();
      throw new VoiceError(VoiceErrorKind.MIC_FAILED, "This browser cannot capture audio.");
    }
    ctx = new AudioCtx();
    if (ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch {
        /* reported below by the state check */
      }
    }
    if (ctx.state !== "running") {
      cleanupCapture();
      throw new VoiceError(
        VoiceErrorKind.MIC_FAILED,
        "The browser blocked audio capture. Tap the screen once and try again."
      );
    }
    stats.sampleRate = ctx.sampleRate;
    log("audio.context", { sampleRate: ctx.sampleRate, state: ctx.state });

    // ---- capture loop ----
    try {
      source = ctx.createMediaStreamSource(stream);
      const capture = await createCaptureNode(ctx, (pcmBuffer, rms) => {
        onFrame(pcmBuffer, rms);
      });
      captureNode = capture.node;
      captureKind = capture.kind;
      stats.captureKind = capture.kind;
      source.connect(captureNode);
      // Zero-gain sink so the graph is pulled without playing the mic back.
      silentGain = ctx.createGain();
      silentGain.gain.value = 0;
      captureNode.connect(silentGain);
      silentGain.connect(ctx.destination);
      log("audio.capture", { kind: captureKind });
    } catch (err) {
      cleanupCapture();
      closeSocket();
      throw new VoiceError(VoiceErrorKind.MIC_FAILED, "Could not start audio capture.", err);
    }

    stats.startedAt = Date.now();
    emitStatus("listening");
    log("recording.start", { sampleRate: stats.sampleRate });
    return stats;
  };

  const stop = async () => {
    if (stopped) {
      return { transcript: finalText || partialText, partial: partialText, stats };
    }
    stopped = true;
    stats.durationMs = Date.now() - (stats.startedAt || Date.now());
    if (recognition) {
      log("recording.stop", { provider: stats.provider, durationMs: stats.durationMs });
      return new Promise((resolve, reject) => {
        browserStopResolve = resolve;
        browserStopReject = reject;
        browserStopTimer = setTimeout(finishBrowserStop, finalizeTimeoutMs);
        if (recognitionEnded || sessionError) {
          finishBrowserStop();
          return;
        }
        try {
          recognition.stop();
        } catch (error) {
          sessionError = new VoiceError(
            VoiceErrorKind.STT_PROVIDER,
            "Browser speech recognition could not be stopped cleanly.",
            error
          );
          finishBrowserStop();
        }
      });
    }

    log("recording.stop", {
      chunks: stats.chunks,
      bytes: stats.bytes,
      durationMs: stats.durationMs,
      peak: Number((stats.peakInt16 / 32768).toFixed(4)),
      captureKind: stats.captureKind,
    });

    // Stop capturing first, THEN ask the backend to finalise. The previous
    // order (close socket -> read state) discarded the final transcript.
    cleanupCapture();

    if (stats.chunks === 0 || stats.bytes === 0) {
      closeSocket();
      throw new VoiceError(
        VoiceErrorKind.EMPTY_AUDIO,
        "The microphone did not deliver any audio."
      );
    }

    // If the connection already failed mid-recording, report that rather
    // than pretending we can still finalise.
    if (sessionError) {
      closeSocket();
      throw sessionError;
    }

    let result;
    try {
      result = await requestFinal();
    } finally {
      closeSocket();
    }
    log("stt.final", { length: result.transcript.length, fromPartial: !!result.fromPartial });
    return { ...result, stats };
  };

  const abort = () => {
    aborted = true;
    stopped = true;
    if (browserStopTimer) {
      clearTimeout(browserStopTimer);
      browserStopTimer = null;
    }
    try {
      recognition?.abort();
    } catch {}
    recognition = null;
    if (browserStopReject) {
      browserStopReject(new VoiceError(VoiceErrorKind.SOCKET_CLOSED, "Recording cancelled."));
      browserStopResolve = null;
      browserStopReject = null;
    }
    settleWith((s) => s.reject(new VoiceError(VoiceErrorKind.SOCKET_CLOSED, "Recording cancelled.")));
    cleanupCapture();
    closeSocket();
    log("recording.abort");
  };

  return {
    start,
    stop,
    abort,
    get stats() {
      return { ...stats };
    },
    get hasPartial() {
      return partialText.trim().length > 0;
    },
  };
}

async function fetchVoiceWsToken() {
  const apiBase = import.meta.env?.VITE_API_BASE || "/api";
  const saved = JSON.parse(localStorage.getItem("asn_auth") || "{}");
  const headers = { "Content-Type": "application/json" };
  if (saved.token) headers.Authorization = `Bearer ${saved.token}`;
  const res = await fetch(`${apiBase.replace(/\/$/, "")}/voice/ws-token`, {
    method: "POST",
    headers,
  });
  if (!res.ok) throw new VoiceError(VoiceErrorKind.SOCKET_FAILED, "Could not authenticate the voice session.");
  const data = await res.json().catch(() => ({}));
  if (!data?.token) throw new VoiceError(VoiceErrorKind.SOCKET_FAILED, "Could not authenticate the voice session.");
  return data.token;
}

/** Builds the voice WebSocket URL, honouring VITE_API_BASE when absolute. */
export function buildSocketUrl(language = "en", base, token = "") {
  const apiBase =
    base ?? (import.meta.env?.VITE_API_BASE || "/api");
  const build = (urlObj) => {
    urlObj.searchParams.set("language", language);
    if (token) urlObj.searchParams.set("token", token);
    return urlObj.toString();
  };
  if (/^https?:\/\//i.test(apiBase)) {
    const url = new URL(apiBase.replace(/\/$/, "") + "/ws/voice");
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return build(url);
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const path = `${apiBase.replace(/\/$/, "")}/ws/voice`;
  const url = new URL(`${proto}//${window.location.host}${path}`);
  return build(url);
}

/**
 * Creates the capture node.
 *
 * Prefers an AudioWorklet: it runs on the audio thread and is reliable.
 * `createScriptProcessor` is deprecated and can silently deliver zeros for a
 * MediaStream source, which made every recording look empty ("no speech
 * captured") even though the microphone was working. The ScriptProcessor path
 * is kept only as a fallback for browsers without AudioWorklet.
 */
async function createCaptureNode(ctx, onFrame) {
  if (ctx.audioWorklet && typeof AudioWorkletNode !== "undefined") {
    try {
      await ctx.audioWorklet.addModule(WORKLET_URL);
      const node = new AudioWorkletNode(ctx, "pcm-capture", {
        processorOptions: { targetSampleRate: TARGET_SAMPLE_RATE },
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
      });
      node.port.onmessage = (event) => {
        const data = event.data || {};
        if (data.pcm) onFrame(data.pcm, data.rms);
      };
      return { node, kind: "audio-worklet" };
    } catch (err) {
      console.warn("[voice] AudioWorklet unavailable, falling back", err);
    }
  }

  // --- fallback: ScriptProcessor ---
  const downsampler = new Pcm16Downsampler(ctx.sampleRate, TARGET_SAMPLE_RATE);
  const node = ctx.createScriptProcessor(4096, 1, 1);
  node.onaudioprocess = (event) => {
    const input = event.inputChannelData[0];
    if (!input || input.length === 0) return;
    let sum = 0;
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
    const rms = Math.sqrt(sum / input.length);
    const samples = downsampler.process(input);
    if (!samples.length) return;
    onFrame(toInt16(samples).buffer, rms);
  };
  return { node, kind: "script-processor" };
}

/**
 * Captures microphone audio and streams it to `ws` as 16 kHz mono PCM16.
 *
 * Returns a stop function. Used by the legacy `streamMicToSocket` wrapper;
 * the Voice Assistant pages use `createVoiceSession` instead.
 */
export async function captureMicrophone(ws, onLevel) {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new VoiceError(
      VoiceErrorKind.MIC_INSECURE_CONTEXT,
      "Microphone capture needs a secure (https) connection."
    );
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  } catch (err) {
    throw micErrorFor(err);
  }

  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) {
    stream.getTracks().forEach((t) => t.stop());
    throw new VoiceError(VoiceErrorKind.MIC_FAILED, "This browser cannot capture audio.");
  }

  const ctx = new AudioCtx();
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      /* verified by the state check below */
    }
  }
  if (ctx.state !== "running") {
    stream.getTracks().forEach((t) => t.stop());
    try {
      await ctx.close();
    } catch {}
    throw new VoiceError(
      VoiceErrorKind.MIC_FAILED,
      "The browser blocked audio capture. Tap the screen once and try again."
    );
  }

  const capture = await createCaptureNode(ctx, (pcmBuffer, rms) => {
    try {
      onLevel?.(rms);
    } catch {}
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(pcmBuffer);
  });
  const source = ctx.createMediaStreamSource(stream);
  source.connect(capture.node);
  // Zero-gain sink: keeps the graph pulled without playing the mic back.
  const silentGain = ctx.createGain();
  silentGain.gain.value = 0;
  capture.node.connect(silentGain);
  silentGain.connect(ctx.destination);

  return () => {
    try {
      if (capture.node.port) capture.node.port.onmessage = null;
      capture.node.disconnect();
      source.disconnect();
      silentGain.disconnect();
    } catch {}
    stream.getTracks().forEach((t) => t.stop());
    try {
      ctx.close();
    } catch {}
  };
}
