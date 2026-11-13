import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ShieldAlert,
  ShieldCheck,
  Waves,
  CheckCircle2,
  Clock,
  Loader2,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";

function severityChip(sev) {
  const s = (sev || "").toLowerCase();
  if (s.includes("crit") || s.includes("high")) return "bg-coral/15 text-coral";
  if (s.includes("med")) return "bg-lavender/20 text-midnight";
  return "bg-mint-soft text-teal-deep";
}

export default function Alerts() {
  const { t } = useI18n();
  const [alerts, setAlerts] = useState(null);
  const [ackingId, setAckingId] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .get("/alerts")
      .then((d) => alive && setAlerts(d.alerts || []))
      .catch((e) => showToast(e.message || t("err.generic"), "error"));
    return () => {
      alive = false;
    };
  }, []);

  const acknowledge = async (id) => {
    setAckingId(id);
    try {
      await api.post(`/alerts/${id}/ack`);
      setAlerts((list) => (list || []).map((a) => (a.id === id ? { ...a, status: "acknowledged" } : a)));
      showToast(t("alerts.ackOk", "Alert acknowledged."), "success");
    } catch (e) {
      showToast(e.message || t("alerts.ackErr", "Could not acknowledge the alert."), "error");
    } finally {
      setAckingId(null);
    }
  };

  const open = (alerts || []).filter((a) => a.status !== "acknowledged");
  const done = (alerts || []).filter((a) => a.status === "acknowledged");

  return (
    <div className="space-y-5">
      {/* safety disclaimer banner */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="card-ivory flex items-start gap-3.5 p-5"
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-mint-soft">
          <ShieldCheck size={19} className="text-teal-deep" strokeWidth={2.2} />
        </div>
        <p className="text-xs font-semibold leading-relaxed text-teal-deep/65 sm:text-sm">
          {t("alerts.disclaimer", "Rule-based detection using the approved danger-sign list. Tara never diagnoses — she only flags verified phrases for review.")}
        </p>
      </motion.div>

      {alerts === null ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="card-ivory">
          <Empty
            icon={ShieldCheck}
            title={t("alerts.empty")}
            subtitle={t("alerts.emptySub", "No verified danger phrases have been detected in your recent voice visits.")}
          />
        </div>
      ) : (
        <>
          {/* open alerts */}
          {open.length > 0 && (
            <div className="space-y-3">
              <AnimatePresence initial={false}>
                {open.map((a, idx) => (
                  <motion.div
                    key={a.id}
                    layout
                    initial={{ opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.97 }}
                    transition={{ duration: 0.3, delay: Math.min(idx * 0.05, 0.3) }}
                    className="card-ivory border-coral/30 p-5"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`chip ${severityChip(a.severity)}`}>
                            <ShieldAlert size={11} /> {a.severity || t("alerts.severity")}
                          </span>
                          <Link
                            to={`/app/beneficiaries/${a.beneficiary_id}`}
                            className="flex items-center gap-1.5 truncate text-sm font-extrabold text-teal-deep underline-offset-2 hover:underline"
                          >
                            <Waves size={13} className="text-mint" /> {a.beneficiary_name}
                          </Link>
                        </div>
                        <p className="mt-2.5 text-sm font-bold text-coral">"{a.phrase}"</p>
                        <p className="mt-1 text-xs font-semibold text-teal-deep/65">{t("alerts.refer")}</p>
                        <p className="mt-1.5 flex items-center gap-1.5 text-[0.68rem] font-medium text-teal-deep/40">
                          <Clock size={11} /> {(a.created_at || "").slice(0, 10)}
                        </p>
                      </div>
                      <button
                        onClick={() => acknowledge(a.id)}
                        disabled={ackingId === a.id}
                        className="flex shrink-0 items-center gap-2 rounded-full bg-teal-deep px-4 py-2.5 text-xs font-bold text-mint transition-transform hover:-translate-y-0.5 disabled:opacity-60"
                      >
                        {ackingId === a.id ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} strokeWidth={2.4} />}
                        {t("alerts.acknowledge", "Acknowledge")}
                      </button>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}

          {/* acknowledged */}
          {done.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-extrabold uppercase tracking-wider text-teal-deep/40">
                {t("alerts.acknowledged", "Acknowledged")} ({done.length})
              </p>
              {done.map((a) => (
                <div key={a.id} className="card-ivory flex items-center gap-3 p-4 opacity-70">
                  <CheckCircle2 size={16} className="shrink-0 text-mint" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-bold text-teal-deep/70">
                      {a.beneficiary_name} — "{a.phrase}"
                    </p>
                  </div>
                  <span className="chip shrink-0 bg-mint-soft text-teal-deep">{t("alerts.acknowledged", "Acknowledged")}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
