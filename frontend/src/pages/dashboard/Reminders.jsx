import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  BellRing,
  BellPlus,
  Send,
  CalendarClock,
  CalendarDays,
  HeartPulse,
  Syringe,
  Baby,
  ShieldCheck,
  MessageSquare,
  Loader2,
  X,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { statusLabel, followupTypeLabel } from "../../lib/labels.js";

/* Canonical reminder type codes understood by the backend. */
const TYPES = ["anc", "vaccination", "newborn"];

/* Exact body the backend sends — generic on purpose, no name, no health detail. */
const SAFE_MESSAGE =
  "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.";

const INPUT =
  "w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 px-4 py-2.5 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30";

const typeIcon = (t) =>
  /vaccin/i.test(t || "") ? Syringe : /anc|pregnan/i.test(t || "") ? HeartPulse : Baby;

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function isOverdue(r) {
  return (
    r.due_date &&
    !/sent|complet|done/i.test(r.status || "") &&
    new Date(r.due_date) < new Date(todayStr())
  );
}

export default function Reminders() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [benList, setBenList] = useState([]);
  const [preselect, setPreselect] = useState(searchParams.get("beneficiary") || "");

  useEffect(() => {
    let alive = true;
    api
      .get("/reminders")
      .then((d) => alive && setItems(d.reminders || []))
      .catch((e) => showToast(e.message || t("err.generic"), "error"));
    api
      .get("/beneficiaries")
      .then((d) => alive && setBenList(d.beneficiaries || []))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const groups = useMemo(() => {
    const list = items || [];
    return {
      overdue: list.filter((r) => isOverdue(r)),
      upcoming: list.filter((r) => !isOverdue(r) && !/sent|complet|done/i.test(r.status || "")),
      sent: list.filter((r) => /sent|complet|done/i.test(r.status || "")),
    };
  }, [items]);

  const refetch = () => api.get("/reminders").then((d) => setItems(d.reminders || []));

  const sendSms = async (r) => {
    try {
      const res = await api.post(`/reminders/${r.id}/send`);
      if (res.status === "demo_sent") {
        showToast(t("reminders.demoSent", "Demo mode: SMS simulated — no real message sent."), "info");
      } else {
        showToast(t("reminders.sentTo", "{name}").replace("{name}", r.beneficiary_name), "success");
      }
      refetch().catch(() => {});
    } catch (e) {
      showToast(e.message || t("reminders.sendErr", "Could not send the SMS."), "error");
    }
  };

  const reschedule = async (r, dueDate) => {
    if (!dueDate) {
      showToast(t("reminders.pickDate", "Pick a new due date first."), "warn");
      return;
    }
    try {
      await api.post(`/reminders/${r.id}/reschedule`, { due_date: dueDate });
      showToast(t("reminders.rescheduled", "Reminder rescheduled."), "success");
      refetch().catch(() => {});
    } catch (e) {
      showToast(e.message || t("reminders.reschedErr", "Could not reschedule."), "error");
    }
  };

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep">{t("reminders.title")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">
            {t("reminders.subtitle", "Gentle, non-sensitive SMS reminders — never any health details.")}
          </p>
        </div>
        <button onClick={() => setModalOpen(true)} className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm">
          <BellPlus size={16} strokeWidth={2.4} /> {t("reminders.schedule")}
        </button>
      </div>

      {items === null ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="card-ivory">
          <Empty
            icon={BellRing}
            title={t("reminders.empty")}
            subtitle={t("reminders.emptySub", "Schedule a reminder so no follow-up is ever missed.")}
            action={
              <button onClick={() => setModalOpen(true)} className="btn-mint flex items-center gap-2 px-5 py-2.5 text-sm">
                <BellPlus size={16} strokeWidth={2.4} /> {t("reminders.schedule")}
              </button>
            }
          />
        </div>
      ) : (
        <>
          {(
            [
              [t("reminders.group.overdue", "Overdue"), groups.overdue, "text-coral"],
              [t("reminders.group.upcoming", "Upcoming"), groups.upcoming, "text-teal-deep"],
              [t("reminders.group.sent", "Sent / Done"), groups.sent, "text-teal-deep/60"],
            ].filter(([, l]) => l.length > 0)
          ).map(([label, list, cls]) => (
            <div key={label} className="space-y-2.5">
              <p className={`text-xs font-extrabold uppercase tracking-wider ${cls}`}>
                {label} ({list.length})
              </p>
              {list.map((r, idx) => (
                <ReminderRow key={r.id} r={r} idx={idx} onSend={sendSms} onReschedule={reschedule} />
              ))}
            </div>
          ))}
        </>
      )}

      <ScheduleModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        benList={benList}
        preselect={preselect}
        onCreated={() => refetch().catch(() => {})}
      />
    </div>
  );
}

