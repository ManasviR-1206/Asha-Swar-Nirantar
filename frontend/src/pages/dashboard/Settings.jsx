import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  User,
  Languages,
  Radio,
  ShieldAlert,
  Heart,
  Ear,
  Brain,
  Save,
  LogOut,
  ListChecks,
} from "lucide-react";
import { LANGUAGES } from "../../lib/api.js";
import { useAuth } from "../../lib/auth.jsx";
import { showToast } from "../../components/ui/Toast.jsx";
import { useI18n } from "../../lib/i18n.jsx";

function greetingKey() {
  const h = new Date().getHours();
  if (h < 12) return "dash.goodMorning";
  if (h < 17) return "dash.goodAfternoon";
  return "dash.goodEvening";
}

export default function Settings() {
  const { user, logout, mode } = useAuth();
  const navigate = useNavigate();
  const { t, lang, setLang } = useI18n();

  const saveLanguage = (code) => {
    setLang(code);
    showToast(t("settings.langSaved", "Preferred language saved. It will be used for new voice visits."), "success");
  };

  const live = mode === "live";

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      {/* ------------------------------ profile ------------------------------ */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="card-ivory p-6"
      >
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-3xl bg-teal-deep text-lg font-extrabold text-mint">
            {(user?.name || "W")
              .trim()
              .split(/\s+/)
              .slice(0, 2)
              .map((w) => w[0]?.toUpperCase())
              .join("")}
          </div>
          <div className="min-w-0">
            <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">
              {t(greetingKey())}, {t("settings.ashaWorker", "ASHA Worker")}
            </p>
            <h2 className="truncate text-xl font-extrabold text-teal-deep">{user?.name || "—"}</h2>
            <div className="mt-1 flex flex-wrap gap-2">
              {user?.worker_id && (
                <span className="chip bg-teal-deep/5 font-mono text-[0.68rem] text-teal-deep/55">{user.worker_id}</span>
              )}
              {user?.phc && <span className="chip bg-mint-soft text-teal-deep">{user.phc}</span>}
            </div>
          </div>
        </div>

        {/* language preference */}
        <div className="mt-6 rounded-2xl bg-ivory/80 p-4">
          <label className="block">
            <span className="mb-2 flex items-center gap-2 text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">
              <Languages size={13} className="text-mint" /> {t("settings.uiLanguage")}
            </span>
            <select
              value={lang}
              onChange={(e) => saveLanguage(e.target.value)}
              className="w-full rounded-2xl border border-teal-deep/10 bg-white px-4 py-2.5 text-sm font-semibold text-teal-deep focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30"
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label} — {l.native}
                </option>
              ))}
            </select>
            <span className="mt-2 block text-[0.7rem] font-medium text-teal-deep/50">
              {t("settings.voiceLanguageNote")}
            </span>
          </label>
        </div>
      </motion.section>

      {/* ------------------------------ integration mode ------------------------------ */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.06 }}
        className="card-ivory p-6"
      >
        <h3 className="flex items-center gap-2.5 text-sm font-extrabold text-teal-deep">
          <Radio size={16} className="text-mint" strokeWidth={2.4} /> {t("settings.integrationMode", "Integration mode")}
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          <span
            className={`chip px-3.5 py-1.5 ${live ? "bg-mint-soft text-teal-deep" : "bg-lavender/20 text-midnight"}`}
          >
            {live ? t("settings.liveMode", "Live") : t("common.demoMode")} {t("settings.modeActive", "mode active")}
          </span>
        </div>
        <p className="mt-3 text-xs font-medium leading-relaxed text-teal-deep/55">
          {live
            ? t("settings.liveDesc", "Connected to the live backend — real speech services, storage and SMS gateway.")
            : t("settings.demoDesc", "Running fully offline-safe demo services. Service status is shown below; simulated SMS never sends a real message.")}
        </p>
        <div className="mt-4 space-y-2">
          {[
            { name: t("settings.svcStt", "Speech-to-text · Gnani Prisma"), live },
            { name: t("settings.svcTts", "Text-to-speech · Gnani Timbre"), live },
            { name: t("settings.svcLlm", "Tara AI (LLM) · Google Gemini"), live },
            { name: t("settings.svcDb", "Records database"), live },
            { name: t("settings.svcSms", "SMS gateway"), live: false, note: t("settings.svcSmsNote", "simulated in demo") },
          ].map((s) => (
            <div key={s.name} className="flex items-center justify-between rounded-xl bg-ivory/70 px-4 py-2.5">
              <p className="text-xs font-bold text-teal-deep/75">{s.name}</p>
              <span className={`chip ${s.live ? "bg-mint-soft text-teal-deep" : "bg-lavender/20 text-midnight"}`}>
                {s.live ? t("settings.liveMode", "Live") : t("common.demoMode")}
                {!s.live && s.note ? ` · ${s.note}` : ""}
              </span>
            </div>
          ))}
        </div>
      </motion.section>

      {/* ------------------------------ danger-sign rules ------------------------------ */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.12 }}
        className="card-ivory p-6"
      >
        <h3 className="flex items-center gap-2.5 text-sm font-extrabold text-teal-deep">
          <ShieldAlert size={16} className="text-coral" strokeWidth={2.4} />{" "}
          {t("settings.dangerRules", "Danger-sign rules (approved list)")}
        </h3>
        <p className="mt-2 text-xs font-medium leading-relaxed text-teal-deep/55">
          {t("settings.dangerRulesDesc", "Tara only flags these exact verified phrases — she never diagnoses. Any match is surfaced for review with a fixed \"Refer to PHC\" guidance.")}
        </p>
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {[
            t("settings.rule.bleeding", "Bleeding during pregnancy"),
            t("settings.rule.headache", "Severe headache or blurred vision"),
            t("settings.rule.convulsions", "Convulsions / fits"),
            t("settings.rule.fever", "High fever with chills"),
            t("settings.rule.swelling", "Swelling of hands, face or feet"),
            t("settings.rule.fetal", "Reduced or absent fetal movement"),
            t("settings.rule.breathing", "Difficulty breathing"),
            t("settings.rule.feeding", "Baby unable to breastfeed or lethargic"),
            t("settings.rule.cord", "Umbilical cord discharge or redness"),
          ].map((r) => (
            <li key={r} className="flex items-start gap-2.5 rounded-xl bg-ivory/70 px-3.5 py-2.5">
              <ListChecks size={13} className="mt-0.5 shrink-0 text-mint" strokeWidth={2.4} />
              <span className="text-xs font-semibold text-teal-deep/75">{r}</span>
            </li>
          ))}
        </ul>
      </motion.section>

      {/* ------------------------------ about ------------------------------ */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.18 }}
        className="rounded-3xl bg-gradient-to-br from-[#321321] to-[#7A1638] p-6 text-white shadow-card border border-[#E8A8B8]/20"
      >
        <h3 className="flex items-center gap-2.5 text-sm font-extrabold text-[#FFF7F0]">
          <Heart size={16} className="text-[#E8A8B8]" strokeWidth={2.4} /> {t("settings.aboutApp", "About ASHA Swar Nirantar")}
        </h3>
        <p className="mt-1 text-[0.68rem] font-bold uppercase tracking-wider text-[#E8A8B8]/90">
          {t("settings.version", "Version 1.0.0")}
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {[
            { icon: Ear, word: t("app.listen"), text: t("settings.p1", "Speak naturally in your language — Tara writes it down.") },
            { icon: Brain, word: t("app.remember"), text: t("settings.p2", "Every visit becomes a permanent, readable pulse thread.") },
            { icon: Save, word: t("app.protect"), text: t("settings.p3", "Danger signs are flagged for review, mothers reach care sooner.") },
          ].map((p) => (
            <div key={p.word} className="rounded-2xl bg-white/10 border border-[#E8A8B8]/15 p-4">
              <p.icon size={16} className="text-[#E8A8B8]" strokeWidth={2.4} />
              <p className="mt-2 text-xs font-extrabold tracking-[0.18em] text-[#F4DCE4]">{p.word}</p>
              <p className="mt-1 text-[0.7rem] font-medium leading-relaxed text-[#FFF7F0]/80">{p.text}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs font-semibold leading-relaxed text-[#FFF7F0]/80">
          {t("settings.aboutDesc", "The voice-first field register for ASHA workers — because every village deserves a pulse that never fades.")}
        </p>
      </motion.section>

      {/* ------------------------------ account ------------------------------ */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.24 }}
        className="card-ivory p-6"
      >
        <h3 className="flex items-center gap-2.5 text-sm font-extrabold text-teal-deep">
          <User size={16} className="text-mint" strokeWidth={2.4} /> {t("nav.account", "Account")}
        </h3>
        <button
          onClick={() => {
            logout();
            navigate("/");
          }}
          className="mt-5 flex w-full items-center justify-center gap-2 rounded-full bg-coral px-5 py-3 text-sm font-extrabold text-white transition-transform hover:-translate-y-0.5 sm:w-auto sm:min-w-64"
        >
          <LogOut size={16} strokeWidth={2.4} /> {t("nav.logout")}
        </button>
      </motion.section>
    </div>
  );
}
