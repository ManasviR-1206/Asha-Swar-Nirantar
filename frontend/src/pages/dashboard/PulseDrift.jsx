import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Eye,
  Filter,
  History,
  Loader2,
  MessageSquare,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  UserRound,
  Users,
  X,
  XCircle,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { categoryLabel, followupTypeLabel, statusLabel } from "../../lib/labels.js";

const STATUSES = ["upcoming", "due", "overdue", "completed", "cancelled"];
const PRIORITIES = ["low", "normal", "high", "urgent"];

const statusMeta = {
  upcoming: { label: "Upcoming", cls: "bg-mint-soft text-teal-deep", icon: CalendarClock },
  due: { label: "Due", cls: "bg-lavender/25 text-midnight", icon: Clock3 },
  overdue: { label: "Overdue", cls: "bg-coral/15 text-coral", icon: AlertCircle },
  completed: { label: "Completed", cls: "bg-teal-deep/10 text-teal-deep", icon: CheckCircle2 },
  cancelled: { label: "Cancelled", cls: "bg-teal-deep/5 text-teal-deep/55", icon: XCircle },
};

const INPUT = "w-full rounded-xl border border-teal-deep/10 bg-ivory/70 px-3 py-2 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none";
const LABEL = "block text-[0.68rem] font-extrabold uppercase tracking-wide text-teal-deep/50 mb-1";

function fmtDate(d) { return d ? String(d).slice(0, 10) : "—"; }

