import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  MessageSquare,
  FileText,
  History,
  Send,
  Loader2,
  X,
  Eye,
  ShieldCheck,
  Download,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Filter,
  Phone,
  Inbox,
} from "lucide-react";
import { api, downloadFile, openFile } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";

const INPUT =
  "w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 px-4 py-2.5 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30";

const TABS = [
  { id: "sms", label: "SMS Notifications", icon: MessageSquare, key: "notif.tab.sms" },
  { id: "pdf", label: "PDF Reports", icon: FileText, key: "notif.tab.pdf" },
  { id: "history", label: "SMS History", icon: History, key: "notif.tab.history" },
];

const NOTIF_TYPES = [
  "anc",
  "vaccination",
  "newborn",
  "nutrition",
  "community",
  "household",
  "appointment",
  "follow_up",
  "medication",
  "care_plan",
  "important_alert",
];

function statusChip(status, isDemo) {
  const s = (status || "").toLowerCase();
  if (isDemo || s === "demo") return "bg-lavender/25 text-midnight";
  if (s === "failed" || s === "error") return "bg-coral/15 text-coral";
  if (s === "submitted" || s === "delivered" || s === "sent") return "bg-mint-soft text-teal-deep";
  if (s === "pending") return "bg-teal-deep/5 text-teal-deep/60";
  return "bg-teal-deep/5 text-teal-deep/55";
}

function displayStatus(status, isDemo) {
  const s = (status || "").toLowerCase();
  if (isDemo || s === "demo") return "Demo (not sent)";
  if (s === "submitted" || s === "delivered" || s === "sent") return "Sent";
  if (s === "failed" || s === "error") return "Failed";
  if (s === "pending") return "Pending";
  return status || "Unknown";
}