/* ------------------------------ reminder row ------------------------------ */

function ReminderRow({ r, idx, onSend, onReschedule }) {
  const { t } = useI18n();
  const Icon = typeIcon(r.type);
  const [reschedOpen, setReschedOpen] = useState(false);
  const [newDate, setNewDate] = useState(r.due_date || "");
  const overdue = isOverdue(r);
  const sent = /sent|complet|done/i.test(r.status || "");

  const smsChip = () => {
    const s = (r.sms_status || r.status || "").toLowerCase();
    if (s.includes("demo")) return "bg-lavender/20 text-midnight";
    if (s.includes("fail")) return "bg-coral/15 text-coral";
    if (s.includes("sent") || s.includes("deliver")) return "bg-mint-soft text-teal-deep";
    if (s.includes("overdue") || s.includes("missed")) return "bg-coral/15 text-coral";
    if (s.includes("schedul") || s.includes("pending")) return "bg-mint-soft text-teal-deep";
    return "bg-teal-deep/5 text-teal-deep/55";
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(idx * 0.04, 0.3) }}
      className="card-ivory p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-mint-soft">
            <Icon size={16} className="text-teal-deep" strokeWidth={2.2} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-extrabold text-teal-deep">{r.beneficiary_name}</p>
            <p className="flex items-center gap-1.5 truncate text-xs font-medium text-teal-deep/45">
              <CalendarDays size={11} /> {t("drift.dueDate")}: {r.due_date || "—"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip bg-teal-deep/5 text-teal-deep/60">{followupTypeLabel(r.type, t)}</span>
          {overdue && <span className="chip bg-coral/15 text-coral">{t("status.overdue")}</span>}
          {!overdue && !sent && (
            <span className="chip bg-mint-soft text-teal-deep">{statusLabel(r.status, t)}</span>
          )}
          {sent && <span className="chip bg-mint-soft text-teal-deep">{t("reminders.done", "Done")}</span>}
          <span className={`chip ${smsChip()}`}>
            <MessageSquare size={10} /> SMS: {statusLabel(r.sms_status || r.status, t) || "—"}
          </span>
        </div>
      </div>

      {!sent && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={() => onSend(r)}
            className="flex items-center gap-2 rounded-full bg-teal-deep px-4 py-2 text-xs font-bold text-mint transition-transform hover:-translate-y-0.5"
          >
            <Send size={12} strokeWidth={2.4} /> {t("reminders.sendSms", "Send SMS")}
          </button>
          <button
            onClick={() => setReschedOpen((o) => !o)}
            className="flex items-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2 text-xs font-bold text-teal-deep/70 transition-colors hover:bg-teal-deep/10"
          >
            <CalendarClock size={12} strokeWidth={2.2} /> {t("drift.reschedule", "Reschedule")}
          </button>
          <AnimatePresence>
            {reschedOpen && (
              <motion.div
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: "auto" }}
                exit={{ opacity: 0, width: 0 }}
                className="flex items-center gap-2 overflow-hidden"
              >
                <input
                  type="date"
                  value={newDate}
                  onChange={(e) => setNewDate(e.target.value)}
                  className="rounded-xl border border-teal-deep/10 bg-ivory/70 px-3 py-1.5 text-xs font-semibold text-teal-deep focus:border-mint focus:outline-none"
                />
                <button
                  onClick={() => {
                    onReschedule(r, newDate);
                    setReschedOpen(false);
                  }}
                  className="rounded-full bg-mint px-3.5 py-1.5 text-xs font-extrabold text-teal-deep"
                >
                  {t("common.save")}
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}

/* ------------------------------ schedule modal ------------------------------ */

function ScheduleModal({ open, onClose, benList, preselect, onCreated }) {
  const { t } = useI18n();
  const [benId, setBenId] = useState(preselect || "");
  const [type, setType] = useState(TYPES[0]);
  const [due, setDue] = useState("");
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setBenId(preselect || "");
      setType(TYPES[0]);
      setDue("");
      setConsent(false);
      setSaving(false);
    }
  }, [open, preselect]);

  const submit = async (e) => {
    e.preventDefault();
    if (!benId) return showToast(t("reminders.pickBeneficiary", "Please choose a beneficiary."), "warn");
    if (!due) return showToast(t("reminders.pickDueDate", "Please pick a due date."), "warn");
    if (!consent) return showToast(t("reminders.confirmConsent", "Please confirm SMS consent."), "warn");
    setSaving(true);
    try {
      await api.post("/reminders", { beneficiary_id: Number(benId) || benId, type, due_date: due });
      showToast(t("reminders.scheduled", "Reminder scheduled."), "success");
      onCreated?.();
      onClose();
    } catch (err) {
      showToast(err.message || t("reminders.scheduleErr", "Could not schedule the reminder."), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-end justify-center bg-teal-deep/50 backdrop-blur-sm sm:items-center sm:p-6"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 60, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 40, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", damping: 28, stiffness: 340 }}
            onClick={(e) => e.stopPropagation()}
            className="card-ivory max-h-[92vh] w-full max-w-md overflow-y-auto rounded-b-none p-6 sm:rounded-3xl"
          >
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h3 className="text-lg font-extrabold text-teal-deep">{t("reminders.schedule")}</h3>
                <p className="mt-0.5 text-xs font-medium text-teal-deep/50">
                  {t("reminders.safeOnly", "Only a safe, generic message will be sent.")}
                </p>
              </div>
              <button onClick={onClose} aria-label={t("common.close")} className="rounded-full bg-teal-deep/5 p-2 text-teal-deep/50">
                <X size={16} />
              </button>
            </div>
            <form onSubmit={submit} className="space-y-3.5">
              <label className="block">
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">
                  {t("nav.beneficiaries")}
                </span>
                <select value={benId} onChange={(e) => setBenId(e.target.value)} className={INPUT}>
                  <option value="">{t("reminders.selectBeneficiary", "Select beneficiary…")}</option>
                  {benList.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} — {b.village || b.category}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">
                  {t("common.category")}
                </span>
                <select value={type} onChange={(e) => setType(e.target.value)} className={INPUT}>
                  {TYPES.map((ty) => (
                    <option key={ty} value={ty}>
                      {followupTypeLabel(ty, t)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">
                  {t("reminders.dueDate", "Due date")}
                </span>
                <input type="date" value={due} min={todayStr()} onChange={(e) => setDue(e.target.value)} className={INPUT} />
              </label>

              {/* message preview */}
              <div className="rounded-2xl bg-ivory/80 p-4">
                <p className="mb-1.5 flex items-center gap-1.5 text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">
                  <MessageSquare size={11} /> {t("reminders.smsPreview", "SMS preview")}
                </p>
                <p className="text-xs font-semibold leading-relaxed text-teal-deep/75">"{SAFE_MESSAGE}"</p>
                <p className="mt-2 flex items-center gap-1.5 text-[0.68rem] font-bold text-mint">
                  <ShieldCheck size={12} /> {t("reminders.noHealth", "SMS never contains health details.")}
                </p>
              </div>

              <label className="flex cursor-pointer items-start gap-2.5 rounded-2xl bg-mint-soft/50 px-4 py-3">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[#39D6B0]"
                />
                <span className="text-xs font-semibold leading-relaxed text-teal-deep/75">
                  {t("reminders.consentText", "I confirm consent to send a non-sensitive reminder SMS")}
                </span>
              </label>

              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60"
                >
                  {saving ? <Loader2 size={15} className="animate-spin" /> : <BellPlus size={15} strokeWidth={2.4} />}
                  {saving ? t("reminders.scheduling", "Scheduling…") : t("reminders.scheduleBtn", "Schedule")}
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
