import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Search,
  UserPlus,
  Users,
  X,
  Download,
  FileJson,
  ShieldCheck,
  CalendarDays,
  CalendarClock,
  Pencil,
  Home,
  Phone,
  Mail,
  Stethoscope,
  AlertCircle,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { categoryLabel } from "../../lib/labels.js";

const CATEGORIES = ["pregnancy", "newborn", "child", "immunisation", "elderly", "nutrition", "adolescent", "community", "general"];
const VERIFICATION = [
  { value: "asha_verified", label: "ASHA verified" },
  { value: "registered", label: "Registered" },
  { value: "pending_verification", label: "Pending verification" },
  { value: "synthetic_demo", label: "Synthetic demo data" },
  { value: "demo", label: "Demo" },
];
const PREGNANCY_STATUS = ["", "pregnant", "postnatal", "not_pregnant", "unknown"];

const INPUT =
  "w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 px-4 py-2.5 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30";
const LABEL = "mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50";

function catKey(cat) {
  return `cat.${(cat || "").toLowerCase()}`;
}

function statusChipStyle(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("active") || s === "ok") return "bg-mint-soft text-teal-deep";
  if (s.includes("overdue") || s.includes("alert") || s.includes("danger")) return "bg-coral/15 text-coral";
  if (s.includes("follow") || s.includes("due") || s.includes("upcoming")) return "bg-lavender/20 text-midnight";
  return "bg-teal-deep/8 text-teal-deep/60";
}

