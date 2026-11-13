const BASE = import.meta.env.VITE_API_BASE || "/api";

import { buildSocketUrl } from "./voice.js";

async function handle(res) {
  if (res.status === 401) {
    localStorage.removeItem("asn_auth");
    window.location.href = "/login";
    throw new Error("Session expired. Please sign in again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  return data;
}

export const api = {
  get: (path) => fetch(`${BASE}${path}`, { headers: authHeaders() }).then(handle),
  post: (path, body) =>
    fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body ?? {}),
    }).then(handle),
};

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

/** Speak text aloud. Uses Gnani Timbre when the backend returns audio, otherwise the Web Speech API. */
export async function speak(text, language, mode) {
  if (mode === "live") {
    try {
      const res = await api.post("/voice/tts", { text, language });
      if (res.audio_base64) {
        const audio = new Audio(`data:audio/wav;base64,${res.audio_base64}`);
        await audio.play();
        return;
      }
    } catch {}
  }
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    if (!synth) return resolve();
    const utter = new SpeechSynthesisUtterance(text);
    const langMap = { en: "en-IN", kn: "kn-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN" };
    utter.lang = langMap[language] || "en-IN";
    utter.rate = 0.95;
    utter.onend = () => resolve();
    utter.onerror = () => resolve();
    synth.cancel();
    synth.speak(utter);
  });
}

export const LANGUAGES = [
  { code: "en", label: "English", native: "English" },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "te", label: "Telugu", native: "తెలుగు" },
  { code: "ta", label: "Tamil", native: "தமிழ்" },
];
