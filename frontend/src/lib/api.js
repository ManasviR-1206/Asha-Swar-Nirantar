const BASE = import.meta.env.VITE_API_BASE || "/api";

import { buildSocketUrl } from "./voice.js";

async function handle(res, { redirectOnUnauthorized = true } = {}) {
  if (res.status === 401 && redirectOnUnauthorized) {
    localStorage.removeItem("asn_auth");
    // Hard redirect to login; return a never-resolving promise so callers don't
    // show spurious error toasts while the browser navigates away.
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    return new Promise(() => {});
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  return data;
}

function fetchWithTimeout(url, options = {}, timeoutMs = 20000) {
  const { timeoutMs: optTimeout, signal: externalSignal, ...fetchOptions } = options;
  const effectiveTimeout = optTimeout ?? (
    /\/voice\/(extract|chat|tts|sessions)|\/ws-token/.test(url) ? 60000 : timeoutMs
  );
  const controller = new AbortController();
  const onExternalAbort = () => controller.abort(externalSignal?.reason);
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort(externalSignal.reason);
    else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }
  const timer = effectiveTimeout > 0 ? setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), effectiveTimeout) : null;
  return fetch(url, { ...fetchOptions, signal: controller.signal })
    .catch((err) => {
      if (err?.name === "AbortError") {
        if (externalSignal?.aborted) throw new Error("Request cancelled.");
        throw new Error("The request took too long. Please check your connection and try again.");
      }
      throw err;
    })
    .finally(() => {
      if (timer) clearTimeout(timer);
      if (externalSignal) externalSignal.removeEventListener("abort", onExternalAbort);
    });
}