export default function PulseDrift() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({ upcoming: 0, due: 0, overdue: 0, completed: 0, cancelled: 0 });
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [statusTab, setStatusTab] = useState("all");
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [refreshKey, setRefreshKey] = useState(0);

  const [workers, setWorkers] = useState([]);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [modal, setModal] = useState(null); // {type, item}
  const [history, setHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [actionForm, setActionForm] = useState({});
  const [view, setView] = useState("tasks"); // tasks | sms
  const [smsHistory, setSmsHistory] = useState([]);
  const [smsStats, setSmsStats] = useState(null);
  const [smsLoading, setSmsLoading] = useState(false);
  const [smsPreview, setSmsPreview] = useState(null);
  const [smsPreviewLoading, setSmsPreviewLoading] = useState(false);
  const [smsSendBusyId, setSmsSendBusyId] = useState(null);
  const [smsConsent, setSmsConsent] = useState({});
  const [smsConsentGranted, setSmsConsentGranted] = useState(false);
  const [smsTarget, setSmsTarget] = useState(null); // {followup, beneficiary}

  useEffect(() => {
    const timer = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(timer);
  }, [q]);

  useEffect(() => { setPage(1); }, [statusTab, qDebounced, category, priority]);

  useEffect(() => {
    api.get("/auth/workers").then((d) => setWorkers(d.workers || [])).catch(() => {});
    api.get("/beneficiaries").then((d) => setBeneficiaries(d.beneficiaries || [])).catch(() => {});
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError("");
    const params = new URLSearchParams();
    if (statusTab !== "all") params.set("status", statusTab);
    if (qDebounced) params.set("q", qDebounced);
    if (category) params.set("category", category);
    if (priority) params.set("priority", priority);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    const ben = searchParams.get("beneficiary");
    if (ben) params.set("beneficiary_id", ben);
    api
      .get(`/follow-ups?${params.toString()}`)
      .then((d) => {
        if (!alive) return;
        setItems(d.items || []);
        setCounts(d.counts || { upcoming: 0, due: 0, overdue: 0, completed: 0, cancelled: 0 });
        setTotal(d.total || 0);
      })
      .catch((e) => {
        if (!alive) return;
        const msg = e?.message || "Could not load follow-ups.";
        setLoadError(msg);
        showToast(msg, "error");
      })
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [statusTab, qDebounced, category, priority, page, pageSize, refreshKey, searchParams]);

  const categories = useMemo(() => {
    const set = new Set((items || []).map((i) => (i.category || i.type || "").trim()).filter(Boolean));
    return Array.from(set).sort();
  }, [items]);

  const pages = Math.max(1, Math.ceil(total / pageSize));
  const refresh = () => setRefreshKey((k) => k + 1);

  const openModal = (type, item = null) => {
    setModal({ type, item });
    if (type === "complete") setActionForm({ completion_notes: "" });
    else if (type === "cancel") setActionForm({ reason: "" });
    else if (type === "reschedule") setActionForm({ due_date: item?.due_date || "" , notes: "" });
    else if (type === "priority") setActionForm({ priority: item?.priority || "normal" });
    else if (type === "reassign") setActionForm({ assigned_worker_id: item?.assigned_worker_id || "" });
    else if (type === "create") setActionForm({ beneficiary_id: searchParams.get("beneficiary") || "", household_id: "", type: "anc", category: "anc", due_date: "", priority: "normal", reason: "", description: "", recommended_action: "", assigned_worker_id: "", notes: "" });
    else setActionForm({});
  };
  const closeModal = () => { setModal(null); setActionForm({}); setHistory(null); };

  const runAction = async () => {
    if (!modal) return;
    const { type, item } = modal;
    setSaving(true);
    try {
      if (type === "complete") {
        await api.post(`/follow-ups/${item.id}/complete`, { notes: actionForm.completion_notes || "", note: actionForm.completion_notes || "" });
        showToast("Follow-up completed.", "success");
      } else if (type === "cancel") {
        if (!(actionForm.reason || "").trim()) { showToast("Cancellation reason is required.", "warn"); setSaving(false); return; }
        await api.post(`/follow-ups/${item.id}/cancel`, { reason: actionForm.reason, notes: actionForm.reason });
        showToast("Follow-up cancelled.", "success");
      } else if (type === "reschedule") {
        if (!actionForm.due_date) { showToast("Please select a due date.", "warn"); setSaving(false); return; }
        await api.post(`/follow-ups/${item.id}/reschedule`, { due_date: actionForm.due_date, notes: actionForm.notes || "" });
        showToast("Follow-up rescheduled.", "success");
      } else if (type === "priority") {
        await api.patch(`/follow-ups/${item.id}`, { priority: actionForm.priority || "normal" });
        showToast("Priority updated.", "success");
      } else if (type === "reassign") {
        const wid = Number(actionForm.assigned_worker_id);
        if (!wid) { showToast("Select a worker.", "warn"); setSaving(false); return; }
        await api.post(`/follow-ups/${item.id}/reassign`, { assigned_worker_id: wid });
        showToast("Worker reassigned.", "success");
      } else if (type === "create") {
        if (!actionForm.due_date) { showToast("Due date is required.", "warn"); setSaving(false); return; }
        if (!actionForm.beneficiary_id && !actionForm.household_id) { showToast("Select a beneficiary or household.", "warn"); setSaving(false); return; }
        const payload = {
          beneficiary_id: actionForm.beneficiary_id ? Number(actionForm.beneficiary_id) : null,
          household_id: actionForm.household_id ? Number(actionForm.household_id) : null,
          type: actionForm.type || "general",
          category: actionForm.category || actionForm.type || "general",
          due_date: actionForm.due_date,
          priority: actionForm.priority || "normal",
          reason: actionForm.reason || "",
          description: actionForm.description || "",
          recommended_action: actionForm.recommended_action || "",
          assigned_worker_id: actionForm.assigned_worker_id ? Number(actionForm.assigned_worker_id) : null,
          notes: actionForm.notes || "",
          source_type: "manual",
        };
        await api.post("/follow-ups", payload);
        showToast("Follow-up created.", "success");
      }
      closeModal();
      refresh();
    } catch (e) {
      showToast(e.message || "Action failed.", "error");
    } finally {
      setSaving(false);
    }
  };

  const openHistory = async (item) => {
    setModal({ type: "history", item });
    setHistory(null);
    setHistoryLoading(true);
    try {
      const d = await api.get(`/follow-ups/${item.id}/history`);
      setHistory(d.history || []);
    } catch (e) {
      showToast(e.message || "Could not load history.", "error");
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadSms = async () => {
    setSmsLoading(true);
    try {
      const [h, s] = await Promise.all([
        api.get("/notifications/sms").catch(() => ({ notifications: [] })),
        api.get("/notifications/stats").catch(() => null),
      ]);
      setSmsHistory(h.notifications || []);
      setSmsStats(s);
    } finally {
      setSmsLoading(false);
    }
  };

  useEffect(() => { if (view === "sms") loadSms(); }, [view, refreshKey]);

  const beneficiaryById = useMemo(() => {
    const m = new Map();
    for (const b of beneficiaries || []) m.set(b.id, b);
    return m;
  }, [beneficiaries]);

  const smsForBeneficiary = (beneficiaryId) =>
    (smsHistory || []).filter((n) => Number(n.beneficiary_id) === Number(beneficiaryId));

  const lastSmsForBeneficiary = (beneficiaryId) => {
    const rows = smsForBeneficiary(beneficiaryId);
    return rows.length ? rows[0] : null;
  };

  const loadConsentFor = async (beneficiaryId) => {
    if (!beneficiaryId) return;
    try {
      const d = await api.get(`/notifications/consent/${beneficiaryId}`);
      const rows = d.consent || d || [];
      const latestSms = (Array.isArray(rows) ? rows : []).find((r) => (r.channel || "sms") === "sms");
      setSmsConsent((m) => ({ ...m, [beneficiaryId]: latestSms || null }));
    } catch {
      setSmsConsent((m) => ({ ...m, [beneficiaryId]: null }));
    }
  };

  const openSmsPreview = async (fu) => {
    const ben = beneficiaryById.get(fu.beneficiary_id);
    if (!fu?.beneficiary_id || !ben) { showToast("Select a follow-up with a linked beneficiary.", "warn"); return; }
    setSmsTarget({ followup: fu, beneficiary: ben });
    setSmsPreview(null);
    setSmsConsentGranted(false);
    setSmsPreviewLoading(true);
    await loadConsentFor(fu.beneficiary_id);
    try {
      const p = await api.post("/notifications/sms/preview", {
        beneficiary_id: fu.beneficiary_id,
        type: fu.type || fu.category || "follow_up",
        language: "en",
      });
      setSmsPreview(p);
    } catch (e) {
      showToast(e.message || "Could not load SMS preview.", "error");
    } finally {
      setSmsPreviewLoading(false);
    }
  };

  const sendSmsReminder = async () => {
    if (!smsTarget?.followup || !smsTarget?.beneficiary) return;
    const fu = smsTarget.followup;
    const ben = smsTarget.beneficiary;
    if (!smsConsentGranted) { showToast("Consent confirmation is required before sending SMS.", "warn"); return; }
    if (!smsPreview?.phone_valid) { showToast("A valid beneficiary phone number is required.", "warn"); return; }
    if (smsStats && smsStats.sms_compliance_approved === false) { showToast("SMS is blocked: compliance approval is required.", "warn"); return; }
    if (smsStats && !smsStats.sms_provider_configured) { showToast("SMS provider not live-configured; a demo/non-sent record may be created.", "info"); }
    setSmsSendBusyId(fu.id);
    try {
      const res = await api.post("/notifications/sms/send", {
        beneficiary_id: ben.id,
        type: fu.type || fu.category || "follow_up",
        language: "en",
        body: smsPreview?.body || undefined,
        follow_up_id: fu.id,
        consent_granted: true,
      });
      showToast(res.is_demo ? "Demo notification recorded — NOT actually sent." : "SMS submitted to provider.", res.is_demo ? "info" : "success");
      setSmsTarget(null);
      setSmsPreview(null);
      setSmsConsentGranted(false);
      await loadSms();
    } catch (e) {
      showToast(e.message || "SMS send failed.", "error");
      await loadSms();
    } finally {
      setSmsSendBusyId(null);
    }
  };

  const tabs = [
    { key: "all", label: "All", count: (counts.upcoming||0)+(counts.due||0)+(counts.overdue||0)+(counts.completed||0)+(counts.cancelled||0) },
    { key: "upcoming", label: "Upcoming", count: counts.upcoming || 0 },
    { key: "due", label: "Due", count: counts.due || 0 },
    { key: "overdue", label: "Overdue", count: counts.overdue || 0 },
    { key: "completed", label: "Completed", count: counts.completed || 0 },
    { key: "cancelled", label: "Cancelled", count: counts.cancelled || 0 },
  ];

  return (
    <div className="space-y-5">
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          <h2 className="text-xl font-extrabold text-teal-deep sm:text-2xl">{t("drift.title", "Pulse Drift")}</h2>
          <p className="mt-1.5 text-sm font-medium leading-relaxed text-teal-deep/55">
            Persistent follow-up task management. Track upcoming, due, overdue, completed, and cancelled follow-ups with full history and actions.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setView(view === "sms" ? "tasks" : "sms")} className={`flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-bold ${view==="sms" ? "bg-teal-deep text-white" : "bg-teal-deep/5 text-teal-deep/70 hover:bg-teal-deep/10"}`}><MessageSquare size={15}/> SMS Reminders</button>
          <button onClick={refresh} className="flex items-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/70 hover:bg-teal-deep/10"><RefreshCw size={15}/> Refresh</button>
          <button onClick={() => openModal("create")} className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm"><Plus size={16}/> Create follow-up</button>
        </div>
      </motion.div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {STATUSES.map((s) => {
          const m = statusMeta[s];
          const Icon = m.icon;
          return (
            <button key={s} onClick={() => setStatusTab(s)} className={`card-ivory flex items-center gap-3 p-3 text-left transition-all ${statusTab===s ? 'ring-2 ring-mint' : 'hover:-translate-y-0.5'}`}>
              <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${m.cls}`}><Icon size={16}/></div>
              <div><p className="text-[0.65rem] font-extrabold uppercase tracking-wide text-teal-deep/45">{m.label}</p><p className="text-lg font-extrabold leading-none text-teal-deep">{counts[s] || 0}</p></div>
            </button>
          );
        })}
      </div>

      <div className="card-ivory p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button key={tab.key} onClick={() => setStatusTab(tab.key)} className={`chip px-3.5 py-1.5 transition-all ${statusTab===tab.key ? 'bg-teal-deep text-white shadow-soft' : 'bg-teal-deep/5 text-teal-deep/60 hover:bg-mint-soft hover:text-teal-deep'}`}>
              {tab.label} <span className="ml-1 opacity-80">({tab.count})</span>
            </button>
          ))}
        </div>
        <div className="grid gap-2 sm:grid-cols-4">
          <label className="sm:col-span-2">
            <span className={LABEL}><Search size={11} className="inline mr-1"/>Search</span>
            <input value={q} onChange={(e)=>setQ(e.target.value)} placeholder="Beneficiary, household, reason, notes…" className={INPUT} />
          </label>
          <label>
            <span className={LABEL}>Category / Type</span>
            <select value={category} onChange={(e)=>setCategory(e.target.value)} className={INPUT}>
              <option value="">All</option>
              {categories.map((c)=><option key={c} value={c}>{followupTypeLabel(c,t) || categoryLabel(c,t) || c}</option>)}
            </select>
          </label>
          <label>
            <span className={LABEL}>Priority</span>
            <select value={priority} onChange={(e)=>setPriority(e.target.value)} className={INPUT}>
              <option value="">All priorities</option>
              {PRIORITIES.map((p)=><option key={p} value={p}>{p}</option>)}
            </select>
          </label>
        </div>
      </div>

      {view === "sms" ? (
        <div className="space-y-4">
          <div className="card-ivory p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-extrabold text-teal-deep">SMS Reminders (Pulse Drift)</p>
                <p className="text-xs text-teal-deep/55">Preview and send follow-up reminders using the existing TextBee integration. SMS is sent only with explicit consent, compliance/config checks, and confirmation. No sensitive health details are included.</p>
              </div>
              <div className="flex flex-wrap gap-2 text-[11px] font-bold">
                <span className={`chip ${smsStats?.sms_compliance_approved ? "bg-mint-soft text-teal-deep" : "bg-coral/10 text-coral"}`}>Compliance: {smsStats?.sms_compliance_approved ? "approved" : "blocked"}</span>
                <span className={`chip ${smsStats?.sms_provider_configured ? "bg-mint-soft text-teal-deep" : "bg-lavender/20 text-midnight"}`}>Provider: {smsStats?.sms_provider_configured ? (smsStats?.sms_provider || "configured") : "not live-configured"}</span>
                <span className="chip bg-teal-deep/5 text-teal-deep/60">History: {(smsHistory||[]).length}</span>
              </div>
            </div>
          </div>

          <div className="card-ivory p-4">
            <p className="mb-3 text-xs font-extrabold uppercase tracking-wide text-teal-deep/55">Follow-up SMS actions</p>
            {smsLoading ? <div className="flex items-center gap-2 text-sm text-teal-deep/60"><Loader2 size={16} className="animate-spin"/> Loading SMS data…</div> : (
              <div className="space-y-2">
                {(items || []).filter(fu => fu.beneficiary_id).map((fu) => {
                  const ben = beneficiaryById.get(fu.beneficiary_id);
                  const phone = ben?.phone || "—";
                  const last = lastSmsForBeneficiary(fu.beneficiary_id);
                  const consent = smsConsent[fu.beneficiary_id];
                  const terminal = fu.status === "completed" || fu.status === "cancelled";
                  return (
                    <div key={`sms-${fu.id}`} className="rounded-2xl border border-teal-deep/10 p-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-extrabold text-teal-deep">{fu.beneficiary_name || ben?.name || "Beneficiary"}</p>
                          <p className="text-xs text-teal-deep/55"><Phone size={11} className="inline mr-1"/>{phone} · Due {fmtDate(fu.due_date)} · {followupTypeLabel(fu.category || fu.type, t) || fu.category || fu.type}</p>
                          <p className="text-xs text-teal-deep/55">Reason: {fu.reason || fu.description || "Follow-up reminder"}</p>
                          <div className="mt-1 flex flex-wrap gap-2 text-[11px]">
                            <span className="chip bg-teal-deep/5 text-teal-deep/60">Follow-up: {fu.status}</span>
                            <span className={`chip ${last ? (last.is_demo ? "bg-lavender/20 text-midnight" : (last.status==="failed"?"bg-coral/10 text-coral":"bg-mint-soft text-teal-deep")) : "bg-teal-deep/5 text-teal-deep/50"}`}>Last SMS: {last ? `${last.is_demo ? "DEMO" : last.status}${last.created_at ? ` (${String(last.created_at).slice(0,16).replace("T"," ")})` : ""}` : "none"}</span>
                            <span className={`chip ${consent?.granted ? "bg-mint-soft text-teal-deep" : "bg-coral/10 text-coral"}`}>Consent: {consent?.granted ? "recorded" : "not recorded/unknown"}</span>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button onClick={() => openSmsPreview(fu)} disabled={smsPreviewLoading} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10 flex items-center gap-1.5"><Eye size={12}/> Preview / Send</button>
                          {last?.status === "failed" ? <button onClick={() => openSmsPreview(fu)} className="rounded-full bg-coral/10 px-3 py-1.5 text-xs font-bold text-coral hover:bg-coral/15">Retry failed</button> : null}
                        </div>
                      </div>
                      {terminal ? <p className="mt-2 text-[11px] text-teal-deep/45">Terminal follow-up: sending is possible only when appropriate and explicitly confirmed; avoid duplicate/unnecessary reminders.</p> : null}
                    </div>
                  );
                })}
                {(items||[]).filter(fu=>fu.beneficiary_id).length === 0 ? <p className="text-sm text-teal-deep/55">No beneficiary-linked follow-ups in current filters.</p> : null}
              </div>
            )}
          </div>

          <div className="card-ivory p-4">
            <p className="mb-3 text-xs font-extrabold uppercase tracking-wide text-teal-deep/55">SMS delivery history</p>
            <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
              {(smsHistory||[]).length === 0 ? <p className="text-sm text-teal-deep/55">No SMS notifications recorded.</p> : (smsHistory||[]).map((n) => (
                <div key={n.id} className="rounded-xl border border-teal-deep/10 p-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-extrabold text-teal-deep">{beneficiaryById.get(n.beneficiary_id)?.name || `Beneficiary #${n.beneficiary_id}`}</p>
                    <span className={`chip ${n.is_demo ? "bg-lavender/20 text-midnight" : n.status==="failed" ? "bg-coral/10 text-coral" : "bg-mint-soft text-teal-deep"}`}>{n.is_demo ? "DEMO — NOT SENT" : n.status}</span>
                  </div>
                  <p className="text-teal-deep/55">{n.phone || "—"} · {n.type} · {String(n.created_at||"").replace("T"," ").slice(0,16)}</p>
                  <p className="mt-1 text-teal-deep/70 whitespace-pre-wrap">{n.body}</p>
                  {n.provider_note ? <p className="mt-1 text-[11px] text-teal-deep/45">{n.provider_note}</p> : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : loading ? (
        <div className="space-y-3">{Array.from({length:4}).map((_,i)=><SkeletonCard key={i}/>)}</div>
      ) : loadError ? (
        <div className="card-ivory p-6 text-center">
          <p className="text-sm font-extrabold text-teal-deep">Could not load follow-ups</p>
          <p className="mt-1 text-xs text-teal-deep/60">{loadError}</p>
          <button onClick={refresh} className="btn-mint mt-4 px-4 py-2 text-sm">Retry</button>
        </div>
      ) : items.length === 0 ? (
        <div className="card-ivory">
          <Empty icon={CalendarClock} title="No follow-ups found" subtitle={statusTab === 'all' ? 'No follow-ups are visible in this mode. In explicit demo mode, existing synthetic demo follow-ups are shown; in normal mode, only genuine operational records are shown. You can also create a follow-up manually or record a confirmed visit.' : `No ${statusTab} follow-ups match the current filters.`} action={<button onClick={()=>openModal('create')} className="btn-mint px-5 py-2.5 text-sm flex items-center gap-2"><Plus size={15}/> Create follow-up</button>} />
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((fu, idx) => {
            const sm = statusMeta[fu.status] || statusMeta.upcoming;
            const Icon = sm.icon;
            const isHousehold = !!fu.household_id && !fu.beneficiary_id;
            const benHref = fu.beneficiary_id ? `/app/beneficiaries/${fu.beneficiary_id}` : (fu.household_id ? `/app/households/${fu.household_id}` : null);
            const threadHref = fu.beneficiary_id ? `/app/beneficiaries/${fu.beneficiary_id}` : null;
            const terminal = fu.status === 'completed' || fu.status === 'cancelled';
            return (
              <motion.div key={fu.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: Math.min(idx*0.03,0.25) }} className="card-ivory p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-extrabold text-teal-deep">{fu.beneficiary_name || fu.household_label || 'Unassigned subject'}</span>
                      {fu.household_label && fu.beneficiary_name ? <span className="chip bg-teal-deep/5 text-teal-deep/60"><Users size={10}/> {fu.household_label}</span> : null}
                      <span className={`chip ${sm.cls}`}><Icon size={11}/> {sm.label}</span>
                      <span className="chip bg-teal-deep/5 text-teal-deep/60">{followupTypeLabel(fu.category || fu.type, t) || fu.category || fu.type}</span>
                      <span className={`chip ${fu.priority==='urgent'||fu.priority==='high' ? 'bg-coral/15 text-coral' : 'bg-teal-deep/5 text-teal-deep/60'}`}>Priority: {fu.priority || 'normal'}</span>
                    </div>
                    <p className="mt-1.5 text-sm font-semibold text-teal-deep/80">{fu.reason || fu.description || 'Follow-up required'}</p>
                    {fu.description && fu.description !== fu.reason ? <p className="mt-0.5 text-xs text-teal-deep/55">{fu.description}</p> : null}
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium text-teal-deep/55">
                      <span className="flex items-center gap-1"><CalendarClock size={12}/> Due: <b className="text-teal-deep/75">{fmtDate(fu.due_date)}</b></span>
                      <span className="flex items-center gap-1"><UserRound size={12}/> Assigned: <b className="text-teal-deep/75">{fu.assigned_worker_name || (fu.assigned_worker_id ? `Worker #${fu.assigned_worker_id}` : 'Unassigned')}</b></span>
                      {fu.overdue_days > 0 ? <span className="text-coral font-bold">{fu.overdue_days} day(s) overdue</span> : null}
                      {fu.visit_id ? <span>Source visit #{fu.visit_id}</span> : (fu.source_ref ? <span>Source: {fu.source_ref}</span> : null)}
                    </div>
                    {fu.recommended_action ? <p className="mt-1.5 text-[0.72rem] font-medium text-teal-deep/55">Recommended: {fu.recommended_action}</p> : null}
                    {fu.status === 'completed' && fu.completion_notes ? <p className="mt-1.5 rounded-xl bg-mint/10 px-3 py-2 text-xs font-medium text-teal-deep/70"><b>Completion notes:</b> {fu.completion_notes}</p> : null}
                    {fu.status === 'cancelled' && fu.cancellation_reason ? <p className="mt-1.5 rounded-xl bg-coral/5 px-3 py-2 text-xs font-medium text-coral/80"><b>Cancellation reason:</b> {fu.cancellation_reason}</p> : null}
                  </div>
                  <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:max-w-[320px] sm:justify-end">
                    {fu.beneficiary_id ? <Link to={benHref} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10 flex items-center gap-1.5"><Eye size={12}/> View beneficiary</Link> : null}
                    {fu.household_id && !fu.beneficiary_id ? <Link to={benHref} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10 flex items-center gap-1.5"><Eye size={12}/> View household</Link> : null}
                    {threadHref ? <Link to={threadHref} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10 flex items-center gap-1.5"><Eye size={12}/> View Pulse Thread</Link> : null}
                    <button onClick={()=>openHistory(fu)} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10 flex items-center gap-1.5"><History size={12}/> History</button>
                    {!terminal && <>
                      <button onClick={()=>openModal('complete',fu)} className="rounded-full bg-mint-soft px-3 py-1.5 text-xs font-bold text-teal-deep hover:brightness-95 flex items-center gap-1.5"><CheckCircle2 size={12}/> Complete</button>
                      <button onClick={()=>openModal('reschedule',fu)} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10 flex items-center gap-1.5"><CalendarClock size={12}/> Reschedule</button>
                      <button onClick={()=>openModal('priority',fu)} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10">Change priority</button>
                      <button onClick={()=>openModal('reassign',fu)} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 hover:bg-teal-deep/10">Reassign</button>
                      <button onClick={()=>openModal('cancel',fu)} className="rounded-full bg-coral/10 px-3 py-1.5 text-xs font-bold text-coral hover:bg-coral/15 flex items-center gap-1.5"><XCircle size={12}/> Cancel</button>
                    </>}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between gap-3 card-ivory p-3">
          <p className="text-xs font-semibold text-teal-deep/55">Page {page} of {pages} · {total} task(s)</p>
          <div className="flex gap-2">
            <button disabled={page<=1} onClick={()=>setPage(p=>Math.max(1,p-1))} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 disabled:opacity-40 flex items-center gap-1"><ChevronLeft size={14}/> Prev</button>
            <button disabled={page>=pages} onClick={()=>setPage(p=>Math.min(pages,p+1))} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70 disabled:opacity-40 flex items-center gap-1">Next <ChevronRight size={14}/></button>
          </div>
        </div>
      )}

      <AnimatePresence>
        {modal && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-50 flex items-end justify-center bg-teal-deep/50 backdrop-blur-sm sm:items-center sm:p-6" onClick={closeModal}>
            <motion.div initial={{y:40,opacity:0,scale:0.98}} animate={{y:0,opacity:1,scale:1}} exit={{y:30,opacity:0,scale:0.98}} onClick={(e)=>e.stopPropagation()} className="card-ivory max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-b-none p-6 sm:rounded-3xl">
              <div className="mb-4 flex items-start justify-between gap-3">
                <h3 className="text-lg font-extrabold text-teal-deep">
                  {modal.type === 'complete' && 'Complete follow-up'}
                  {modal.type === 'cancel' && 'Cancel follow-up'}
                  {modal.type === 'reschedule' && 'Reschedule follow-up'}
                  {modal.type === 'priority' && 'Change priority'}
                  {modal.type === 'reassign' && 'Reassign worker'}
                  {modal.type === 'history' && `Follow-up history #${modal.item?.id}`}
                  {modal.type === 'create' && 'Create follow-up'}
                </h3>
                <button onClick={closeModal} className="rounded-full bg-teal-deep/5 p-2 text-teal-deep/50"><X size={16}/></button>
              </div>

              {modal.type === 'complete' && (
                <div className="space-y-3">
                  <p className="text-sm text-teal-deep/65">Mark <b>{modal.item?.beneficiary_name || modal.item?.household_label || 'this follow-up'}</b> as completed.</p>
                  <label><span className={LABEL}>Completion notes</span><textarea className={INPUT} rows={4} value={actionForm.completion_notes||''} onChange={(e)=>setActionForm(f=>({...f,completion_notes:e.target.value}))} placeholder="What was done, observations, outcome (factual)…"/></label>
                </div>
              )}
              {modal.type === 'cancel' && (
                <div className="space-y-3">
                  <p className="text-sm text-teal-deep/65">Cancel this follow-up. The record and history will be preserved.</p>
                  <label><span className={LABEL}>Cancellation reason *</span><textarea className={INPUT} rows={4} value={actionForm.reason||''} onChange={(e)=>setActionForm(f=>({...f,reason:e.target.value}))} placeholder="Reason for cancellation" required/></label>
                </div>
              )}
              {modal.type === 'reschedule' && (
                <div className="space-y-3">
                  <label><span className={LABEL}>New due date *</span><input type="date" className={INPUT} value={actionForm.due_date||''} onChange={(e)=>setActionForm(f=>({...f,due_date:e.target.value}))} /></label>
                  <label><span className={LABEL}>Notes (optional)</span><textarea className={INPUT} rows={3} value={actionForm.notes||''} onChange={(e)=>setActionForm(f=>({...f,notes:e.target.value}))} placeholder="Reason for rescheduling"/></label>
                </div>
              )}
              {modal.type === 'priority' && (
                <div className="space-y-3">
                  <label><span className={LABEL}>Priority</span><select className={INPUT} value={actionForm.priority||'normal'} onChange={(e)=>setActionForm(f=>({...f,priority:e.target.value}))}>{PRIORITIES.map(p=><option key={p} value={p}>{p}</option>)}</select></label>
                </div>
              )}
              {modal.type === 'reassign' && (
                <div className="space-y-3">
                  <label><span className={LABEL}>Assigned ASHA worker *</span><select className={INPUT} value={actionForm.assigned_worker_id||''} onChange={(e)=>setActionForm(f=>({...f,assigned_worker_id:e.target.value}))}><option value="">Select worker…</option>{workers.map(w=><option key={w.id} value={w.id}>{w.name} ({w.worker_id})</option>)}</select></label>
                  <p className="text-xs text-teal-deep/50">Reassignment is persisted and recorded in history.</p>
                </div>
              )}
              {modal.type === 'history' && (
                <div className="space-y-2">
                  {historyLoading ? <div className="flex items-center gap-2 text-sm text-teal-deep/60"><Loader2 size={16} className="animate-spin"/> Loading history…</div>
                    : !history || history.length === 0 ? <p className="text-sm text-teal-deep/55">No history recorded.</p>
                    : <div className="space-y-2">{history.map(h => (
                        <div key={h.id} className="rounded-xl border border-teal-deep/10 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-extrabold text-teal-deep">{h.action} {h.from_status || h.to_status ? `(${h.from_status || '?'} -> ${h.to_status || '?'})` : ''}</p><span className="text-[0.66rem] text-teal-deep/45">{String(h.changed_at||'').replace('T',' ').slice(0,16)}</span></div>
                          {(() => {
                            const actorRaw = String(h.actor_label || 'system');
                            const isSynthetic = /synthetic/i.test(actorRaw) || /SYNTHETIC DEMO DATA/i.test(String(h.note || ''));
                            const actorLabel = isSynthetic ? 'Demo setup (isolated)' : actorRaw;
                            const note = isSynthetic ? String(h.note || '').replace(/SYNTHETIC DEMO DATA[:\s-]*/ig, '').trim() : h.note;
                            return (
                              <>
                                <p className="mt-0.5 text-[0.7rem] text-teal-deep/60">By: {actorLabel}{!isSynthetic && h.actor_id ? ` (ID ${h.actor_id})` : ''}</p>
                                {note ? <p className="mt-1 text-xs text-teal-deep/70 whitespace-pre-wrap">{note}</p> : null}
                              </>
                            );
                          })()}
                        </div>
                      ))}</div>}
                </div>
              )}
              {modal.type === 'create' && (
                <div className="space-y-3">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="sm:col-span-2"><span className={LABEL}>Beneficiary *</span><select className={INPUT} value={actionForm.beneficiary_id||''} onChange={(e)=>setActionForm(f=>({...f,beneficiary_id:e.target.value, household_id: e.target.value ? '' : f.household_id}))}><option value="">Select beneficiary…</option>{beneficiaries.map(b=><option key={b.id} value={b.id}>{b.name} — {b.village || b.category} ({b.qr_id})</option>)}</select></label>
                    <label><span className={LABEL}>Type/Category</span><select className={INPUT} value={actionForm.type||'general'} onChange={(e)=>setActionForm(f=>({...f,type:e.target.value, category:e.target.value}))}>{['anc','postnatal','newborn','vaccination','nutrition','community','household','growth','followup','general'].map(x=><option key={x} value={x}>{followupTypeLabel(x,t)||x}</option>)}</select></label>
                    <label><span className={LABEL}>Due date *</span><input type="date" className={INPUT} value={actionForm.due_date||''} onChange={(e)=>setActionForm(f=>({...f,due_date:e.target.value}))} /></label>
                    <label><span className={LABEL}>Priority</span><select className={INPUT} value={actionForm.priority||'normal'} onChange={(e)=>setActionForm(f=>({...f,priority:e.target.value}))}>{PRIORITIES.map(p=><option key={p} value={p}>{p}</option>)}</select></label>
                    <label><span className={LABEL}>Assigned worker</span><select className={INPUT} value={actionForm.assigned_worker_id||''} onChange={(e)=>setActionForm(f=>({...f,assigned_worker_id:e.target.value}))}><option value="">Auto / unassigned</option>{workers.map(w=><option key={w.id} value={w.id}>{w.name} ({w.worker_id})</option>)}</select></label>
                    <label className="sm:col-span-2"><span className={LABEL}>Reason</span><input className={INPUT} value={actionForm.reason||''} onChange={(e)=>setActionForm(f=>({...f,reason:e.target.value}))} placeholder="Why this follow-up is needed" /></label>
                    <label className="sm:col-span-2"><span className={LABEL}>Description</span><textarea className={INPUT} rows={2} value={actionForm.description||''} onChange={(e)=>setActionForm(f=>({...f,description:e.target.value}))} placeholder="Additional details" /></label>
                    <label className="sm:col-span-2"><span className={LABEL}>Recommended action</span><input className={INPUT} value={actionForm.recommended_action||''} onChange={(e)=>setActionForm(f=>({...f,recommended_action:e.target.value}))} placeholder="Suggested next step" /></label>
                    <label className="sm:col-span-2"><span className={LABEL}>Notes</span><textarea className={INPUT} rows={2} value={actionForm.notes||''} onChange={(e)=>setActionForm(f=>({...f,notes:e.target.value}))} placeholder="Optional notes" /></label>
                  </div>
                  <p className="text-[0.68rem] text-teal-deep/50">Manual follow-ups are persisted as real task records (no fabricated clinical schedules). Only create when supported by actual need.</p>
                </div>
              )}

              {modal.type !== 'history' && (
                <div className="mt-5 flex gap-3">
                  <button onClick={closeModal} className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 hover:bg-teal-deep/10">Close</button>
                  <button onClick={runAction} disabled={saving} className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60">
                    {saving ? <Loader2 size={15} className="animate-spin"/> : <CheckCircle2 size={15}/>}
                    {modal.type === 'create' ? 'Create' : 'Save'}
                  </button>
                </div>
              )}
              {modal.type === 'history' && (
                <div className="mt-5 flex gap-3">
                  <button onClick={closeModal} className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 hover:bg-teal-deep/10">Close</button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {smsTarget && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-50 flex items-end justify-center bg-teal-deep/50 backdrop-blur-sm sm:items-center sm:p-6" onClick={() => { if(!smsSendBusyId) { setSmsTarget(null); setSmsPreview(null); setSmsConsentGranted(false); } }}>
            <motion.div initial={{y:40,opacity:0,scale:0.98}} animate={{y:0,opacity:1,scale:1}} exit={{y:30,opacity:0,scale:0.98}} onClick={(e)=>e.stopPropagation()} className="card-ivory max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-b-none p-6 sm:rounded-3xl">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-extrabold text-teal-deep">SMS Reminder Preview</h3>
                  <p className="text-xs text-teal-deep/55">Review consent, compliance, and message before sending. No sensitive health details are sent.</p>
                </div>
                <button onClick={() => { if(!smsSendBusyId){ setSmsTarget(null); setSmsPreview(null); setSmsConsentGranted(false);} }} className="rounded-full bg-teal-deep/5 p-2 text-teal-deep/50"><X size={16}/></button>
              </div>
              {smsPreviewLoading ? (
                <div className="flex items-center gap-2 text-sm text-teal-deep/60"><Loader2 size={16} className="animate-spin"/> Loading preview…</div>
              ) : (
                <div className="space-y-3">
                  <div className="rounded-2xl bg-ivory/80 p-3 text-xs text-teal-deep/70 space-y-1">
                    <p><b>Beneficiary:</b> {smsTarget.beneficiary?.name}</p>
                    <p><b>Phone:</b> {smsPreview?.phone || smsTarget.beneficiary?.phone || "—"} {smsPreview?.phone_valid ? "" : <span className="text-coral font-bold">(invalid/missing)</span>}</p>
                    <p><b>Follow-up:</b> {followupTypeLabel(smsTarget.followup?.category || smsTarget.followup?.type, t) || smsTarget.followup?.type} · Due {fmtDate(smsTarget.followup?.due_date)}</p>
                    <p><b>Consent:</b> {smsConsent[smsTarget.beneficiary?.id]?.granted ? "Recorded" : "Not recorded/unknown"}</p>
                    <p><b>Compliance:</b> {smsStats?.sms_compliance_approved ? "Approved" : "Blocked (SMS_COMPLIANCE_APPROVED required)"}</p>
                    <p><b>Provider:</b> {smsStats?.sms_provider_configured ? (smsStats?.sms_provider || "configured") : "Not live-configured (demo/non-sent only)"}</p>
                  </div>
                  <div className="rounded-2xl border border-teal-deep/10 p-3">
                    <p className="text-[11px] font-extrabold uppercase tracking-wide text-teal-deep/45 mb-1">Message preview</p>
                    <p className="text-sm text-teal-deep/80 whitespace-pre-wrap">{smsPreview?.body || "—"}</p>
                    <p className="mt-2 text-[11px] text-teal-deep/45">{smsPreview?.demo_label || ""}</p>
                  </div>
                  <label className="flex items-start gap-2 rounded-2xl bg-mint-soft/40 px-3 py-3 text-xs font-semibold text-teal-deep/75">
                    <input type="checkbox" checked={smsConsentGranted} onChange={(e)=>setSmsConsentGranted(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#B96F85]" />
                    <span>I confirm documented SMS consent, verify the recipient/number, and authorize sending this non-sensitive reminder. I understand delivery is reported only as provider confirms.</span>
                  </label>
                  <div className="flex gap-3 pt-1">
                    <button onClick={() => { if(!smsSendBusyId){ setSmsTarget(null); setSmsPreview(null); setSmsConsentGranted(false);} }} className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 hover:bg-teal-deep/10">Close</button>
                    <button onClick={sendSmsReminder} disabled={!!smsSendBusyId || smsPreviewLoading} className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60">
                      {smsSendBusyId ? <Loader2 size={15} className="animate-spin"/> : <Send size={15}/>} Send reminder
                    </button>
                  </div>
                  <p className="text-[11px] text-teal-deep/45">If SMS is blocked/fails, the follow-up remains unchanged and no delivery is fabricated.</p>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}