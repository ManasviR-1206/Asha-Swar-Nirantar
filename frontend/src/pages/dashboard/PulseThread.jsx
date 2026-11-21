import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Waves,
  Mic,
  QrCode,
  Download,
  ShieldAlert,
  CalendarClock,
  User,
  ChevronRight,
  Filter,
  LineChart,
  ClipboardList,
  Eye,
  Paperclip,
  CheckCircle2,
  Plus,
  Pencil,
  Upload,
  Trash2,
  Save,
  X,
  Activity,
} from "lucide-react";
import { api, downloadFile, openFile } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { categoryLabel, followupTypeLabel } from "../../lib/labels.js";

const MEAS_LABELS = {
  height_cm: "Height (cm)",
  weight_kg: "Weight (kg)",
  bmi: "BMI (kg/m²)",
  bp_sys: "Systolic BP (mmHg)",
  bp_dia: "Diastolic BP (mmHg)",
  pulse_bpm: "Pulse (bpm)",
  temperature_c: "Temperature (°C)",
  blood_glucose_mgdl: "Blood glucose (mg/dL)",
  spo2: "SpO₂ (%)",
  haemoglobin_gdl: "Haemoglobin (g/dL)",
  muac_cm: "MUAC (cm)",
  head_circumference_cm: "Head circumference (cm)",
  fundal_height_cm: "Fundal height (cm)",
  fetal_heart_rate_bpm: "Fetal heart rate (bpm)",
  gestational_weeks: "Gestational weeks",
  birth_weight_kg: "Birth weight (kg)",
};

const MEAS_TYPES = Object.keys(MEAS_LABELS);
const MEAS_DEFAULT_UNIT = {
  height_cm: "cm", weight_kg: "kg", bmi: "kg/m2", bp_sys: "mmHg", bp_dia: "mmHg", pulse_bpm: "bpm",
  temperature_c: "°C", blood_glucose_mgdl: "mg/dL", spo2: "%", haemoglobin_gdl: "g/dL", muac_cm: "cm",
  head_circumference_cm: "cm", fundal_height_cm: "cm", fetal_heart_rate_bpm: "bpm", gestational_weeks: "weeks", birth_weight_kg: "kg",
};
const SOURCES = ["manual", "voice", "device", "ocr", "import", "estimated"];
const VSTATUSES = ["recorded", "pending_verification", "verified", "entered_in_error"];
const DOC_CATEGORIES = ["prescription", "lab_report", "blood_test", "scan_report", "vaccination_card", "pregnancy_record", "health_card", "other"];

