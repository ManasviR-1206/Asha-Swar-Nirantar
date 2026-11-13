import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Home as HomeIcon,
  Users,
  Mic,
  QrCode,
  Download,
  CalendarDays,
  CalendarClock,
  Droplets,
  ShieldCheck,
  Waves,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { statusLabel, relationLabel, genderLabel } from "../../lib/labels.js";

/** Human labels for the household hygiene structured fields. */
const HH_FIELD_LABELS = {
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

function fmtValue(key, value, t) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
  if (key === "water_storage_covered") return value ? t("hh.covered") : t("hh.uncovered");
  if (key === "toilet_usage") return value === "used" ? t("hh.used") : t("hh.notUsed");
  return String(value);
}

export default function HouseholdDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [qr, setQr] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.get(`/households/${id}`);
      setData(d);
      try {
        const q = await api.get(`/households/${id}/qr`);
        setQr(q);
      } catch {}
    } catch (e) {
      showToast(e.message || t("households.loadOneErr", "Could not load household."), "error");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card-ivory">
        <Empty icon={HomeIcon} title={t("households.title")} subtitle={t("qr.notFound")} />
      </div>
    );
  }

  const { household, members, visits, followups } = data;
  const linkedBeneficiaries = members.filter((m) => m.beneficiary_id);

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify({ household, members, visits, followups }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${household.qr_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <button
            onClick={() => navigate("/app/households")}
            className="mt-1 rounded-full bg-teal-deep/5 p-2 text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
            aria-label={t("common.back")}
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-extrabold text-teal-deep">{household.village}</h2>
              <span className="font-mono text-xs font-bold tracking-wider text-teal-deep/45">{household.qr_id}</span>
            </div>
            <p className="mt-0.5 text-sm font-medium text-teal-deep/55">
              {household.address || "—"} · <Users size={12} className="inline" /> {t("households.members")}: {household.member_count}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {qr?.data_url && (
            <a href={qr.data_url} download={`${household.qr_id}.png`} className="chip bg-mint-soft text-teal-deep hover:bg-mint/40 transition-colors flex items-center gap-1.5 cursor-pointer">
              <Download size={12} /> {t("households.qrTitle")}
            </a>
          )}
          <button
            onClick={() => navigate(`/app/household-health?household=${household.id}`)}
            className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm"
          >
            <Mic size={16} strokeWidth={2.4} /> {t("households.startVoiceVisit")}
          </button>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* ================= timeline (Pulse Thread, household level) ================= */}
        <div className="space-y-5 lg:col-span-2">
          <div className="card-ivory p-5">
            <div className="mb-4 flex items-center gap-2">
              <Waves size={17} className="text-pink" />
              <h3 className="text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">
                {t("households.timeline")}
              </h3>
            </div>
            {visits.length === 0 ? (
              <Empty icon={CalendarDays} title={t("households.noVisits")} subtitle={t("empty.recordsSub")} />
            ) : (
              <ol className="relative space-y-4 border-l-2 border-mint/40 pl-5">
                {visits.map((v, i) => (
                  <motion.li
                    key={v.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: Math.min(i * 0.06, 0.3) }}
                    className="relative"
                  >
                    <span className="absolute -left-[27px] top-1 flex h-4 w-4 items-center justify-center rounded-full bg-mint shadow-[0_0_10px_rgba(240,120,173,0.7)]">
                      <span className="h-1.5 w-1.5 rounded-full bg-white" />
                    </span>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-extrabold text-teal-deep">
                        {t("households.healthVisits")} — {v.visit_date}
                      </p>
                      <span className={`chip ${v.source === "voice" ? "bg-mint-soft text-teal-deep" : "bg-teal-deep/5 text-teal-deep/55"}`}>
                        {v.source === "voice" ? t("pt.voiceSource", "🎙 Voice") : t("pt.manualSource", "Manual")}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
                      {Object.entries(v.structured || {})
                        .filter(([k]) => HH_FIELD_LABELS[k] && !["visit_date", "follow_up_days"].includes(k))
                        .map(([k, val]) => (
                          <p key={k} className="text-xs font-medium text-teal-deep/60">
                            <span className="font-bold text-teal-deep/45">{t(HH_FIELD_LABELS[k])}: </span>
                            {fmtValue(k, val, t)}
                          </p>
                        ))}
                    </div>
                  </motion.li>
                ))}
              </ol>
            )}
          </div>
        </div>

        {/* ================= side column ================= */}
        <div className="space-y-5">
          {/* QR card */}
          <div className="card-ivory p-5 text-center">
            <div className="mb-3 flex items-center justify-center gap-2">
              <QrCode size={16} className="text-pink" />
              <h3 className="text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">
                {t("households.qrTitle")}
              </h3>
            </div>
            {qr?.data_url ? (
              <>
                <img src={qr.data_url} alt={`QR ${household.qr_id}`} className="mx-auto h-40 w-40 rounded-2xl border border-teal-deep/10 bg-white p-2" />
                <p className="mt-2 font-mono text-xs font-bold tracking-wider text-teal-deep/55">{household.qr_id}</p>
                <p className="mt-1 text-[0.68rem] font-medium text-teal-deep/45">
                  {t("households.qrAnonNote", "Anonymous ID only — no personal data.")}
                </p>
                <a
                  href={qr.data_url}
                  download={`${household.qr_id}.png`}
                  className="btn-mint mt-3 flex items-center justify-center gap-2 px-4 py-2.5 text-sm"
                >
                  <Download size={15} /> {t("common.downloadPng")}
                </a>
                <button
                  onClick={downloadJson}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                >
                  <Download size={15} /> {t("common.downloadJson")}
                </button>
              </>
            ) : (
              <div className="mx-auto flex h-40 w-40 items-center justify-center rounded-2xl bg-mint-soft text-teal-deep">
                <ShieldCheck size={38} />
              </div>
            )}
          </div>

          {/* members */}
          <div className="card-ivory p-5">
            <div className="mb-3 flex items-center gap-2">
              <Users size={16} className="text-pink" />
              <h3 className="text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">
                {t("households.registeredMembers")}
              </h3>
            </div>
            <ul className="space-y-2.5">
              {members.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2 rounded-2xl bg-teal-deep/[0.04] px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-teal-deep">{m.name}</p>
                    <p className="text-[0.68rem] font-semibold text-teal-deep/45">
                      {relationLabel(m.relation, t)} · {m.age} {m.gender ? `· ${genderLabel(m.gender, t)}` : ""}
                    </p>
                  </div>
                  {m.beneficiary_id && (
                    <button
                      onClick={() => navigate(`/app/beneficiaries/${m.beneficiary_id}`)}
                      className="chip shrink-0 bg-mint-soft text-teal-deep hover:bg-mint/40 transition-colors cursor-pointer"
                    >
                      {t("common.view")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {/* follow-ups */}
          <div className="card-ivory p-5">
            <div className="mb-3 flex items-center gap-2">
              <CalendarClock size={16} className="text-pink" />
              <h3 className="text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">
                {t("households.followups")}
              </h3>
            </div>
            {followups.length === 0 ? (
              <p className="text-xs font-medium text-teal-deep/45">{t("reminders.empty")}</p>
            ) : (
              <ul className="space-y-2.5">
                {followups.map((f) => (
                  <li key={f.id} className="flex items-center justify-between gap-2 rounded-2xl bg-teal-deep/[0.04] px-3 py-2">
                    <p className="text-xs font-bold text-teal-deep">{f.due_date}</p>
                    <span className={`chip shrink-0 ${
                      f.status === "overdue" || f.status === "missed"
                        ? "bg-coral/15 text-coral"
                        : f.status === "upcoming"
                          ? "bg-lavender/20 text-midnight"
                          : "bg-mint-soft text-teal-deep"
                    }`}>
                      {statusLabel(f.status, t)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* linked beneficiary profiles */}
          {linkedBeneficiaries.length > 0 && (
            <div className="card-ivory p-5">
              <div className="mb-3 flex items-center gap-2">
                <Droplets size={16} className="text-pink" />
                <h3 className="text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">
                  {t("households.linkedProfiles")}
                </h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {linkedBeneficiaries.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => navigate(`/app/beneficiaries/${m.beneficiary_id}`)}
                    className="chip bg-lavender/20 text-midnight hover:bg-lavender/40 transition-colors cursor-pointer"
                  >
                    {m.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