export default function Notifications() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get("tab");
  const [tab, setTab] = useState(initialTab === "history" ? "history" : initialTab === "pdf" ? "pdf" : "sms");
  const [stats, setStats] = useState(null);
  const [sms, setSms] = useState(null);
  const [reports, setReports] = useState(null);
  const [benList, setBenList] = useState([]);
  const [composing, setComposing] = useState(false);

  /* filters */
  const [fBen, setFBen] = useState("");
  const [fType, setFType] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fFrom, setFFrom] = useState("");
  const [fTo, setFTo] = useState("");

  const load = useCallback(() => {
    api.get("/notifications/stats").then(setStats).catch(() => {});
    api.get("/notifications/sms").then((d) => setSms(d.notifications || [])).catch(() => setSms([]));
    api.get("/notifications/reports").then((d) => setReports(d.reports || [])).catch(() => setReports([]));
    api.get("/beneficiaries").then((d) => setBenList(d.beneficiaries || [])).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const benName = useCallback((id) => benList.find((b) => b.id === id)?.name || `#${id}`, [benList]);

  const matchRow = useCallback(
    (row, dateField) => {
      if (fBen && String(row.beneficiary_id) !== String(fBen)) return false;
      if (fType && (row.type || "") !== fType) return false;
      if (fStatus) {
        const s = (row.status || "").toLowerCase();
        const isDemo = !!row.is_demo || s === "demo";
        const normalized =
          isDemo ? "demo" : s === "failed" || s === "error" ? "failed" : s === "pending" ? "pending" : s === "submitted" || s === "delivered" || s === "sent" ? "sent" : s;
        if (fStatus !== normalized) return false;
      }
      if (fFrom || fTo) {
        const raw = row[dateField];
        if (!raw) return false;
        const d = String(raw).slice(0, 10);
        if (fFrom && d < fFrom) return false;
        if (fTo && d > fTo) return false;
      }
      return true;
    },
    [fBen, fType, fStatus, fFrom, fTo]
  );

  const filteredSms = useMemo(() => (sms || []).filter((r) => matchRow(r, "created_at")), [sms, matchRow]);
  const filteredReports = useMemo(
    () =>
      (reports || []).filter((r) => {
        if (fBen && String(r.beneficiary_id) !== String(fBen)) return false;
        if (fFrom || fTo) {
          const d = String(r.generated_at || "").slice(0, 10);
          if (!d) return false;
          if (fFrom && d < fFrom) return false;
          if (fTo && d > fTo) return false;
        }
        return true;
      }),
    [reports, fBen, fFrom, fTo]
  );

  const anyFilter = !!(fBen || fType || fStatus || fFrom || fTo);
  const clearFilters = () => {
    setFBen("");
    setFType("");
    setFStatus("");
    setFFrom("");
    setFTo("");
  };

  const loading = sms === null || reports === null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep">{t("notif.title", "Notifications")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">
            {t(
              "notif.subtitle",
              "Send SMS notifications, review delivery status, and access PDF follow-up reports."
            )}
          </p>
        </div>
        <button onClick={() => setComposing(true)} className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm">
          <MessageSquare size={15} strokeWidth={2.4} /> {t("notif.newSms", "New SMS")}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <MiniStat
          label={t("notif.stat.smsTotal", "Total SMS")}
          value={stats?.sms_total ?? 0}
          icon={MessageSquare}
          sub={`${stats?.sms_demo ?? 0} demo • ${stats?.sms_real ?? 0} real`}
        />
        <MiniStat
          label={t("notif.stat.pending", "Pending")}
          value={stats?.pending ?? 0}
          icon={Inbox}
          tone={stats?.pending ? "warn" : "ok"}
        />
        <MiniStat
          label={t("notif.stat.failed", "Failed")}
          value={stats?.failed ?? 0}
          icon={AlertTriangle}
          tone={stats?.failed ? "bad" : "ok"}
        />
        <MiniStat label={t("notif.stat.pdf", "PDF Reports")} value={stats?.pdf_reports ?? 0} icon={FileText} />
        <MiniStat
          label={t("notif.stat.upcoming", "Upcoming follow-ups")}
          value={stats?.upcoming_followups ?? 0}
          icon={CheckCircle2}
        />
      </div>

      {stats && (
        <div className="card-ivory flex flex-wrap items-center gap-3 px-4 py-3">
          <ShieldCheck size={15} className="text-teal-deep/50" strokeWidth={2.2} />
          <p className="text-xs font-semibold text-teal-deep/70">{t("notif.providerStatus", "Delivery configuration")}</p>
          <ProviderChip
            ok={stats.sms_provider_configured && stats.sms_enabled !== false}
            label={`SMS: ${
              stats.sms_enabled === false
                ? "disabled"
                : stats.sms_provider_configured
                  ? `configured${stats.sms_provider && stats.sms_provider !== "demo" ? ` (${stats.sms_provider})` : ""}`
                  : t("notif.demoMode", "demo mode")
            }`}
          />
          {(!stats.sms_provider_configured || stats.sms_enabled === false) && (
            <span className="chip bg-lavender/25 text-midnight">SMS: DEMO — NOT ACTUALLY SENT</span>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 rounded-2xl bg-teal-deep/5 p-1.5">
        {TABS.map((tb) => {
          const Icon = tb.icon;
          const active = tab === tb.id;
          const count = tb.id === "pdf" ? filteredReports.length : filteredSms.length;
          return (
            <button
              key={tb.id}
              onClick={() => setTab(tb.id)}
              className={[
                "flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-extrabold transition-all",
                active ? "bg-white text-teal-deep shadow-soft" : "text-teal-deep/55 hover:text-teal-deep",
              ].join(" ")}
            >
              <Icon size={14} strokeWidth={2.3} />
              <span className="hidden sm:inline">{t(tb.key, tb.label)}</span>
              <span className="sm:hidden">{tb.label.split(" ")[0]}</span>
              <span className="chip bg-teal-deep/8 px-1.5 text-[0.6rem]">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="card-ivory p-4">
        <div className="mb-3 flex items-center gap-2">
          <Filter size={14} className="text-teal-deep/50" strokeWidth={2.2} />
          <p className="text-xs font-extrabold uppercase tracking-wider text-teal-deep/60">{t("notif.filters", "Filters")}</p>
          {anyFilter && (
            <button onClick={clearFilters} className="ml-auto text-xs font-bold text-pink underline-offset-2 hover:underline">
              {t("common.clear", "Clear")}
            </button>
          )}
        </div>
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
          <select value={fBen} onChange={(e) => setFBen(e.target.value)} className={INPUT}>
            <option value="">{t("notif.allBeneficiaries", "All beneficiaries")}</option>
            {benList.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
          <select value={fType} onChange={(e) => setFType(e.target.value)} className={INPUT} disabled={tab === "pdf"}>
            <option value="">{t("notif.allTypes", "All types")}</option>
            {NOTIF_TYPES.map((ty) => (
              <option key={ty} value={ty}>
                {ty.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} className={INPUT} disabled={tab === "pdf"}>
            <option value="">{t("notif.allStatuses", "All statuses")}</option>
            {[
              ["pending", "Pending"],
              ["sent", "Sent"],
              ["failed", "Failed"],
              ["demo", "Demo (not sent)"],
            ].map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
          <input type="date" value={fFrom} onChange={(e) => setFFrom(e.target.value)} className={INPUT} aria-label={t("notif.from", "From date")} />
          <input type="date" value={fTo} onChange={(e) => setFTo(e.target.value)} className={INPUT} aria-label={t("notif.to", "To date")} />
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <>
          {tab === "sms" && <SmsTab rows={filteredSms} benName={benName} />}
          {tab === "pdf" && <PdfTab rows={filteredReports} benName={benName} />}
          {tab === "history" && <SmsTab rows={filteredSms} benName={benName} title={t("notif.tab.history", "SMS History")} />}
        </>
      )}

      <Composer open={composing} onClose={() => setComposing(false)} benList={benList} onSent={load} />
    </div>
  );
}

function MiniStat({ label, value, icon: Icon, sub, tone = "ok" }) {
  const toneCls = tone === "bad" ? "bg-coral/15 text-coral" : tone === "warn" ? "bg-lavender/25 text-midnight" : "bg-mint-soft text-teal-deep";
  return (
    <div className="card-ivory flex items-center gap-3 px-3.5 py-3">
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${toneCls}`}>
        <Icon size={15} strokeWidth={2.2} />
      </div>
      <div className="min-w-0">
        <p className="truncate text-lg font-extrabold leading-none text-teal-deep">{value ?? 0}</p>
        <p className="mt-1 truncate text-[0.65rem] font-bold uppercase tracking-wide text-teal-deep/50">{label}</p>
        {sub && <p className="truncate text-[0.62rem] font-semibold text-teal-deep/40">{sub}</p>}
      </div>
    </div>
  );
}

function ProviderChip({ ok, label }) {
  return (
    <span className={`chip ${ok ? "bg-mint-soft text-teal-deep" : "bg-lavender/25 text-midnight"}`}>
      {ok ? <CheckCircle2 size={10} /> : <HelpCircle size={10} />} {label}
    </span>
  );
}

function DemoBadge({ isDemo }) {
  if (!isDemo) return null;
  return <span className="chip bg-lavender/25 text-[0.62rem] font-extrabold text-midnight">DEMO — NOT ACTUALLY SENT</span>;
}

function SmsTab({ rows, benName, title }) {
  const { t } = useI18n();
  if (!rows.length) {
    return (
      <div className="card-ivory">
        <Empty
          icon={MessageSquare}
          title={title || t("notif.smsEmpty", "No SMS notifications yet")}
          subtitle={t("notif.smsEmptySub", "Prepare a reminder and approve it before anything is sent.")}
        />
      </div>
    );
  }
  return (
    <div className="space-y-2.5">
      {rows.map((r, i) => (
        <motion.div
          key={r.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: Math.min(i * 0.03, 0.25) }}
          className="card-ivory p-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-extrabold text-teal-deep">{benName(r.beneficiary_id)}</p>
              <p className="mt-0.5 flex items-center gap-1.5 text-xs font-medium text-teal-deep/45">
                <Phone size={11} /> {r.phone || "—"} • {String(r.created_at || "").slice(0, 16).replace("T", " ")}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip bg-teal-deep/5 text-teal-deep/60">{r.type}</span>
              <span className={`chip ${statusChip(r.status, r.is_demo)}`}>{displayStatus(r.status, r.is_demo)}</span>
              <DemoBadge isDemo={r.is_demo} />
            </div>
          </div>
          <p className="mt-2.5 rounded-xl bg-ivory/80 px-3.5 py-2.5 text-xs font-medium leading-relaxed text-teal-deep/75">{r.body}</p>
          {r.provider_note && <p className="mt-1.5 text-[0.68rem] font-semibold text-teal-deep/45">{r.provider_note}</p>}
        </motion.div>
      ))}
    </div>
  );
}

function PdfTab({ rows, benName }) {
  const { t } = useI18n();
  if (!rows.length) {
    return (
      <div className="card-ivory">
        <Empty
          icon={FileText}
          title={t("notif.pdfEmpty", "No PDF reports yet")}
          subtitle={t("notif.pdfEmptySub", "A report is generated from the real visit history of a beneficiary.")}
        />
      </div>
    );
  }
  return (
    <div className="space-y-2.5">
      {rows.map((r, i) => (
        <motion.div
          key={r.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: Math.min(i * 0.03, 0.25) }}
          className="card-ivory flex flex-wrap items-center justify-between gap-3 p-4"
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-mint-soft">
              <FileText size={16} className="text-teal-deep" strokeWidth={2.2} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-extrabold text-teal-deep">{r.filename}</p>
              <p className="truncate text-xs font-medium text-teal-deep/45">
                {benName(r.beneficiary_id)} • {Math.round((r.size_bytes || 0) / 1024)} KB • {String(r.generated_at || "").slice(0, 16).replace("T", " ")}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => openFile(`/notifications/reports/preview/${r.beneficiary_id}`).catch((e) => showToast(e.message, "error"))}
              className="flex items-center gap-1.5 rounded-full bg-teal-deep/5 px-3.5 py-1.5 text-xs font-bold text-teal-deep/70 transition-colors hover:bg-teal-deep/10"
            >
              <Eye size={12} strokeWidth={2.2} /> {t("notif.preview", "Preview")}
            </button>
            <button
              onClick={() => downloadFile(`/notifications/reports/${r.id}/download`, r.filename || "followup-report.pdf").catch((e) => showToast(e.message, "error"))}
              className="flex items-center gap-1.5 rounded-full bg-mint px-3.5 py-1.5 text-xs font-extrabold text-teal-deep transition-colors hover:bg-mint/80"
            >
              <Download size={12} strokeWidth={2.4} /> {t("notif.downloadPdf", "Download PDF")}
            </button>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

function Composer({ open, onClose, benList, onSent }) {
  const { t } = useI18n();
  const [benId, setBenId] = useState("");
  const [type, setType] = useState("anc");
  const [language, setLanguage] = useState("en");
  const [body, setBody] = useState("");
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => {
    if (!open) return;
    setBenId("");
    setType("anc");
    setLanguage("en");
    setBody("");
    setConsent(false);
    setSaving(false);
    setPreview(null);
  }, [open]);

  const selected = benList.find((b) => String(b.id) === String(benId));

  const loadPreview = async () => {
    if (!benId) return;
    setLoadingPreview(true);
    try {
      const p = await api.post("/notifications/sms/preview", {
        beneficiary_id: Number(benId),
        type,
        language,
      });
      setPreview(p);
      if (!body) setBody(p.body || "");
    } catch (e) {
      showToast(e.message || t("err.generic"), "error");
    } finally {
      setLoadingPreview(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!benId) return showToast(t("reminders.pickBeneficiary", "Please choose a beneficiary."), "warn");
    if (!consent) return showToast(t("notif.consentRequired", "Please confirm consent before sending."), "warn");
    setSaving(true);
    try {
      const res = await api.post("/notifications/sms/send", {
        beneficiary_id: Number(benId),
        type,
        language,
        body,
        consent_granted: true,
      });
      showToast(
        res.is_demo
          ? t("notif.demoSaved", "Demo notification saved — it was NOT actually sent.")
          : t("notif.submittedToProvider", "Submitted to the provider."),
        res.is_demo ? "info" : "success"
      );
      onSent?.();
      onClose();
    } catch (err) {
      showToast(err.message || t("err.generic"), "error");
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
            className="card-ivory max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-b-none p-6 sm:rounded-3xl"
          >
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h3 className="text-lg font-extrabold text-teal-deep">{t("notif.composeSms", "Prepare SMS")}</h3>
                <p className="mt-0.5 text-xs font-medium text-teal-deep/50">
                  {t("notif.smsSafeNote", "The message stays generic — no health details are sent.")}
                </p>
              </div>
              <button onClick={onClose} aria-label={t("common.close")} className="rounded-full bg-teal-deep/5 p-2 text-teal-deep/50">
                <X size={16} />
              </button>
            </div>

            <form onSubmit={submit} className="space-y-3.5">
              <label className="block">
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">{t("nav.beneficiaries")}</span>
                <select
                  value={benId}
                  onChange={(e) => {
                    setBenId(e.target.value);
                    setPreview(null);
                  }}
                  className={INPUT}
                >
                  <option value="">{t("reminders.selectBeneficiary", "Select beneficiary…")}</option>
                  {benList.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} — {b.village || b.category}
                    </option>
                  ))}
                </select>
              </label>

              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">{t("common.category")}</span>
                  <select
                    value={type}
                    onChange={(e) => {
                      setType(e.target.value);
                      setPreview(null);
                    }}
                    className={INPUT}
                  >
                    {NOTIF_TYPES.map((ty) => (
                      <option key={ty} value={ty}>
                        {ty.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">{t("common.language")}</span>
                  <select
                    value={language}
                    onChange={(e) => {
                      setLanguage(e.target.value);
                      setPreview(null);
                    }}
                    className={INPUT}
                  >
                    <option value="en">English</option>
                    <option value="kn">Kannada</option>
                    <option value="hi">Hindi</option>
                    <option value="te">Telugu</option>
                    <option value="ta">Tamil</option>
                  </select>
                </label>
              </div>

              <button
                type="button"
                onClick={loadPreview}
                disabled={!benId || loadingPreview}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-teal-deep/5 px-4 py-2 text-xs font-extrabold text-teal-deep/70 transition-colors hover:bg-teal-deep/10 disabled:opacity-50"
              >
                {loadingPreview ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} strokeWidth={2.3} />}
                {t("notif.loadPreview", "Load the preview")}
              </button>

              {preview && (
                <div className="rounded-2xl bg-ivory/80 p-3.5">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">{t("notif.smsPreview", "SMS preview")}</p>
                    <span className="chip bg-teal-deep/5 text-[0.6rem] text-teal-deep/70">
                      <Phone size={9} /> {preview.phone}
                      {preview.phone_valid ? "" : " (invalid)"}
                    </span>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-xs font-medium leading-relaxed text-teal-deep/75">{preview.body}</p>
                  <p className={`mt-2 flex items-center gap-1.5 text-[0.68rem] font-bold ${preview.is_demo ? "text-pink" : "text-teal-deep/65"}`}>
                    <ShieldCheck size={12} /> {preview.demo_label}
                  </p>
                </div>
              )}

              <label className="block">
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">{t("notif.body", "Body")}</span>
                <textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} className={INPUT + " resize-y"} />
              </label>

              {selected && !selected.phone && (
                <p className="rounded-2xl bg-coral/10 px-3.5 py-2.5 text-xs font-semibold text-coral">
                  {t("notif.noPhone", "This beneficiary has no phone number on file.")}
                </p>
              )}

              <label className="flex cursor-pointer items-start gap-2.5 rounded-2xl bg-mint-soft/50 px-4 py-3">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#B96F85]" />
                <span className="text-xs font-semibold leading-relaxed text-teal-deep/75">
                  {t("notif.consentText", "I confirm that consent has been obtained for this notification.")}
                </span>
              </label>

              <div className="flex gap-3 pt-1">
                <button type="button" onClick={onClose} className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10">
                  {t("common.cancel")}
                </button>
                <button type="submit" disabled={saving} className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60">
                  {saving ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} strokeWidth={2.4} />}
                  {saving ? t("common.sending", "Sending…") : t("notif.sendNow", "Send")}
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
