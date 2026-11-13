import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Mic,
  Square,
  User,
  Home as HomeIcon,
  HeartPulse,
  CalendarHeart,
  Activity,
  Scale,
  Thermometer,
  Syringe,
  CalendarDays,
  Volume2,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Waves,
  Languages,
  UserPlus,
  BadgeCheck,
  X,
  CircleAlert,
  Droplets,
  Edit3,
  Trash2,
  Plus,
  Check,
  Users,
} from "lucide-react";
import { api, speak, LANGUAGES } from "../../lib/api.js";
import { createVoiceSession, VoiceError, VoiceErrorKind } from "../../lib/voice.js";
import { useAuth } from "../../lib/auth.jsx";
import { showToast } from "../../components/ui/Toast.jsx";
import { useI18n } from "../../lib/i18n.jsx";

/* ----------------------------- field metadata ----------------------------- */

const FIELD_DEFS = [
  // Identity & Demographics
  { key: "beneficiary_name", label: "field.beneficiary", icon: User, render: (v) => v },
  { key: "category", label: "field.category", icon: HeartPulse, render: (v) => v },
  { key: "age", label: "field.age", icon: Activity, render: (v) => `${v} yrs` },
  { key: "gender", label: "field.gender", icon: User, render: (v) => v },
  { key: "relation", label: "field.relation", icon: Users, render: (v) => v },
  { key: "village", label: "field.village", icon: HomeIcon, render: (v) => v },
  { key: "phone", label: "field.phone", icon: Activity, render: (v) => v },

  // Maternal Health
  { key: "weeks_pregnant", label: "field.weeksPregnant", icon: CalendarHeart, render: (v) => `${v} weeks` },
  {
    key: "bp",
    label: "field.bp",
    icon: Activity,
    from: (r) => (r.bp_sys && r.bp_dia ? `${r.bp_sys}/${r.bp_dia}` : r.bp_sys ? `${r.bp_sys}/—` : null),
  },
  { key: "weight_kg", label: "field.weight", icon: Scale, render: (v) => `${v} kg` },
  { key: "hemoglobin", label: "field.hemoglobin", icon: HeartPulse, render: (v) => `${v} g/dL` },
  { key: "fetal_heart", label: "field.fetalHeart", icon: HeartPulse, render: (v) => v },
  {
    key: "ifa_tablets",
    label: "field.ifa",
    icon: Sparkles,
    render: (v, t) => (v ? t("common.yes") : t("common.no")),
  },
  { key: "td_vaccine", label: "field.tdVaccine", icon: Syringe, render: (v) => v },

  // Child & Newborn Health
  { key: "vaccine_name", label: "field.vaccine", icon: Syringe, render: (v) => v },
  { key: "temperature", label: "field.temperature", icon: Thermometer, render: (v) => `${v} °C` },
  { key: "height_cm", label: "field.height", icon: Scale, render: (v) => `${v} cm` },
  { key: "feeding", label: "field.feeding", icon: Sparkles, render: (v) => v },
  { key: "jaundice", label: "field.jaundice", icon: AlertTriangle, render: (v) => v },

  // Elderly & Nutrition
  { key: "blood_sugar", label: "field.bloodSugar", icon: HeartPulse, render: (v) => `${v} mg/dL` },
  { key: "mobility", label: "field.mobility", icon: Activity, render: (v) => v },

  // General & Dates
  { key: "visit_date", label: "field.visitDate", icon: CalendarDays, render: (v) => v },
  { key: "household_id", label: "field.household", icon: HomeIcon, render: (v) => v },

  // Household Hygiene
  { key: "water_source", label: "hh.waterSource", icon: Droplets, render: (v) => v },
  {
    key: "water_storage_covered",
    label: "hh.waterStorage",
    icon: Droplets,
    render: (v, t) => (v ? t("hh.covered") : t("hh.uncovered")),
  },
  {
    key: "toilet_available",
    label: "hh.toiletAvailable",
    icon: HomeIcon,
    render: (v, t) => (v ? t("common.yes") : t("common.no")),
  },
  {
    key: "toilet_usage",
    label: "hh.toiletUsage",
    icon: HomeIcon,
    render: (v, t) => (v === "used" ? t("hh.used") : t("hh.notUsed")),
  },
  { key: "waste_disposal", label: "hh.wasteDisposal", icon: Waves, render: (v) => v },
  { key: "drainage", label: "hh.drainage", icon: Waves, render: (v) => v },
  {
    key: "stagnant_water",
    label: "hh.stagnantWater",
    icon: Droplets,
    render: (v, t) => (v ? t("common.yes") : t("common.no")),
  },
  {
    key: "handwashing",
    label: "hh.handwashing",
    icon: Droplets,
    render: (v, t) => (v ? t("common.yes") : t("common.no")),
  },
  {
    key: "awareness_provided",
    label: "hh.awareness",
    icon: Sparkles,
    render: (v, t) => (v ? t("common.yes") : t("common.no")),
  },
  { key: "follow_up_days", label: "hh.followUpIn", icon: CalendarDays, render: (v) => v },
  { key: "follow_up_date", label: "field.followUpDate", icon: CalendarDays, render: (v) => v },
];

/* Structured preview sections grouping */
const SECTION_DEFS = [
  {
    id: "identity",
    titleKey: "sec.identity",
    fallback: "Beneficiary Identity",
    icon: User,
    keys: ["beneficiary_name", "category", "age", "gender", "relation", "village", "phone"],
  },
  {
    id: "maternal",
    titleKey: "sec.maternal",
    fallback: "Maternal Health",
    icon: CalendarHeart,
    keys: ["weeks_pregnant", "bp", "weight_kg", "hemoglobin", "ifa_tablets", "td_vaccine", "fetal_heart"],
  },
  {
    id: "child",
    titleKey: "sec.child",
    fallback: "Child & Newborn Health",
    icon: Syringe,
    keys: ["vaccine_name", "temperature", "height_cm", "feeding", "jaundice"],
  },
  {
    id: "measurements",
    titleKey: "sec.measurements",
    fallback: "Measurements & Nutrition",
    icon: Scale,
    keys: ["weight_kg", "height_cm", "hemoglobin", "blood_sugar"],
  },
  {
    id: "elderly",
    titleKey: "sec.elderly",
    fallback: "Elderly Health",
    icon: Activity,
    keys: ["age", "bp", "blood_sugar", "mobility"],
  },
  {
    id: "sanitation",
    titleKey: "sec.sanitation",
    fallback: "Household Sanitation",
    icon: HomeIcon,
    keys: [
      "household_id",
      "water_source",
      "water_storage_covered",
      "toilet_available",
      "toilet_usage",
      "waste_disposal",
      "drainage",
      "stagnant_water",
      "handwashing",
      "awareness_provided",
    ],
  },
  {
    id: "followup",
    titleKey: "sec.followup",
    fallback: "Follow-up Actions",
    icon: CalendarDays,
    keys: ["follow_up_days", "follow_up_date"],
  },
];

function fieldsOf(rec) {
  if (!rec) return [];
  return FIELD_DEFS.map((d) => {
    const value = d.from ? d.from(rec) : rec[d.key];
    return value === null || value === undefined || value === "" ? null : { ...d, value };
  }).filter(Boolean);
}

