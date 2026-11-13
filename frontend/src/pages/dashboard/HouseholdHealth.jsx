import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Droplets,
  Mic,
  Square,
  Loader2,
  CheckCircle2,
  Volume2,
  Home as HomeIcon,
  PenLine,
  Sparkles,
} from "lucide-react";
import { api, speak, LANGUAGES } from "../../lib/api.js";
import { createVoiceSession, VoiceErrorKind } from "../../lib/voice.js";
import { useAuth } from "../../lib/auth.jsx";
import { showToast } from "../../components/ui/Toast.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { Field } from "./Households.jsx";
import { useI18n } from "../../lib/i18n.jsx";

const INPUT =
  "w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 px-4 py-2.5 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30";

const WATER_SOURCES = ["borewell", "piped water", "hand pump", "open well", "rainwater harvesting", "river / pond"];
const WASTE_OPTIONS = ["waste is collected twice a week", "waste is collected weekly", "waste is burnt", "waste is thrown in the open"];
const DRAINAGE_OPTIONS = ["good", "closed", "open", "blocked"];

const EMPTY = {
  water_source: "",
  water_storage_covered: true,
  toilet_available: true,
  toilet_usage: "used",
  waste_disposal: "",
  drainage: "",
  stagnant_water: false,
  handwashing: true,
  awareness_provided: true,
  observations: "",
  follow_up_days: "",
};