function initials(name) {
  return (name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

function downloadJson(payload, name) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function emptyForm() {
  return {
    name: "",
    age: "",
    category: "general",
    gender: "",
    village: "",
    address: "",
    phone: "",
    email: "",
    date_of_birth: "",
    birth_date: "",
    lmp_date: "",
    household_id: "",
    pregnancy_status: "",
    medical_conditions: "",
    allergies: "",
    current_medications: "",
    child_health_notes: "",
    registration_notes: "",
    emergency_contact: "",
    emergency_contact_consent: false,
    verification_status: "asha_verified",
  };
}

function toForm(ben) {
  if (!ben) return emptyForm();
  const dateVal = (v) => (v ? String(v).slice(0, 10) : "");
  return {
    name: ben.name || "",
    age: ben.age ?? "",
    category: (ben.category || "general").toLowerCase(),
    gender: ben.gender || "",
    village: ben.village || "",
    address: ben.address || "",
    phone: ben.phone || "",
    email: ben.email || "",
    date_of_birth: dateVal(ben.date_of_birth),
    birth_date: dateVal(ben.birth_date),
    lmp_date: dateVal(ben.lmp_date),
    household_id: ben.household_id ?? "",
    pregnancy_status: ben.pregnancy_status || "",
    medical_conditions: ben.medical_conditions || "",
    allergies: ben.allergies || "",
    current_medications: ben.current_medications || "",
    child_health_notes: ben.child_health_notes || "",
    registration_notes: ben.registration_notes || "",
    emergency_contact: ben.emergency_contact || "",
    emergency_contact_consent: !!ben.emergency_contact_consent,
    verification_status: ben.verification_status || "asha_verified",
  };
}

export default function Beneficiaries() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [originFilter, setOriginFilter] = useState("all"); // all | registered | synthetic_demo
  const [items, setItems] = useState([]);
  const [households, setHouseholds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null); // beneficiary object or null for create

  useEffect(() => {
    api.get("/households").then((d) => setHouseholds(d.households || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (searchParams.get("add") === "1") {
      setEditing(null);
      setModalOpen(true);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchList = useCallback(
    async (q, cat) => {
      setLoading(true);
      setLoadError("");
      try {
        const params = new URLSearchParams();
        if (q) params.set("search", q);
        if (cat) params.set("category", cat);
        const qs = params.toString();
        const d = await api.get(`/beneficiaries${qs ? `?${qs}` : ""}`);
        setItems(d.beneficiaries || []);
      } catch (e) {
        const msg = e?.message || t("ben.loadErr", "Could not load beneficiaries.");
        setLoadError(msg);
        showToast(msg, "error");
      } finally {
        setLoading(false);
      }
    },
    [t]
  );

  const debounceRef = useRef(null);
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchList(search, category), 380);
    return () => clearTimeout(debounceRef.current);
  }, [search, category, fetchList]);

  const changeCategory = (c) => {
    setCategory(c);
    clearTimeout(debounceRef.current);
    fetchList(search, c);
  };

  const openCreate = () => { setEditing(null); setModalOpen(true); };
  const openEdit = (b, e) => {
    e?.stopPropagation();
    setEditing(b);
    setModalOpen(true);
  };

  const filteredItems = useMemo(() => {
    if (originFilter === "all") return items;
    if (originFilter === "synthetic_demo") return items.filter((b) => b.data_origin === "synthetic_demo" || b.verification_status === "synthetic_demo");
    if (originFilter === "registered") return items.filter((b) => b.data_origin !== "synthetic_demo" && b.verification_status !== "synthetic_demo");
    return items;
  }, [items, originFilter]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep">{t("nav.beneficiaries")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">
            Register, review, and update beneficiary profiles (household, health details, verification) with persistent records. Records are separated by origin (registered vs synthetic demo); public research data is not shown as beneficiaries.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <button onClick={openCreate} className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm">
            <UserPlus size={16} strokeWidth={2.4} /> Register Beneficiary
          </button>
        </div>
      </div>

      <div className="card-ivory flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-teal-deep/40" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, village or QR ID…"
            className="w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 py-2.5 pl-10 pr-9 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30"
          />
          {search && (
            <button onClick={() => setSearch("")} aria-label="Clear search" className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-teal-deep/40 hover:text-teal-deep">
              <X size={14} />
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => changeCategory("")} className={["chip px-3.5 py-1.5 transition-all", category === "" ? "bg-teal-deep text-white shadow-soft" : "bg-teal-deep/5 text-teal-deep/60 hover:bg-mint-soft hover:text-teal-deep"].join(" ")}>All</button>
          {CATEGORIES.map((c) => (
            <button key={c} onClick={() => changeCategory(c)} className={["chip px-3.5 py-1.5 transition-all", category === c ? "bg-teal-deep text-white shadow-soft" : "bg-teal-deep/5 text-teal-deep/60 hover:bg-mint-soft hover:text-teal-deep"].join(" ")}>{categoryLabel(c, t)}</button>
          ))}
        </div>
      </div>

      <div className="card-ivory flex flex-wrap items-center gap-2 p-3">
        <span className="text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">Data origin filter:</span>
        {[
          { key: "all", label: "All local records" },
          { key: "registered", label: "Registered data" },
          { key: "synthetic_demo", label: "Synthetic demo data" },
        ].map((o) => (
          <button key={o.key} onClick={() => setOriginFilter(o.key)} className={["chip px-3 py-1.5 transition-all", originFilter === o.key ? "bg-[#7A1638] text-white" : "bg-teal-deep/5 text-teal-deep/60 hover:bg-mint-soft hover:text-teal-deep"].join(" ")}>{o.label}</button>
        ))}
        <span className="ml-auto text-[0.68rem] font-semibold text-teal-deep/45">Public research data is available separately in Research &amp; Population Insights (not patient records).</span>
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}</div>
      ) : loadError ? (
        <div className="card-ivory p-6 text-center">
          <p className="text-sm font-extrabold text-teal-deep">{t("ben.loadErr", "Could not load beneficiaries.")}</p>
          <p className="mt-1 text-xs text-teal-deep/60">{loadError}</p>
          <button onClick={() => fetchList(search, category)} className="btn-mint mt-4 px-4 py-2 text-sm">{t("common.retry", "Retry")}</button>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="card-ivory">
          <Empty icon={Users} title="No beneficiaries found" subtitle={search || category || originFilter !== "all" ? "Try a different search, category, or origin filter." : (items.length === 0 ? t("ben.emptyNormalMode", "No beneficiaries are visible in this mode. If demo data exists, enable explicit demo mode to view it.") : "Register your first beneficiary to begin recording visits and health history.")}
            action={<button onClick={openCreate} className="btn-mint flex items-center gap-2 px-5 py-2.5 text-sm"><UserPlus size={16} strokeWidth={2.4} /> Register Beneficiary</button>} />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredItems.map((b, i) => (
            <motion.div key={b.id} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: Math.min(i * 0.05, 0.4), ease: "easeOut" }}
              className="card-ivory group relative p-5 text-left transition-all hover:-translate-y-0.5 hover:shadow-card">
              <button onClick={(e) => openEdit(b, e)} className="absolute right-3 top-3 rounded-full bg-teal-deep/5 p-2 text-teal-deep/50 hover:bg-mint-soft hover:text-teal-deep" title="Edit profile" aria-label="Edit profile">
                <Pencil size={14} />
              </button>
              <button onClick={() => navigate(`/app/beneficiaries/${b.id}`)} className="w-full text-left focus:outline-none">
                <div className="flex items-start gap-3.5 pr-8">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-teal-deep text-sm font-extrabold text-mint">{initials(b.name)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-base font-extrabold text-teal-deep">{b.name}</p>
                      <span className={`chip shrink-0 ${statusChipStyle(b.status)}`}>{b.status === "ok" ? "Active" : b.status || "—"}</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs font-semibold text-teal-deep/50">{b.age != null ? `${b.age} yrs` : "Age —"} · {b.village || "Village —"}</p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span className="chip bg-mint-soft text-teal-deep">{categoryLabel(b.category, t)}</span>
                  {b.household_id ? <span className="chip bg-teal-deep/5 text-teal-deep/55"><Home size={11}/> Household #{b.household_id}</span> : null}
                  {(b.data_origin === "synthetic_demo" || b.verification_status === "synthetic_demo") && (
                    <span className="chip bg-amber-100 text-amber-900 border border-amber-200">SYNTHETIC DEMO DATA</span>
                  )}
                  {b.verification_status && b.verification_status !== "asha_verified" && b.verification_status !== "synthetic_demo" ? <span className="chip bg-lavender/20 text-midnight">{b.verification_status.replace(/_/g," ")}</span> : null}
                  {b.last_visit_date && <span className="chip bg-teal-deep/5 text-teal-deep/55"><CalendarDays size={11}/> Last: {b.last_visit_date}</span>}
                  {b.next_followup_date && <span className="chip bg-lavender/20 text-midnight"><CalendarClock size={11}/> Next: {b.next_followup_date}</span>}
                </div>
                <p className="mt-3 truncate font-mono text-[0.68rem] font-semibold tracking-wide text-teal-deep/35">{b.qr_id}</p>
              </button>
            </motion.div>
          ))}
        </div>
      )}

      <BeneficiaryModal
        open={modalOpen}
        editing={editing}
        households={households}
        onClose={() => { setModalOpen(false); setEditing(null); }}
        onSaved={() => fetchList(search, category)}
      />
    </div>
  );
}