function isHouseholdRecord(r) {
  if (!r) return false;
  return (
    ["water_source", "water_storage_covered", "toilet_available", "waste_disposal", "drainage", "stagnant_water"].some(
      (k) => r[k] !== undefined
    ) || (!!r.household_id && !r.beneficiary_name)
  );
}

function fullSummary(r, fallbackName, t) {
  if (!r) return "";
  if (isHouseholdRecord(r)) {
    const parts = [];
    if (r.household_id) parts.push(`${t("field.household")}: ${r.household_id}.`);
    if (r.water_source) parts.push(`${t("hh.waterSource")}: ${r.water_source}.`);
    if (r.water_storage_covered !== undefined)
      parts.push(r.water_storage_covered ? t("hh.covered") + "." : t("hh.uncovered") + ".");
    if (r.toilet_available !== undefined)
      parts.push(r.toilet_available ? `${t("hh.toiletAvailable")}: ${t("common.yes")}.` : `${t("hh.toiletAvailable")}: ${t("common.no")}.`);
    if (r.waste_disposal) parts.push(`${t("hh.wasteDisposal")}: ${r.waste_disposal}.`);
    if (r.drainage) parts.push(`${t("hh.drainage")}: ${r.drainage}.`);
    if (r.stagnant_water !== undefined)
      parts.push(`${t("hh.stagnantWater")}: ${r.stagnant_water ? t("common.yes") : t("common.no")}.`);
    if (r.handwashing !== undefined)
      parts.push(`${t("hh.handwashing")}: ${r.handwashing ? t("common.yes") : t("common.no")}.`);
    if (r.awareness_provided) parts.push(`${t("hh.awareness")}: ${t("common.yes")}.`);
    if (r.follow_up_days) parts.push(`${t("hh.followUpIn")}: ${r.follow_up_days}.`);
    return parts.join(" ");
  }
  const name = r.beneficiary_name || fallbackName || t("vv.readbackFallback", "the beneficiary");
  const parts = [];
  if (r.age) parts.push(`Age ${r.age}.`);
  if (r.weeks_pregnant) parts.push(t("vv.rb.weeks", "{n} weeks pregnant.").replace("{n}", r.weeks_pregnant));
  if (r.bp_sys && r.bp_dia)
    parts.push(t("vv.rb.bp", "Blood pressure {s} over {d}.").replace("{s}", r.bp_sys).replace("{d}", r.bp_dia));
  if (r.weight_kg) parts.push(t("vv.rb.weight", "Weight {n} kilograms.").replace("{n}", r.weight_kg));
  if (r.temperature) parts.push(t("vv.rb.temp", "Temperature {n} degrees.").replace("{n}", r.temperature));
  if (r.vaccine_name) parts.push(t("vv.rb.vaccine", "Vaccine {n}.").replace("{n}", r.vaccine_name));
  if (r.blood_sugar) parts.push(`Blood sugar ${r.blood_sugar}.`);
  return t("vv.rb.visited", "Visited {name}.").replace("{name}", name) + " " + parts.join(" ");
}

/** Universal comparison: outputs explicit Old -> New comparison */
function changedSummary(merged, prev, keys, t) {
  const lines = [];
  const handled = new Set();

  (keys || []).forEach((k) => {
    if (handled.has(k) || !merged || merged[k] === undefined) return;
    const oldV = prev ? prev[k] : undefined;
    const newV = merged[k];

    if (k === "bp_sys" || k === "bp_dia") {
      handled.add("bp_sys");
      handled.add("bp_dia");
      const oldBp = prev && prev.bp_sys && prev.bp_dia ? `${prev.bp_sys}/${prev.bp_dia}` : null;
      const newBp = merged.bp_sys && merged.bp_dia ? `${merged.bp_sys}/${merged.bp_dia}` : `${merged.bp_sys || merged.bp_dia}`;
      if (oldBp && oldBp !== newBp) {
        lines.push(`${t("field.bp")}: ${oldBp} → ${newBp} (${t("vv.updated")}).`);
      } else {
        lines.push(`${t("field.bp")}: ${newBp} (${t("vv.updated")}).`);
      }
      return;
    }

    handled.add(k);
    const label = t(fieldLabelKey(k));
    const format = (v) => (typeof v === "boolean" ? (v ? t("common.yes") : t("common.no")) : String(v));

    if (oldV !== undefined && oldV !== newV) {
      lines.push(`${label}: ${format(oldV)} → ${format(newV)} (${t("vv.updated")}).`);
    } else {
      lines.push(`${label}: ${format(newV)} (${t("vv.updated")}).`);
    }
  });

  return lines.join(" ") || t("vv.noChanges", "No changes detected.");
}

function fieldLabelKey(key) {
  const def = FIELD_DEFS.find((d) => d.key === key);
  return def ? def.label : key;
}

function safeCategory(raw) {
  const c = String(raw || "").toLowerCase();
  const known = ["pregnancy", "newborn", "child", "immunisation", "elderly", "nutrition", "adolescent", "community", "general"];
  if (known.includes(c)) return c;
  if (/preg|anc|matern/i.test(c)) return "pregnancy";
  if (/newborn|neonat|infant/i.test(c)) return "newborn";
  if (/vaccin|immun/i.test(c)) return "immunisation";
  if (/child|toddler/i.test(c)) return "child";
  if (/elder|senior|old/i.test(c)) return "elderly";
  if (/nutri|anaem|breastfeed/i.test(c)) return "nutrition";
  if (/communit/i.test(c)) return "community";
  return "general";
}

const STATUS_KEYS = {
  ready: "vv.status.ready",
  listening: "vv.status.listening",
  processing: "vv.status.processing",
  speaking: "vv.status.speaking",
  confirm: "vv.status.confirm",
  saved: "vv.status.saved",
};

const STATUS_META = {
  ready: { key: "ready", icon: Mic, cls: "bg-white/10 text-white/80" },
  listening: { key: "listening", icon: Mic, cls: "bg-coral/20 text-coral" },
  processing: { key: "processing", icon: Loader2, cls: "bg-lavender/25 text-lavender" },
  speaking: { key: "speaking", icon: Volume2, cls: "bg-mint/20 text-mint" },
  confirm: { key: "confirm", icon: CheckCircle2, cls: "bg-mint/20 text-mint" },
  saved: { key: "saved", icon: BadgeCheck, cls: "bg-mint/25 text-mint" },
};

const HOW_IT_WORKS = [
  "vv.step1",
  "vv.step2",
  "vv.step3",
  "vv.step4",
  "vv.step5",
  "vv.step6",
  "vv.step7",
];

const BAR_MULTS = Array.from({ length: 22 }, (_, i) => 0.35 + 0.65 * Math.abs(Math.sin((i / 22) * Math.PI * 1.6)));

/* ================================= page ================================= */