export const api = {
  get: (path, options = {}) => fetchWithTimeout(`${BASE}${path}`, { headers: authHeaders(), signal: options.signal, timeoutMs: options.timeoutMs }).then((res) => handle(res, options)),
  post: (path, body, options = {}) =>
    fetchWithTimeout(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body ?? {}),
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    }).then((res) => handle(res, options)),
  patch: (path, body, options = {}) =>
    fetchWithTimeout(`${BASE}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body ?? {}),
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    }).then((res) => handle(res, options)),
  /** Multipart upload (e.g. an audio file for voice verification or document upload). */
  postForm: (path, formData, options = {}) =>
    fetchWithTimeout(`${BASE}${path}`, {
      method: "POST",
      // No explicit Content-Type - browser adds the multipart boundary.
      headers: authHeaders(),
      body: formData,
      signal: options.signal,
      timeoutMs: options.timeoutMs || 60000,
    }).then((res) => handle(res, options)),
  del: (path, options = {}) => fetchWithTimeout(`${BASE}${path}`, { method: "DELETE", headers: authHeaders(), signal: options.signal, timeoutMs: options.timeoutMs }).then((res) => handle(res, options)),
};

/**
 * Download a protected file (e.g. a PDF report) with the auth header.
 * Returns a Blob URL the caller can hand to an <a download>.
 */
export async function downloadFile(path, fallbackName = "download") {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Give the browser a moment to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return blob;
}

/** Open a protected file in a new tab (used for the PDF preview). */
export async function openFile(path) {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Could not open the file (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function authHeaders() {
  try {
    const saved = JSON.parse(localStorage.getItem("asn_auth") || "{}");
    if (saved.token) return { Authorization: `Bearer ${saved.token}` };
  } catch {}
  return {};
}

/** Open the streaming voice WebSocket. Returns the WebSocket instance. */
export function openVoiceSocket(language, handlers) {
  const ws = new WebSocket(buildSocketUrl(language));
  ws.onopen = () => handlers.onOpen?.();
  ws.onmessage = (e) => {
    try {
      handlers.onMessage(JSON.parse(e.data));
    } catch {}
  };
  ws.onclose = (e) => handlers.onClose?.(e);
  ws.onerror = () => handlers.onError?.();
  return ws;
}

/**
 * Stream microphone audio into the voice WebSocket.
 *
 * Kept for backwards compatibility — the Voice Assistant pages use
 * `createVoiceSession` (src/lib/voice.js) which adds the finalise handshake
 * and precise error handling. This wrapper shares the same corrected
 * capture path: 16 kHz downsampling, resumed AudioContext and a muted
 * output so the microphone is never played back through the speakers.
 */
export async function streamMicToSocket(ws, onLevel) {
  const { captureMicrophone } = await import("./voice.js");
  return captureMicrophone(ws, onLevel);
}

let currentAudio = null;
let currentUtterance = null;
let speakGeneration = 0;
let pendingPlayback = null; // { kind: 'audio'|'synth', audio?, text?, language? } for autoplay-block retry

/** Stop any active Tara/browser speech immediately (barge-in / cancel). */
export function stopSpeaking() {
  speakGeneration += 1;
  pendingPlayback = null;
  try {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio.src = "";
    }
  } catch {}
  currentAudio = null;
  try {
    window.speechSynthesis?.cancel();
  } catch {}
  currentUtterance = null;
}

export function pauseSpeaking() {
  try { if (currentAudio && !currentAudio.paused) { currentAudio.pause(); return true; } } catch {}
  try { if (window.speechSynthesis?.speaking && !window.speechSynthesis.paused) { window.speechSynthesis.pause(); return true; } } catch {}
  return false;
}

export function resumeSpeaking() {
  try { if (currentAudio?.paused) { const p = currentAudio.play(); return p; } } catch {}
  try { if (window.speechSynthesis?.paused) { window.speechSynthesis.resume(); return true; } } catch {}
  return false;
}

export function getPlaybackState() {
  if (pendingPlayback) return "blocked";
  try { if (currentAudio && !currentAudio.paused) return "speaking"; } catch {}
  try { if (currentAudio?.paused) return "paused"; } catch {}
  try { if (window.speechSynthesis?.speaking) return window.speechSynthesis.paused ? "paused" : "speaking"; } catch {}
  return "idle";
}

export async function retryPendingPlayback() {
  const pending = pendingPlayback;
  pendingPlayback = null;
  if (!pending) return { error: true, message: "No pending audio" };
  if (pending.kind === "audio" && pending.audio) {
    try {
      await pending.audio.play();
      return { ended: true, provider: pending.provider || "backend" };
    } catch (e) {
      console.warn("[TTS] pending audio replay failed", e?.name, e?.message);
      return { error: true, autoplayBlocked: e?.name === "NotAllowedError" };
    }
  }
  if (pending.kind === "synth") {
    return speak(pending.text, pending.language, "demo", { _skipBackend: true });
  }
  return { error: true };
}

export function hasPendingPlayback() { return !!pendingPlayback; }

/** Speak text aloud. Uses Gnani Timbre/backend TTS when configured, else browser speech synthesis.
 *  Supports barge-in via stopSpeaking(). opts.onFirstAudio(msSinceRequest) reports TTFA.
 *  Returns { ended, interrupted, error, unsupported, autoplayBlocked, provider }.
 */
export async function speak(text, language, mode, opts = {}) {
  const myGen = ++speakGeneration;
  const requestedAt = performance.now();
  const reportFirstAudio = () => {
    if (opts.firstAudioReported) return;
    opts.firstAudioReported = true;
    const ms = Math.max(0, Math.round(performance.now() - requestedAt));
    try { opts.onFirstAudio?.(ms); } catch {}
  };

  stopSpeaking();
  speakGeneration = myGen;
  const cleanText = String(text || "").trim();
  if (!cleanText) return { ended: true, provider: "none" };

  const playAudioBase64 = async (audioBase64, mime, provider) => {
    const audio = new Audio(`data:${mime || "audio/wav"};base64,${audioBase64}`);
    currentAudio = audio;
    const playPromise = new Promise((resolve) => {
      let done = false;
      const timer = setTimeout(() => finish({ error: true, timeout: true }), 45000);
      const finish = (r = {}) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        if (currentAudio === audio) currentAudio = null;
        resolve(r);
      };
      audio.onplaying = () => { console.info("[TTS] playback started", { provider }); reportFirstAudio(); };
      audio.onended = () => { console.info("[TTS] playback completed", { provider }); finish({ ended: true }); };
      audio.onerror = (e) => { console.warn("[TTS] audio element error", { provider, e }); finish({ error: true }); };
      audio.onpause = () => { if (myGen !== speakGeneration) finish({ interrupted: true }); };
    });
    try {
      await audio.play();
      if (myGen !== speakGeneration) return { interrupted: true, provider };
    } catch (e) {
      console.warn("[TTS] audio.play() failed", { provider, name: e?.name, message: e?.message });
      if (e?.name === "NotAllowedError") {
        pendingPlayback = { kind: "audio", audio, provider };
        if (currentAudio === audio) currentAudio = null;
        return { error: true, autoplayBlocked: true, provider };
      }
      if (currentAudio === audio) currentAudio = null;
      return { error: true, provider };
    }
    const result = await playPromise;
    return { ...result, provider };
  };

  // Try backend TTS first (Gnani Timbre when configured).
  if (!opts._skipBackend) {
    try {
      console.info("[TTS] requesting backend TTS", { language, chars: cleanText.length });
      const res = await api.post("/voice/tts", { text: cleanText, language });
      if (myGen !== speakGeneration) return { interrupted: true, provider: "backend" };
      const hasAudio = !!res?.audio_base64;
      console.info("[TTS] backend response", { mode: res?.mode, hasAudio, provider: res?.provider, mime: res?.mime_type, audioChars: res?.audio_base64?.length || 0 });
      if (hasAudio) {
        const result = await playAudioBase64(res.audio_base64, res.mime_type || "audio/wav", res.provider || "Gnani Timbre");
        if (result?.ended) return result;
        if (result?.interrupted) return result;
        if (result?.autoplayBlocked) return result;
        console.warn("[TTS] backend audio playback failed, falling back to browser synthesis", result);
      } else {
        console.info("[TTS] backend returned no audio; falling back to browser speech synthesis", { mode: res?.mode });
      }
    } catch (e) {
      console.warn("[TTS] backend TTS request failed, falling back to browser speech synthesis", { message: e?.message });
    }
  }

  if (myGen !== speakGeneration) return { interrupted: true, provider: "browser" };
  const synth = window.speechSynthesis;
  if (!synth) return { unsupported: true, provider: "browser" };
  return new Promise((resolve) => {
    const utter = new SpeechSynthesisUtterance(cleanText);
    const langMap = { en: "en-IN", kn: "kn-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN" };
    utter.lang = langMap[language] || "en-IN";
    utter.rate = 0.95;
    currentUtterance = utter;
    let done = false;
    const timer = setTimeout(() => finish({ error: true, timeout: true }), 45000);
    const finish = (r = {}) => { if (done) return; done = true; clearTimeout(timer); if (currentUtterance === utter) currentUtterance = null; resolve(r); };
    utter.onstart = () => { console.info("[TTS] browser speech started"); reportFirstAudio(); };
    utter.onend = () => { console.info("[TTS] browser speech completed"); finish({ ended: true, provider: "browser" }); };
    utter.onerror = (e) => {
      console.warn("[TTS] browser speech error", e?.error);
      if (e?.error === "not-allowed" || e?.error === "service-not-allowed") {
        pendingPlayback = { kind: "synth", text: cleanText, language };
        finish({ error: true, autoplayBlocked: true, provider: "browser" });
      } else {
        finish({ interrupted: myGen !== speakGeneration, error: myGen === speakGeneration, provider: "browser" });
      }
    };
    try {
      synth.cancel();
      synth.speak(utter);
    } catch (e) {
      console.warn("[TTS] browser speech speak() threw", e?.message);
      finish({ error: true, provider: "browser" });
    }
  });
}

export const LANGUAGES = [
  { code: "en", label: "English", native: "English" },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "te", label: "Telugu", native: "తెలుగు" },
  { code: "ta", label: "Tamil", native: "தமிழ்" },
];
