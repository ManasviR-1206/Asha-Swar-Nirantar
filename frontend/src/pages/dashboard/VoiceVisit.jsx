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
import { api, speak, stopSpeaking, retryPendingPlayback, pauseSpeaking, resumeSpeaking, getPlaybackState, LANGUAGES } from "../../lib/api.js";
import { createVoiceSession, VoiceError, VoiceErrorKind } from "../../lib/voice.js";
import { formatTaraHeardTranscript, mergeExtractedRecord, selectBeneficiaryName } from "../../lib/beneficiaryName.js";
import { useAuth } from "../../lib/auth.jsx";
import { showToast } from "../../components/ui/Toast.jsx";
import { IdentityBadge } from "../../components/dashboard/Identity.jsx";
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
    render: (v) => `${v} mmHg`,
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
  { key: "td_vaccine", label: "field.tdVaccine", icon: Syringe, render: (v) => v ? `TT/TD ${String(v).replace(/^TT|^TD/i, "")}`.replace(/TT\/TD\s*$/, String(v)) : v },

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
  { key: "follow_up_days", label: "hh.followUpIn", icon: CalendarDays, render: (v) => `${v} days` },
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
    keys: ["vaccine_name", "temperature", "feeding", "jaundice"],
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
    keys: ["bp", "blood_sugar", "mobility"],
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

