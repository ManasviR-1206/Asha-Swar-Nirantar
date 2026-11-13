import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  TrendingDown,
  Mic,
  CalendarClock,
  Eye,
  AlarmClock,
  Scale,
  ChevronRight,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { driftIssue, driftAction, categoryLabel } from "../../lib/labels.js";

export default function PulseDrift() {
  const { t } = useI18n();
  const [items, setItems] = useState(null);
  const [cat, setCat] = useState("All");

  useEffect(() => {
    let alive = true;
    api
      .get("/drift")
      .then((d) => alive && setItems(d.items || []))
      .catch((e) => showToast(e.message || t("err.generic"), "error"));
    return () => {
      alive = false;
    };
  }, []);

  const categories = useMemo(() => {
    const set = new Set((items || []).map((i) => i.category).filter(Boolean));
    return ["All", ...Array.from(set)];
  }, [items]);

  const sorted = useMemo(
    () =>
      (items || [])
        .filter((i) => cat === "All" || i.category === cat)
        .sort((a, b) => (b.overdue_days || 0) - (a.overdue_days || 0)),
    [items, cat]
  );

  return (
    <div className="space-y-5">
      {/* header + explainer */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="max-w-2xl"
      >
        <h2 className="text-xl font-extrabold text-teal-deep sm:text-2xl">{t("drift.title")}</h2>
        <p className="mt-1.5 text-sm font-medium leading-relaxed text-teal-deep/55">
          {t("drift.explainer", "Smart follow-up monitoring — deterministic rules flag what's overdue or missing. An unchanged weight is never treated as a medical problem on its own; it is flagged for verification.")}
        </p>
      </motion.div>

      {/* category filter chips */}
      {items && items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className={[
                "chip px-3.5 py-1.5 transition-all",
                cat === c
                  ? "bg-teal-deep text-white shadow-soft"
                  : "bg-teal-deep/5 text-teal-deep/60 hover:bg-mint-soft hover:text-teal-deep",
              ].join(" ")}
            >
              {c === "All" ? t("common.all") : categoryLabel(c, t)}
            </button>
          ))}
        </div>
      )}

      {/* content */}
      {items === null ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <div className="card-ivory">
          <Empty
            icon={TrendingDown}
            title={t("drift.empty")}
            subtitle={t("drift.emptySub", "Tara is watching quietly.")}
          />
        </div>
      ) : (
        <div className="space-y-3">
          {sorted.map((d, idx) => {
            const overdue = (d.overdue_days || 0) > 0;
            const isHousehold = !!d.household_id;
            const detailHref = isHousehold ? `/app/households/${d.household_id}` : `/app/beneficiaries/${d.beneficiary_id}`;
            return (
              <motion.div
                key={d.beneficiary_id || d.household_id || idx}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: Math.min(idx * 0.05, 0.35) }}
                className="card-ivory p-4 sm:p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        to={detailHref}
                        className="truncate text-sm font-extrabold text-teal-deep underline-offset-2 hover:underline"
                      >
                        {d.name || d.beneficiary_name}
                      </Link>
                      {d.category && <span className="chip bg-mint-soft text-teal-deep">{categoryLabel(d.category, t)}</span>}
                      {overdue && (
                        <span className="chip bg-coral/15 text-coral">
                          <AlarmClock size={11} /> {t("drift.overdueBy", "{n}").replace("{n}", d.overdue_days)}
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 text-sm font-semibold text-teal-deep/75">{driftIssue(d, t)}</p>
                    <p className="mt-1 flex items-center gap-1.5 text-xs font-medium text-teal-deep/45">
                      <CalendarClock size={12} /> {t("drift.dueDate")}: {d.due_date || "—"}
                    </p>
                    <p className="mt-1 text-[0.7rem] font-medium text-teal-deep/50">
                      {t("drift.recommended")}: {driftAction(d, t)}
                    </p>
                  </div>
                  <div className="flex w-full shrink-0 flex-wrap gap-2 sm:w-auto sm:flex-col sm:items-end">
                    <Link
                      to={isHousehold ? `/app/household-health?household=${d.household_id}` : `/app/voice-visit?beneficiary=${d.beneficiary_id}`}
                      className="btn-mint flex items-center gap-2 px-4 py-2 text-xs"
                    >
                      <Mic size={13} strokeWidth={2.4} />{" "}
                      {isHousehold ? t("households.startVoiceVisit") : t("drift.recordFollowup", "Record follow-up visit")}
                    </Link>
                    <Link
                      to={`/app/reminders?beneficiary=${d.beneficiary_id || ""}`}
                      className="flex items-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2 text-xs font-bold text-teal-deep/70 transition-colors hover:bg-teal-deep/10"
                    >
                      <CalendarClock size={13} strokeWidth={2.2} /> {t("drift.reschedule", "Reschedule")}
                    </Link>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
