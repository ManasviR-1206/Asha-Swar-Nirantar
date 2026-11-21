import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowUpCircle,
  CheckCircle,
  CheckCircle2,
  FileText,
  Filter,
  History,
  Loader2,
  PlayCircle,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  XCircle,
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

function statusChipStyle(status) {
  const s = (status || "").toLowerCase().replace("-", "_");
  if (s === "resolved") return "bg-mint-soft text-teal-deep";
  if (s === "dismissed") return "bg-midnight/10 text-midnight/70";
  if (s === "escalated") return "bg-coral/15 text-coral";
  if (s === "acknowledged") return "bg-lavender/20 text-midnight";
  if (s === "in_progress") return "bg-lavender/25 text-teal-deep";
  return "bg-coral/10 text-coral";
}

function fmtDate(v) {
  if (!v) return "";
  try {
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v);
    return d.toLocaleString();
  } catch {
    return String(v);
  }
}

function normStatus(s) {
  return (s || "new").toLowerCase().replace("-", "_");
}

export default function Alerts() {
  const { t } = useI18n();
  const [alerts, setAlerts] = useState(null); // null = initial loading; [] = loaded empty
  const [summary, setSummary] = useState(null); // backend aggregate counts
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [expandedId, setExpandedId] = useState(null);
  const [historyById, setHistoryById] = useState({});
  const [historyLoadingId, setHistoryLoadingId] = useState(null);
  const requestSeq = useRef(0);
  const didMount = useRef(false);

  const buildQuery = useCallback(() => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (severityFilter !== "all") params.set("severity", severityFilter);
    // Send status filter to backend (functional filters). "all" => no status filter.
    if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
    return params.toString();
  }, [q, severityFilter, statusFilter]);

  const load = useCallback(async ({ silent = false, background = false } = {}) => {
    const seq = ++requestSeq.current;
    if (!background) setLoading(true);
    setError("");
    try {
      const qs = buildQuery();
      const path = `/alerts${qs ? `?${qs}` : ""}`;
      const d = await api.get(path);
      if (seq !== requestSeq.current) return;
      setAlerts(Array.isArray(d?.alerts) ? d.alerts : []);
      // Use backend counts (scoped aggregates) for summary cards when provided
      if (d?.counts && typeof d.counts === "object") {
        setSummary(d.counts);
      } else {
        // fallback: fetch summary endpoint
        try {
          const s = await api.get("/alerts/summary");
          if (seq === requestSeq.current) setSummary(s?.counts || s || null);
        } catch {
          /* ignore secondary failure; keep prior summary */
        }
      }
    } catch (e) {
      if (seq !== requestSeq.current) return;
      const msg = e?.message || t("err.generic", "Something went wrong");
      setError(msg);
      // Do NOT convert backend failures into empty lists / zero-count success states
      // Keep alerts null/previous? set to null to force error UI (not empty state)
      setAlerts(null);
      setSummary(null);
      if (!silent && !background) {
        // Avoid repeated toasts on background/debounced reloads; show once on explicit/manual load
        showToast(msg, "error");
      }
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [buildQuery, t]);

  // Initial load and filter changes (status/severity) - reload
  useEffect(() => {
    load({ silent: didMount.current, background: false });
    didMount.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, severityFilter]);

  // Debounced search - background-style (no toast spam on failure)
  useEffect(() => {
    const id = setTimeout(() => {
      if (!didMount.current) return;
      load({ silent: true, background: true });
    }, 350);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const counts = useMemo(() => {
    const c = summary || {};
    const pick = (...keys) => {
      for (const k of keys) if (c[k] != null) return Number(c[k]) || 0;
      return 0;
    };
    return {
      new: pick("new", "open"),
      unresolved: pick("unresolved", "active"),
      high: pick("high_critical_unresolved", "high"),
      in_progress: pick("in_progress"),
      escalated: pick("escalated"),
      referral_pending: pick("referral_pending", "referred"),
      resolved: pick("resolved"),
      total: pick("total"),
    };
  }, [summary]);

  // Alerts are already filtered by backend; keep a defensive client filter for consistency
  const filtered = useMemo(() => alerts || [], [alerts]);

  const requireNote = (action) => {
    if (action === "escalate") {
      const note = window.prompt(t("alerts.prompt.escalate"), "");
      if (note == null) return null;
      if (!note.trim()) {
        showToast(t("alerts.noteRequired.escalate"), "error");
        return null;
      }
      return { note: note.trim() };
    }
    if (action === "resolve") {
      const note = window.prompt(t("alerts.prompt.resolve"), "");
      if (note == null) return null;
      if (!note.trim()) {
        showToast(t("alerts.noteRequired.resolve"), "error");
        return null;
      }
      return { note: note.trim() };
    }
    if (action === "dismiss") {
      const reason = window.prompt(t("alerts.prompt.dismiss"), "");
      if (reason == null) return null;
      if (!reason.trim()) {
        showToast(t("alerts.noteRequired.dismiss"), "error");
        return null;
      }
      return { reason: reason.trim(), note: reason.trim() };
    }
    if (action === "referral-initiated" || action === "mark-referral-initiated") {
      const note = window.prompt("Referral initiated note (optional):", "");
      if (note == null) return null;
      return { note: (note || "").trim() };
    }
    if (action === "referral" || action === "record-referral") {
      const facility = window.prompt("Referral facility (required):", "");
      if (facility == null) return null;
      if (!facility.trim()) { showToast("Referral facility is required.", "error"); return null; }
      const refDate = window.prompt("Referral date (YYYY-MM-DD, optional):", new Date().toISOString().slice(0,10)) || "";
      const refNote = window.prompt("Referral note (optional):", "") || "";
      return { referral_facility: facility.trim(), referral_date: refDate.trim(), referral_note: refNote.trim(), note: refNote.trim() };
    }
    if (action === "ack" || action === "in-progress") {
      const note = window.prompt(t("alerts.prompt.note"), "");
      if (note == null) return null;
      return { note: (note || "").trim() };
    }
    return { note: "" };
  };

  const fetchHistory = async (id) => {
    setHistoryLoadingId(id);
    try {
      const d = await api.get(`/alerts/${id}/history`);
      setHistoryById((m) => ({ ...m, [id]: d.history || [] }));
    } catch (e) {
      showToast(e.message || t("alerts.historyLoadError"), "error");
    } finally {
      setHistoryLoadingId(null);
    }
  };

  const doAction = async (id, action, label) => {
    const payload = requireNote(action);
    if (payload == null) return;
    setBusyId(`${id}-${action}`);
    try {
      await api.post(`/alerts/${id}/${action}`, payload);
      showToast(label, "success");
      await load({ silent: true });
      if (expandedId === id) {
        setHistoryById((m) => ({ ...m, [id]: undefined }));
        await fetchHistory(id);
      }
    } catch (e) {
      showToast(e.message || t("alerts.ackErr", "Could not update the alert."), "error");
    } finally {
      setBusyId(null);
    }
  };

  const toggleDetails = async (id) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (!historyById[id]) await fetchHistory(id);
  };

  const summaryLoading = loading && summary == null && alerts == null && !error;

  return (
    <div className="space-y-5">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="card-ivory flex items-start gap-3.5 p-5"
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-mint-soft">
          <ShieldCheck size={19} className="text-teal-deep" strokeWidth={2.2} />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold leading-relaxed text-teal-deep/70 sm:text-sm">
            {t(
              "alerts.disclaimer",
              "Rule-based detection using configured danger-sign logic. Alerts explain trigger and recommended action; AI does not diagnose. Seek emergency care and follow local clinical protocols."
            )}
          </p>
          <p className="mt-1 text-[11px] text-midnight/45">
            Alerts are generated from verified/recorded observations using approved deterministic rules, linked to actual beneficiary and visit records. Actions are persisted with audit history.
          </p>
        </div>
      </motion.div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: t("alerts.count.unresolved", "Active"), value: counts.unresolved, tone: "text-coral" },
          { label: t("alerts.count.highCritical", "High priority"), value: counts.high, tone: "text-coral" },
          { label: t("alerts.count.inProgress", "Acknowledged/In progress"), value: (counts.in_progress||0) + (counts.new||0), tone: "text-teal-deep" },
          { label: t("alerts.count.referralPending", "Referral pending"), value: counts.referral_pending, tone: "text-coral" },
          { label: t("alerts.count.resolved", "Resolved"), value: counts.resolved, tone: "text-teal-deep" },
          { label: t("alerts.count.total", "Total"), value: counts.total, tone: "text-midnight" },
        ].map((c) => (
          <div key={c.label} className="card-ivory p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-midnight/45">{c.label}</p>
            <p className={`mt-1 text-xl font-extrabold ${c.tone}`}>
              {summaryLoading ? "…" : error && summary == null ? "—" : c.value}
            </p>
          </div>
        ))}
      </div>

      <div className="card-ivory space-y-3 p-4 sm:p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full lg:max-w-md">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-midnight/35" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("alerts.searchPlaceholder")}
              className="input-base !pl-9"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-midnight/45"><Filter size={13} /> {t("common.filters")}</span>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input-base !w-auto !py-2 text-xs">
              <option value="active">{t("alerts.filter.active")}</option>
              <option value="all">{t("alerts.filter.all")}</option>
              <option value="new">{t("alerts.filter.new")}</option>
              <option value="acknowledged">{t("alerts.filter.ack")}</option>
              <option value="in_progress">{t("alerts.filter.inProgress")}</option>
              <option value="escalated">{t("alerts.filter.escalated")}</option>
              <option value="referral_pending">{t("alerts.filter.referralPending", "Referral pending")}</option>
              <option value="resolved_dismissed">{t("alerts.filter.resolvedDismissed")}</option>
              <option value="resolved">{t("alerts.filter.resolved")}</option>
              <option value="dismissed">{t("alerts.filter.dismissed")}</option>
            </select>
            <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} className="input-base !w-auto !py-2 text-xs">
              <option value="all">{t("alerts.severity.all")}</option>
              <option value="high">{t("alerts.severity.high")}</option>
              <option value="medium">{t("alerts.severity.medium")}</option>
              <option value="low">{t("alerts.severity.low")}</option>
            </select>
            <button type="button" onClick={() => load({ silent: false })} className="btn-secondary !px-3 !py-2 text-xs" disabled={loading && alerts != null}>
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> {t("common.refresh")}
            </button>
          </div>
        </div>
      </div>

      {error && alerts == null ? (
        <div className="card-ivory border border-coral/20 p-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-coral/10 text-coral">
              <AlertTriangle size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold text-midnight">{t("alerts.loadError")}</p>
              <p className="mt-1 text-xs text-midnight/65">{error}</p>
              <p className="mt-1 text-[11px] text-midnight/45">{t("alerts.loadErrorSub")}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => load({ silent: false })} className="btn-primary !px-3 !py-2 text-xs">
                  <RefreshCw size={13} /> {t("common.retry")}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : loading && alerts == null ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : alerts != null && filtered.length === 0 ? (
        <div className="card-ivory">
          <Empty
            icon={statusFilter === "resolved_dismissed" || statusFilter === "resolved" ? CheckCircle2 : ShieldCheck}
            title={statusFilter === "all" && !q.trim() && severityFilter === "all" ? t("alerts.empty", "No danger alerts") : t("alerts.noMatch")}
            subtitle={
              statusFilter === "all" && !q.trim() && severityFilter === "all"
                ? t("alerts.emptySub", "No rule-based danger alerts are currently recorded for beneficiaries in your access scope.")
                : t("alerts.noMatchSub")
            }
          />
        </div>
      ) : (
        <div className="space-y-3">
          {error && (
            <div className="rounded-2xl border border-coral/20 bg-coral/5 px-4 py-3 text-xs text-coral">
              {t("alerts.latestRefreshFailed")} {error}. {t("alerts.showingLast")}
            </div>
          )}
          <AnimatePresence initial={false}>
            {(filtered || []).map((a, idx) => {
              const st = normStatus(a.status);
              const isTerminal = ["resolved", "dismissed"].includes(st);
              const open = expandedId === a.id;
              const history = historyById[a.id];
              return (
                <motion.div
                  key={a.id}
                  layout
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ duration: 0.25, delay: Math.min(idx * 0.03, 0.2) }}
                  className={`card-ivory p-5 ${isTerminal ? "opacity-85" : "border-coral/25"}`}
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`chip ${severityChip(a.severity)}`}>
                          <ShieldAlert size={11} /> {a.severity || "alert"}
                        </span>
                        <span className={`chip ${statusChipStyle(st)}`}>{st.replace("_", " ")}</span>
                        {a.alert_category && <span className="chip bg-mint-soft/70 text-teal-deep">{a.alert_category}</span>}
                        <span className="chip bg-midnight/5 text-midnight/60">ID #{a.id}</span>
                      </div>

                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <p className="text-sm font-bold text-midnight">
                          {a.beneficiary_name || `Beneficiary #${a.beneficiary_id}`}
                        </p>
                        {a.household_name && <span className="text-xs text-midnight/50">{a.household_name}</span>}
                      </div>

                      <p className="mt-1 text-xs text-midnight/65"><span className="font-semibold">{t("alerts.detectedSign")}</span> {a.detected_danger_sign || a.phrase || "—"}</p>
                      <p className="mt-1 text-xs text-midnight/65"><span className="font-semibold">{t("alerts.sourceObservation")}</span> {a.source_observation || a.trigger_detail || a.triggering_event || (a.visit_id ? `Visit #${a.visit_id}` : "—")}</p>
                      <p className="mt-1 text-xs text-midnight/65"><span className="font-semibold">{t("alerts.reason")}</span> {a.reason || a.message || "—"}</p>
                      <p className="mt-1 text-xs font-semibold text-teal-deep/85"><span className="font-semibold text-teal-deep">{t("alerts.recommendedAction")}</span> {a.recommended_action || "Review and follow approved local protocol."}</p>

                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-midnight/45">
                        <span>{t("alerts.rule")} {a.rule_id || "—"}{a.rule_version ? ` (${a.rule_version})` : ""}</span>
                        <span>{t("alerts.visitRecord")} {a.visit_id ? `#${a.visit_id}` : t("common.notLinked")}</span>
                        <span>{t("alerts.detected")} {fmtDate(a.detection_timestamp || a.generated_at || a.created_at)}</span>
                        {a.updated_at && <span>{t("alerts.updated")} {fmtDate(a.updated_at)}</span>}
                      </div>
                      {a.clinical_source && (
                        <p className="mt-1 text-[11px] leading-relaxed text-midnight/45"><span className="font-semibold">{t("alerts.ruleSource")}</span> {a.clinical_source}</p>
                      )}
                      {a.escalation_note && st === "escalated" && (
                        <p className="mt-1 text-xs text-coral"><span className="font-semibold">{t("alerts.escalationNote")}</span> {a.escalation_note}</p>
                      )}
                      {(a.referral_facility || a.referred_at) && (
                        <p className="mt-1 text-xs text-teal-deep/80"><span className="font-semibold">Referral:</span> {a.referral_facility || "Recorded"}{a.referral_date ? ` · ${String(a.referral_date).slice(0,10)}` : ""}{a.referral_note ? ` · ${a.referral_note}` : ""}</p>
                      )}
                      {(a.resolved_note || a.dismiss_reason) && isTerminal && (
                        <p className="mt-1 text-xs text-midnight/60"><span className="font-semibold">{st === "dismissed" ? t("alerts.dismissReason") : t("alerts.resolutionNote")}:</span> {a.dismiss_reason || a.resolved_note}</p>
                      )}
                    </div>

                    <div className="flex flex-col items-stretch gap-2 lg:items-end">
                      <div className="flex flex-wrap gap-2 lg:justify-end">
                        <Link to={`/app/beneficiaries/${a.beneficiary_id}`} className="btn-secondary !px-3 !py-1.5 text-xs">
                          Beneficiary
                        </Link>
                        <button type="button" onClick={() => toggleDetails(a.id)} className="btn-secondary !px-3 !py-1.5 text-xs">
                          <History size={12} /> {open ? t("alerts.hide") : t("alerts.details")}
                        </button>
                      </div>
                      {!isTerminal && (
                        <div className="flex flex-wrap gap-2 lg:justify-end">
                          {(st === "new" || st === "open") && (
                            <button type="button" onClick={() => doAction(a.id, "ack", t("alerts.ackSuccess"))} disabled={busyId === `${a.id}-ack`} className="btn-secondary !px-3 !py-1.5 text-xs disabled:opacity-60">
                              {busyId === `${a.id}-ack` ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />} Ack
                            </button>
                          )}
                          {st !== "in_progress" && (
                            <button type="button" onClick={() => doAction(a.id, "in-progress", t("alerts.inProgressSuccess"))} disabled={busyId === `${a.id}-in-progress`} className="btn-secondary !px-3 !py-1.5 text-xs disabled:opacity-60">
                              {busyId === `${a.id}-in-progress` ? <Loader2 size={12} className="animate-spin" /> : <PlayCircle size={12} />} In progress
                            </button>
                          )}
                          <button type="button" onClick={() => doAction(a.id, "referral-initiated", "Referral initiated.")} disabled={busyId === `${a.id}-referral-initiated`} className="btn-secondary !px-3 !py-1.5 text-xs disabled:opacity-60">
                            {busyId === `${a.id}-referral-initiated` ? <Loader2 size={12} className="animate-spin" /> : <ArrowUpCircle size={12} />} Referral initiated
                          </button>
                          <button type="button" onClick={() => doAction(a.id, "record-referral", "Referral recorded.")} disabled={busyId === `${a.id}-record-referral`} className="btn-secondary !px-3 !py-1.5 text-xs disabled:opacity-60">
                            {busyId === `${a.id}-record-referral` ? <Loader2 size={12} className="animate-spin" /> : <ArrowUpCircle size={12} />} Record referral
                          </button>
                          <button type="button" onClick={() => doAction(a.id, "escalate", t("alerts.escalateSuccess"))} disabled={busyId === `${a.id}-escalate`} className="btn-secondary !px-3 !py-1.5 text-xs disabled:opacity-60">
                            {busyId === `${a.id}-escalate` ? <Loader2 size={12} className="animate-spin" /> : <ArrowUpCircle size={12} />} Escalate
                          </button>
                          <button type="button" onClick={() => doAction(a.id, "resolve", t("alerts.resolveSuccess"))} disabled={busyId === `${a.id}-resolve`} className="btn-primary !px-3 !py-1.5 text-xs disabled:opacity-60">
                            {busyId === `${a.id}-resolve` ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />} Resolve
                          </button>
                          <button type="button" onClick={() => doAction(a.id, "dismiss", t("alerts.dismissSuccess"))} disabled={busyId === `${a.id}-dismiss`} className="btn-secondary !border-coral/30 !px-3 !py-1.5 text-xs !text-coral disabled:opacity-60">
                            {busyId === `${a.id}-dismiss` ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />} Dismiss
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  <AnimatePresence initial={false}>
                    {open && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="mt-4 border-t border-midnight/10 pt-4">
                          <div className="grid gap-3 md:grid-cols-2">
                            <div className="rounded-2xl bg-white/60 p-3 text-xs text-midnight/65">
                              <p className="mb-1 font-semibold text-midnight/75"><FileText size={12} className="mr-1 inline" /> {t("alerts.alertDetails")}</p>
                              <p><span className="font-semibold">{t("alerts.alertId")}</span> {a.id}</p>
                              <p><span className="font-semibold">{t("alerts.beneficiary")}:</span> {a.beneficiary_name || "—"} (ID {a.beneficiary_id})</p>
                              <p><span className="font-semibold">{t("alerts.dataOrigin")}</span> {a.beneficiary_data_origin || "registered"}</p>
                              <p><span className="font-semibold">{t("alerts.household")}</span> {a.household_name || (a.household_id ? `#${a.household_id}` : "—")}</p>
                              <p><span className="font-semibold">{t("alerts.detectedSign")}</span> {a.detected_danger_sign || a.phrase || "—"}</p>
                              <p><span className="font-semibold">{t("alerts.sourceObservation")}</span> {a.source_observation || (a.visit_id ? `Visit #${a.visit_id}` : "Not linked")}</p>
                              <p><span className="font-semibold">{t("alerts.triggerValue")}</span> {a.trigger_value || "—"}</p>
                              <p><span className="font-semibold">{t("alerts.detectionTimestamp")}</span> {fmtDate(a.detection_timestamp || a.created_at)}</p>
                              <p><span className="font-semibold">{t("alerts.assignedWorker")}</span> {a.assigned_worker_id ? `#${a.assigned_worker_id}` : t("alerts.unassigned")}</p>
                              <p><span className="font-semibold">Referral facility:</span> {a.referral_facility || "—"}</p>
                              <p><span className="font-semibold">Referral date:</span> {a.referral_date ? String(a.referral_date).slice(0,10) : "—"}</p>
                              <p><span className="font-semibold">Referral note:</span> {a.referral_note || "—"}</p>
                            </div>
                            <div className="rounded-2xl bg-white/60 p-3 text-xs text-midnight/65">
                              <p className="mb-1 font-semibold text-midnight/75"><History size={12} className="mr-1 inline" /> {t("alerts.history")}</p>
                              {historyLoadingId === a.id ? (
                                <div className="flex items-center gap-2 text-midnight/50"><Loader2 size={12} className="animate-spin" /> {t("alerts.loadingHistory")}</div>
                              ) : !history || history.length === 0 ? (
                                <p className="text-midnight/45">{t("alerts.noHistory")}</p>
                              ) : (
                                <ul className="space-y-2">
                                  {history.map((h) => (
                                    <li key={h.id} className="rounded-xl border border-midnight/10 bg-white/70 p-2">
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <span className="font-semibold text-midnight/75">{h.action}</span>
                                        <span className="text-[11px] text-midnight/45">{fmtDate(h.created_at)}</span>
                                      </div>
                                      <p className="mt-0.5 text-[11px] text-midnight/55">{t("alerts.by")} {h.actor_label || "system"}{h.actor_id ? ` (#${h.actor_id})` : ""}</p>
                                      {h.note && <p className="mt-0.5 text-[11px] text-midnight/60">{h.note}</p>}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          </div>
                          <p className="mt-3 text-[11px] text-midnight/45">
                            {t("alerts.factualRecord")}
                          </p>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