function BeneficiaryModal({ open, editing, households, onClose, onSaved }) {
  const { t } = useI18n();
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("basic");

  useEffect(() => {
    if (open) {
      setForm(toForm(editing));
      setCreated(null);
      setSaving(false);
      setActiveTab("basic");
    }
  }, [open, editing]);

  const set = (k) => (e) => {
    const v = e?.target?.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };

  const buildPayload = () => {
    const p = {
      name: form.name.trim(),
      age: form.age === "" ? 0 : Number(form.age),
      category: form.category,
      gender: (form.gender || "").trim(),
      village: (form.village || "").trim(),
      address: (form.address || "").trim(),
      phone: (form.phone || "").trim() || null,
      email: (form.email || "").trim() || null,
      date_of_birth: form.date_of_birth || null,
      birth_date: form.birth_date || null,
      lmp_date: form.lmp_date || null,
      household_id: form.household_id === "" ? null : Number(form.household_id),
      pregnancy_status: (form.pregnancy_status || "").trim(),
      medical_conditions: (form.medical_conditions || "").trim(),
      allergies: (form.allergies || "").trim(),
      current_medications: (form.current_medications || "").trim(),
      child_health_notes: (form.child_health_notes || "").trim(),
      registration_notes: (form.registration_notes || "").trim(),
      emergency_contact: (form.emergency_contact || "").trim(),
      emergency_contact_consent: !!form.emergency_contact_consent,
      verification_status: form.verification_status || "asha_verified",
    };
    return p;
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      showToast("Please enter the beneficiary's name.", "warn");
      return;
    }
    setSaving(true);
    try {
      if (editing?.id) {
        const payload = buildPayload();
        // PATCH accepts subset; sending full profile is fine
        const res = await api.patch(`/beneficiaries/${editing.id}`, payload);
        showToast(`${form.name.trim()} updated.`, "success");
        onSaved?.();
        onClose();
        return;
      }
      const d = await api.post("/beneficiaries", buildPayload());
      showToast(`${form.name.trim()} registered.`, "success");
      onSaved?.();
      const created0 = d?.beneficiary || d?.beneficiaries?.[0] || d;
      if (created0?.id) {
        setCreated(created0);
        setQrLoading(true);
        try {
          const qr = await api.get(`/beneficiaries/${created0.id}/qr`);
          setCreated((c) => ({ ...c, data_url: qr.data_url, qr_id: qr.qr_id || c.qr_id }));
        } catch {
          showToast("Could not load the QR code image.", "warn");
        } finally {
          setQrLoading(false);
        }
      } else {
        onClose();
      }
    } catch (err) {
      showToast(err.message || "Could not save beneficiary.", "error");
    } finally {
      setSaving(false);
    }
  };

  const tabs = [
    { id: "basic", label: "Basic" },
    { id: "household", label: "Household & contact" },
    { id: "health", label: "Health details" },
  ];

  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-end justify-center bg-teal-deep/50 p-0 backdrop-blur-sm sm:items-center sm:p-6" onClick={onClose}>
          <motion.div initial={{ y: 60, opacity: 0, scale: 0.98 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 40, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", damping: 28, stiffness: 340 }} onClick={(e) => e.stopPropagation()}
            className="card-ivory max-h-[94vh] w-full max-w-2xl overflow-y-auto rounded-b-none p-6 sm:rounded-3xl">
            {!created ? (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-extrabold text-teal-deep">{editing ? "Edit beneficiary profile" : "Register Beneficiary"}</h3>
                    <p className="mt-1 text-sm font-medium text-teal-deep/55">
                      {editing ? "Update profile and review recorded details. Measurements and documents have their own history/audit in Pulse Thread." : "Create a persistent beneficiary record. QR contains only an anonymous ID (no health data)."}
                    </p>
                  </div>
                  <button onClick={onClose} className="rounded-full bg-teal-deep/5 p-2 text-teal-deep/50 hover:bg-teal-deep/10"><X size={16}/></button>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {tabs.map(tab => (
                    <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} className={`chip px-3.5 py-1.5 ${activeTab===tab.id ? 'bg-teal-deep text-white' : 'bg-teal-deep/5 text-teal-deep/60'}`}>{tab.label}</button>
                  ))}
                </div>

                <form onSubmit={submit} className="mt-4 space-y-4">
                  {activeTab === "basic" && (
                    <div className="grid gap-3.5 sm:grid-cols-2">
                      <Field label="Full name *" className="sm:col-span-2"><input value={form.name} onChange={set("name")} required className={INPUT} placeholder="e.g. Lakshmi Devi" /></Field>
                      <Field label="Age"><input type="number" min="0" max="120" value={form.age} onChange={set("age")} className={INPUT} placeholder="Years" /></Field>
                      <Field label="Category *"><select value={form.category} onChange={set("category")} className={INPUT}>{CATEGORIES.map(c => <option key={c} value={c}>{categoryLabel(c,t)}</option>)}</select></Field>
                      <Field label="Gender"><select value={form.gender} onChange={set("gender")} className={INPUT}><option value="">Not recorded</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></Field>
                      <Field label="Date of birth"><input type="date" value={form.date_of_birth} onChange={set("date_of_birth")} className={INPUT} /></Field>
                      <Field label="Birth date (if applicable)"><input type="date" value={form.birth_date} onChange={set("birth_date")} className={INPUT} /></Field>
                      <Field label="LMP date (pregnancy)"><input type="date" value={form.lmp_date} onChange={set("lmp_date")} className={INPUT} /></Field>
                      <Field label="Verification status"><select value={form.verification_status} onChange={set("verification_status")} className={INPUT}>{VERIFICATION.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}</select></Field>
                    </div>
                  )}

                  {activeTab === "household" && (
                    <div className="grid gap-3.5 sm:grid-cols-2">
                      <Field label="Household"><select value={form.household_id} onChange={set("household_id")} className={INPUT}><option value="">No household linked</option>{households.map(h => <option key={h.id} value={h.id}>{h.village || "Household"} — {h.qr_id} (#{h.id})</option>)}</select></Field>
                      <Field label="Village"><input value={form.village} onChange={set("village")} className={INPUT} placeholder="Village/locality" /></Field>
                      <Field label="Address" className="sm:col-span-2"><input value={form.address} onChange={set("address")} className={INPUT} placeholder="Address / landmark" /></Field>
                      <Field label="Phone"><input value={form.phone} onChange={set("phone")} className={INPUT} placeholder="Contact number" /></Field>
                      <Field label="Email"><input type="email" value={form.email} onChange={set("email")} className={INPUT} placeholder="Email (optional)" /></Field>
                      <Field label="Emergency contact"><input value={form.emergency_contact} onChange={set("emergency_contact")} className={INPUT} placeholder="Name/number" /></Field>
                      <label className="sm:col-span-2 flex items-center gap-2 rounded-2xl bg-ivory/60 px-3 py-2.5 text-xs font-semibold text-teal-deep/70">
                        <input type="checkbox" checked={form.emergency_contact_consent} onChange={set("emergency_contact_consent")} className="h-4 w-4 accent-[#2f6f68]" />
                        Emergency contact consent recorded
                      </label>
                      <Field label="Registration / review notes" className="sm:col-span-2"><textarea rows={3} value={form.registration_notes} onChange={set("registration_notes")} className={INPUT} placeholder="Any registration or verification notes (factual)" /></Field>
                    </div>
                  )}

                  {activeTab === "health" && (
                    <div className="grid gap-3.5 sm:grid-cols-2">
                      <Field label="Pregnancy status"><select value={form.pregnancy_status} onChange={set("pregnancy_status")} className={INPUT}>{PREGNANCY_STATUS.map(s => <option key={s} value={s}>{s ? s.replace(/_/g,' ') : 'Not specified'}</option>)}</select></Field>
                      <Field label="(Informational)"><div className="rounded-2xl bg-ivory/60 px-3 py-2.5 text-xs font-medium text-teal-deep/55">Record facts only. Do not enter invented clinical information. Leave blank if not recorded.</div></Field>
                      <Field label="Existing medical conditions / history" className="sm:col-span-2"><textarea rows={3} value={form.medical_conditions} onChange={set("medical_conditions")} className={INPUT} placeholder="Known conditions or relevant medical history (as recorded)" /></Field>
                      <Field label="Allergies" className="sm:col-span-2"><textarea rows={2} value={form.allergies} onChange={set("allergies")} className={INPUT} placeholder="Known allergies (if recorded)" /></Field>
                      <Field label="Current medications" className="sm:col-span-2"><textarea rows={2} value={form.current_medications} onChange={set("current_medications")} className={INPUT} placeholder="Current medications (if recorded)" /></Field>
                      <Field label="Child health / vaccination notes" className="sm:col-span-2"><textarea rows={2} value={form.child_health_notes} onChange={set("child_health_notes")} className={INPUT} placeholder="Child health or vaccination notes (if recorded)" /></Field>
                    </div>
                  )}

                  <div className="flex gap-3 pt-1">
                    <button type="button" onClick={onClose} className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10">Cancel</button>
                    <button type="submit" disabled={saving} className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60">{saving ? "Saving…" : (editing ? "Save changes" : "Register")}</button>
                  </div>
                </form>
              </>
            ) : (
              <div className="text-center">
                <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", damping: 14 }} className="mx-auto mb-4 w-fit">
                  {qrLoading ? <div className="skeleton mx-auto h-44 w-44 rounded-2xl" /> : created.data_url ? (
                    <img src={created.data_url} alt={`QR code for ${created.qr_id}`} className="mx-auto h-44 w-44 rounded-2xl border border-teal-deep/10 bg-white p-2" />
                  ) : <div className="mx-auto flex h-44 w-44 items-center justify-center rounded-2xl bg-mint-soft text-teal-deep"><ShieldCheck size={40} /></div>}
                </motion.div>
                <h3 className="text-lg font-extrabold text-teal-deep">{created.name} is registered</h3>
                <p className="mt-1 font-mono text-xs font-bold tracking-wider text-teal-deep/60">{created.qr_id}</p>
                <p className="mx-auto mt-3 max-w-xs text-xs font-medium leading-relaxed text-teal-deep/55">QR contains only an anonymous beneficiary ID — no health information.</p>
                <div className="mt-5 flex flex-col gap-2.5">
                  {created.data_url && <a href={created.data_url} download={`${created.qr_id}.png`} className="btn-mint flex items-center justify-center gap-2 px-4 py-2.5 text-sm"><Download size={16} strokeWidth={2.4} /> Download QR</a>}
                  <button onClick={() => downloadJson({ type: "beneficiary", qr_id: created.qr_id, name: created.name, category: created.category, village: created.village || "", age: created.age ?? 0 }, created.qr_id)} className="flex items-center justify-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"><FileJson size={16} strokeWidth={2.4} /> Download data (JSON)</button>
                  <button onClick={onClose} className="rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10">Done</button>
                </div>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Field({ label, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className={LABEL}>{label}</span>
      {children}
    </label>
  );
}