function measLabel(type) {
  return MEAS_LABELS[type] || (type || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function fmtDateTime(v) {
  if (!v) return "—";
  const s = String(v);
  if (s.includes("T")) return s.replace("T", " ").slice(0, 16);
  return s.slice(0, 10);
}
function toDateKey(v) { return v ? String(v).slice(0, 10) : ""; }
function nowLocalInput() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function SimpleTrendChart({ points, unit, label }) {
  const vals = points.map((p) => p.value).filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (vals.length < 1) return <div className="rounded-xl bg-ivory/70 px-3 py-4 text-xs font-semibold text-teal-deep/45">No numeric values recorded for {label}.</div>;
  const w = 520, h = 140, padL = 36, padR = 10, padT = 10, padB = 26;
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const innerW = w - padL - padR, innerH = h - padT - padB;
  const xAt = (i) => padL + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const yAt = (v) => padT + innerH - ((v - min) / span) * innerH;
  const linePts = points.map((p, i) => (p.value == null || Number.isNaN(p.value) ? null : `${xAt(i)},${yAt(p.value)}`)).filter(Boolean).join(" ");
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="min-w-[320px] w-full">
        <line x1={padL} y1={padT} x2={padL} y2={h - padB} stroke="#d8e3e1" />
        <line x1={padL} y1={h - padB} x2={w - padR} y2={h - padB} stroke="#d8e3e1" />
        <text x={4} y={padT + 8} fontSize="9" fill="#6b7c78">{max.toFixed(1)}</text>
        <text x={4} y={h - padB} fontSize="9" fill="#6b7c78">{min.toFixed(1)}</text>
        {linePts && <polyline fill="none" stroke="#5aa7a0" strokeWidth="2.5" points={linePts} />}
        {points.map((p, i) => p.value == null || Number.isNaN(p.value)
          ? <text key={i} x={xAt(i)} y={h - 8} fontSize="8" textAnchor="middle" fill="#b08995">missing</text>
          : <g key={i}><circle cx={xAt(i)} cy={yAt(p.value)} r="3.5" fill="#2f6f68" /><text x={xAt(i)} y={h - 8} fontSize="8" textAnchor="middle" fill="#6b7c78">{p.xLabel}</text></g>)}
      </svg>
      <p className="mt-1 text-[0.65rem] font-medium text-teal-deep/45">Actual dated records only. Missing data shown as missing (not zero). {unit ? `Unit: ${unit}.` : ""}</p>
    </div>
  );
}

function Badge({ children, tone = "mint" }) {
  const cls = tone === "coral" ? "bg-coral/15 text-coral" : tone === "lavender" ? "bg-lavender/20 text-midnight" : tone === "gray" ? "bg-teal-deep/5 text-teal-deep/60" : "bg-mint-soft text-teal-deep";
  return <span className={`chip ${cls}`}>{children}</span>;
}

const INPUT = "w-full rounded-xl border border-teal-deep/10 bg-ivory/70 px-3 py-2 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none";
const LABEL = "block text-[0.68rem] font-extrabold uppercase tracking-wide text-teal-deep/50 mb-1";

export default function PulseThread() {
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [benId, setBenId] = useState(routeId || "");
  const [list, setList] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!!routeId);
  const [showQr, setShowQr] = useState(false);
  const [qr, setQr] = useState(null);

  // filters
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [visitType, setVisitType] = useState("all");
  const [measCategory, setMeasCategory] = useState("all");

  // management UI state
  const [showAddMeas, setShowAddMeas] = useState(false);
  const [measForm, setMeasForm] = useState({ measurement_type: "weight_kg", value: "", unit: "kg", value_text: "", recorded_at: nowLocalInput(), source: "manual", verification_status: "recorded", notes: "" });
  const [measSaving, setMeasSaving] = useState(false);
  const [editingMeasId, setEditingMeasId] = useState(null);
  const [editMeasForm, setEditMeasForm] = useState(null);
  const [editReason, setEditReason] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [docFile, setDocFile] = useState(null);
  const [docCat, setDocCat] = useState("lab_report");
  const [docNotes, setDocNotes] = useState("");
  const [docSaving, setDocSaving] = useState(false);

  useEffect(() => setBenId(routeId || ""), [routeId]);

  const loadDetail = async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const d = await api.get(`/beneficiaries/${id}`);
      setData(d);
    } catch (e) {
      showToast(e.message || "Could not load this beneficiary.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (routeId) return;
    let alive = true;
    api.get("/beneficiaries").then((d) => alive && setList(d.beneficiaries || [])).catch((e) => showToast(e.message || "Could not load beneficiaries.", "error"));
    return () => { alive = false; };
  }, [routeId]);

  useEffect(() => {
    if (!benId) return;
    setData(null); setShowQr(false); setQr(null);
    loadDetail(benId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [benId]);

  const toggleQr = async () => {
    const next = !showQr; setShowQr(next);
    if (next && !qr) {
      try { const d = await api.get(`/beneficiaries/${benId}/qr`); setQr({ data_url: d.data_url, qr_id: d.qr_id }); }
      catch { showToast("Could not load the QR code image.", "warn"); setShowQr(false); }
    }
  };

  const beneficiary = data?.beneficiary || null;
  const allMeasurements = useMemo(() => (data?.measurements || []).slice().sort((a,b) => String(a.recorded_at||"").localeCompare(String(b.recorded_at||"")) || a.id-b.id), [data]);
  const measurementTypes = useMemo(() => ["all", ...Array.from(new Set(allMeasurements.map(m => m.measurement_type)))], [allMeasurements]);
  const visitTypes = useMemo(() => ["all", ...Array.from(new Set((data?.visits || []).map(v => v.category).filter(Boolean)))], [data]);
  const inDateRange = (dateStr) => { const d = toDateKey(dateStr); if (!d) return true; if (dateFrom && d < dateFrom) return false; if (dateTo && d > dateTo) return false; return true; };
  const filteredMeasurements = useMemo(() => allMeasurements.filter(m => (measCategory === "all" || m.measurement_type === measCategory) && inDateRange(m.recorded_at)), [allMeasurements, measCategory, dateFrom, dateTo]);

  const chartGroups = useMemo(() => {
    const byType = new Map();
    filteredMeasurements.forEach(m => { if (!byType.has(m.measurement_type)) byType.set(m.measurement_type, []); byType.get(m.measurement_type).push(m); });
    return Array.from(byType.entries()).map(([type, rows]) => {
      const pts = rows.map(r => ({ xLabel: toDateKey(r.recorded_at).slice(5), value: (r.value == null) ? null : Number(r.value), date: r.recorded_at, unit: r.unit }));
      pts.sort((a,b)=>String(a.date||"").localeCompare(String(b.date||"")));
      return { type, label: measLabel(type), unit: rows[rows.length-1]?.unit || "", points: pts };
    }).filter(g => g.points.length > 0);
  }, [filteredMeasurements]);

  const timelineEvents = useMemo(() => {
    if (!data) return [];
    const ev = []; const b = data.beneficiary || {};
    if (b && (b.created_at || b.id)) ev.push({ kind: "registration", date: "", sort: "0000-00-00", title: "Registration", detail: `Registered as ${categoryLabel(b.category,t)}. Origin: ${b.data_origin === "synthetic_demo" ? "synthetic_demo (SYNTHETIC DEMO DATA)" : (b.data_origin || 'registered')}. Verification: ${b.verification_status || '—'}.`, meta: [b.village, b.household_id ? `Household #${b.household_id}` : null].filter(Boolean) });
    (data.visits || []).forEach(v => { if (!inDateRange(v.visit_date)) return; if (visitType !== "all" && v.category !== visitType) return; ev.push({ kind: "visit", date: v.visit_date, sort: toDateKey(v.visit_date), title: `Visit — ${categoryLabel(v.category,t)}`, detail: (v.source || "manual") === "voice" ? "Voice-recorded visit" : "Recorded visit", raw: v, meta: [] }); });
    (data.measurements || []).forEach(m => { if (!inDateRange(m.recorded_at)) return; if (measCategory !== "all" && m.measurement_type !== measCategory) return; const val = m.value != null ? `${m.value} ${m.unit||""}`.trim() : (m.value_text || "—"); ev.push({ kind: "measurement", date: toDateKey(m.recorded_at), sort: toDateKey(m.recorded_at), title: `Measurement — ${measLabel(m.measurement_type)}`, detail: `${val} • Source: ${m.source||'manual'} • ${m.verification_status||'recorded'}`, raw: m, meta: m.notes ? [m.notes] : [] }); });
    (data.alerts || []).forEach(a => { if (!inDateRange(a.created_at)) return; ev.push({ kind: "alert", date: toDateKey(a.created_at), sort: toDateKey(a.created_at), title: `Alert (${a.status || 'open'})`, detail: a.reason || a.message || a.phrase, raw: a, meta: [a.severity ? `Severity: ${a.severity}` : null, a.recommended_action ? `Action: ${a.recommended_action}` : null].filter(Boolean) }); });
    (data.followups || []).forEach(f => { const d = f.due_date || f.updated_at || f.created_at; if (d && !inDateRange(d)) return; ev.push({ kind: "followup", date: toDateKey(d), sort: toDateKey(d), title: `Follow-up — ${followupTypeLabel(f.type,t)} (${f.status})`, detail: f.reason || f.recommended_action || "Scheduled follow-up", raw: f, meta: [f.due_date ? `Due: ${f.due_date}` : null, f.priority ? `Priority: ${f.priority}` : null].filter(Boolean) }); });
    (data.immunisation_records || []).forEach(im => { if (im.date_given && !inDateRange(im.date_given)) return; ev.push({ kind: "immunisation", date: toDateKey(im.date_given || im.next_due_date), sort: toDateKey(im.date_given || im.next_due_date || ""), title: `Immunisation — ${im.vaccine_name || 'Vaccine'}`, detail: `Dose: ${im.dose_number ?? '—'}${im.next_due_date ? ` • Next due: ${im.next_due_date}` : ''}`, raw: im, meta: [] }); });
    (data.pregnancy_records || []).forEach(p => ev.push({ kind: "pregnancy", date: "", sort: "9999-99-99", title: "Pregnancy record", detail: `Weeks: ${p.weeks_pregnant ?? '—'} • BP: ${p.bp_sys ?? '—'}/${p.bp_dia ?? '—'} • Weight: ${p.weight_kg ?? '—'} kg • Hb: ${p.hemoglobin ?? '—'}`, raw: p, meta: [] }));
    (data.newborn_records || []).forEach(n => ev.push({ kind: "newborn", date: "", sort: "9999-99-99", title: "Newborn/child record", detail: `Weight: ${n.weight_kg ?? '—'} kg • Temp: ${n.temperature ?? '—'} • Feeding: ${n.feeding ?? '—'} • Jaundice: ${n.jaundice ?? '—'}`, raw: n, meta: [] }));
    (data.documents || []).forEach(doc => { if (!inDateRange(doc.created_at)) return; ev.push({ kind: "document", date: toDateKey(doc.created_at), sort: toDateKey(doc.created_at), title: `Document — ${doc.category || 'other'}`, detail: `${doc.original_filename} (${doc.mime_type || 'file'})`, raw: doc, meta: [] }); });
    ev.sort((a,b) => (b.sort || "").localeCompare(a.sort || ""));
    return ev;
  }, [data, dateFrom, dateTo, visitType, measCategory, t]);

  const openDoc = async (doc, download=false) => {
    try { if (download) await downloadFile(doc.download_url, doc.original_filename || 'document'); else await openFile(doc.preview_url); }
    catch (e) { showToast(e.message || 'Could not open document', 'error'); }
  };

  const submitMeasurement = async (e) => {
    e.preventDefault();
    if (!beneficiary) return;
    setMeasSaving(true);
    try {
      const payload = {
        beneficiary_id: beneficiary.id,
        measurement_type: measForm.measurement_type,
        value: measForm.value === "" ? null : Number(measForm.value),
        value_text: measForm.value_text || "",
        unit: measForm.unit || MEAS_DEFAULT_UNIT[measForm.measurement_type] || "",
        recorded_at: measForm.recorded_at || null,
        source: measForm.source,
        verification_status: measForm.verification_status,
        notes: measForm.notes || "",
      };
      await api.post("/measurements", payload);
      showToast("Measurement recorded.", "success");
      setShowAddMeas(false);
      setMeasForm({ measurement_type: "weight_kg", value: "", unit: "kg", value_text: "", recorded_at: nowLocalInput(), source: "manual", verification_status: "recorded", notes: "" });
      await loadDetail(beneficiary.id);
    } catch (err) { showToast(err.message || "Could not save measurement.", "error"); }
    finally { setMeasSaving(false); }
  };

  const startEditMeas = (m) => {
    setEditingMeasId(m.id);
    setEditReason("");
    setEditMeasForm({
      value: m.value ?? "",
      value_text: m.value_text || "",
      unit: m.unit || "",
      recorded_at: m.recorded_at ? String(m.recorded_at).slice(0,16) : "",
      source: m.source || "manual",
      verification_status: m.verification_status || "recorded",
      notes: m.notes || "",
    });
  };

  const saveEditMeas = async () => {
    if (!editingMeasId || !editMeasForm) return;
    setEditSaving(true);
    try {
      const payload = {
        value: editMeasForm.value === "" ? null : Number(editMeasForm.value),
        value_text: editMeasForm.value_text || "",
        unit: editMeasForm.unit || "",
        recorded_at: editMeasForm.recorded_at || null,
        source: editMeasForm.source,
        verification_status: editMeasForm.verification_status,
        notes: editMeasForm.notes || "",
        reason: editReason || "Corrected/updated by ASHA worker",
      };
      await api.patch(`/measurements/${editingMeasId}`, payload);
      showToast("Measurement updated (history preserved).", "success");
      setEditingMeasId(null); setEditMeasForm(null); setEditReason("");
      await loadDetail(beneficiary.id);
    } catch (err) { showToast(err.message || "Could not update measurement.", "error"); }
    finally { setEditSaving(false); }
  };

  const uploadDocument = async (e) => {
    e.preventDefault();
    if (!beneficiary || !docFile) { showToast("Select a file to upload.", "warn"); return; }
    setDocSaving(true);
    try {
      const fd = new FormData();
      fd.append("file", docFile);
      fd.append("beneficiary_id", String(beneficiary.id));
      fd.append("category", docCat);
      fd.append("notes", docNotes || "");
      fd.append("upload_source", "upload");
      await api.postForm("/documents/upload", fd);
      showToast("Document uploaded securely.", "success");
      setShowUpload(false); setDocFile(null); setDocNotes(""); setDocCat("lab_report");
      await loadDetail(beneficiary.id);
    } catch (err) { showToast(err.message || "Could not upload document.", "error"); }
    finally { setDocSaving(false); }
  };

  const removeDocument = async (doc) => {
    if (!window.confirm(`Remove "${doc.original_filename}" from this profile? This is recorded in audit history (file access will be disabled).`)) return;
    try {
      const fd = new FormData();
      fd.append("reason", "Removed by authorized user from Pulse Thread");
      await api.postForm(`/documents/${doc.id}/delete`, fd);
      showToast("Document removed (audited).", "success");
      await loadDetail(beneficiary.id);
    } catch (err) { showToast(err.message || "Could not remove document.", "error"); }
  };

  // Picker
  if (!routeId && !benId) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div><h2 className="text-xl font-extrabold text-teal-deep">Pulse Thread</h2><p className="mt-0.5 text-sm font-medium text-teal-deep/55">Select a beneficiary to view and manage their health timeline, measurements, and documents.</p></div>
        {list === null ? <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}</div>
          : list.length === 0 ? <div className="card-ivory"><Empty icon={User} title="No beneficiaries found" subtitle="Register a beneficiary to start recording real health history." action={<Link to="/app/beneficiaries" className="btn-mint px-5 py-2.5 text-sm">Open Beneficiaries</Link>} /></div>
          : <div className="grid gap-3 sm:grid-cols-2">{list.map((b, i) => (
              <motion.button key={b.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: Math.min(i * 0.05, 0.3) }} onClick={() => navigate(`/app/beneficiaries/${b.id}`)} className="card-ivory flex items-center gap-3.5 p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-card">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-teal-deep text-sm font-extrabold text-mint">{(b.name || "?").slice(0, 2).toUpperCase()}</div>
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-extrabold text-teal-deep">{b.name}</p><p className="truncate text-xs font-medium text-teal-deep/50">{categoryLabel(b.category, t)} · {b.village || "—"}</p></div>
                <ChevronRight size={16} className="shrink-0 text-teal-deep/30" />
              </motion.button>))}</div>}
      </div>
    );
  }

  if (loading) return <div className="space-y-5"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>;
  if (!data || !beneficiary) return <div className="card-ivory"><Empty icon={Waves} title="Beneficiary not found" subtitle="This record may not exist or you may not have access." action={<Link to="/app/beneficiaries" className="btn-mint px-5 py-2.5 text-sm">Back</Link>} /></div>;

  const alerts = data.alerts || []; const followups = data.followups || []; const documents = data.documents || [];

  return (
    <div className="space-y-5">
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="card-ivory p-5 sm:p-6">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-3xl bg-teal-deep text-lg font-extrabold text-mint">{(beneficiary.name || "?").trim().split(/\s+/).slice(0,2).map(w=>w[0]?.toUpperCase()).join("")}</div>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-xl font-extrabold text-teal-deep">{beneficiary.name}</h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Badge>{categoryLabel(beneficiary.category, t)}</Badge>
              {beneficiary.age != null && <Badge tone="gray">{beneficiary.age} yrs</Badge>}
              {beneficiary.gender ? <Badge tone="gray">{beneficiary.gender}</Badge> : null}
              {beneficiary.village ? <Badge tone="gray">{beneficiary.village}</Badge> : null}
              {(beneficiary.data_origin === "synthetic_demo" || beneficiary.verification_status === "synthetic_demo") ? (
                <span className="chip bg-amber-100 text-amber-900 border border-amber-200">SYNTHETIC DEMO DATA</span>
              ) : (
                <Badge tone="lavender">{beneficiary.verification_status || 'registered'}</Badge>
              )}
              <span className="chip bg-teal-deep/5 font-mono text-[0.68rem] tracking-wide text-teal-deep/55">{beneficiary.qr_id}</span>
            </div>
            <div className="mt-2 grid gap-1 text-xs font-medium text-teal-deep/65 sm:grid-cols-2">
              <div><b>Address:</b> {beneficiary.address || '—'}</div>
              <div><b>Phone:</b> {beneficiary.phone || '—'} {beneficiary.email ? `• ${beneficiary.email}` : ''}</div>
              <div><b>DOB:</b> {beneficiary.date_of_birth || beneficiary.birth_date || '—'}</div>
              <div><b>Household:</b> {data.household ? `${data.household.village || 'Household'} (${data.household.qr_id})` : (beneficiary.household_id ? `#${beneficiary.household_id}` : '—')}</div>
              <div><b>Pregnancy:</b> {beneficiary.pregnancy_status || (beneficiary.category === 'pregnancy' ? 'Recorded as pregnancy category' : '—')} {beneficiary.lmp_date ? `• LMP ${beneficiary.lmp_date}` : ''}</div>
              <div><b>Assigned ASHA:</b> {beneficiary.assigned_worker_id ? `Worker #${beneficiary.assigned_worker_id}` : '—'}</div>
            </div>
            {(beneficiary.medical_conditions || beneficiary.allergies || beneficiary.current_medications || beneficiary.child_health_notes) ? (
              <div className="mt-3 grid gap-2 rounded-2xl bg-ivory/70 p-3 text-xs sm:grid-cols-2">
                <div><b>Medical conditions/history:</b> {beneficiary.medical_conditions || 'Not recorded'}</div>
                <div><b>Allergies:</b> {beneficiary.allergies || 'Not recorded'}</div>
                <div><b>Current medications:</b> {beneficiary.current_medications || 'Not recorded'}</div>
                <div><b>Child/vaccination notes:</b> {beneficiary.child_health_notes || 'Not recorded'}</div>
              </div>
            ) : <p className="mt-2 text-xs font-semibold text-teal-deep/45">No additional medical history, allergies, medications, or child-health notes recorded yet. Edit the profile in Beneficiaries to add details.</p>}
          </div>
          <div className="flex flex-col items-end gap-2">
            <button onClick={toggleQr} className="flex items-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2 text-xs font-bold text-teal-deep/70 hover:bg-mint-soft"><QrCode size={14}/> {showQr ? 'Hide QR' : 'Show QR'}</button>
            <Link to={`/app/voice-visit?beneficiary=${beneficiary.id}`} className="btn-mint flex items-center gap-2 px-4 py-2 text-xs"><Mic size={13}/> New Voice Visit</Link>
          </div>
        </div>
        <AnimatePresence>{showQr && (<motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden"><div className="mt-4 flex items-center gap-4 rounded-2xl bg-ivory/80 p-4">{qr?.data_url ? <img src={qr.data_url} alt="QR" className="h-32 w-32 rounded-2xl border bg-white p-2" /> : <div className="skeleton h-32 w-32 rounded-2xl" />}<div className="text-xs text-teal-deep/60"><p className="font-mono font-bold text-teal-deep">{qr?.qr_id || beneficiary.qr_id}</p><p className="mt-1">QR contains only anonymous beneficiary ID.</p></div></div></motion.div>)}</AnimatePresence>
      </motion.div>

      <div className="card-ivory p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-extrabold text-teal-deep"><Filter size={14}/> Timeline filters</div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs font-bold text-teal-deep/60">From date<input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)} className="mt-1 w-full rounded-xl border border-teal-deep/10 bg-ivory/70 px-3 py-2 text-sm"/></label>
          <label className="text-xs font-bold text-teal-deep/60">To date<input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)} className="mt-1 w-full rounded-xl border border-teal-deep/10 bg-ivory/70 px-3 py-2 text-sm"/></label>
          <label className="text-xs font-bold text-teal-deep/60">Visit type<select value={visitType} onChange={e=>setVisitType(e.target.value)} className="mt-1 w-full rounded-xl border border-teal-deep/10 bg-ivory/70 px-3 py-2 text-sm">{visitTypes.map(v=> <option key={v} value={v}>{v==='all'?'All visit types':categoryLabel(v,t)}</option>)}</select></label>
          <label className="text-xs font-bold text-teal-deep/60">Measurement category<select value={measCategory} onChange={e=>setMeasCategory(e.target.value)} className="mt-1 w-full rounded-xl border border-teal-deep/10 bg-ivory/70 px-3 py-2 text-sm">{measurementTypes.map(m=> <option key={m} value={m}>{m==='all'?'All measurements':measLabel(m)}</option>)}</select></label>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
        <div className="space-y-5">
          <section className="card-ivory p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2"><Activity size={16} className="text-teal-deep"/><h3 className="text-sm font-extrabold text-teal-deep">Measurements (historical, append-oriented)</h3></div>
              <button onClick={() => setShowAddMeas(v=>!v)} className="btn-mint flex items-center gap-1.5 px-3 py-1.5 text-xs"><Plus size={13}/> Add measurement</button>
            </div>
            <p className="mb-3 text-[0.68rem] font-medium text-teal-deep/50">New measurements are added as dated records. Edits preserve history via audit entries (no silent overwrite). BMI is calculated only when valid height and weight are available.</p>
            <AnimatePresence>{showAddMeas && (
              <motion.form initial={{opacity:0,height:0}} animate={{opacity:1,height:'auto'}} exit={{opacity:0,height:0}} onSubmit={submitMeasurement} className="mb-4 overflow-hidden rounded-2xl border border-mint/30 bg-mint/5 p-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <label><span className={LABEL}>Type *</span><select className={INPUT} value={measForm.measurement_type} onChange={e=>{const t=e.target.value; setMeasForm(f=>({...f,measurement_type:t,unit:MEAS_DEFAULT_UNIT[t]||f.unit}));}}>{MEAS_TYPES.map(mt => <option key={mt} value={mt}>{measLabel(mt)}</option>)}</select></label>
                  <label><span className={LABEL}>Value</span><input className={INPUT} type="number" step="any" value={measForm.value} onChange={e=>setMeasForm(f=>({...f,value:e.target.value}))} placeholder="Numeric value" /></label>
                  <label><span className={LABEL}>Unit</span><input className={INPUT} value={measForm.unit} onChange={e=>setMeasForm(f=>({...f,unit:e.target.value}))} placeholder={MEAS_DEFAULT_UNIT[measForm.measurement_type]||"unit"} /></label>
                  <label><span className={LABEL}>Recorded at *</span><input className={INPUT} type="datetime-local" value={measForm.recorded_at} onChange={e=>setMeasForm(f=>({...f,recorded_at:e.target.value}))} required /></label>
                  <label><span className={LABEL}>Source</span><select className={INPUT} value={measForm.source} onChange={e=>setMeasForm(f=>({...f,source:e.target.value}))}>{SOURCES.map(s=><option key={s} value={s}>{s}</option>)}</select></label>
                  <label><span className={LABEL}>Verification</span><select className={INPUT} value={measForm.verification_status} onChange={e=>setMeasForm(f=>({...f,verification_status:e.target.value}))}>{VSTATUSES.map(s=><option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}</select></label>
                  <label className="sm:col-span-2"><span className={LABEL}>Value text (optional, e.g. 120/80)</span><input className={INPUT} value={measForm.value_text} onChange={e=>setMeasForm(f=>({...f,value_text:e.target.value}))} placeholder="Optional text value" /></label>
                  <label className="sm:col-span-2"><span className={LABEL}>Notes</span><textarea className={INPUT} rows={2} value={measForm.notes} onChange={e=>setMeasForm(f=>({...f,notes:e.target.value}))} placeholder="Optional notes" /></label>
                </div>
                <div className="mt-2 flex gap-2"><button type="submit" disabled={measSaving} className="btn-mint px-4 py-2 text-xs disabled:opacity-60">{measSaving?'Saving…':'Save measurement'}</button><button type="button" onClick={()=>setShowAddMeas(false)} className="rounded-full bg-teal-deep/5 px-4 py-2 text-xs font-bold text-teal-deep/60">Cancel</button></div>
              </motion.form>
            )}</AnimatePresence>

            {chartGroups.length === 0 ? <div className="rounded-xl bg-ivory/70 px-3 py-4 text-center text-xs font-semibold text-teal-deep/45">No measurement records match the current filters.</div> : (
              <div className="space-y-3">{chartGroups.map(g => (<div key={g.type} className="rounded-2xl border border-teal-deep/10 p-3"><p className="mb-1 text-xs font-extrabold text-teal-deep">{g.label}</p><SimpleTrendChart points={g.points} unit={g.unit} label={g.label} /></div>))}</div>
            )}

            <div className="mt-4">
              <p className="mb-2 text-xs font-extrabold text-teal-deep/70">Measurement records ({filteredMeasurements.length} shown)</p>
              {filteredMeasurements.length === 0 ? <p className="text-xs font-semibold text-teal-deep/45">No measurements recorded yet.</p> : (
                <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
                  {[...filteredMeasurements].sort((a,b)=>String(b.recorded_at||"").localeCompare(String(a.recorded_at||"")) || b.id-a.id).map(m => (
                    <div key={m.id} className="rounded-xl border border-teal-deep/10 p-3">
                      {editingMeasId === m.id && editMeasForm ? (
                        <div className="space-y-2">
                          <p className="text-xs font-extrabold text-teal-deep">Edit {measLabel(m.measurement_type)} (audit recorded)</p>
                          <div className="grid gap-2 sm:grid-cols-2">
                            <label><span className={LABEL}>Value</span><input className={INPUT} type="number" step="any" value={editMeasForm.value} onChange={e=>setEditMeasForm(f=>({...f,value:e.target.value}))}/></label>
                            <label><span className={LABEL}>Unit</span><input className={INPUT} value={editMeasForm.unit} onChange={e=>setEditMeasForm(f=>({...f,unit:e.target.value}))}/></label>
                            <label><span className={LABEL}>Recorded at</span><input className={INPUT} type="datetime-local" value={editMeasForm.recorded_at} onChange={e=>setEditMeasForm(f=>({...f,recorded_at:e.target.value}))}/></label>
                            <label><span className={LABEL}>Source</span><select className={INPUT} value={editMeasForm.source} onChange={e=>setEditMeasForm(f=>({...f,source:e.target.value}))}>{SOURCES.map(s=><option key={s} value={s}>{s}</option>)}</select></label>
                            <label><span className={LABEL}>Verification</span><select className={INPUT} value={editMeasForm.verification_status} onChange={e=>setEditMeasForm(f=>({...f,verification_status:e.target.value}))}>{VSTATUSES.map(s=><option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}</select></label>
                            <label><span className={LABEL}>Value text</span><input className={INPUT} value={editMeasForm.value_text} onChange={e=>setEditMeasForm(f=>({...f,value_text:e.target.value}))}/></label>
                            <label className="sm:col-span-2"><span className={LABEL}>Notes</span><input className={INPUT} value={editMeasForm.notes} onChange={e=>setEditMeasForm(f=>({...f,notes:e.target.value}))}/></label>
                            <label className="sm:col-span-2"><span className={LABEL}>Reason for edit (audit)</span><input className={INPUT} value={editReason} onChange={e=>setEditReason(e.target.value)} placeholder="Why this was corrected"/></label>
                          </div>
                          <div className="flex gap-2"><button onClick={saveEditMeas} disabled={editSaving} className="btn-mint flex items-center gap-1.5 px-3 py-1.5 text-xs disabled:opacity-60"><Save size={12}/>{editSaving?'Saving…':'Save'}</button><button onClick={()=>{setEditingMeasId(null);setEditMeasForm(null);}} className="rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/60"><X size={12}/></button></div>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-xs font-extrabold text-teal-deep">{measLabel(m.measurement_type)}: {m.value != null ? `${m.value} ${m.unit||''}`.trim() : (m.value_text || '—')}</p>
                            <p className="text-[0.66rem] text-teal-deep/55">{fmtDateTime(m.recorded_at)} • {m.source || 'manual'} • {m.verification_status || 'recorded'}{m.updated_at ? ' • edited' : ''}</p>
                            {m.notes ? <p className="mt-0.5 text-[0.66rem] text-teal-deep/60">{m.notes}</p> : null}
                          </div>
                          <button onClick={()=>startEditMeas(m)} className="shrink-0 rounded-full bg-teal-deep/5 p-1.5 text-teal-deep/60 hover:bg-mint-soft" title="Edit (audited)"><Pencil size={13}/></button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="card-ivory p-5">
            <div className="mb-3 flex items-center gap-2"><Waves size={16} className="text-teal-deep"/><h3 className="text-sm font-extrabold text-teal-deep">Pulse Thread timeline</h3></div>
            {timelineEvents.length === 0 ? <Empty icon={ClipboardList} title="No timeline records yet" subtitle="Recorded visits, measurements, follow-ups, alerts, immunisations and documents will appear here." /> : (
              <div className="relative ml-2 space-y-3 border-l-2 border-teal-deep/10 pl-5">
                {timelineEvents.map((e, idx) => (
                  <div key={`${e.kind}-${idx}`} className="relative rounded-2xl bg-ivory/60 p-3.5">
                    <span className="absolute -left-[1.7rem] top-4 h-3 w-3 rounded-full border-2 border-mint bg-white" />
                    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-extrabold text-teal-deep">{e.title}</p><span className="text-[0.68rem] font-bold text-teal-deep/45">{e.date || 'record'}</span></div>
                    <p className="mt-1 text-xs font-medium text-teal-deep/70 whitespace-pre-wrap">{e.detail || '—'}</p>
                    {e.meta?.length ? <div className="mt-1.5 flex flex-wrap gap-1.5">{e.meta.map((m,i)=><span key={i} className="chip bg-teal-deep/5 text-teal-deep/60">{m}</span>)}</div> : null}
                    {e.kind === 'document' && e.raw && (<div className="mt-2 flex flex-wrap gap-2"><button onClick={()=>openDoc(e.raw,false)} className="flex items-center gap-1.5 rounded-full bg-mint-soft px-3 py-1.5 text-xs font-bold text-teal-deep"><Eye size={12}/> Preview</button><button onClick={()=>openDoc(e.raw,true)} className="flex items-center gap-1.5 rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70"><Download size={12}/> Download</button></div>)}
                    {e.kind === 'visit' && e.raw?.structured && Object.keys(e.raw.structured).length > 0 && (<details className="mt-2"><summary className="cursor-pointer text-xs font-bold text-pink">View recorded fields</summary><pre className="mt-1 overflow-auto rounded-xl bg-white/70 p-2 text-[0.68rem] text-teal-deep/70">{JSON.stringify(e.raw.structured, null, 2)}</pre></details>)}
                    {e.kind === 'alert' && (<div className="mt-2 flex flex-wrap gap-1.5">{e.raw?.severity && <Badge tone={/high|urgent|critical/i.test(e.raw.severity)?'coral':'lavender'}>{e.raw.severity}</Badge>}{e.raw?.status && <Badge tone="gray">{e.raw.status}</Badge>}</div>)}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="space-y-5">
          <section className="card-ivory p-5">
            <div className="mb-3 flex items-center gap-2"><ShieldAlert size={15} className="text-coral"/><h3 className="text-sm font-extrabold text-teal-deep">Alerts</h3></div>
            {alerts.length === 0 ? <p className="text-xs font-semibold text-teal-deep/45">No alerts recorded.</p> : <div className="space-y-2">{alerts.slice(0,8).map(a => (<div key={a.id} className="rounded-xl border border-coral/20 bg-coral/5 p-3"><p className="text-xs font-extrabold text-coral">{a.phrase || a.trigger_detail || 'Alert'} <span className="font-bold text-teal-deep/50">({a.status})</span></p><p className="mt-0.5 text-xs text-teal-deep/70">{a.reason || a.message}</p>{a.recommended_action ? <p className="mt-1 text-[0.68rem] font-semibold text-teal-deep/60">Action: {a.recommended_action}</p> : null}</div>))}</div>}
          </section>

          <section className="card-ivory p-5">
            <div className="mb-3 flex items-center justify-between gap-2"><div className="flex items-center gap-2"><CalendarClock size={15} className="text-teal-deep"/><h3 className="text-sm font-extrabold text-teal-deep">Follow-ups (Pulse Drift tasks)</h3></div><Link to={`/app/pulse-drift${beneficiary?.id ? `?beneficiary=${beneficiary.id}` : ''}`} className="text-xs font-extrabold text-pink hover:underline">Manage</Link></div>
            {followups.length === 0 ? <p className="text-xs font-semibold text-teal-deep/45">No follow-up tasks recorded.</p> : <div className="space-y-2">{followups.slice(0,12).map(f => {
              const terminal = f.status === 'completed' || f.status === 'cancelled';
              const tone = f.status === 'overdue' ? 'coral' : f.status === 'due' ? 'lavender' : 'gray';
              return (
                <div key={f.id} className="rounded-xl bg-ivory/70 p-3">
                  <div className="flex items-center justify-between gap-2"><p className="text-xs font-extrabold text-teal-deep">{followupTypeLabel(f.category || f.type, t)}{f.reason ? ` — ${f.reason}` : ''}</p><Badge tone={tone}>{f.status}</Badge></div>
                  <p className="mt-0.5 text-[0.68rem] text-teal-deep/60">Due: {f.due_date || '—'} {f.priority ? `• Priority: ${f.priority}` : ''} {f.assigned_worker_id ? `• Worker #${f.assigned_worker_id}` : ''}</p>
                  {(f.description && f.description !== f.reason) ? <p className="mt-1 text-xs text-teal-deep/65">{f.description}</p> : null}
                  {f.recommended_action ? <p className="mt-1 text-[0.68rem] text-teal-deep/55">Action: {f.recommended_action}</p> : null}
                  {f.status === 'completed' && f.completion_notes ? <p className="mt-1 text-[0.68rem] font-semibold text-teal-deep/60">Completed notes: {f.completion_notes}</p> : null}
                  {f.status === 'cancelled' && f.cancellation_reason ? <p className="mt-1 text-[0.68rem] font-semibold text-coral/80">Cancelled: {f.cancellation_reason}</p> : null}
                  {f.rescheduled_from ? <p className="mt-0.5 text-[0.66rem] text-teal-deep/45">Rescheduled from: {f.rescheduled_from}</p> : null}
                </div>
              );
            })}</div>}
          </section>

          <section className="card-ivory p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2"><Paperclip size={15} className="text-teal-deep"/><h3 className="text-sm font-extrabold text-teal-deep">Medical documents</h3></div>
              <button onClick={()=>setShowUpload(v=>!v)} className="btn-mint flex items-center gap-1.5 px-3 py-1.5 text-xs"><Upload size={12}/> Upload</button>
            </div>
            <AnimatePresence>{showUpload && (
              <motion.form initial={{opacity:0,height:0}} animate={{opacity:1,height:'auto'}} exit={{opacity:0,height:0}} onSubmit={uploadDocument} className="mb-3 overflow-hidden rounded-2xl border border-mint/30 bg-mint/5 p-3 space-y-2">
                <label><span className={LABEL}>File (PDF/JPG/PNG/WEBP/HEIC, max 10 MB) *</span><input className={INPUT} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,image/*,application/pdf" onChange={e=>setDocFile(e.target.files?.[0]||null)} required /></label>
                <label><span className={LABEL}>Category</span><select className={INPUT} value={docCat} onChange={e=>setDocCat(e.target.value)}>{DOC_CATEGORIES.map(c=><option key={c} value={c}>{c.replace(/_/g,' ')}</option>)}</select></label>
                <label><span className={LABEL}>Notes</span><input className={INPUT} value={docNotes} onChange={e=>setDocNotes(e.target.value)} placeholder="Optional notes" /></label>
                <div className="flex gap-2"><button type="submit" disabled={docSaving} className="btn-mint px-4 py-2 text-xs disabled:opacity-60">{docSaving?'Uploading…':'Upload securely'}</button><button type="button" onClick={()=>setShowUpload(false)} className="rounded-full bg-teal-deep/5 px-4 py-2 text-xs font-bold text-teal-deep/60">Cancel</button></div>
                <p className="text-[0.64rem] text-teal-deep/50">Stored outside public directories, accessed via authenticated endpoints. No automatic medical-value extraction.</p>
              </motion.form>
            )}</AnimatePresence>

            {documents.length === 0 ? <div className="rounded-xl bg-ivory/70 px-3 py-4 text-xs font-semibold text-teal-deep/45">No medical documents uploaded yet.</div> : (
              <div className="space-y-2">{documents.map(doc => (
                <div key={doc.id} className="rounded-xl border border-teal-deep/10 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0"><p className="truncate text-xs font-extrabold text-teal-deep">{doc.original_filename}</p><p className="text-[0.68rem] text-teal-deep/55">{doc.category} • {doc.mime_type} • {(doc.size_bytes/1024).toFixed(1)} KB</p><p className="text-[0.66rem] text-teal-deep/45">Uploaded: {fmtDateTime(doc.created_at)} {doc.uploaded_by ? `• by worker #${doc.uploaded_by}` : ''}</p></div>
                    <Badge tone="gray">{doc.verified ? 'verified' : 'uploaded'}</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button onClick={()=>openDoc(doc,false)} className="flex items-center gap-1.5 rounded-full bg-mint-soft px-3 py-1.5 text-xs font-bold text-teal-deep"><Eye size={12}/> Preview</button>
                    <button onClick={()=>openDoc(doc,true)} className="flex items-center gap-1.5 rounded-full bg-teal-deep/5 px-3 py-1.5 text-xs font-bold text-teal-deep/70"><Download size={12}/> Download</button>
                    <button onClick={()=>removeDocument(doc)} className="flex items-center gap-1.5 rounded-full bg-coral/10 px-3 py-1.5 text-xs font-bold text-coral"><Trash2 size={12}/> Remove</button>
                  </div>
                </div>
              ))}</div>
            )}
          </section>

          <section className="card-ivory p-5">
            <div className="mb-3 flex items-center gap-2"><CheckCircle2 size={15} className="text-teal-deep"/><h3 className="text-sm font-extrabold text-teal-deep">Care plan & requests</h3></div>
            <p className="text-xs font-medium text-teal-deep/60">Care plan tasks: {(data.care_plan_tasks||[]).length} • Requests: {(data.requests||[]).length}</p>
            {((data.care_plan_tasks||[]).length === 0 && (data.requests||[]).length === 0) ? <p className="mt-2 text-xs font-semibold text-teal-deep/45">No care plan tasks or requests recorded for this beneficiary yet.</p> : (
              <div className="mt-2 space-y-2">
                {(data.care_plan_tasks||[]).slice(0,4).map(tk => <div key={`t${tk.id}`} className="rounded-xl bg-ivory/70 p-2.5 text-xs"><b>{tk.title}</b> — {tk.status} {tk.due_date ? `• due ${tk.due_date}` : ''}</div>)}
                {(data.requests||[]).slice(0,4).map(r => <div key={`r${r.id}`} className="rounded-xl bg-ivory/70 p-2.5 text-xs"><b>{r.category}</b> — {r.status} <div className="text-teal-deep/55">{(r.message||'').slice(0,80)}</div></div>)}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