export default function VoiceVisit() {
  const { user, mode } = useAuth();
  const navigate = useNavigate();
  const { t, lang } = useI18n();
  const [searchParams] = useSearchParams();

  /* ---------- setup state ---------- */
  const [language, setLanguage] = useState(lang || "en");
  const languageRef = useRef(language);
  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  const [target, setTarget] = useState(searchParams.get("household") ? "household" : "beneficiary");
  const [visitType, setVisitType] = useState("general");

  const [benList, setBenList] = useState([]);
  const benListRef = useRef([]);
  const [selectedBenId, setSelectedBenId] = useState(searchParams.get("beneficiary") || "");
  const [contextBen, setContextBen] = useState(null);
  const contextRef = useRef(null);
  useEffect(() => {
    contextRef.current = contextBen;
  }, [contextBen]);

  const [hhList, setHhList] = useState([]);
  const hhListRef = useRef([]);
  const [selectedHhId, setSelectedHhId] = useState(searchParams.get("household") || "");
  const selectedHhRef = useRef("");
  useEffect(() => {
    selectedHhRef.current = selectedHhId;
  }, [selectedHhId]);

  /* ---------- visit state ---------- */
  const [status, setStatus] = useState("ready");
  const [voiceProvider, setVoiceProvider] = useState("");
  const [partial, setPartial] = useState("");
  const [finalText, setFinalText] = useState("");
  const partialRef = useRef("");
  const finalRef = useRef("");
  const [record, setRecord] = useState(null);
  const recordRef = useRef(null);
  const [changedKeys, setChangedKeys] = useState([]);
  const [dangerFlags, setDangerFlags] = useState([]);
  const [taraLine, setTaraLine] = useState("");
  const [level, setLevel] = useState(0);
  const [micError, setMicError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savedResult, setSavedResult] = useState(null);
  const [registerCandidate, setRegisterCandidate] = useState(null);
  const [showHow, setShowHow] = useState(false);

  /* Multi-entity visit extraction state */
  const [multiVisits, setMultiVisits] = useState([]);
  const [scenarioType, setScenarioType] = useState("single_beneficiary");
  const [editingCardIdx, setEditingCardIdx] = useState(null);
  const [manualEditKey, setManualEditKey] = useState("");
  const [manualEditVal, setManualEditVal] = useState("");
  const [disambiguateCandidates, setDisambiguateCandidates] = useState(null);

  const sessionRef = useRef(null);
  const correctingRef = useRef(false);
  const [correcting, setCorrecting] = useState(false);

  /* ---------- data loads ---------- */
  useEffect(() => {
    let alive = true;
    api
      .get("/beneficiaries")
      .then((d) => {
        const list = d.beneficiaries || [];
        if (alive) {
          setBenList(list);
          benListRef.current = list;
        }
      })
      .catch(() => {});
    api
      .get("/households")
      .then((d) => {
        const list = d.households || [];
        if (alive) {
          setHhList(list);
          hhListRef.current = list;
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedBenId) {
      setContextBen(null);
      return;
    }
    let alive = true;
    api
      .get(`/beneficiaries/${selectedBenId}`)
      .then((d) => alive && setContextBen(d.beneficiary))
      .catch(() => alive && setContextBen(null));
    return () => {
      alive = false;
    };
  }, [selectedBenId]);

  useEffect(
    () => () => {
      try {
        sessionRef.current?.abort();
      } catch {}
      sessionRef.current = null;
    },
    []
  );

  /* ------------------------------ voice chain ------------------------------ */

  const stopAudioChain = useCallback(() => {
    try {
      sessionRef.current?.abort();
    } catch {}
    sessionRef.current = null;
    setLevel(0);
  }, []);

  const handleFinal = useCallback(
    async (text) => {
      const txt = (text || "").trim();
      finalRef.current = txt;
      setFinalText(txt);
      partialRef.current = "";
      setPartial("");
      stopAudioChain();
      if (!txt) {
        setStatus("ready");
        showToast(t("vv.noSpeech"), "info");
        return;
      }
      setStatus("processing");
      try {
        // Multi-entity extractor supporting Scenario A, B, C & voice corrections
        const res = await api.post("/voice/extract-multi", {
          transcript: txt,
          language: languageRef.current,
        });

        const visits = res.visits || [];
        const detectedScenario = res.scenario || "single_beneficiary";
        setScenarioType(detectedScenario);
        setDangerFlags(res.danger_flags || []);

        // Disambiguate names across the existing beneficiary list
        const processedVisits = visits.map((v) => {
          const rawName = v.beneficiary_name || "";
          const list = benListRef.current;
          const spoken = rawName.trim().toLowerCase();
          const matches = list.filter((b) => {
            const bn = (b.name || "").toLowerCase();
            return bn === spoken || bn.split(/\s+/)[0] === spoken || bn.startsWith(spoken + " ") || spoken.startsWith(bn + " ");
          });
          return {
            ...v,
            matchedBeneficiary: matches.length === 1 ? matches[0] : null,
            candidateMatches: matches.length > 1 ? matches : [],
            needsRegistration: matches.length === 0 && rawName.length > 1,
            raw_structured: v.raw_structured || {},
          };
        });

        if (processedVisits.length > 1) {
          // Multiple visits detected (Scenario B: Household members or Scenario C: Cross-household)
          setMultiVisits(processedVisits);
          setRecord(null);
          recordRef.current = null;

          const spokenCount = processedVisits.length;
          const readLine =
            detectedScenario === "household_members"
              ? `Extracted ${spokenCount} family members in ${res.household_id || "household"}. Review each visit.`
              : `Extracted ${spokenCount} beneficiary visits across field locations. Review and confirm.`;
          setTaraLine(readLine);
          setStatus("speaking");
          await speak(readLine, languageRef.current, mode);
          setStatus("confirm");
          return;
        }

        // Single beneficiary visit (Scenario A or single parsed entity)
        const singleVisit = processedVisits[0];
        const incoming = singleVisit ? singleVisit.raw_structured : {};
        Object.entries(res.structured || {}).forEach(([k, v]) => {
          if (v !== null && v !== undefined && v !== "") incoming[k] = v;
        });

        if (incoming.household_id && !selectedHhRef.current) {
          const key = String(incoming.household_id).toLowerCase();
          const match = hhListRef.current.find(
            (h) => (h.qr_id || "").toLowerCase() === key || String(h.id) === key
          );
          if (match) {
            setSelectedHhId(match.id);
            selectedHhRef.current = match.id;
          }
        }

        const keys = [];
        let merged;
        const prev = recordRef.current ? { ...recordRef.current } : null;
        if (correctingRef.current && recordRef.current) {
          merged = { ...recordRef.current };
          Object.entries(incoming).forEach(([k, v]) => {
            if (merged[k] !== v) keys.push(k);
            merged[k] = v;
          });
        } else {
          merged = incoming;
        }

        recordRef.current = merged;
        setRecord(merged);
        setChangedKeys(correctingRef.current ? (keys.length > 0 ? keys : Object.keys(incoming)) : []);

        const line = correctingRef.current
          ? `${changedSummary(merged, prev, keys.length > 0 ? keys : Object.keys(incoming), t)} ${t("vv.confirmQuestion")}`
          : fullSummary(merged, contextRef.current?.name, t);
        setTaraLine(line);
        setStatus("speaking");
        await speak(line, languageRef.current, mode);
        setStatus("confirm");
      } catch (e) {
        showToast(e.message || t("vv.analysisError"), "error");
        setStatus("ready");
      }
    },
    [mode, stopAudioChain, t]
  );

  const voiceErrorMessage = useCallback(
    (err) => {
      switch (err?.kind) {
        case VoiceErrorKind.MIC_PERMISSION_DENIED:
          return t("vv.errMicDenied", "Microphone permission was denied.");
        case VoiceErrorKind.MIC_NO_DEVICE:
          return t("vv.errMicMissing", "No microphone was found on this device.");
        case VoiceErrorKind.MIC_BUSY:
          return t("vv.errMicBusy", "The microphone is being used by another application.");
        case VoiceErrorKind.MIC_INSECURE_CONTEXT:
          return t("vv.errInsecure", "Microphone capture needs a secure (https) connection.");
        case VoiceErrorKind.SOCKET_FAILED:
          return t("vv.errSocket", "Could not reach the speech service.");
        case VoiceErrorKind.SOCKET_CLOSED:
          return t("vv.errSocketClosed", "The speech connection dropped while recording.");
        case VoiceErrorKind.STT_PROVIDER:
          return t("vv.errProvider", "The speech service could not produce a transcript.");
        case VoiceErrorKind.SPEECH_UNSUPPORTED:
          return t("vv.errSpeechUnsupported", "Speech recognition is not available in this browser.");
        case VoiceErrorKind.SPEECH_LANGUAGE_UNSUPPORTED:
          return t("vv.errSpeechLanguage", "This browser does not support speech recognition for the selected language.");
        case VoiceErrorKind.SPEECH_NETWORK:
          return t("vv.errSpeechNetwork", "Browser speech recognition could not reach its service.");
        case VoiceErrorKind.EMPTY_AUDIO:
          return t("vv.errEmptyAudio", "The microphone did not deliver any audio.");
        case VoiceErrorKind.TIMEOUT:
          return t("vv.errTimeout", "The recording took too long to process.");
        case VoiceErrorKind.NO_SPEECH:
          return t("vv.errNoSpeech", "No speech was detected.");
        default:
          return t("vv.micError");
      }
    },
    [t]
  );

  const startListening = useCallback(
    async (isCorrection = false) => {
      setMicError(null);
      setVoiceProvider("");
      setPartial("");
      partialRef.current = "";
      setRegisterCandidate(null);
      correctingRef.current = isCorrection;
      setCorrecting(isCorrection);
      setStatus("listening");

      const session = createVoiceSession({
        language: languageRef.current,
        preferBrowser: mode !== "live",
        onProvider: setVoiceProvider,
        onPartial: (text) => {
          partialRef.current = text || "";
          setPartial(text || "");
        },
        onStatus: (stage) => {
          if (stage === "listening") setStatus("listening");
          else if (stage === "processing") setStatus("processing");
          else if (stage === "finalizing") setStatus("processing");
        },
        onLevel: (lv) => setLevel(lv),
        onError: (err) => {
          sessionRef.current?.abort();
          sessionRef.current = null;
          setStatus("ready");
          setLevel(0);
          const msg = voiceErrorMessage(err);
          setMicError(msg);
          showToast(msg, "warn");
        },
        onLog: (e) => console.info("[voice]", e.event, e),
      });
      sessionRef.current = session;

      try {
        await session.start();
      } catch (e) {
        sessionRef.current = null;
        setStatus("ready");
        setLevel(0);
        const msg = voiceErrorMessage(e);
        setMicError(msg);
        showToast(msg, "warn");
      }
    },
    [mode, t, voiceErrorMessage]
  );

  const stopRecording = useCallback(async () => {
    const session = sessionRef.current;
    sessionRef.current = null;
    if (!session) {
      setStatus("ready");
      showToast(t("vv.nothingRecorded"), "info");
      return;
    }
    setStatus("processing");
    try {
      const { transcript } = await session.stop();
      if (!transcript || !transcript.trim()) {
        setStatus("ready");
        showToast(t("vv.errNoSpeech"), "warn");
        return;
      }
      await handleFinal(transcript);
    } catch (e) {
      setStatus("ready");
      setLevel(0);
      const msg = voiceErrorMessage(e);
      setMicError(msg);
      showToast(msg, "warn");
    }
  }, [handleFinal, t, voiceErrorMessage]);

  /* ------------------------------ save operations ------------------------------ */

  const doSaveBeneficiary = async (benId) => {
    const res = await api.post("/visits", {
      beneficiary_id: benId,
      structured: recordRef.current,
      transcript: finalRef.current,
      language: languageRef.current,
      visit_type: visitType !== "general" ? visitType : undefined,
    });
    setSavedResult({ ...res, beneficiary_id: benId });
    setStatus("saved");
  };

  const doSaveHousehold = async (hhId) => {
    const res = await api.post(`/households/${hhId}/visits`, {
      structured: recordRef.current,
      transcript: finalRef.current,
      language: languageRef.current,
    });
    setSavedResult({ ...res, household_id: hhId });
    setStatus("saved");
  };

  const confirmSaveSingle = async () => {
    const rec = recordRef.current;
    if (!rec || Object.keys(rec).length === 0) {
      showToast(t("vv.nothingToSave"), "warn");
      return;
    }
    setSaving(true);
    try {
      if (target === "household") {
        const hhId = selectedHhRef.current || contextRef.current?.household_id;
        if (!hhId) {
          showToast(t("vv.chooseHouseholdFirst"), "warn");
          setSaving(false);
          return;
        }
        await doSaveHousehold(hhId);
        return;
      }
      let benId = contextRef.current?.id || null;
      const name = rec.beneficiary_name || contextRef.current?.name || "";
      if (!benId) {
        let list = benListRef.current;
        if (!list.length) {
          const d = await api.get("/beneficiaries");
          list = d.beneficiaries || [];
          benListRef.current = list;
        }
        const spoken = name.trim().toLowerCase();
        const matches = list.filter((b) => {
          const bn = (b.name || "").toLowerCase();
          return bn === spoken || bn.split(/\s+/)[0] === spoken || bn.startsWith(spoken + " ") || spoken.startsWith(bn + " ");
        });

        if (matches.length === 1) {
          benId = matches[0].id;
        } else if (matches.length > 1) {
          setDisambiguateCandidates({ name, candidates: matches });
          setSaving(false);
          return;
        } else {
          setRegisterCandidate(name || t("vv.thisBeneficiary"));
          setSaving(false);
          return;
        }
      }
      await doSaveBeneficiary(benId);
    } catch (e) {
      showToast(e.message || t("vv.saveError"), "error");
    } finally {
      setSaving(false);
    }
  };

  /** Batch save for multi-visit recordings (Scenario B & C) */
  const confirmSaveBatch = async () => {
    if (!multiVisits.length) return;
    setSaving(true);
    try {
      const items = multiVisits.map((v) => ({
        beneficiary_id: v.matchedBeneficiary?.id || null,
        beneficiary_name: v.beneficiary_name || "",
        category: safeCategory(v.category),
        age: v.raw_structured?.age || v.age || null,
        gender: v.raw_structured?.gender || v.gender || null,
        create_if_missing: true,
        structured: v.raw_structured || {},
        transcript: finalRef.current,
        language: languageRef.current,
      }));

      const payload = {
        visits: items,
        household_visits: [],
      };

      const res = await api.post("/visits/batch", payload);
      setSavedResult({
        total_saved: res.total_saved,
        saved_visits: res.saved_visits,
        alerts: res.alerts || [],
      });
      setStatus("saved");
      setMultiVisits([]);
      showToast(`Saved ${res.total_saved} visits successfully!`, "success");
    } catch (e) {
      showToast(e.message || "Failed to save multi-visit batch", "error");
    } finally {
      setSaving(false);
    }
  };

  const registerAndSaveSingle = async () => {
    if (!registerCandidate) return;
    setSaving(true);
    try {
      const d = await api.post("/beneficiaries", {
        name: registerCandidate,
        category: safeCategory(recordRef.current?.category),
        age: recordRef.current?.age || undefined,
        gender: recordRef.current?.gender || undefined,
        village: user?.phc || undefined,
      });
      const b = d?.beneficiary || d?.beneficiaries?.[0] || d;
      if (!b?.id) throw new Error(t("vv.registerError", "Could not register the new beneficiary."));
      benListRef.current = [...benListRef.current, b];
      await doSaveBeneficiary(b.id);
      showToast(t("vv.registeredSaved", "{name}").replace("{name}", registerCandidate), "success");
    } catch (e) {
      showToast(e.message || t("vv.registerError"), "error");
    } finally {
      setSaving(false);
    }
  };

  const resetAll = () => {
    stopAudioChain();
    correctingRef.current = false;
    setCorrecting(false);
    setPartial("");
    partialRef.current = "";
    setFinalText("");
    finalRef.current = "";
    recordRef.current = null;
    setRecord(null);
    setMultiVisits([]);
    setChangedKeys([]);
    setDangerFlags([]);
    setTaraLine("");
    setSavedResult(null);
    setRegisterCandidate(null);
    setDisambiguateCandidates(null);
    setEditingCardIdx(null);
    setMicError(null);
    setStatus("ready");
  };

  const switchTarget = (next) => {
    if (next === target) return;
    resetAll();
    setTarget(next);
  };

  /* Manual field edit helpers */
  const handleAddManualField = (targetRec, updateFn) => {
    if (!manualEditKey.trim() || manualEditVal === "") return;
    const key = manualEditKey.trim();
    let val = manualEditVal;
    if (key === "weight_kg" || key === "height_cm" || key === "hemoglobin" || key === "blood_sugar" || key === "temperature") {
      val = parseFloat(val) || val;
    } else if (key === "age" || key === "weeks_pregnant") {
      val = parseInt(val, 10) || val;
    }
    updateFn({ ...targetRec, [key]: val });
    setManualEditKey("");
    setManualEditVal("");
  };

  const handleRemoveField = (k, targetRec, updateFn) => {
    const updated = { ...targetRec };
    delete updated[k];
    updateFn(updated);
  };

  /* -------------------------------- render -------------------------------- */

  const fields = fieldsOf(record);
  const sm = STATUS_META[status] || STATUS_META.ready;
  const StatusIcon = sm.icon;
  const listening = status === "listening";
  const isHhTarget = target === "household";
  const savedHouseholdId = savedResult?.household_id || savedResult?.visit?.household_id;

  return (
    <div className="space-y-5">
      {/* heading */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="flex flex-wrap items-center justify-between gap-3"
      >
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep sm:text-2xl">{t("nav.newVoiceVisit")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">{t("vv.subtitle")}</p>
        </div>
        {mode === "demo" && <span className="chip bg-lavender/20 text-midnight">{t("common.demoMode")}</span>}
      </motion.div>

      {/* ============================ studio panel ============================ */}
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.06, ease: "easeOut" }}
        className="overflow-hidden rounded-3xl bg-gradient-to-br from-teal-deep to-midnight p-5 text-white shadow-glass sm:p-7"
      >
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          {/* ------------------------------ left: interaction ------------------------------ */}
          <div className="flex min-w-0 flex-col items-center gap-6">
            {/* status pill + language */}
            <div className="flex w-full flex-wrap items-center justify-center gap-3">
              <span className={`chip px-3.5 py-1.5 ${sm.cls}`}>
                <StatusIcon size={13} className={status === "processing" ? "animate-spin" : listening ? "animate-pulse" : ""} />
                {t(STATUS_KEYS[sm.key])}
              </span>
              <label className="chip cursor-pointer gap-1.5 bg-white/10 text-white/80">
                <Languages size={13} />
                <select
                  value={language}
                  disabled={listening || status === "processing"}
                  onChange={(e) => setLanguage(e.target.value)}
                  aria-label={t("voice.spokenLanguage", "Spoken language")}
                  className="bg-transparent text-[0.72rem] font-bold text-white outline-none [&>option]:text-teal-deep"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.native}
                    </option>
                  ))}
                </select>
              </label>
              <span className="text-[0.68rem] font-semibold text-white/55" aria-live="polite">
                {voiceProvider || t("voice.providerOnRecord", "Speech provider selected on Record")}
              </span>
            </div>

            {/* target selector: beneficiary or household */}
            <div className="flex w-full flex-wrap items-center justify-center gap-2">
              <button
                onClick={() => switchTarget("beneficiary")}
                className={[
                  "chip px-3.5 py-1.5 transition-colors",
                  !isHhTarget ? "bg-mint text-teal-deep" : "bg-white/10 text-white/70 hover:bg-white/20",
                ].join(" ")}
              >
                <User size={13} /> {t("vv.target.beneficiary")}
              </button>
              <button
                onClick={() => switchTarget("household")}
                className={[
                  "chip px-3.5 py-1.5 transition-colors",
                  isHhTarget ? "bg-mint text-teal-deep" : "bg-white/10 text-white/70 hover:bg-white/20",
                ].join(" ")}
              >
                <HomeIcon size={13} /> {t("vv.target.household")}
              </button>
            </div>

            {/* context selector */}
            <div className="w-full">
              {isHhTarget ? (
                <select
                  value={selectedHhId}
                  onChange={(e) => setSelectedHhId(e.target.value)}
                  className="mx-auto block w-full max-w-xs rounded-2xl border border-white/15 bg-white/10 px-4 py-2.5 text-center text-sm font-semibold text-white outline-none [&>option]:text-teal-deep"
                >
                  <option value="">{t("vv.chooseHousehold")}</option>
                  {hhList.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.village} — {h.qr_id}
                    </option>
                  ))}
                </select>
              ) : contextBen ? (
                <div className="flex items-center justify-center gap-2.5">
                  <span className="chip max-w-full bg-mint/15 px-3.5 py-1.5 text-mint">
                    <User size={12} />
                    <span className="truncate">{contextBen.name}</span>
                  </span>
                  <button
                    onClick={() => setSelectedBenId("")}
                    aria-label={t("vv.clearBeneficiary")}
                    className="rounded-full bg-white/10 p-1.5 text-white/60 transition-colors hover:text-white"
                  >
                    <X size={13} />
                  </button>
                </div>
              ) : (
                <select
                  value={selectedBenId}
                  onChange={(e) => setSelectedBenId(e.target.value)}
                  className="mx-auto block w-full max-w-xs rounded-2xl border border-white/15 bg-white/10 px-4 py-2.5 text-center text-sm font-semibold text-white outline-none [&>option]:text-teal-deep"
                >
                  <option value="">{t("vv.extractName")}</option>
                  {benList.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} — {b.village || b.category}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* visit type (beneficiary visits only) */}
            {!isHhTarget && (
              <div className="flex w-full flex-wrap items-center justify-center gap-2">
                {[
                  { key: "general", icon: Waves },
                  { key: "nutrition", icon: HeartPulse },
                  { key: "community", icon: Activity },
                ].map(({ key, icon: Icon }) => (
                  <button
                    key={key}
                    onClick={() => setVisitType(key)}
                    className={[
                      "chip px-3.5 py-1.5 transition-colors",
                      visitType === key ? "bg-mint text-teal-deep" : "bg-white/10 text-white/70 hover:bg-white/20",
                    ].join(" ")}
                  >
                    <Icon size={13} /> {t(`vv.type.${key}`)}
                  </button>
                ))}
              </div>
            )}

            {/* mic button + rings + waveform */}
            <div className="relative flex flex-col items-center gap-5 py-2">
              <div className="relative flex items-center justify-center">
                {listening &&
                  [0, 1].map((i) => (
                    <motion.span
                      key={i}
                      animate={{ scale: [1, 1.9], opacity: [0.55, 0] }}
                      transition={{ duration: 1.8, repeat: Infinity, delay: i * 0.9, ease: "easeOut" }}
                      className="absolute h-24 w-24 rounded-full bg-coral"
                    />
                  ))}
                {!listening && status !== "ready" && (
                  <motion.span
                    animate={{ scale: [1, 1.5], opacity: [0.4, 0] }}
                    transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
                    className="absolute h-24 w-24 rounded-full bg-mint"
                  />
                )}
                <motion.button
                  whileTap={{ scale: 0.92 }}
                  onClick={() => (listening ? stopRecording() : startListening(status === "confirm"))}
                  aria-label={listening ? t("voice.stop") : t("voice.record")}
                  className={[
                    "relative z-10 flex h-24 w-24 items-center justify-center rounded-full transition-colors duration-300 sm:h-28 sm:w-28",
                    listening
                      ? "bg-coral text-white shadow-[0_0_44px_rgba(255,128,111,0.55)]"
                      : "btn-mint shadow-[0_0_40px_rgba(240,120,173,0.5)]",
                  ].join(" ")}
                >
                  {listening ? <Square size={30} strokeWidth={2.4} /> : <Mic size={34} strokeWidth={2.2} />}
                </motion.button>
              </div>

              {/* live waveform */}
              <div className="flex h-10 w-full max-w-xs items-center justify-center gap-1">
                {BAR_MULTS.map((m, i) => (
                  <div
                    key={i}
                    className="w-1.5 rounded-full transition-[height] duration-100"
                    style={{
                      height: `${listening ? Math.max(10, Math.min(100, level * m * 260 + 10)) : 14}%`,
                      background: listening ? "rgba(255,128,111,0.85)" : "rgba(240,120,173,0.35)",
                    }}
                  />
                ))}
              </div>

              <p className="text-center text-xs font-semibold text-white/55">
                {listening
                  ? t("vv.hint.listening")
                  : status === "confirm"
                  ? t("vv.hint.confirm")
                  : t("vv.hint.tap")}
              </p>
            </div>

            {/* mic permission error */}
            {micError && (
              <div className="w-full rounded-2xl border border-coral/40 bg-coral/10 px-4 py-3.5">
                <p className="flex items-start gap-2 text-xs font-semibold leading-relaxed text-coral">
                  <CircleAlert size={15} className="mt-0.5 shrink-0" />
                  {micError}
                </p>
              </div>
            )}

            {/* transcript panel */}
            {(partial || finalText) && (
              <div className="w-full rounded-2xl border border-white/10 bg-white/5 px-5 py-4">
                <p className="mb-2 text-[0.65rem] font-extrabold uppercase tracking-[0.18em] text-mint/80">
                  {t("voice.transcript")}
                </p>
                {partial && (
                  <p className={`text-sm italic leading-relaxed text-white/50 ${finalText ? "opacity-40" : ""}`}>
                    {partial}
                  </p>
                )}
                {finalText && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-sm font-semibold leading-relaxed text-white"
                  >
                    {finalText}
                  </motion.p>
                )}
              </div>
            )}

            {/* Tara read-back bubble */}
            <AnimatePresence>
              {taraLine && (status === "speaking" || status === "confirm" || status === "saved") && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="w-full rounded-2xl border border-mint/25 bg-mint/10 px-5 py-4"
                >
                  <p className="mb-1.5 flex items-center gap-1.5 text-[0.65rem] font-extrabold uppercase tracking-[0.18em] text-mint">
                    <Sparkles size={12} /> {t("vv.taraSays")}
                  </p>
                  <p className="text-sm font-semibold leading-relaxed text-white/90">{taraLine}</p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* danger banner */}
            {dangerFlags.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="w-full rounded-2xl border border-coral/50 bg-coral/15 px-5 py-4"
              >
                {dangerFlags.map((f, i) => (
                  <p key={i} className={`flex items-start gap-2 text-sm font-bold text-coral ${i > 0 ? "mt-2" : ""}`}>
                    <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                    {t("vv.dangerSign")} "{f.phrase}" — {t("alerts.refer")}
                  </p>
                ))}
              </motion.div>
            )}

            {/* disambiguation panel if multiple candidates match */}
            {disambiguateCandidates && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="w-full rounded-2xl border border-amber-400/40 bg-amber-400/10 p-4 text-white"
              >
                <p className="text-sm font-bold text-amber-200">
                  Multiple beneficiaries named "{disambiguateCandidates.name}". Select the correct person:
                </p>
                <div className="mt-3 space-y-2">
                  {disambiguateCandidates.candidates.map((cand) => (
                    <button
                      key={cand.id}
                      onClick={() => {
                        setSelectedBenId(cand.id);
                        setContextBen(cand);
                        setDisambiguateCandidates(null);
                        doSaveBeneficiary(cand.id);
                      }}
                      className="flex w-full items-center justify-between rounded-xl bg-white/10 px-4 py-2.5 text-xs font-semibold hover:bg-white/20"
                    >
                      <span>
                        {cand.name} (Age: {cand.age || "—"}, {cand.village || cand.category})
                      </span>
                      <Check size={14} className="text-mint" />
                    </button>
                  ))}
                  <button
                    onClick={() => {
                      const name = disambiguateCandidates.name;
                      setDisambiguateCandidates(null);
                      setRegisterCandidate(name);
                    }}
                    className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-white/20 px-3 py-2 text-xs font-bold text-mint hover:bg-white/10"
                  >
                    <Plus size={13} /> Register as a New Person
                  </button>
                </div>
              </motion.div>
            )}

            {/* confirm actions for single record */}
            <AnimatePresence>
              {status === "confirm" && !multiVisits.length && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex w-full flex-col gap-2.5 sm:flex-row"
                >
                  <button
                    onClick={confirmSaveSingle}
                    disabled={saving}
                    className="btn-mint flex flex-1 items-center justify-center gap-2 px-5 py-3 text-sm disabled:opacity-60"
                  >
                    {saving ? <Loader2 size={16} className="animate-spin" /> : <BadgeCheck size={16} strokeWidth={2.4} />}
                    {saving ? t("vv.saving") : t("voice.confirmSave")}
                  </button>
                  <button
                    onClick={() => startListening(true)}
                    className="flex flex-1 items-center justify-center gap-2 rounded-full border border-white/25 px-5 py-3 text-sm font-bold text-white transition-colors hover:bg-white/10"
                  >
                    <Mic size={16} strokeWidth={2.4} /> {t("voice.correctField")}
                  </button>
                  <button
                    onClick={resetAll}
                    className="flex items-center justify-center gap-2 rounded-full px-4 py-3 text-sm font-bold text-white/50 transition-colors hover:text-white"
                  >
                    <RotateCcw size={15} /> {t("voice.discard")}
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* register-new inline action */}
            <AnimatePresence>
              {registerCandidate && status !== "saved" && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="w-full rounded-2xl border border-lavender/40 bg-lavender/10 px-5 py-4 text-center"
                >
                  <p className="text-sm font-semibold text-white/85">
                    {t("vv.registerCandidate", "“{name}”").replace("{name}", registerCandidate)}
                  </p>
                  <button
                    onClick={registerAndSaveSingle}
                    disabled={saving}
                    className="btn-mint mt-3 flex w-full items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60"
                  >
                    {saving ? <Loader2 size={15} className="animate-spin" /> : <UserPlus size={15} strokeWidth={2.4} />}
                    {t("vv.registerAndSave").replace("{name}", registerCandidate)}
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* success panel */}
            <AnimatePresence>
              {status === "saved" && savedResult && (
                <motion.div
                  initial={{ opacity: 0, y: 16, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ type: "spring", damping: 20 }}
                  className="w-full rounded-2xl bg-white p-5 text-teal-deep shadow-card"
                >
                  <p className="flex items-center gap-2 text-sm font-extrabold text-teal-deep">
                    <CheckCircle2 size={18} className="text-mint" strokeWidth={2.4} />
                    {savedResult.total_saved ? `Saved ${savedResult.total_saved} Visits!` : t("voice.saved")}
                  </p>
                  {fields.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {fields.map((f) => (
                        <span key={f.key} className="chip bg-ivory/90 text-teal-deep/70">
                          {t(f.label)}: {String(f.value)}
                        </span>
                      ))}
                    </div>
                  )}
                  {(savedResult.alerts || []).length > 0 && (
                    <div className="mt-3 rounded-xl bg-coral/10 px-3.5 py-3">
                      {savedResult.alerts.map((a, i) => (
                        <p key={i} className="flex items-start gap-2 text-xs font-bold text-coral">
                          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                          "{a.phrase}" — {a.message || t("alerts.refer")}
                        </p>
                      ))}
                    </div>
                  )}
                  {savedResult.follow_up?.due_date && (
                    <p className="mt-3 text-xs font-semibold text-teal-deep/60">
                      {t("households.nextFollowup")}:{" "}
                      <span className="font-extrabold text-teal-deep">{savedResult.follow_up.due_date}</span>
                    </p>
                  )}
                  <div className="mt-4 flex flex-col gap-2.5 sm:flex-row">
                    <button
                      onClick={() =>
                        navigate(
                          isHhTarget && savedHouseholdId
                            ? `/app/households/${savedHouseholdId}`
                            : savedResult.beneficiary_id
                            ? `/app/beneficiaries/${savedResult.beneficiary_id}`
                            : `/app/visits`
                        )
                      }
                      className="flex flex-1 items-center justify-center gap-2 rounded-full bg-teal-deep px-4 py-2.5 text-sm font-bold text-mint transition-transform hover:-translate-y-0.5"
                    >
                      {isHhTarget && savedHouseholdId ? (
                        <>
                          <HomeIcon size={15} strokeWidth={2.4} /> {t("households.timeline")}
                        </>
                      ) : (
                        <>
                          <Waves size={15} strokeWidth={2.4} /> {t("vv.openPulseThread")}
                        </>
                      )}
                    </button>
                    <button
                      onClick={resetAll}
                      className="flex flex-1 items-center justify-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/70 transition-colors hover:bg-teal-deep/10"
                    >
                      <Mic size={15} strokeWidth={2.4} /> {t("vv.recordAnother")}
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* ------------------------------ right: structured preview & multi-visit cards ------------------------------ */}
          <div className="min-w-0">
            {multiVisits.length > 0 ? (
              /* Multi-Visit Review & Card Deck */
              <div className="space-y-4">
                <div className="flex items-center justify-between rounded-2xl bg-white/10 p-3 text-white">
                  <div className="flex items-center gap-2">
                    <Users size={16} className="text-mint" />
                    <div>
                      <p className="text-xs font-extrabold">
                        {scenarioType === "household_members"
                          ? `Household Members (${multiVisits.length})`
                          : `Multiple Beneficiaries (${multiVisits.length})`}
                      </p>
                      <p className="text-[0.65rem] text-white/60">Independent records extracted in one session</p>
                    </div>
                  </div>
                  <button
                    onClick={confirmSaveBatch}
                    disabled={saving}
                    className="btn-mint flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold"
                  >
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <BadgeCheck size={14} />}
                    Confirm All ({multiVisits.length})
                  </button>
                </div>

                <div className="space-y-3 max-h-[580px] overflow-y-auto pr-1">
                  {multiVisits.map((v, idx) => {
                    const isEditing = editingCardIdx === idx;
                    const cardRec = v.raw_structured || {};
                    const cardFields = fieldsOf(cardRec);

                    return (
                      <motion.div
                        key={v.visit_id || idx}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="rounded-2xl bg-white p-4 text-teal-deep shadow-soft"
                      >
                        <div className="flex items-start justify-between gap-2 border-b border-teal-deep/10 pb-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-extrabold text-teal-deep">{v.beneficiary_name}</span>
                              <span className="chip bg-mint/20 text-[0.65rem] font-bold text-teal-deep">
                                {v.category || "general"}
                              </span>
                            </div>
                            <p className="mt-0.5 text-[0.68rem] text-teal-deep/55">
                              {v.relation ? `Relation: ${v.relation} · ` : ""}
                              {v.gender ? `Gender: ${v.gender} · ` : ""}
                              {v.household_id ? `Household: ${v.household_id}` : ""}
                            </p>
                          </div>

                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => setEditingCardIdx(isEditing ? null : idx)}
                              className="rounded-lg p-1.5 text-teal-deep/50 hover:bg-teal-deep/5 hover:text-teal-deep"
                              title="Edit fields"
                            >
                              <Edit3 size={13} />
                            </button>
                            <button
                              onClick={() => {
                                const next = multiVisits.filter((_, i) => i !== idx);
                                setMultiVisits(next);
                                if (next.length === 0) resetAll();
                              }}
                              className="rounded-lg p-1.5 text-coral/70 hover:bg-coral/10 hover:text-coral"
                              title="Discard this visit"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>

                        {/* Card observations */}
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {cardFields.map((f) => (
                            <span key={f.key} className="chip bg-ivory/90 text-[0.68rem] font-semibold text-teal-deep/80">
                              {t(f.label)}: {f.render ? f.render(f.value, t) : String(f.value)}
                            </span>
                          ))}
                        </div>

                        {/* Inline card field editor */}
                        {isEditing && (
                          <div className="mt-3 rounded-xl bg-ivory/60 p-2.5">
                            <p className="text-[0.65rem] font-bold uppercase tracking-wider text-teal-deep/60">
                              Manual Quick Edit
                            </p>
                            <div className="mt-2 flex gap-2">
                              <input
                                type="text"
                                placeholder="Field name (e.g. weight_kg)"
                                value={manualEditKey}
                                onChange={(e) => setManualEditKey(e.target.value)}
                                className="w-1/2 rounded-lg border border-teal-deep/15 bg-white px-2 py-1 text-xs"
                              />
                              <input
                                type="text"
                                placeholder="New value"
                                value={manualEditVal}
                                onChange={(e) => setManualEditVal(e.target.value)}
                                className="w-1/2 rounded-lg border border-teal-deep/15 bg-white px-2 py-1 text-xs"
                              />
                              <button
                                onClick={() =>
                                  handleAddManualField(cardRec, (updated) => {
                                    const next = [...multiVisits];
                                    next[idx].raw_structured = updated;
                                    setMultiVisits(next);
                                  })
                                }
                                className="rounded-lg bg-teal-deep px-3 py-1 text-xs font-bold text-mint"
                              >
                                Save
                              </button>
                            </div>
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Single Visit Structured Preview by Clinical Sections */
              <div className="card-ivory p-5">
                <div className="mb-4 flex items-center justify-between">
                  <p className="text-sm font-extrabold text-teal-deep">{t("vv.structuredRecord")}</p>
                  <span className="chip bg-mint/15 text-pink">
                    <Sparkles size={11} /> {t("vv.livePreview")}
                  </span>
                </div>

                {fields.length === 0 ? (
                  <div className="rounded-2xl bg-ivory/80 px-4 py-8 text-center">
                    <Waves size={26} className="mx-auto mb-2 text-teal-deep/25" />
                    <p className="text-xs font-semibold leading-relaxed text-teal-deep/45">
                      {correcting ? t("vv.previewHintCorrection") : t("vv.previewHint")}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4 max-h-[580px] overflow-y-auto pr-1">
                    {SECTION_DEFS.map((sec) => {
                      const secFields = fields.filter((f) => sec.keys.includes(f.key));
                      if (secFields.length === 0) return null;
                      const SecIcon = sec.icon;

                      return (
                        <div key={sec.id} className="rounded-2xl bg-white/70 p-3 shadow-soft">
                          <div className="mb-2.5 flex items-center gap-1.5 border-b border-teal-deep/10 pb-1.5">
                            <SecIcon size={13} className="text-teal-deep/70" />
                            <span className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/60">
                              {t(sec.titleKey, sec.fallback)}
                            </span>
                          </div>

                          <div className="space-y-1.5">
                            {secFields.map((f) => {
                              const Icon = f.icon;
                              const isChanged =
                                changedKeys.includes(f.key) ||
                                (f.key === "bp" && (changedKeys.includes("bp_sys") || changedKeys.includes("bp_dia")));
                              return (
                                <div
                                  key={f.key}
                                  className={[
                                    "flex items-center justify-between rounded-xl px-2.5 py-1.5 text-xs transition-colors",
                                    isChanged ? "bg-mint-soft ring-1 ring-mint/40" : "bg-ivory/80",
                                  ].join(" ")}
                                >
                                  <div className="flex items-center gap-2">
                                    <Icon size={12} className="text-teal-deep/60" />
                                    <span className="text-[0.68rem] font-semibold text-teal-deep/60">{t(f.label)}:</span>
                                    <span className="font-extrabold text-teal-deep">
                                      {f.render ? f.render(f.value, t) : String(f.value)}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    {isChanged && (
                                      <span className="chip bg-mint text-[0.55rem] text-teal-deep">{t("vv.updated")}</span>
                                    )}
                                    <button
                                      onClick={() => handleRemoveField(f.key, record, (up) => setRecord(up))}
                                      className="text-teal-deep/30 hover:text-coral"
                                    >
                                      <X size={11} />
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}

                    {/* Manual field addition panel */}
                    <div className="rounded-2xl bg-ivory/90 p-3">
                      <p className="text-[0.65rem] font-bold uppercase tracking-wider text-teal-deep/60">
                        Add Field Manually
                      </p>
                      <div className="mt-2 flex gap-2">
                        <select
                          value={manualEditKey}
                          onChange={(e) => setManualEditKey(e.target.value)}
                          className="w-1/2 rounded-lg border border-teal-deep/15 bg-white px-2 py-1.5 text-xs font-semibold text-teal-deep outline-none"
                        >
                          <option value="">Select Field...</option>
                          {FIELD_DEFS.map((f) => (
                            <option key={f.key} value={f.key}>
                              {t(f.label)}
                            </option>
                          ))}
                        </select>
                        <input
                          type="text"
                          placeholder="Value..."
                          value={manualEditVal}
                          onChange={(e) => setManualEditVal(e.target.value)}
                          className="w-1/2 rounded-lg border border-teal-deep/15 bg-white px-2 py-1.5 text-xs text-teal-deep outline-none"
                        />
                        <button
                          onClick={() => handleAddManualField(record, (up) => setRecord(up))}
                          className="rounded-lg bg-teal-deep px-3 py-1.5 text-xs font-bold text-mint"
                        >
                          <Plus size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* ------------------------------ how it works strip ------------------------------ */}
      <div className="card-ivory overflow-hidden">
        <button
          onClick={() => setShowHow((s) => !s)}
          className="flex w-full items-center justify-between px-5 py-4 text-left"
        >
          <p className="flex items-center gap-2.5 text-sm font-extrabold text-teal-deep">
            <Sparkles size={15} className="text-mint" strokeWidth={2.4} /> {t("vv.howItWorks")}
          </p>
          {showHow ? <ChevronUp size={16} className="text-teal-deep/40" /> : <ChevronDown size={16} className="text-teal-deep/40" />}
        </button>
        <AnimatePresence>
          {showHow && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="overflow-hidden"
            >
              <div className="flex flex-wrap gap-2 px-5 pb-5">
                {HOW_IT_WORKS.map((key, i) => (
                  <span key={key} className="chip bg-ivory/90 text-teal-deep/70">
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-teal-deep text-[0.55rem] font-extrabold text-mint">
                      {i + 1}
                    </span>
                    {t(key)}
                  </span>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* honest labelling footer */}
      <p className="text-center text-[0.68rem] font-semibold tracking-wide text-teal-deep/40">
        STT: Gnani Prisma · TTS: Gnani Timbre · mode: {mode}
      </p>
    </div>
  );
}