export default function HouseholdHealth() {
  const navigate = useNavigate();
  const { mode } = useAuth();
  const { t, lang } = useI18n();
  const [searchParams] = useSearchParams();

  const [households, setHouseholds] = useState(null);
  const [hhId, setHhId] = useState("");
  const [detail, setDetail] = useState(null);

  // voice pipeline state
  const [recording, setRecording] = useState(false);
  const [spokenLanguage, setSpokenLanguage] = useState(lang || "en");
  const [voiceProvider, setVoiceProvider] = useState("");
  const [transcript, setTranscript] = useState("");
  const [partial, setPartial] = useState("");
  const [extracted, setExtracted] = useState(null);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [savedResult, setSavedResult] = useState(null);

  // manual form
  const [manual, setManual] = useState(EMPTY);
  const [manualOpen, setManualOpen] = useState(false);
  const [savingManual, setSavingManual] = useState(false);

  const sessionRef = useRef(null);

  /* ---------- data ---------- */
  useEffect(() => {
    api
      .get("/households")
      .then((d) => setHouseholds(d.households || []))
      .catch((e) => showToast(e.message || t("households.loadErr", "Could not load households."), "error"));
  }, []);

  useEffect(() => {
    const q = searchParams.get("household");
    if (q) setHhId(q);
  }, [searchParams]);

  useEffect(() => {
    setDetail(null);
    if (!hhId) return;
    api
      .get(`/households/${hhId}`)
      .then(setDetail)
      .catch((e) => showToast(e.message || t("households.loadOneErr", "Could not load household."), "error"));
  }, [hhId]);

  useEffect(
    () => () => {
      try {
        sessionRef.current?.abort();
      } catch {}
      sessionRef.current = null;
      window.speechSynthesis?.cancel();
    },
    []
  );

  /* ---------- voice pipeline (STT → extract → read-back → confirm → save) ---------- */

  /** Maps a VoiceError kind to a specific, actionable message. */
  const voiceErrorMessage = (err) => {
    switch (err?.kind) {
      case VoiceErrorKind.MIC_PERMISSION_DENIED:
        return t(
          "hh.errMicDenied",
          "Microphone permission was denied. Allow microphone access for this site in your browser settings, then tap the mic again."
        );
      case VoiceErrorKind.MIC_NO_DEVICE:
        return t(
          "hh.errMicMissing",
          "No microphone was found on this device. Connect a microphone and try again."
        );
      case VoiceErrorKind.MIC_BUSY:
        return t(
          "hh.errMicBusy",
          "The microphone is being used by another application. Close it and try again."
        );
      case VoiceErrorKind.MIC_INSECURE_CONTEXT:
        return t("hh.errInsecure", "Microphone capture needs a secure (https) connection.");
      case VoiceErrorKind.SOCKET_FAILED:
        return t(
          "hh.errSocket",
          "Could not reach the speech service. Check your connection and try again."
        );
      case VoiceErrorKind.SOCKET_CLOSED:
        return t(
          "hh.errSocketClosed",
          "The speech connection dropped while recording. Please try again."
        );
      case VoiceErrorKind.STT_PROVIDER:
        return t(
          "hh.errProvider",
          "The speech service could not produce a transcript. Please try again."
        );
      case VoiceErrorKind.SPEECH_UNSUPPORTED:
        return t("hh.errSpeechUnsupported", "Speech recognition is not available in this browser.");
      case VoiceErrorKind.SPEECH_LANGUAGE_UNSUPPORTED:
        return t("hh.errSpeechLanguage", "This browser does not support speech recognition for the selected language.");
      case VoiceErrorKind.SPEECH_NETWORK:
        return t("hh.errSpeechNetwork", "Browser speech recognition could not reach its service.");
      case VoiceErrorKind.EMPTY_AUDIO:
        return t(
          "hh.errEmptyAudio",
          "The microphone did not deliver any audio. Check that it is unmuted and try again."
        );
      case VoiceErrorKind.TIMEOUT:
        return t(
          "hh.errTimeout",
          "The recording took too long to process. Please try a shorter recording."
        );
      case VoiceErrorKind.NO_SPEECH:
        return t("hh.errNoSpeech", "No speech was detected. Tap the mic and speak while recording.");
      default:
        return t("hh.micUnavailable", "Microphone unavailable — use Manual Entry instead.");
    }
  };

  const startRecording = async () => {
    setTranscript("");
    setPartial("");
    setExtracted(null);
    setSavedResult(null);
    setVoiceProvider("");
    setRecording(true);

    const session = createVoiceSession({
      language: spokenLanguage,
      preferBrowser: mode !== "live",
      onProvider: setVoiceProvider,
      onPartial: (text) => setPartial(text || ""),
      onStatus: (stage) => {
        if (stage === "processing" || stage === "finalizing") setBusy(true);
      },
      onError: (err) => {
        // A mid-recording failure (e.g. the speech service went away) must
        // be reported immediately, not after the user stops.
        setRecording(false);
        setBusy(false);
        sessionRef.current?.abort();
        sessionRef.current = null;
        const msg = voiceErrorMessage(err);
        showToast(msg, "warn");
      },
      onLog: (e) => console.info("[voice]", e.event, e),
    });
    sessionRef.current = session;

    try {
      await session.start();
    } catch (e) {
      sessionRef.current = null;
      setRecording(false);
      setBusy(false);
      const msg = voiceErrorMessage(e);
      showToast(msg, "warn");
      setManualOpen(true);
    }
  };

  const stopRecording = async () => {
    const session = sessionRef.current;
    sessionRef.current = null;
    setRecording(false);

    if (!session) {
      showToast(t("hh.errNoSpeech"), "warn");
      setManualOpen(true);
      return;
    }

    setBusy(true);
    try {
      // Wait for the backend's final transcript before deciding that nothing
      // was captured — a transient empty partial is not a failure.
      const { transcript: text } = await session.stop();
      if (!text || !text.trim()) {
        showToast(t("hh.errNoSpeech"), "warn");
        setManualOpen(true);
        return;
      }
      setTranscript(text);
      const res = await api.post("/voice/extract", { transcript: text, language: spokenLanguage });
      setExtracted(res);
      setSpeaking(true);
      await speak(readBackText(res.structured), spokenLanguage, mode);
      setSpeaking(false);
    } catch (e) {
      const msg = voiceErrorMessage(e);
      showToast(msg, "warn");
      setManualOpen(true);
    } finally {
      setBusy(false);
      setSpeaking(false);
    }
  };

  /** Tara reads the extracted household observations back in the worker's language. */
  const readBackText = (s) => {
    const parts = [];
    if (s.household_id) parts.push(`${t("field.household")} ${s.household_id}.`);
    if (s.water_source) parts.push(`${t("hh.waterSource")}: ${s.water_source}.`);
    if (s.water_storage_covered !== undefined)
      parts.push(
        s.water_storage_covered
          ? t("hh.rb.covered", "Water is stored in a covered container.")
          : t("hh.rb.uncovered", "Water storage is not covered.")
      );
    if (s.toilet_available !== undefined)
      parts.push(
        s.toilet_available
          ? t("hh.rb.toiletYes", "Toilet is available.")
          : t("hh.rb.toiletNo", "No toilet is available.")
      );
    if (s.waste_disposal) parts.push(`${t("hh.wasteDisposal")}: ${s.waste_disposal}.`);
    if (s.drainage) parts.push(`${t("hh.drainage")}: ${s.drainage}.`);
    if (s.stagnant_water !== undefined)
      parts.push(
        s.stagnant_water
          ? t("hh.rb.stagnantYes", "Stagnant water is present.")
          : t("hh.rb.stagnantNo", "No stagnant water.")
      );
    if (s.handwashing !== undefined)
      parts.push(
        s.handwashing
          ? t("hh.rb.handYes", "Handwashing facility available.")
          : t("hh.rb.handNo", "No handwashing facility.")
      );
    if (s.awareness_provided) parts.push(t("hh.rb.awareness", "Health awareness was provided."));
    if (s.follow_up_days)
      parts.push(t("hh.rb.followUp", "Follow-up in {n} days.").replace("{n}", s.follow_up_days));
    return parts.join(" ") || t("hh.rb.generic", "Household visit recorded.");
  };

  /** Only fields the worker re-states change — simulated via editing the preview. */
  const confirmSave = async () => {
    if (!extracted || !hhId) return;
    setBusy(true);
    try {
      const structured = { ...extracted.structured };
      if (structured.observations) delete structured.observations;
      const res = await api.post(`/households/${hhId}/visits`, {
        structured,
        transcript: transcript || "",
        language: spokenLanguage,
      });
      setSavedResult(res);
      setExtracted(null);
      setTranscript("");
      showToast(t("hh.recorded"), "success");
      api.get(`/households/${hhId}`).then(setDetail).catch(() => {});
      if (res.follow_up) showToast(t("hh.stagnantNote"), "info");
    } catch (e) {
      showToast(e.message || t("hh.saveFailed", "Could not save the visit."), "error");
    } finally {
      setBusy(false);
    }
  };

  /* ---------- manual entry ---------- */
  const saveManual = async () => {
    if (!hhId) {
      showToast(t("hh.chooseHouseholdFirst", "Choose a household first."), "warn");
      return;
    }
    if (!manual.water_source || !manual.waste_disposal || !manual.drainage) {
      showToast(
        t("hh.fillRequired", "Please fill water source, waste disposal and drainage."),
        "warn"
      );
      return;
    }
    setSavingManual(true);
    try {
      const structured = {
        ...manual,
        follow_up_days: manual.follow_up_days ? Number(manual.follow_up_days) : undefined,
      };
      delete structured.observations;
      if (manual.observations?.trim()) structured.hygiene_observations = manual.observations.trim();
      const res = await api.post(`/households/${hhId}/visits`, {
        structured,
        transcript: "",
        language: lang,
      });
      setSavedResult(res);
      setManual(EMPTY);
      setManualOpen(false);
      showToast(t("hh.recorded"), "success");
      api.get(`/households/${hhId}`).then(setDetail).catch(() => {});
      if (res.follow_up) showToast(t("hh.stagnantNote"), "info");
    } catch (e) {
      showToast(e.message || t("hh.saveFailed", "Could not save the visit."), "error");
    } finally {
      setSavingManual(false);
    }
  };

  const selectedHousehold = households?.find((h) => String(h.id) === String(hhId));

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep">{t("hh.title")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">{t("hh.subtitle")}</p>
        </div>
        <button
          onClick={() => setManualOpen((v) => !v)}
          className="chip bg-teal-deep/5 text-teal-deep/70 hover:bg-teal-deep/10 transition-colors flex items-center gap-1.5"
        >
          <PenLine size={13} /> {t("hh.manualEntry", "Manual Entry")}
        </button>
      </div>

      {/* household selector */}
      <div className="card-ivory p-4">
        {households === null ? (
          <SkeletonCard />
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-3">
              <HomeIcon size={17} className="text-pink" />
              <select value={hhId} onChange={(e) => setHhId(e.target.value)} className={`${INPUT} max-w-sm`}>
                <option value="">{t("hh.chooseHousehold", "— Choose a household —")}</option>
                {households.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.village} ({h.qr_id})
                  </option>
                ))}
              </select>
            </label>
            {selectedHousehold && (
              <span className="chip bg-mint-soft text-teal-deep">
                {t("households.members")}: {selectedHousehold.member_count}
              </span>
            )}
          </div>
        )}
      </div>

      {/* voice visit studio */}
      <div className="card-ivory overflow-hidden p-0">
        <div className="bg-teal-deep px-6 py-5 text-white">
          <div className="flex items-center gap-3">
            <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-mint/20">
              <Mic size={18} className="text-mint" />
              {recording && (
                <span className="absolute inset-0 animate-ping rounded-full bg-mint/30" />
              )}
            </span>
            <div>
              <p className="text-sm font-extrabold">{t("voice.speakNow")}</p>
              <p className="text-[0.7rem] font-medium text-white/60">
                {voiceProvider || t("voice.providerOnRecord", "Speech provider selected on Record")}
              </p>
            </div>
          </div>
          <label className="mt-4 flex items-center gap-2 text-xs font-bold text-white/75">
            <span>{t("voice.spokenLanguage", "Spoken language")}</span>
            <select
              value={spokenLanguage}
              disabled={recording || busy}
              onChange={(e) => setSpokenLanguage(e.target.value)}
              className="rounded-lg border border-white/15 bg-white/10 px-2.5 py-1.5 text-xs text-white outline-none [&>option]:text-teal-deep"
            >
              {LANGUAGES.map((item) => (
                <option key={item.code} value={item.code}>{item.native}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="p-5 sm:p-6">
          {/* waveform / status */}
          <div className="flex flex-col items-center gap-4 py-4">
            <div className="flex h-16 w-full max-w-lg items-center justify-center gap-1.5 rounded-3xl bg-teal-deep/[0.04] px-4">
              {recording || speaking ? (
                Array.from({ length: 32 }).map((_, i) => (
                  <motion.span
                    key={i}
                    className="w-1 rounded-full bg-mint"
                    animate={{
                      height: recording
                        ? [8, 10 + 34 * Math.abs(Math.sin(i * 0.7)), 8]
                        : [8, 10 + 24 * Math.abs(Math.sin(i * 0.9)), 8],
                    }}
                    transition={{
                      repeat: Infinity,
                      duration: speaking ? 1.1 : 0.8,
                      delay: (i % 8) * 0.06,
                      ease: "easeInOut",
                    }}
                  />
                ))
              ) : (
                <p className="text-xs font-semibold text-teal-deep/40">
                  {busy ? t("voice.processing") : t("voice.speakNow")}
                </p>
              )}
            </div>

            <button
              onClick={recording ? stopRecording : startRecording}
              disabled={busy || !hhId}
              className={[
                "flex h-16 w-16 items-center justify-center rounded-full text-white transition-all",
                recording
                  ? "bg-coral shadow-[0_0_36px_rgba(255,128,111,0.6)]"
                  : "bg-mint shadow-[0_0_36px_rgba(240,120,173,0.55)] hover:scale-105",
                busy || !hhId ? "opacity-50 cursor-not-allowed" : "",
              ].join(" ")}
              aria-label={
                !hhId
                  ? t("hh.chooseHouseholdFirst", "Choose a household first")
                  : recording
                    ? t("voice.stop")
                    : t("voice.record")
              }
              title={
                !hhId
                  ? t("hh.chooseHouseholdFirst", "Choose a household first")
                  : recording
                    ? t("voice.stop")
                    : t("voice.record")
              }
            >
              {recording ? <Square size={24} /> : <Mic size={26} />}
            </button>
            <p className="text-xs font-bold text-teal-deep/50">
              {recording ? t("voice.listening") : speaking ? t("voice.readback") : busy ? t("voice.processing") : `${t("voice.record")} / ${t("voice.stop")}`}
            </p>
          </div>

          {/* live transcript */}
          {(transcript || partial) && (
            <div className="mt-4 rounded-2xl bg-teal-deep/[0.04] p-4">
              <p className="mb-1 text-[0.68rem] font-extrabold uppercase tracking-wider text-teal-deep/45">
                {t("voice.transcript")}
              </p>
              <p className="text-sm font-medium leading-relaxed text-teal-deep/80">
                {transcript}
                {partial && <span className="text-teal-deep/40"> {partial}</span>}
              </p>
            </div>
          )}

          {/* structured preview + confirm */}
          {extracted && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 rounded-2xl border border-mint/40 bg-mint/[0.06] p-4"
            >
              <p className="mb-3 flex items-center gap-2 text-[0.68rem] font-extrabold uppercase tracking-wider text-teal-deep/60">
                <Sparkles size={13} className="text-pink" /> {t("voice.preview")}
                <span className="chip bg-white/70 text-[0.62rem] text-teal-deep/60 normal-case">
                  {extracted.mode === "demo" ? t("common.demoMode") : "Live"}
                </span>
              </p>
              <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
                {Object.entries(extracted.structured).map(([k, v]) => (
                  <p key={k} className="text-xs font-medium text-teal-deep/75">
                    <span className="font-extrabold text-teal-deep/50">{fieldLabel(k, t)}: </span>
                    {fmtPreview(k, v, t)}
                  </p>
                ))}
              </div>
              <div className="mt-4 flex flex-col gap-2.5 sm:flex-row">
                <button
                  onClick={confirmSave}
                  disabled={busy}
                  className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60"
                >
                  {busy ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={16} />}
                  {t("voice.confirmSave")}
                </button>
                <button
                  onClick={() => setExtracted(null)}
                  className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                >
                  {t("voice.discard")}
                </button>
              </div>
            </motion.div>
          )}

          {/* saved */}
          {savedResult && (
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mt-4 flex flex-col items-center gap-3 rounded-2xl border border-mint/40 bg-mint/[0.08] p-5 text-center"
            >
              <CheckCircle2 size={34} className="text-mint" />
              <p className="text-sm font-extrabold text-teal-deep">{t("hh.recorded")}</p>
              {savedResult.follow_up && (
                <p className="text-xs font-semibold text-teal-deep/60">
                  {t("households.nextFollowup")}: {savedResult.follow_up.due_date} ({savedResult.follow_up.status})
                </p>
              )}
              <div className="flex gap-2.5">
                <button
                  onClick={() => navigate(`/app/households/${hhId}`)}
                  className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm"
                >
                  {t("households.timeline")}
                </button>
                <button
                  onClick={() => {
                    setSavedResult(null);
                    setTranscript("");
                  }}
                  className="rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                >
                  {t("voice.record")}
                </button>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* manual entry */}
      {manualOpen && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="card-ivory p-5 sm:p-6"
        >
          <h3 className="mb-1 flex items-center gap-2 text-base font-extrabold text-teal-deep">
            <PenLine size={16} className="text-pink" /> {t("hh.manualEntry", "Manual Entry")}
          </h3>
          <p className="mb-4 text-xs font-semibold text-teal-deep/50">{t("hh.noShaming")}</p>
          <div className="grid gap-3.5 sm:grid-cols-2">
            <Field label={t("hh.waterSource")}>
              <select value={manual.water_source} onChange={(e) => setManual({ ...manual, water_source: e.target.value })} className={INPUT}>
                <option value="">—</option>
                {WATER_SOURCES.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label={t("hh.waterStorage")}>
              <select value={String(manual.water_storage_covered)} onChange={(e) => setManual({ ...manual, water_storage_covered: e.target.value === "true" })} className={INPUT}>
                <option value="true">{t("hh.covered")}</option>
                <option value="false">{t("hh.uncovered")}</option>
              </select>
            </Field>
            <Field label={t("hh.toiletAvailable")}>
              <select value={String(manual.toilet_available)} onChange={(e) => setManual({ ...manual, toilet_available: e.target.value === "true" })} className={INPUT}>
                <option value="true">{t("common.yes")}</option>
                <option value="false">{t("common.no")}</option>
              </select>
            </Field>
            <Field label={t("hh.toiletUsage")}>
              <select value={manual.toilet_usage} onChange={(e) => setManual({ ...manual, toilet_usage: e.target.value })} className={INPUT}>
                <option value="used">{t("hh.used")}</option>
                <option value="not used">{t("hh.notUsed")}</option>
              </select>
            </Field>
            <Field label={t("hh.wasteDisposal")}>
              <select value={manual.waste_disposal} onChange={(e) => setManual({ ...manual, waste_disposal: e.target.value })} className={INPUT}>
                <option value="">—</option>
                {WASTE_OPTIONS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label={t("hh.drainage")}>
              <select value={manual.drainage} onChange={(e) => setManual({ ...manual, drainage: e.target.value })} className={INPUT}>
                <option value="">—</option>
                {DRAINAGE_OPTIONS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label={t("hh.stagnantWater")}>
              <select value={String(manual.stagnant_water)} onChange={(e) => setManual({ ...manual, stagnant_water: e.target.value === "true" })} className={INPUT}>
                <option value="false">{t("common.no")}</option>
                <option value="true">{t("common.yes")}</option>
              </select>
            </Field>
            <Field label={t("hh.handwashing")}>
              <select value={String(manual.handwashing)} onChange={(e) => setManual({ ...manual, handwashing: e.target.value === "true" })} className={INPUT}>
                <option value="true">{t("common.yes")}</option>
                <option value="false">{t("common.no")}</option>
              </select>
            </Field>
            <Field label={t("hh.awareness")}>
              <select value={String(manual.awareness_provided)} onChange={(e) => setManual({ ...manual, awareness_provided: e.target.value === "true" })} className={INPUT}>
                <option value="true">{t("common.yes")}</option>
                <option value="false">{t("common.no")}</option>
              </select>
            </Field>
            <Field label={t("hh.followUpIn")}>
              <input type="number" min="0" max="180" value={manual.follow_up_days} onChange={(e) => setManual({ ...manual, follow_up_days: e.target.value })} placeholder="e.g. 7" className={INPUT} />
            </Field>
            <div className="sm:col-span-2">
              <Field label={t("hh.observations")}>
                <textarea rows={2} value={manual.observations} onChange={(e) => setManual({ ...manual, observations: e.target.value })} placeholder="e.g. Advised the family to clear stagnant water and prevent mosquito breeding." className={INPUT} />
              </Field>
            </div>
          </div>
          <button
            onClick={saveManual}
            disabled={savingManual}
            className="btn-mint mt-4 flex items-center gap-2 px-6 py-2.5 text-sm disabled:opacity-60"
          >
            {savingManual ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={16} />}
            {t("common.save")}
          </button>
        </motion.div>
      )}

      {/* recent household visits for the selected household */}
      {detail && detail.visits.length > 0 && (
        <div className="card-ivory p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">
            <Droplets size={15} className="text-pink" /> {t("households.healthVisits")}
          </h3>
          <ul className="space-y-2">
            {detail.visits.slice(0, 5).map((v) => (
              <li key={v.id} className="flex items-center justify-between gap-2 rounded-2xl bg-teal-deep/[0.04] px-3 py-2">
                <p className="text-xs font-bold text-teal-deep">{v.visit_date}</p>
                <span className={`chip ${v.source === "voice" ? "bg-mint-soft text-teal-deep" : "bg-teal-deep/5 text-teal-deep/55"}`}>
                  {v.source === "voice" ? "🎙" : "Manual"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function fieldLabel(key, t) {
  const map = {
    household_id: "Household",
    water_source: "hh.waterSource",
    water_storage_covered: "hh.waterStorage",
    toilet_available: "hh.toiletAvailable",
    toilet_usage: "hh.toiletUsage",
    waste_disposal: "hh.wasteDisposal",
    drainage: "hh.drainage",
    stagnant_water: "hh.stagnantWater",
    handwashing: "hh.handwashing",
    awareness_provided: "hh.awareness",
    follow_up_days: "hh.followUpIn",
    visit_date: "common.date",
  };
  return map[key] ? t(map[key]) : key;
}

function fmtPreview(key, v, t) {
  if (typeof v === "boolean") return v ? t("common.yes") : t("common.no");
  return String(v);
}