function parseVoiceCorrections(text) {
  const t = (text || "").trim();
  const lower = t.toLower();
  const corrections = [];
  const push = (field, value, label) => corrections.push({ field, value, label });

  // Age: "age is 37", "her age is 37 now", "age 37 years"
  const age = lower.match(/\b(?:age|umar)\s*(?:is|to|should be|=|:)?\s*(\d{1,3})\b/) || lower.match(/\b(\d{1,3})\s*(?:years old|yrs old|year old)\b/);
  if (age && /\b(age|years old|yrs old|year old|umar)\b/.test(lower)) push("age", parseInt(age[1], 10), "Age");

  // BP: "bp 130/85", "130 over 85"
  const bp = lower.match(/\b(?:bp|blood pressure)\s*(?:is|to|should be|=|:)?\s*(\d{2,3})\s*(?:\/|over|upon)\s*(\d{2,3})\b/) || lower.match(/\b(\d{2,3})\s*(?:\/|over|upon)\s*(\d{2,3})\b/);
  if (bp && (/\b(bp|blood pressure|over)\b/.test(lower) || /\/\d{2,3}/.test(lower))) {
    push("bp_sys", parseInt(bp[1], 10), "BP systolic");
    push("bp_dia", parseInt(bp[2], 10), "BP diastolic");
  }

  // Weight
  const wt = lower.match(/\b(?:weight)\s*(?:is|to|should be|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:kg|kilo|kilogram)?\b/);
  if (wt) push("weight_kg", parseFloat(wt[1]), "Weight");

  // Height
  const ht = lower.match(/\b(?:height)\s*(?:is|to|should be|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:cm)?\b/);
  if (ht) push("height_cm", parseFloat(ht[1]), "Height");

  // Temperature
  const temp = lower.match(/\b(?:temp|temperature|fever)\s*(?:is|to|should be|=|:)?\s*(\d+(?:\.\d+)?)\b/);
  if (temp) push("temperature", parseFloat(temp[1]), "Temperature");

  // Visit date
  const vd = lower.match(/\b(?:next visit|visit date|follow up|follow-up)\s*(?:is|to|on|should be)?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\b/);
  if (vd) push("follow_up_date", vd[1], "Follow-up date");

  // Cancel visit
  if (/\b(cancel this visit|discard this visit|delete this visit)\b/.test(lower)) push("__cancel_visit__", true, "Cancel visit");

  // de-dup by field, keep last
  const byField = new Map();
  for (const c of corrections) byField.set(c.field, c);
  return Array.from(byField.values());
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
  const selectedBenIdRef = useRef(searchParams.get("beneficiary") || "");
  useEffect(() => { selectedBenIdRef.current = selectedBenId; }, [selectedBenId]);
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
  const [benSearch, setBenSearch] = useState("");
  const [hhSearch, setHhSearch] = useState("");
  const [benConfirmed, setBenConfirmed] = useState(false);
  const [hhConfirmed, setHhConfirmed] = useState(false);
  const benConfirmedRef = useRef(false);
  const hhConfirmedRef = useRef(false);
  useEffect(() => { setBenConfirmed(false); benConfirmedRef.current = false; }, [selectedBenId]);
  useEffect(() => { setHhConfirmed(false); hhConfirmedRef.current = false; }, [selectedHhId]);
  useEffect(() => { benConfirmedRef.current = benConfirmed; }, [benConfirmed]);
  useEffect(() => { hhConfirmedRef.current = hhConfirmed; }, [hhConfirmed]);

  /* ---------- visit state ---------- */
  const [status, setStatus] = useState("ready");
  const statusRef = useRef("ready");
  statusRef.current = status;
  const [voiceProvider, setVoiceProvider] = useState("");
  const [partial, setPartial] = useState("");
  const [finalText, setFinalText] = useState("");
  const partialRef = useRef("");
  const finalRef = useRef("");
  const speechEndRef = useRef(null);
  const [record, setRecord] = useState(null);
  const recordRef = useRef(null);
  const [changedKeys, setChangedKeys] = useState([]);
  const [dangerFlags, setDangerFlags] = useState([]);
  const [taraLine, setTaraLine] = useState("");
  const [ttfaMs, setTtfaMs] = useState(null);
  const [playbackError, setPlaybackError] = useState("");
  const [autoplayBlocked, setAutoplayBlocked] = useState(false);
  const [playbackStatus, setPlaybackStatus] = useState("idle"); // idle|preparing|speaking|paused|completed|failed|blocked
  const [playbackProvider, setPlaybackProvider] = useState("");
  const lastSpokenRef = useRef("");
  const [ttfaHistory, setTtfaHistory] = useState([]);
  const [correctionHistory, setCorrectionHistory] = useState([]);
  const [level, setLevel] = useState(0);
  const [micError, setMicError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savedResult, setSavedResult] = useState(null);
  const [registerCandidate, setRegisterCandidate] = useState(null);
  const [showHow, setShowHow] = useState(false);
  const [showManualLink, setShowManualLink] = useState(false);

  /* Multi-entity visit extraction state */
  const [multiVisits, setMultiVisits] = useState([]);
  const [sessionMeta, setSessionMeta] = useState(null);
  const multiVisitsRef = useRef([]);
  const sessionMetaRef = useRef(null);
  multiVisitsRef.current = multiVisits;
  sessionMetaRef.current = sessionMeta;
  const sessionIdRef = useRef(null);
  const extractAbortRef = useRef(null);
  const [scenarioType, setScenarioType] = useState("single_beneficiary");
  const [editingCardIdx, setEditingCardIdx] = useState(null);
  const [manualEditKey, setManualEditKey] = useState("");
  const [manualEditVal, setManualEditVal] = useState("");
  const [disambiguateCandidates, setDisambiguateCandidates] = useState(null);
  const [singleIdentity, setSingleIdentity] = useState(null); // {status, matchedBeneficiary, candidates, reason, spokenName}
  const singleIdentityRef = useRef(null);
  useEffect(() => { singleIdentityRef.current = singleIdentity; }, [singleIdentity]);
  const [editingTranscript, setEditingTranscript] = useState(false);
  const [transcriptDraft, setTranscriptDraft] = useState("");

  const sessionRef = useRef(null);
  const confirmSaveSingleRef = useRef(null);
  const confirmSaveBatchRef = useRef(null);
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
      stopSpeaking();
    } catch {}
    try {
      sessionRef.current?.abort();
    } catch {}
    sessionRef.current = null;
    setLevel(0);
    setPlaybackStatus("idle");
  }, []);

  const reportTtfa = useCallback((ms) => {
    if (!Number.isFinite(ms) || ms < 0) return;
    setTtfaMs(ms);
    setTtfaHistory((prev) => {
      const next = [...prev, ms].slice(-20);
      return next;
    });
  }, []);

  const speakWithMetrics = useCallback(async (text) => {
    const speechEnd = speechEndRef.current;
    const clean = String(text || "").trim();
    lastSpokenRef.current = clean;
    setPlaybackError("");
    setAutoplayBlocked(false);
    setPlaybackStatus("preparing");
    setPlaybackProvider("");
    const result = await speak(clean, languageRef.current, mode, {
      onFirstAudio: () => {
        setPlaybackStatus("speaking");
        const ms = speechEnd ? Math.max(0, Math.round(performance.now() - speechEnd)) : null;
        if (ms != null) reportTtfa(ms);
      },
    });
    if (result?.provider) setPlaybackProvider(result.provider);
    if (result?.autoplayBlocked) {
      setAutoplayBlocked(true);
      setPlaybackStatus("blocked");
      setPlaybackError(t("vv.tapToHear", "Browser blocked autoplay. Tap to hear Tara."));
    } else if (result?.error || result?.unsupported) {
      setPlaybackStatus("failed");
      setPlaybackError(t("vv.playbackFailed", "Tara audio could not be played. You can replay or continue with the on-screen text."));
    } else if (result?.interrupted) {
      setPlaybackStatus("idle");
    } else if (result?.ended) {
      setPlaybackStatus("completed");
    } else {
      setPlaybackStatus(getPlaybackState() === "speaking" ? "speaking" : "idle");
    }
    return result;
  }, [mode, reportTtfa, t]);

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

      const lowerTxt = txt.toLowerCase().replace(/[.!?,]/g, " ").replace(/\s+/g, " ").trim();
      const isConfirmState = statusRef.current === "confirm";
      const looksLikeCorrection = /\b(no|not|wrong|change|correct|update|make it|should be|instead|actually)\b/.test(lowerTxt) && /\d|age|bp|weight|height|temp|date|name|vaccine|phone|visit/.test(lowerTxt);
      const isCancelIntent = !looksLikeCorrection && /\b(cancel|discard|delete|stop|don't save|do not save|mat karo|radd karo)\b/.test(lowerTxt);
      const isConfirmIntent = !looksLikeCorrection && /\b(yes save|yes, save|save it|save this|confirm|confirmed|haan save|ha save|theek hai save|ok save|okay save)\b/.test(lowerTxt);
      if (isConfirmState && isCancelIntent) {
        setTaraLine("Visit discarded. Nothing was saved.");
        resetAll();
        return;
      }
      if (isConfirmState && isConfirmIntent) {
        setStatus("processing");
        const voiceConfirmation = { confirmed: true, method: "voice", phrase: txt, confirmed_at: new Date().toISOString() };
        if ((multiVisitsRef.current?.length || 0) > 0 && sessionMetaRef.current?.id) {
          await confirmSaveBatchRef.current?.(voiceConfirmation);
        } else {
          await confirmSaveSingleRef.current?.(voiceConfirmation);
        }
        return;
      }

      if (isConfirmState && looksLikeCorrection && recordRef.current && !multiVisitsRef.current?.length) {
        const parsed = parseVoiceCorrections(txt);
        const cancel = parsed.find((c) => c.field === "__cancel_visit__");
        if (cancel) {
          setTaraLine("Visit discarded. Nothing was saved.");
          resetAll();
          return;
        }
        if (parsed.length > 0) {
          const prev = { ...recordRef.current };
          const next = { ...recordRef.current };
          const changed = [];
          for (const c of parsed) {
            if (c.field === "__cancel_visit__") continue;
            const oldVal = prev[c.field];
            if (oldVal !== c.value) changed.push({ field: c.field, label: c.label, old_value: oldVal, new_value: c.value, source: "voice_correction", transcript: txt, at: new Date().toISOString() });
            next[c.field] = c.value;
          }
          recordRef.current = next;
          setRecord(next);
          setChangedKeys(changed.map((c) => c.field));
          if (changed.length > 0) setCorrectionHistory((h) => [...h, ...changed]);
          const readback = changed.length
            ? formatTaraHeardTranscript(txt)
            : `I heard: ${txt.trim()}. I could not identify a supported field to update. Please say, for example, age is 37 or BP is 130 over 85.`;
          setTaraLine(readback);
          setStatus("speaking");
          speechEndRef.current = performance.now();
          await speakWithMetrics(readback);
          setStatus("confirm");
          return;
        }
      }

      const geoIntent = /\b(map|geopulse|show households|show village|pending visits|upcoming follow|maternal care|newborn care|referral|danger alert households)\b/.test(lowerTxt);
      if (geoIntent && /\b(show|open|map|where|which households|geopulse)\b/.test(lowerTxt)) {
        let f = "all";
        if (/pending visit/.test(lowerTxt)) f = "pending_visits";
        else if (/upcoming follow/.test(lowerTxt)) f = "upcoming_followups";
        else if (/maternal/.test(lowerTxt)) f = "maternal_care";
        else if (/newborn|child/.test(lowerTxt)) f = "newborn_care";
        else if (/referral|danger|alert/.test(lowerTxt)) f = "referrals";
        setStatus("ready");
        setTaraLine(`Opening GeoPulse map${f !== "all" ? `: ${f.replace(/_/g, " ")}` : ""}.`);
        navigate(`/app/geopulse?filter=${encodeURIComponent(f)}`);
        return;
      }

      setStatus("processing");
      const pipelineT0 = performance.now();
      const pipeline = { speechEndMs: speechEndRef.current ? Math.round(speechEndRef.current) : null };
      try {
        if (extractAbortRef.current) extractAbortRef.current.abort();
        const controller = new AbortController();
        extractAbortRef.current = controller;
        /* Single round trip: create/reuse session and extract. */
        const clientSessionId = sessionIdRef.current || `s-${Date.now()}-${Math.round(Math.random() * 1e6)}`;
        sessionIdRef.current = clientSessionId;
        const tExtract = performance.now();
        const session = await api.post("/voice/sessions/extract-direct", {
          client_session_id: clientSessionId,
          language: languageRef.current,
          transcript: txt,
          mode,
        }, { signal: controller.signal });
        pipeline.extractMs = Math.round(performance.now() - tExtract);
        pipeline.sessionMs = 0;
        pipeline.backendMode = session?.mode;

        const visits = session.visits || [];
        const detectedScenario = session.scenario || "single_beneficiary";
        setScenarioType(detectedScenario);
        setDangerFlags(session.danger_flags || []);
        setSessionMeta({
          id: session.id,
          scenario: detectedScenario,
          householdVisits: session.household_visits || [],
          corrections: session.corrections || [],
        });

        // Each visit carries its own identity resolution result.
        const processedVisits = visits.map((v) => ({
          ...v,
          temp_id: v.temp_id || v.visit_id,
          matchedBeneficiary:
            v.identity_status === "resolved" && v.beneficiary_id
              ? { id: v.beneficiary_id, name: v.beneficiary_name }
              : null,
          candidateMatches: v.candidates || [],
          needsRegistration: v.identity_status === "unresolved" && !!v.beneficiary_name,
          raw_structured: v.raw_structured || {},
        }));

        if (processedVisits.length > 1) {
          // Multiple beneficiaries in one continuous recording.
          setMultiVisits(processedVisits);
          setRecord(null);
          recordRef.current = null;

          const spokenCount = processedVisits.length;
          const readLine =
            detectedScenario === "household_members"
              ? t("vv.readbackMembers", "Extracted {n} family members in one household. Review each visit.").replace("{n}", spokenCount)
              : t("vv.readbackMulti", "Extracted {n} beneficiary visits. Review each one before saving.").replace("{n}", spokenCount);
          setTaraLine(readLine);
          const tTts = performance.now();
          setStatus("speaking");
          await speakWithMetrics(readLine);
          pipeline.ttsMs = Math.round(performance.now() - tTts);
          pipeline.totalMs = Math.round(performance.now() - pipelineT0);
          console.info("[voice-pipeline]", pipeline);
          if (sessionRef.current === null) { /* may have been barged-in */ }
          setStatus("confirm");
          return;
        }

        // Single beneficiary visit (Scenario A or single parsed entity)
        const singleVisit = processedVisits[0];
        const incoming = singleVisit ? { ...(singleVisit.raw_structured || {}) } : {};
        const sessionStructured =
          session?.structured && typeof session.structured === "object" && !Array.isArray(session.structured)
            ? session.structured
            : {};
        Object.entries(sessionStructured).forEach(([k, v]) => {
          if (v !== null && v !== undefined && v !== "") incoming[k] = v;
        });
        // Flatten nested extraction shapes so Structured Record fields populate reliably.
        const pdRaw = incoming.personal_details && typeof incoming.personal_details === "object" ? incoming.personal_details : {};
        const pdTop = singleVisit?.personal_details && typeof singleVisit.personal_details === "object" ? singleVisit.personal_details : {};
        const pd = { ...pdRaw, ...Object.fromEntries(Object.entries(pdTop).filter(([,v]) => v !== null && v !== undefined && v !== "")) };
        const measRaw = incoming.measurements && typeof incoming.measurements === "object" ? incoming.measurements : {};
        const measTop = singleVisit?.measurements && typeof singleVisit.measurements === "object" ? singleVisit.measurements : {};
        const meas = { ...measRaw, ...Object.fromEntries(Object.entries(measTop).filter(([,v]) => v !== null && v !== undefined && v !== "")) };
        const spokenNameCandidate = (
          singleVisit?.beneficiary_name ||
          incoming.beneficiary_name ||
          pd.name ||
          incoming.name ||
          singleVisit?.raw_structured?.beneficiary_name ||
          singleVisit?.raw_structured?.name ||
          singleVisit?.raw_structured?.personal_details?.name ||
          ""
        );
        const normalizedSpokenName = selectBeneficiaryName(spokenNameCandidate);
        if (normalizedSpokenName) {
          incoming.beneficiary_name = normalizedSpokenName;
          incoming.personal_details = { ...(incoming.personal_details && typeof incoming.personal_details === "object" ? incoming.personal_details : {}), ...pd, name: normalizedSpokenName };
        }
        if (incoming.age == null && pd.age != null) incoming.age = pd.age;
        if (!incoming.gender && pd.gender) incoming.gender = pd.gender;
        if (!incoming.category && (singleVisit?.category || incoming.category)) incoming.category = singleVisit?.category || incoming.category;
        if (!incoming.visit_date && (singleVisit?.visit_date || incoming.visit_date)) incoming.visit_date = singleVisit?.visit_date || incoming.visit_date;
        Object.entries(meas).forEach(([k, v]) => { if (incoming[k] == null && v !== null && v !== "") incoming[k] = v; });
        if (!incoming.observations && Array.isArray(singleVisit?.observations)) incoming.observations = singleVisit.observations;
        if (!incoming.follow_ups && Array.isArray(singleVisit?.follow_ups)) incoming.follow_ups = singleVisit.follow_ups;

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
        const prev = recordRef.current ? { ...recordRef.current } : null;
        const merged = mergeExtractedRecord(prev, incoming, { correcting: correctingRef.current });
        Object.keys(incoming).forEach((k) => {
          if (prev?.[k] !== merged[k]) keys.push(k);
        });

        recordRef.current = merged;
        setRecord(merged);
        setChangedKeys(correctingRef.current ? (keys.length > 0 ? keys : Object.keys(incoming)) : []);

        // Extraction-first: show extracted info directly. Do NOT auto-search DB or auto-link.
        if (singleVisit && !correctingRef.current) {
          const spokenName = (merged.beneficiary_name || singleVisit.beneficiary_name || "").trim();
          const candidates = []; // no automatic candidate search
          setDisambiguateCandidates(null);
          setRegisterCandidate(null);
          // Keep any existing manual selection? No - new extraction means new visit.
          setSelectedBenId(""); selectedBenIdRef.current = "";
          setBenConfirmed(false); benConfirmedRef.current = false;
          setSingleIdentity({
            status: spokenName ? "extracted_unlinked" : "name_missing",
            matchedBeneficiary: null,
            candidates,
            reason: spokenName ? "Name extracted from transcript. Link beneficiary manually before saving." : "Beneficiary name not extracted.",
            spokenName,
          });
        }

        const transcriptForReadback = (finalRef.current || transcript || "").trim();
        const line = transcriptForReadback
          ? formatTaraHeardTranscript(transcriptForReadback)
          : (correctingRef.current
              ? `${changedSummary(merged, prev, keys.length > 0 ? keys : Object.keys(incoming), t)} ${t("vv.confirmQuestion")}`
              : fullSummary(merged, merged.beneficiary_name || incoming.beneficiary_name || "", t));
        setTaraLine(line);
        const tTts = performance.now();
        setStatus("speaking");
        await speakWithMetrics(line);
        pipeline.ttsMs = Math.round(performance.now() - tTts);
        pipeline.totalMs = Math.round(performance.now() - pipelineT0);
        console.info("[voice-pipeline]", pipeline);
        setStatus("confirm");
      } catch (e) {
        if (e?.name === "AbortError" || /cancelled/i.test(e?.message || "")) {
          // Cancelled by a newer extraction or user action; transcript is preserved.
          return;
        }
        const msg = e?.message || t("vv.analysisError");
        setMicError(`${msg} ${t("vv.retryExtractionHint", "Your transcript is preserved. Tap Retry extraction.")}`);
        showToast(msg, "error");
        setStatus("ready");
      } finally {
        // Only clear if this is the current controller
        if (extractAbortRef.current?.signal?.aborted) { /* keep */ }
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
      stopAudioChain(); // barge-in: stop Tara playback / previous session
      speechEndRef.current = null;
      setMicError(null);
      // Voice-first: no mandatory beneficiary selection before recording.
      // Beneficiary identity is resolved from speech; ambiguity is handled after extraction.
      setVoiceProvider("");
      setPartial("");
      partialRef.current = "";
      setRegisterCandidate(null);
      setDisambiguateCandidates(null);
      setSingleIdentity(null); setEditingTranscript(false); setTranscriptDraft("");
      if (!isCorrection) {
        // New visit: clear previous visit-specific extraction/identity state to prevent stale leakage.
        setFinalText(""); finalRef.current = "";
        recordRef.current = null; setRecord(null);
        setMultiVisits([]); setChangedKeys([]); setCorrectionHistory([]);
        setDangerFlags([]); setTaraLine(""); setSavedResult(null);
        setEditingCardIdx(null);
        setSelectedBenId(""); selectedBenIdRef.current = "";
        setBenConfirmed(false); benConfirmedRef.current = false;
      }
      correctingRef.current = isCorrection;
      setCorrecting(isCorrection);
      setStatus("listening");

      const session = createVoiceSession({
        language: languageRef.current,
        // Attempt configured server/Gnani Prisma path first; backend/client falls back
        // to browser speech recognition only when Prisma is unavailable (reported honestly).
        preferBrowser: false,
        onProvider: (provider, reason) => {
          if (reason === "provider_auth") {
            setVoiceProvider("Browser Speech Recognition (fallback: Gnani authentication failed)");
            return;
          }
          if (provider === "Browser Speech Recognition" || String(provider || "").startsWith("Browser Speech Recognition")) {
            setVoiceProvider(String(provider || "").includes("fallback") ? provider : "Browser Speech Recognition (fallback)");
            return;
          }
          if (provider === "Gnani Prisma") {
            setVoiceProvider("Gnani Prisma v3.0");
            return;
          }
          setVoiceProvider(provider || "");
        },
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
    [mode, t, voiceErrorMessage, target]
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
      speechEndRef.current = performance.now();
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

  const doSaveBeneficiary = async (benId, confirmationOverride = null) => {
    const confirmation = confirmationOverride || { confirmed: true, method: "ui_fallback", phrase: "Confirm & Save button", confirmed_at: new Date().toISOString() };
    const res = await api.post("/visits", {
      beneficiary_id: benId,
      structured: recordRef.current,
      transcript: finalRef.current,
      language: languageRef.current,
      visit_type: visitType !== "general" ? visitType : undefined,
      confirmation,
      corrections: correctionHistory,
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

  const confirmSaveSingle = async (confirmationOverride = null) => {
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
      /* Resolve the person the WORKER SPOKE ABOUT.
       *
       * The previous code preferred `contextRef.current?.id` (whoever
       * happened to be selected in the context selector) over the spoken
       * name, so every visit ended up on the same beneficiary — the
       * "always Lakshmi" bug. The spoken identity now always wins; the
       * context beneficiary is only used when the utterance names nobody.
       */
      const spokenName = (rec.beneficiary_name || "").trim();
      let benId = null;
      const name = spokenName || contextRef.current?.name || "";

      // Extraction-first: do NOT auto-search/match by name. Require explicit manual linking/confirmation.
      const selectedId = selectedBenIdRef.current ? Number(selectedBenIdRef.current) : null;
      const manuallyLinked = singleIdentityRef.current?.status === "resolved" && singleIdentityRef.current?.matchedBeneficiary?.id;
      if (manuallyLinked) {
        benId = Number(singleIdentityRef.current.matchedBeneficiary.id);
      } else if (selectedId && benConfirmedRef.current) {
        benId = selectedId;
      } else {
        showToast(t("vv.saveNeedsBeneficiary", "Extracted information is preserved. Beneficiary linking is required before saving in the current system."), "warn");
        setSaving(false);
        return;
      }
      await doSaveBeneficiary(benId, confirmationOverride);
    } catch (e) {
      showToast(e.message || t("vv.saveError"), "error");
    } finally {
      setSaving(false);
    }
  };

  /**
   * Save the reviewed multi-visit session.
   *
   * Only visits the worker confirmed AND whose identity was resolved are
   * persisted; the backend reports the rest as skipped instead of writing
   * them against an arbitrary beneficiary.
   */
  const confirmSaveBatch = async (confirmationOverride = null) => {
    if (!multiVisits.length || !sessionMeta?.id) return;
    setSaving(true);
    try {
      const items = multiVisits.map((v) => ({
        temp_id: v.temp_id,
        beneficiary_id: v.matchedBeneficiary?.id || null,
        status: v.status === "rejected" ? "rejected" : "confirmed",
        raw_structured: v.raw_structured || {},
      }));

      const confirmation = confirmationOverride || { confirmed: true, method: "ui_fallback", phrase: "Confirm & Save button", confirmed_at: new Date().toISOString() };
      const res = await api.post(`/voice/sessions/${sessionMeta.id}/save`, {
        visits: items,
        household_visits: sessionMeta.householdVisits || [],
        confirmation,
      });

      setSavedResult({
        total_saved: res.total_saved,
        saved_visits: res.saved_visits,
        skipped_visits: res.skipped_visits,
        alerts: res.alerts || [],
      });
      setStatus("saved");
      setMultiVisits([]);
      sessionIdRef.current = null;

      const skipped = (res.skipped_visits || []).length;
      if (skipped > 0) {
        showToast(
          t("vv.savedWithSkipped", "Saved {n} visits; {m} still need a beneficiary.").replace("{n}", res.total_saved).replace("{m}", skipped),
          "warn"
        );
      } else {
        showToast(
          t("vv.savedVisits", "Saved {n} visits successfully!").replace("{n}", res.total_saved),
          "success"
        );
      }
    } catch (e) {
      showToast(e.message || t("vv.saveError"), "error");
    } finally {
      setSaving(false);
    }
  };
  confirmSaveSingleRef.current = confirmSaveSingle;
  confirmSaveBatchRef.current = confirmSaveBatch;

  function makeRegisterDraft(name) {
    const r = recordRef.current || {};
    const symptoms = r.symptoms || r.observations || r.chief_complaint || r.notes || "";
    return {
      name: (name || r.beneficiary_name || "").trim(),
      age: r.age ?? "",
      gender: r.gender || "",
      category: safeCategory(r.category),
      village: r.village || user?.phc || "",
      household_id: selectedHhRef.current || r.household_id || contextRef.current?.household_id || "",
      symptoms: Array.isArray(symptoms) ? symptoms.join(", ") : String(symptoms || ""),
      visit_date: r.visit_date || new Date().toISOString().slice(0, 10),
    };
  }

  const registerAndSaveSingle = async () => {
    const draft = registerCandidate && typeof registerCandidate === "object" ? registerCandidate : makeRegisterDraft(registerCandidate);
    if (!draft?.name?.trim()) {
      showToast(t("vv.registerNeedName", "Beneficiary name is required before registration."), "warn");
      return;
    }
    setSaving(true);
    try {
      // Check existing beneficiaries by name to avoid duplicates.
      const existing = await api.get(`/beneficiaries?search=${encodeURIComponent(draft.name.trim())}`).catch(() => ({ beneficiaries: [] }));
      const nameLower = draft.name.trim().toLowerCase();
      const exact = (existing.beneficiaries || []).filter((b) => String(b.name || "").trim().toLowerCase() === nameLower);
      if (exact.length === 1) {
        benListRef.current = [...benListRef.current.filter((x) => x.id !== exact[0].id), exact[0]];
        await doSaveBeneficiary(exact[0].id);
        showToast(t("vv.matchedExisting", "Matched existing beneficiary and saved visit."), "success");
        return;
      }
      if (exact.length > 1) {
        setDisambiguateCandidates({ name: draft.name.trim(), candidates: exact });
        setSaving(false);
        return;
      }

      const payload = {
        name: draft.name.trim(),
        category: safeCategory(draft.category),
        age: draft.age === "" || draft.age === null || draft.age === undefined ? undefined : Number(draft.age),
        gender: (draft.gender || "").trim() || undefined,
        village: (draft.village || "").trim() || undefined,
        household_id: draft.household_id ? Number(draft.household_id) : undefined,
        registration_notes: draft.symptoms ? `Voice registration: ${draft.symptoms}` : "Registered from voice visit",
      };
      const d = await api.post("/beneficiaries", payload);
      const b = d?.beneficiary || d?.beneficiaries?.[0] || d;
      if (!b?.id) throw new Error(t("vv.registerError", "Could not register the new beneficiary."));
      benListRef.current = [...benListRef.current.filter((x) => x.id !== b.id), b];
      await doSaveBeneficiary(b.id);
      showToast(t("vv.registeredSaved", "{name} registered and visit saved.").replace("{name}", draft.name.trim()), "success");
    } catch (e) {
      showToast(e.message || t("vv.registerError"), "error");
    } finally {
      setSaving(false);
    }
  };

  const keepAsUnassignedDraft = async () => {
    const draftName = registerCandidate && typeof registerCandidate === "object" ? registerCandidate.name : registerCandidate;
    setRegisterCandidate(null);
    setDisambiguateCandidates(null);
    setSingleIdentity(null); setEditingTranscript(false); setTranscriptDraft("");
    setTaraLine(t("vv.keptAsDraftMsg", "Kept as unassigned draft. Transcript preserved; no beneficiary was created or linked."));
    showToast(t("vv.keptAsDraftToast", "Kept as unassigned draft. Transcript preserved; no beneficiary was linked."), "info");
    console.info("[voice] kept as unassigned draft", { name: draftName, sessionId: sessionMetaRef.current?.id || null });
    // Keep record/transcript visible for review; do not save against any beneficiary.
    setStatus(recordRef.current ? "confirm" : "ready");
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
    setCorrectionHistory([]);
    setDangerFlags([]);
    setTaraLine("");
    setSavedResult(null);
    setRegisterCandidate(null);
    setDisambiguateCandidates(null);
    setSingleIdentity(null); setEditingTranscript(false); setTranscriptDraft("");
    setEditingCardIdx(null);
    setMicError(null);
    setStatus("ready");
  };

  const applyEditedTranscript = async () => {
    const txt = (transcriptDraft || "").trim();
    if (!txt) return;
    setEditingTranscript(false);
    setFinalText(txt); finalRef.current = txt;
    setMicError(null);
    setStatus("processing");
    try {
      const clientSessionId = sessionIdRef.current || `s-${Date.now()}-${Math.round(Math.random() * 1e6)}`;
      sessionIdRef.current = clientSessionId;
      const session = await api.post("/voice/sessions/extract-direct", {
        client_session_id: clientSessionId,
        language: languageRef.current,
        transcript: txt,
        mode,
      });
      const visits = session.visits || [];
      const detectedScenario = session.scenario || "single_beneficiary";
      setScenarioType(detectedScenario);
      setDangerFlags(session.danger_flags || []);
      setSessionMeta({ id: session.id, scenario: detectedScenario, householdVisits: session.household_visits || [], corrections: session.corrections || [] });
      const processedVisits = visits.map((v) => ({ ...v, temp_id: v.temp_id || v.visit_id, matchedBeneficiary: null, candidateMatches: [], needsRegistration: false, raw_structured: v.raw_structured || {} }));
      if (processedVisits.length > 1) {
        setMultiVisits(processedVisits); setRecord(null); recordRef.current = null;
        const readLine = formatTaraHeardTranscript(txt);
        setTaraLine(readLine); setStatus("speaking"); await speakWithMetrics(readLine); setStatus("confirm"); return;
      }
      const singleVisit = processedVisits[0];
      const incoming = singleVisit ? { ...(singleVisit.raw_structured || {}) } : {};
      const pdRaw = incoming.personal_details && typeof incoming.personal_details === "object" ? incoming.personal_details : {};
      const pdTop = singleVisit?.personal_details && typeof singleVisit.personal_details === "object" ? singleVisit.personal_details : {};
      const pd = { ...pdRaw, ...Object.fromEntries(Object.entries(pdTop).filter(([,v]) => v !== null && v !== undefined && v !== "")) };
      const measRaw = incoming.measurements && typeof incoming.measurements === "object" ? incoming.measurements : {};
      const measTop = singleVisit?.measurements && typeof singleVisit.measurements === "object" ? singleVisit.measurements : {};
      const meas = { ...measRaw, ...Object.fromEntries(Object.entries(measTop).filter(([,v]) => v !== null && v !== undefined && v !== "")) };
      const spokenNameCandidate = (singleVisit?.beneficiary_name || incoming.beneficiary_name || pd.name || incoming.name || singleVisit?.raw_structured?.beneficiary_name || singleVisit?.raw_structured?.name || singleVisit?.raw_structured?.personal_details?.name || "");
      const normalizedSpokenName = selectBeneficiaryName(spokenNameCandidate);
      if (normalizedSpokenName) {
        incoming.beneficiary_name = normalizedSpokenName;
        incoming.personal_details = { ...(incoming.personal_details && typeof incoming.personal_details === "object" ? incoming.personal_details : {}), ...pd, name: normalizedSpokenName };
      }
      if (incoming.age == null && pd.age != null) incoming.age = pd.age;
      if (!incoming.gender && pd.gender) incoming.gender = pd.gender;
      if (!incoming.category && (singleVisit?.category || incoming.category)) incoming.category = singleVisit?.category || incoming.category;
      Object.entries(meas).forEach(([k, v]) => { if (incoming[k] == null && v !== null && v !== "") incoming[k] = v; });
      const prev = recordRef.current ? { ...recordRef.current } : null;
      const merged = mergeExtractedRecord(prev, incoming, { correcting: correctingRef.current });
      recordRef.current = merged; setRecord(merged);
      setChangedKeys(correctingRef.current ? Object.keys(incoming) : []);
      if (!correctingRef.current) {
        const spokenName = (merged.beneficiary_name || singleVisit?.beneficiary_name || "").trim();
        setSelectedBenId(""); selectedBenIdRef.current = ""; setBenConfirmed(false); benConfirmedRef.current = false;
        setSingleIdentity({ status: spokenName ? "extracted_unlinked" : "name_missing", matchedBeneficiary: null, candidates: [], reason: spokenName ? "Name extracted from transcript. Link beneficiary manually before saving." : "Beneficiary name not extracted.", spokenName });
      }
      const line = formatTaraHeardTranscript(txt);
      setTaraLine(line); setStatus("speaking"); await speakWithMetrics(line); setStatus("confirm");
    } catch (e) {
      setMicError(e?.message || "Extraction failed"); setStatus("ready");
    }
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
  const ttfaMedian = ttfaHistory.length
    ? (() => {
        const s = [...ttfaHistory].sort((a, b) => a - b);
        const mid = Math.floor(s.length / 2);
        return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
      })()
    : null;

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
                {voiceProvider || t("voice.providerOnRecord", "Speech provider selected when recording starts")}
              </span>
              {(ttfaMs != null || ttfaMedian != null) && (
                <span className="text-[0.68rem] font-semibold text-mint/85" aria-live="polite">
                  TTFA {ttfaMs != null ? `${ttfaMs}ms` : "—"} · median {ttfaMedian != null ? `${ttfaMedian}ms` : "—"}
                </span>
              )}
            </div>

            <div className="w-full text-center">
              <p className="text-sm font-semibold text-white/80">{t("vv.voiceFirstHint","Tap the mic and speak naturally. Tara will identify the beneficiary from your speech.")}</p>
              <button type="button" onClick={()=>setShowManualLink(v=>!v)} className="mt-2 text-[11px] font-bold text-white/45 underline-offset-2 hover:text-white/70 hover:underline">
                {showManualLink ? t("vv.hideManualLink","Hide manual link") : t("vv.manualLink","Optional: link beneficiary manually")}
              </button>
              {showManualLink && (
                <div className="mt-3 rounded-2xl border border-white/10 bg-white/5 p-3 text-left space-y-2">
                  <select value={selectedHhId} onChange={(e)=>{setSelectedHhId(e.target.value); setSelectedBenId("");}} className="w-full rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-sm text-white outline-none [&>option]:text-teal-deep">
                    <option value="">{t("vv.allHouseholds","All households")}</option>
                    {hhList.map(h => <option key={h.id} value={h.id}>{h.village} - {h.qr_id}</option>)}
                  </select>
                  <select value={selectedBenId} onChange={(e)=>setSelectedBenId(e.target.value)} className="w-full rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-sm text-white outline-none [&>option]:text-teal-deep">
                    <option value="">{t("vv.optionalBeneficiary","Optional beneficiary link")}</option>
                    {benList.filter(b=>!selectedHhId || String(b.household_id||"")===String(selectedHhId)).map(b => <option key={b.id} value={b.id}>{b.name} - {b.village || b.category}</option>)}
                  </select>
                </div>
              )}
            </div>

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
                  : status === "processing"
                  ? t("vv.hint.processing", "Understanding your request...")
                  : status === "speaking"
                  ? t("vv.hint.speaking", "Tara is speaking...")
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
                  <span className="flex-1">{micError}</span>
                </p>
                {finalText && status === "ready" && (
                  <button
                    type="button"
                    onClick={() => { setMicError(null); handleFinal(finalText); }}
                    className="mt-3 rounded-full bg-white/10 px-3 py-1.5 text-[11px] font-extrabold text-white hover:bg-white/20"
                  >
                    {t("vv.retryExtraction", "Retry extraction")}
                  </button>
                )}
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
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] font-bold">
                    <span className="text-white/60">
                      {playbackStatus === "preparing" ? t("vv.playbackPreparing", "Preparing audio…")
                        : playbackStatus === "speaking" ? t("vv.playbackSpeaking", "Speaking…")
                        : playbackStatus === "paused" ? t("vv.playbackPaused", "Paused")
                        : playbackStatus === "completed" ? t("vv.playbackCompleted", "Playback completed")
                        : playbackStatus === "blocked" ? t("vv.playbackBlocked", "Autoplay blocked")
                        : playbackStatus === "failed" ? t("vv.playbackFailedShort", "Playback failed")
                        : t("vv.playbackReady", "Audio readback")}
                    </span>
                    {playbackProvider ? (
                      <span className="rounded-full bg-white/10 px-2 py-0.5 text-white/50">
                        {/gnani|timbre/i.test(playbackProvider) ? "Gnani Timbre" : t("vv.browserFallback", "Browser fallback")}
                      </span>
                    ) : null}
                    {autoplayBlocked ? (
                      <button
                        type="button"
                        onClick={async () => {
                          setPlaybackStatus("preparing");
                          const r = await retryPendingPlayback();
                          if (r?.provider) setPlaybackProvider(r.provider);
                          if (r?.ended) { setAutoplayBlocked(false); setPlaybackError(""); setPlaybackStatus("completed"); }
                          else if (r?.autoplayBlocked) { setAutoplayBlocked(true); setPlaybackStatus("blocked"); }
                          else if (r?.error) { setPlaybackError(t("vv.playbackFailed", "Tara audio could not be played. You can replay or continue with the on-screen text.")); setPlaybackStatus("failed"); }
                        }}
                        className="rounded-full bg-mint px-3 py-1 text-teal-deep"
                      >
                        {t("vv.tapToHearBtn", "Tap to hear Tara")}
                      </button>
                    ) : (
                      <>
                        {playbackStatus === "speaking" ? (
                          <button type="button" onClick={() => { pauseSpeaking(); setPlaybackStatus("paused"); }} className="rounded-full bg-white/10 px-2.5 py-1 text-white/80 hover:bg-white/20">{t("vv.pause", "Pause")}</button>
                        ) : playbackStatus === "paused" ? (
                          <button type="button" onClick={async () => { const r = resumeSpeaking(); if (r && typeof r.then === "function") { try { await r; } catch {} } setPlaybackStatus("speaking"); }} className="rounded-full bg-white/10 px-2.5 py-1 text-white/80 hover:bg-white/20">{t("vv.resume", "Resume")}</button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => { if (taraLine) { setStatus("speaking"); speakWithMetrics(taraLine).finally(() => setStatus((s)=>s==="speaking"?"confirm":s)); } }}
                          className="rounded-full bg-white/10 px-2.5 py-1 text-white/80 hover:bg-white/20"
                        >
                          {playbackError ? t("vv.retryPlayback", "Retry playback") : t("vv.replay", "Replay")}
                        </button>
                      </>
                    )}
                    {playbackError ? <span className="text-coral">{playbackError}</span> : null}
                  </div>
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
                      setRegisterCandidate(makeRegisterDraft(name));
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
              {status === "confirm" && !multiVisits.length && !registerCandidate && !disambiguateCandidates && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex w-full flex-col gap-2.5 sm:flex-row"
                >
                  <div className="flex w-full flex-col gap-2">
                    {editingTranscript && (
                      <div className="rounded-2xl border border-white/15 bg-white/10 p-3">
                        <p className="text-xs font-bold text-mint mb-2">Edit transcript</p>
                        <textarea value={transcriptDraft} onChange={(e)=>setTranscriptDraft(e.target.value)} className="w-full rounded-xl bg-white/10 border border-white/15 p-2 text-sm text-white min-h-[72px]" />
                        <div className="mt-2 flex gap-2">
                          <button onClick={applyEditedTranscript} className="btn-mint px-3 py-1.5 text-xs">Apply & re-check</button>
                          <button onClick={()=>setEditingTranscript(false)} className="rounded-full border border-white/20 px-3 py-1.5 text-xs font-bold text-white/80">Cancel</button>
                        </div>
                      </div>
                    )}
                    <div className="flex flex-col gap-2.5 sm:flex-row">
                      <button
                        onClick={confirmSaveSingle}
                        disabled={saving}
                        className="btn-mint flex flex-1 items-center justify-center gap-2 px-5 py-3 text-sm disabled:opacity-60"
                      >
                        {saving ? <Loader2 size={16} className="animate-spin" /> : <BadgeCheck size={16} strokeWidth={2.4} />}
                        {saving ? t("vv.saving") : "Confirm"}
                      </button>
                      <button
                        onClick={() => startListening(true)}
                        className="flex flex-1 items-center justify-center gap-2 rounded-full border border-white/25 px-5 py-3 text-sm font-bold text-white transition-colors hover:bg-white/10"
                      >
                        <Mic size={16} strokeWidth={2.4} /> Correct by voice
                      </button>
                      <button
                        onClick={() => { setTranscriptDraft(finalRef.current || finalText || ""); setEditingTranscript(true); }}
                        className="flex flex-1 items-center justify-center gap-2 rounded-full border border-white/25 px-5 py-3 text-sm font-bold text-white transition-colors hover:bg-white/10"
                      >
                        <Edit3 size={16} strokeWidth={2.4} /> Edit transcript
                      </button>
                      <button
                        onClick={resetAll}
                        className="flex items-center justify-center gap-2 rounded-full px-4 py-3 text-sm font-bold text-white/50 transition-colors hover:text-white"
                      >
                        <RotateCcw size={15} /> Discard
                      </button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* register-new inline action */}
            <AnimatePresence>
              {registerCandidate && status !== "saved" && (() => {
                const draft = typeof registerCandidate === "object" ? registerCandidate : makeRegisterDraft(registerCandidate);
                const setDraft = (patch) => setRegisterCandidate({ ...draft, ...patch });
                return (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="w-full rounded-2xl border border-lavender/40 bg-lavender/10 px-5 py-4 text-left"
                >
                  <p className="text-sm font-extrabold text-mint">{t("vv.newBeneficiaryDetected", "New beneficiary detected!")}</p>
                  <p className="mt-1 text-[11px] text-white/65">{t("vv.newBeneficiaryHint", "Review extracted details. Register only after confirmation, or keep as unassigned draft.")}</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <label className="text-[11px] text-white/60">{t("field.beneficiary","Name")}<input className="mt-1 w-full rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-sm text-white" value={draft.name || ""} onChange={(e)=>setDraft({name:e.target.value})} /></label>
                    <label className="text-[11px] text-white/60">{t("field.age","Age")}<input className="mt-1 w-full rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-sm text-white" value={draft.age ?? ""} onChange={(e)=>setDraft({age:e.target.value})} /></label>
                    <label className="text-[11px] text-white/60">{t("field.gender","Gender")}<input className="mt-1 w-full rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-sm text-white" value={draft.gender || ""} onChange={(e)=>setDraft({gender:e.target.value})} /></label>
                    <label className="text-[11px] text-white/60">{t("field.category","Category")}<input className="mt-1 w-full rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-sm text-white" value={draft.category || ""} onChange={(e)=>setDraft({category:e.target.value})} /></label>
                    <label className="text-[11px] text-white/60">{t("field.village","Village/Household")}<input className="mt-1 w-full rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-sm text-white" value={draft.village || ""} onChange={(e)=>setDraft({village:e.target.value})} /></label>
                    <label className="text-[11px] text-white/60">{t("field.visitDate","Visit date")}<input className="mt-1 w-full rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-sm text-white" value={draft.visit_date || ""} onChange={(e)=>setDraft({visit_date:e.target.value})} /></label>
                  </div>
                  <label className="mt-2 block text-[11px] text-white/60">{t("vv.symptomsHealthInfo","Symptoms / health info")}<input className="mt-1 w-full rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-sm text-white" value={draft.symptoms || ""} onChange={(e)=>setDraft({symptoms:e.target.value})} /></label>
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                    <button onClick={registerAndSaveSingle} disabled={saving} className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60">
                      {saving ? <Loader2 size={15} className="animate-spin" /> : <UserPlus size={15} strokeWidth={2.4} />}
                      {t("vv.registerAndSaveAction", "Register New Beneficiary")}
                    </button>
                    <button onClick={keepAsUnassignedDraft} disabled={saving} className="flex flex-1 items-center justify-center gap-2 rounded-full border border-white/20 px-4 py-2.5 text-sm font-bold text-white/80 hover:bg-white/10 disabled:opacity-60">
                      {t("vv.keepAsDraft", "Keep as Unassigned Draft")}
                    </button>
                  </div>
                </motion.div>
                );
              })()}
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
                  {(savedResult.alerts || []).length > 0 ? (
                    <div className="mt-3 rounded-xl bg-coral/10 px-3.5 py-3">
                      <p className="text-xs font-extrabold text-coral mb-2">
                        Visit saved successfully. {(savedResult.alerts || []).length} danger alert{(savedResult.alerts || []).length === 1 ? "" : "s"} generated.
                      </p>
                      {savedResult.alerts.map((a, i) => (
                        <p key={i} className="flex items-start gap-2 text-xs font-bold text-coral">
                          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                          "{a.phrase || a.triggering_phrase || a.detected_danger_sign}" - {a.message || t("alerts.refer")}
                        </p>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs font-semibold text-teal-deep/65">
                      Visit saved successfully. No danger signs detected by the configured rules.
                    </p>
                  )}
                  {savedResult.alert_generation_error && (
                    <p className="mt-3 rounded-xl bg-amber-50 px-3.5 py-2.5 text-xs font-bold text-amber-800">
                      Visit saved, but danger-alert processing failed. Please retry or contact support. {String(savedResult.alert_generation_error)}
                    </p>
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
                          ? t("vv.householdMembers", "Household Members ({n})").replace("{n}", multiVisits.length)
                          : t("vv.multipleBeneficiaries", "Multiple Beneficiaries ({n})").replace("{n}", multiVisits.length)}
                      </p>
                      <p className="text-[0.65rem] text-white/60">
                        {t("vv.independentRecords", "Independent records extracted in one session")}
                      </p>
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
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-extrabold text-teal-deep">
                                {v.beneficiary_name || t("vv.unnamedVisit", "Unnamed visit")}
                              </span>
                              <span className="chip bg-mint/20 text-[0.65rem] font-bold text-teal-deep">
                                {v.category || "general"}
                              </span>
                              <IdentityBadge visit={v} />
                            </div>
                            <p className="mt-0.5 text-[0.68rem] text-teal-deep/55">
                              {v.personal_details?.relation ? `${t("vv.relation", "Relation")}: ${v.personal_details.relation} · ` : ""}
                              {v.personal_details?.gender ? `${t("vv.gender", "Gender")}: ${v.personal_details.gender} · ` : ""}
                              {v.personal_details?.age != null ? `${t("vv.age", "Age")}: ${v.personal_details.age} · ` : ""}
                              {v.household_label || v.household_id || ""}
                            </p>
                            {v.identity_reason && (
                              <p className="mt-1 text-[0.65rem] font-medium text-teal-deep/50">
                                {v.identity_reason}
                              </p>
                            )}
                          </div>

                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => setEditingCardIdx(isEditing ? null : idx)}
                              className="rounded-lg p-1.5 text-teal-deep/50 hover:bg-teal-deep/5 hover:text-teal-deep"
                              title={t("vv.editFields", "Edit fields")}
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
                              title={t("vv.discardThisVisit", "Discard this visit")}
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

                {(() => {
                  const hasName = !!selectBeneficiaryName(record?.beneficiary_name, record?.personal_details?.name, record?.raw_structured?.beneficiary_name, record?.raw_structured?.name, record?.name);
                  const showIdentityNotice = !hasName && !isHhTarget && (fields.length > 0 || status === "confirm");
                  if (fields.length === 0 && !showIdentityNotice) {
                    return (
                      <div className="rounded-2xl bg-ivory/80 px-4 py-8 text-center">
                        <Waves size={26} className="mx-auto mb-2 text-teal-deep/25" />
                        <p className="text-xs font-semibold leading-relaxed text-teal-deep/45">
                          {correcting ? t("vv.previewHintCorrection") : t("vv.previewHint")}
                        </p>
                      </div>
                    );
                  }
                  const cat = String(record?.category ?? "").toLowerCase();
                  const relevant = (id) => {
                    if (id === "identity" || id === "followup") return true;
                    if (id === "sanitation") return isHhTarget || cat === "household" || ["water_source","toilet_available","waste_disposal","drainage","stagnant_water"].some(k => record?.[k] !== undefined);
                    if (id === "maternal") return cat === "pregnancy" || record?.weeks_pregnant != null || record?.ifa_tablets != null || record?.td_vaccine != null;
                    if (id === "child") return ["newborn","child","immunisation"].includes(cat) || record?.vaccine_name != null || record?.temperature != null || record?.feeding != null || record?.jaundice != null;
                    if (id === "elderly") return cat === "elderly" || record?.mobility != null || record?.blood_sugar != null;
                    if (id === "measurements") return ["weight_kg","height_cm","hemoglobin","blood_sugar"].some(k => record?.[k] != null);
                    return true;
                  };
                  return (
                  <div className="space-y-4 max-h-[580px] overflow-y-auto pr-1">

                    {SECTION_DEFS.filter(sec => relevant(sec.id)).map((sec) => {
                      let secFields = fields.filter((f) => sec.keys.includes(f.key));
                      if (sec.id === "identity" && !isHhTarget) {
                        const displayName = selectBeneficiaryName(record?.beneficiary_name, record?.personal_details?.name, record?.raw_structured?.beneficiary_name, record?.raw_structured?.name, record?.name);
                        if (!displayName && showIdentityNotice) {
                          secFields = [{ key: "beneficiary_name", label: "field.beneficiary", icon: User, value: t("vv.nameNotMentionedShort", "Name not mentioned"), render: (v) => v }, ...secFields];
                        } else if (displayName && !secFields.some((f) => f.key === "beneficiary_name")) {
                          secFields = [{ key: "beneficiary_name", label: "field.beneficiary", icon: User, value: displayName, render: (v) => v }, ...secFields];
                        } else if (displayName) {
                          secFields = secFields.map((f) => f.key === "beneficiary_name" ? { ...f, value: displayName } : f);
                        }
                      }
                      if (sec.id !== "identity") {
                        secFields = secFields.filter((f) => f.key !== "beneficiary_name" && !(f.key === "age" && sec.id !== "identity"));
                      }
                      // avoid showing same measurement duplicated confusingly across maternal/child/elderly when not primary
                      if (sec.id === "child" && ["pregnancy","elderly"].includes(cat)) secFields = secFields.filter(f => ["vaccine_name","temperature","feeding","jaundice"].includes(f.key));
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
                                      {(() => {
                                        const v = f.value;
                                        if (v === null || v === undefined || v === "" || (typeof v === "number" && Number.isNaN(v))) return t("vv.notMentioned", "Not mentioned");
                                        const out = f.render ? f.render(v, t) : String(v);
                                        if (out === null || out === undefined || out === "" || out === "NaN" || out === "undefined" || out === "null") return t("vv.notMentioned", "Not mentioned");
                                        return out;
                                      })()}
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
                  );
                })()}
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
        STT: {voiceProvider || "determined on record"} · TTS: Gnani Timbre (live when available, browser fallback otherwise) · app mode: {mode}
      </p>
    </div>
  );
}
