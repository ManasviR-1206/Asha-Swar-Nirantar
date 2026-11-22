import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { AlertTriangle, Crosshair, Filter, List, MapPin, Navigation, RefreshCw, Save, Search, X } from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import { useI18n } from "../../lib/i18n.jsx";

const FILTER_IDS = [
  { id: "all", key: "geopulse.filter.all" },
  { id: "pending_visits", key: "geopulse.filter.pendingVisits" },
  { id: "upcoming_followups", key: "geopulse.filter.upcomingFollowups" },
  { id: "maternal_care", key: "geopulse.filter.maternalCare" },
  { id: "newborn_care", key: "geopulse.filter.newbornCare" },
  { id: "immunisation", key: "geopulse.filter.immunisation" },
  { id: "referrals", key: "geopulse.filter.referrals" },
];

const STATUS_COLORS = {
  referral: "#e85d75",
  pending: "#f59e0b",
  upcoming: "#2f7a6d",
  maternal: "#8b5cf6",
  newborn: "#3b82f6",
  normal: "#64748b",
};

export default function GeoPulse() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialFilter = searchParams.get("filter") || "all";
  const [filter, setFilter] = useState(initialFilter);
  const [data, setData] = useState({ items: [], mapped_items: [], total_households: 0, mapped_households: 0, note: "" });
  const [facilities, setFacilities] = useState({ items: [], available: false, note: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isOffline, setIsOffline] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false);
  const [isCached, setIsCached] = useState(false);
  const [cacheSavedAt, setCacheSavedAt] = useState(null);
  const [showFacilityForm, setShowFacilityForm] = useState(false);
  const [facilityForm, setFacilityForm] = useState({ name: "", facility_type: "PHC", address: "", village: "", latitude: "", longitude: "", location_source: "manual_verified", verification_status: "verified" });
  const [facilitySaving, setFacilitySaving] = useState(false);
  const [query, setQuery] = useState("");
  const [editingLocId, setEditingLocId] = useState(null);
  const [locDraft, setLocDraft] = useState({ latitude: "", longitude: "", location_source: "manual_verified" });
  const [locSaving, setLocSaving] = useState(false);

  const filters = useMemo(() => FILTER_IDS.map((f) => ({ ...f, label: t(f.key) })), [t]);

  const CACHE_KEY = "geopulse_cache_v1_redacted";

  const redactForCache = (payload) => {
    // Safety: do not persist beneficiary names/addresses/personal details.
    const items = (payload?.items || []).map((h) => ({
      household_id: h.household_id,
      qr_id: h.qr_id,
      village: h.village || "",
      member_count: h.member_count,
      beneficiary_count: h.beneficiary_count,
      data_origin: h.data_origin,
      is_synthetic_demo: !!h.is_synthetic_demo,
      latitude: h.latitude,
      longitude: h.longitude,
      location_source: h.location_source || "",
      location_updated_at: h.location_updated_at || null,
      has_coordinates: !!h.has_coordinates,
      status: h.status,
      last_visit_date: h.last_visit_date || null,
      pending_followups_count: h.pending_followups_count ?? 0,
      upcoming_followups_count: h.upcoming_followups_count ?? 0,
      active_alerts_count: h.active_alerts_count ?? 0,
      maternal_count: h.maternal_count ?? 0,
      newborn_count: h.newborn_count ?? 0,
      referral_count: h.referral_count ?? 0,
      beneficiaries: [], // redacted
    }));
    return {
      items,
      mapped_items: items.filter((i) => i.has_coordinates),
      total_households: payload?.total_households ?? items.length,
      mapped_households: payload?.mapped_households ?? items.filter((i) => i.has_coordinates).length,
      filters_applied: payload?.filters_applied || "all",
      synthetic_labeled: true,
      note: (payload?.note || "") + " (Cached redacted view)",
    };
  };

  const saveCache = (f, res, fac) => {
    try {
      const redacted = redactForCache(res);
      const safeFacilities = {
        items: (fac?.items || []).filter((x) => x.verification_status === "verified").map((x) => ({
          id: x.id, name: x.name, facility_type: x.facility_type, address: x.address || "", village: x.village || "",
          latitude: x.latitude, longitude: x.longitude, location_source: x.location_source || "", verification_status: x.verification_status,
        })),
        available: !!fac?.available,
        note: fac?.note || "",
      };
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ savedAt: new Date().toISOString(), filter: f, data: redacted, facilities: safeFacilities }));
    } catch { /* ignore storage failures */ }
  };

  const loadCache = (f) => {
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.filter !== f || !parsed.data) return null;
      return parsed;
    } catch { return null; }
  };

  useEffect(() => {
    const on = () => setIsOffline(false);
    const off = () => setIsOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  const load = async (f = filter) => {
    setLoading(true);
    setError("");
    try {
      const [res, fac] = await Promise.all([
        api.get(`/geopulse/households?filter=${encodeURIComponent(f)}`),
        api.get("/geopulse/facilities").catch(() => ({ items: [], available: false, note: t("geopulse.noFacilityData") })),
      ]);
      const nextData = res || { items: [], mapped_items: [], total_households: 0, mapped_households: 0 };
      const nextFac = fac || { items: [], available: false };
      setData(nextData);
      setFacilities(nextFac);
      setIsCached(false);
      setCacheSavedAt(null);
      saveCache(f, nextData, nextFac);
    } catch (e) {
      const msg = e.message || t("geopulse.loadError");
      const cached = loadCache(f);
      if (cached?.data) {
        setData(cached.data);
        setFacilities(cached.facilities || { items: [], available: false });
        setIsCached(true);
        setCacheSavedAt(cached.savedAt || null);
        setError("");
        showToast(t("geopulse.cached") + " (" + t("geopulse.cachedMayBeStale") + ")", "warn");
      } else if ((data.items || []).length > 0) {
        setIsCached(true);
        setError("");
        showToast(t("geopulse.cached") + " (" + t("geopulse.cachedMayBeStale") + ")", "warn");
      } else {
        setError(msg);
        showToast(msg, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const f = searchParams.get("filter");
    if (f && FILTER_IDS.some((x) => x.id === f)) setFilter(f);
  }, [searchParams]);

  useEffect(() => { load(filter); }, [filter]); // eslint-disable-line

  const q = query.trim().toLowerCase();
  const filteredItems = useMemo(() => {
    const items = data.items || [];
    if (!q) return items;
    return items.filter((h) => [h.qr_id, h.village, h.address, String(h.household_id)].some((v) => String(v || "").toLowerCase().includes(q)));
  }, [data, q]);
  const mapped = useMemo(() => filteredItems.filter((i) => i.has_coordinates), [filteredItems]);
  const listItems = filteredItems;
  const center = mapped.length ? [mapped[0].latitude, mapped[0].longitude] : [20.5937, 78.9629];

  const submitFacility = async () => {
    const lat = parseFloat(facilityForm.latitude);
    const lng = parseFloat(facilityForm.longitude);
    if (!facilityForm.name.trim()) { showToast(t("geopulse.facilityNameRequired"), "warn"); return; }
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) { showToast(t("geopulse.facilityCoordsRequired"), "warn"); return; }
    setFacilitySaving(true);
    try {
      await api.post("/geopulse/facilities", { ...facilityForm, latitude: lat, longitude: lng });
      showToast(t("geopulse.facilitySaved"), "success");
      setFacilityForm({ name: "", facility_type: "PHC", address: "", village: "", latitude: "", longitude: "", location_source: "manual_verified", verification_status: "verified" });
      setShowFacilityForm(false);
      await load(filter);
    } catch (e) {
      showToast(e.message || t("geopulse.facilitySaveError"), "error");
    } finally {
      setFacilitySaving(false);
    }
  };

  const openLocEditor = (h) => {
    setEditingLocId(h.household_id);
    setLocDraft({
      latitude: h.latitude ?? "",
      longitude: h.longitude ?? "",
      location_source: h.location_source || "manual_verified",
    });
  };

  const captureGps = () => {
    if (!navigator.geolocation) { showToast(t("geopulse.gpsUnavailable", "GPS is not available in this browser."), "error"); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocDraft((d) => ({ ...d, latitude: Number(pos.coords.latitude.toFixed(6)), longitude: Number(pos.coords.longitude.toFixed(6)), location_source: "gps" }));
        showToast(t("geopulse.gpsCaptured", "GPS location captured. Review and save."), "success");
      },
      (err) => showToast(err?.message || t("geopulse.gpsDenied", "Could not get GPS location."), "error"),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  };

  const saveLocation = async (householdId) => {
    const lat = parseFloat(locDraft.latitude);
    const lng = parseFloat(locDraft.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) { showToast(t("geopulse.invalidCoords", "Enter valid latitude and longitude."), "warn"); return; }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) { showToast(t("geopulse.invalidCoords", "Enter valid latitude and longitude."), "warn"); return; }
    setLocSaving(true);
    try {
      await api.patch(`/households/${householdId}/location`, { latitude: lat, longitude: lng, location_source: locDraft.location_source || "manual_verified" });
      showToast(t("geopulse.locationSaved", "Household location saved."), "success");
      setEditingLocId(null);
      await load(filter);
    } catch (e) {
      showToast(e?.message || t("geopulse.locationSaveError", "Could not save location."), "error");
    } finally {
      setLocSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-teal-deep">{t("geopulse.title")}</h1>
          <p className="text-sm font-medium text-teal-deep/60">Village Health Intelligence Map â€” actual stored coordinates only, no fabricated locations.</p>
        </div>
        <button onClick={() => load(filter)} className="btn-secondary inline-flex items-center gap-2 px-3 py-2 text-sm">
          <RefreshCw size={15} /> {t("geopulse.refresh")}
        </button>
      </div>

      <div className="rounded-2xl border border-amber-300/40 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-900">
        <AlertTriangle size={14} className="mr-1 inline" />
        {t("geopulse.authNote")}
      </div>
      {(isOffline || isCached) && (
        <div className="rounded-2xl border border-sky-300/40 bg-sky-50 px-4 py-3 text-xs font-semibold text-sky-900">
          {isOffline ? t("geopulse.offline") + " " : ""}
          {isCached ? `Showing cached redacted data${cacheSavedAt ? ` (saved ${new Date(cacheSavedAt).toLocaleString()})` : ""}; it may be stale. ` : ""}
          {t("geopulse.cachePrivacy")}
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-sm">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-teal-deep/40" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("geopulse.searchPlaceholder", "Search household, village, or ID")} className="w-full rounded-xl border border-teal-deep/10 bg-white py-2 pl-9 pr-3 text-sm" />
        </div>
        <div className="flex flex-wrap gap-2">
          {filters.map((f) => (
            <button key={f.id} onClick={() => setFilter(f.id)} className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${filter === f.id ? "bg-teal-deep text-mint" : "bg-white text-teal-deep/70 border border-teal-deep/10"}`}>
              <Filter size={12} className="mr-1 inline" /> {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-3">
        <div className="rounded-xl border border-teal-deep/10 bg-white p-3 text-sm"><div className="text-teal-deep/55 text-xs font-bold">Total households</div><div className="text-lg font-extrabold text-teal-deep">{data.total_households ?? 0}</div></div>
        <div className="rounded-xl border border-teal-deep/10 bg-white p-3 text-sm"><div className="text-teal-deep/55 text-xs font-bold">Mapped</div><div className="text-lg font-extrabold text-teal-deep">{data.mapped_households ?? mapped.length}</div></div>
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm"><div className="text-amber-700/70 text-xs font-bold">Unmapped</div><div className="text-lg font-extrabold text-amber-800">{Math.max(0, (data.total_households ?? 0) - (data.mapped_households ?? mapped.length))}</div></div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="overflow-hidden rounded-2xl border border-teal-deep/10 bg-white shadow-sm">
          <div className="border-b border-teal-deep/10 px-4 py-3 text-sm font-bold text-teal-deep">
            <MapPin size={15} className="mr-1 inline" /> {t("geopulse.map")} ({mapped.length} {t("geopulse.mapped")} / {data.total_households || 0} {t("geopulse.households")})
          </div>
          {error ? <div className="p-4 text-sm text-coral">{error}</div> : mapped.length === 0 ? (
            <div className="flex min-h-[280px] flex-col items-center justify-center px-6 py-10 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#F4DCE4] text-[#7A1638]"><MapPin size={28} /></div>
              <h3 className="mt-4 text-base font-extrabold text-teal-deep">{t("geopulse.noCoordsTitle")}</h3>
              <p className="mt-2 max-w-xl text-sm text-teal-deep/65">
                {t("geopulse.noCoordsBody")}
              </p>
              <p className="mt-2 text-xs font-semibold text-teal-deep/55">{t("geopulse.noCoordsList")}</p>
            </div>
          ) : (
            <div className="h-[420px] w-full">
              <MapContainer center={center} zoom={13} style={{ height: "100%", width: "100%" }}>
                <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                {mapped.map((h) => (
                  <CircleMarker key={h.household_id} center={[h.latitude, h.longitude]} radius={10}
                    pathOptions={{ color: STATUS_COLORS[h.status] || STATUS_COLORS.normal, fillColor: STATUS_COLORS[h.status] || STATUS_COLORS.normal, fillOpacity: 0.8 }}>
                    <Popup>
                      <div className="text-xs">
                        <div className="font-bold">{h.village || "Household"} {h.qr_id ? `(${h.qr_id})` : ""}</div>
                        <div>{t("geopulse.status")}: {h.status}</div>
                        <div>{t("geopulse.members")}: {h.member_count}</div>
                        <div>{t("geopulse.pendingFollowups")}: {h.pending_followups_count}</div>
                        <div>{t("geopulse.upcomingFollowups")}: {h.upcoming_followups_count}</div>
                        <div>{t("geopulse.activeAlerts")}: {h.active_alerts_count}</div>
                        <div>{t("geopulse.lastVisit")}: {h.last_visit_date || t("common.notRecorded")}</div>
                        <button className="mt-2 rounded bg-teal-700 px-2 py-1 text-white" onClick={() => navigate(`/app/households/${h.household_id}`)}>{t("geopulse.openHousehold")}</button>
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
                {(facilities.items || []).filter((f) => f.latitude != null && f.longitude != null && f.verification_status === "verified").map((f) => (
                  <CircleMarker key={`fac-${f.id}`} center={[f.latitude, f.longitude]} radius={9}
                    pathOptions={{ color: "#0ea5e9", fillColor: "#0ea5e9", fillOpacity: 0.85 }}>
                    <Popup>
                      <div className="text-xs">
                        <div className="font-bold">{f.name}</div>
                        <div>{f.facility_type || "Facility"} {f.village ? `Â· ${f.village}` : ""}</div>
                        <div>{f.address || ""}</div>
                        <div className="mt-1 font-semibold text-sky-700">{t("geopulse.verifiedFacility")}</div>
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
            </div>
          )}
          {mapped.length > 0 && (
            <div className="flex flex-wrap gap-2 border-t border-teal-deep/10 px-4 py-3 text-[11px] font-semibold text-teal-deep/70">
              {Object.entries(STATUS_COLORS).map(([k, c]) => (<span key={k} className="inline-flex items-center gap-1"><span style={{ background: c, width: 10, height: 10, borderRadius: 999 }} />{k}</span>))}
              <span className="inline-flex items-center gap-1"><span style={{ background: "#0ea5e9", width: 10, height: 10, borderRadius: 999 }} />{t("geopulse.verifiedFacility")}</span>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-teal-deep/10 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-sm font-bold text-teal-deep"><List size={15} /> {t("geopulse.listFallback")}</div>
          <p className="mb-3 text-xs text-teal-deep/60">{data.note || t("geopulse.listNote")}</p>
          <div className="max-h-[420px] space-y-2 overflow-auto pr-1">
            {loading ? <div className="text-sm text-teal-deep/60">{t("common.loading")}</div> : listItems.length === 0 ? <div className="text-sm text-teal-deep/60">{t("geopulse.noMatch")}</div> : listItems.map((h) => (
              <div key={h.household_id} className="w-full rounded-xl border border-teal-deep/10 p-3 text-left hover:bg-teal-deep/5">
                <button onClick={() => navigate(`/app/households/${h.household_id}`)} className="w-full text-left">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-bold text-teal-deep">{h.village || "Household"} <span className="text-teal-deep/50">{h.qr_id}</span></div>
                    <span className="rounded-full px-2 py-0.5 text-[10px] font-bold text-white" style={{ background: STATUS_COLORS[h.status] || STATUS_COLORS.normal }}>{h.status}</span>
                  </div>
                  <div className="mt-1 text-[11px] text-teal-deep/65">
                    {h.has_coordinates ? `Coords: ${Number(h.latitude).toFixed(4)}, ${Number(h.longitude).toFixed(4)}` : t("geopulse.noCoordinatesFallback")}
                  </div>
                  <div className="mt-1 text-[11px] text-teal-deep/65">Pending {h.pending_followups_count} · Upcoming {h.upcoming_followups_count} · Alerts {h.active_alerts_count} · Last visit {h.last_visit_date || "-"}</div>
                </button>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button onClick={() => openLocEditor(h)} className="rounded-full bg-teal-deep/5 px-2.5 py-1 text-[10px] font-bold text-teal-deep hover:bg-teal-deep/10"><MapPin size={11} className="mr-1 inline" />{h.has_coordinates ? t("geopulse.editLocation", "Edit location") : t("geopulse.setLocation", "Set location")}</button>
                  {h.has_coordinates && <a href={`https://www.google.com/maps/dir/?api=1&destination=${h.latitude},${h.longitude}`} target="_blank" rel="noreferrer" className="rounded-full bg-teal-deep/5 px-2.5 py-1 text-[10px] font-bold text-teal-deep hover:bg-teal-deep/10"><Navigation size={11} className="mr-1 inline" />{t("geopulse.directions", "Directions")}</a>}
                </div>
                {editingLocId === h.household_id && (
                  <div className="mt-2 space-y-2 rounded-lg border border-teal-deep/10 bg-ivory/60 p-2">
                    <div className="grid grid-cols-2 gap-2">
                      <input className="rounded border px-2 py-1 text-xs" placeholder={t("geopulse.latitude", "Latitude")} value={locDraft.latitude} onChange={(e)=>setLocDraft({...locDraft, latitude:e.target.value})} />
                      <input className="rounded border px-2 py-1 text-xs" placeholder={t("geopulse.longitude", "Longitude")} value={locDraft.longitude} onChange={(e)=>setLocDraft({...locDraft, longitude:e.target.value})} />
                    </div>
                    <select className="w-full rounded border px-2 py-1 text-xs" value={locDraft.location_source} onChange={(e)=>setLocDraft({...locDraft, location_source:e.target.value})}>
                      <option value="gps">gps</option>
                      <option value="manual_verified">manual_verified</option>
                      <option value="verified_import">verified_import</option>
                    </select>
                    <div className="flex flex-wrap gap-2">
                      <button onClick={captureGps} type="button" className="rounded bg-white px-2 py-1 text-[10px] font-bold text-teal-deep border border-teal-deep/10"><Crosshair size={11} className="mr-1 inline" />{t("geopulse.captureGps", "Capture GPS")}</button>
                      <button disabled={locSaving} onClick={() => saveLocation(h.household_id)} type="button" className="rounded bg-teal-700 px-2 py-1 text-[10px] font-bold text-white disabled:opacity-60"><Save size={11} className="mr-1 inline" />{locSaving ? t("common.loading", "Saving...") : t("geopulse.saveLocation", "Save location")}</button>
                      <button onClick={() => setEditingLocId(null)} type="button" className="rounded px-2 py-1 text-[10px] font-bold text-teal-deep/60"><X size={11} className="mr-1 inline" />{t("common.cancel", "Cancel")}</button>
                    </div>
                    <p className="text-[10px] text-teal-deep/55">{t("geopulse.locationPrivacy", "Only store verified or worker-captured coordinates. Do not invent locations.")}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-xl bg-teal-deep/5 p-3 text-[11px] text-teal-deep/70">
            <div className="flex items-center justify-between gap-2">
              <div className="font-bold text-teal-deep">{t("geopulse.facilities")}</div>
              <button onClick={() => setShowFacilityForm((v) => !v)} className="rounded bg-teal-deep px-2 py-1 text-[10px] font-bold text-white">{showFacilityForm ? t("geopulse.close") : t("geopulse.registerImport")}</button>
            </div>
            <div className="mt-1">{facilities.note || (facilities.available ? t("geopulse.facilityAvailable") : t("geopulse.noFacilityData"))}</div>
            {showFacilityForm && (
              <div className="mt-3 space-y-2 rounded-lg border border-teal-deep/10 bg-white p-3">
                <div className="text-[10px] font-semibold text-teal-deep/60">{t("geopulse.facilityAuth")}</div>
                <input className="w-full rounded border px-2 py-1 text-xs" placeholder={t("geopulse.facilityName")} value={facilityForm.name} onChange={(e) => setFacilityForm({ ...facilityForm, name: e.target.value })} />
                <div className="grid grid-cols-2 gap-2">
                  <input className="rounded border px-2 py-1 text-xs" placeholder={t("geopulse.facilityType")} value={facilityForm.facility_type} onChange={(e) => setFacilityForm({ ...facilityForm, facility_type: e.target.value })} />
                  <input className="rounded border px-2 py-1 text-xs" placeholder={t("geopulse.villageArea")} value={facilityForm.village} onChange={(e) => setFacilityForm({ ...facilityForm, village: e.target.value })} />
                </div>
                <input className="w-full rounded border px-2 py-1 text-xs" placeholder={t("geopulse.address")} value={facilityForm.address} onChange={(e) => setFacilityForm({ ...facilityForm, address: e.target.value })} />
                <div className="grid grid-cols-2 gap-2">
                  <input className="rounded border px-2 py-1 text-xs" placeholder={t("geopulse.latitude")} value={facilityForm.latitude} onChange={(e) => setFacilityForm({ ...facilityForm, latitude: e.target.value })} />
                  <input className="rounded border px-2 py-1 text-xs" placeholder={t("geopulse.longitude")} value={facilityForm.longitude} onChange={(e) => setFacilityForm({ ...facilityForm, longitude: e.target.value })} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <select className="rounded border px-2 py-1 text-xs" value={facilityForm.location_source} onChange={(e) => setFacilityForm({ ...facilityForm, location_source: e.target.value })}>
                    <option value="manual_verified">manual_verified</option>
                    <option value="verified_import">verified_import</option>
                    <option value="gps">gps</option>
                  </select>
                  <select className="rounded border px-2 py-1 text-xs" value={facilityForm.verification_status} onChange={(e) => setFacilityForm({ ...facilityForm, verification_status: e.target.value })}>
                    <option value="verified">verified</option>
                    <option value="pending">pending</option>
                    <option value="rejected">rejected</option>
                  </select>
                </div>
                <button disabled={facilitySaving} onClick={submitFacility} className="w-full rounded bg-teal-700 px-2 py-1.5 text-xs font-bold text-white disabled:opacity-60">{facilitySaving ? t("geopulse.saving") : t("geopulse.saveFacility")}</button>
                <div className="text-[10px] text-teal-deep/55">Bulk import: POST /api/geopulse/facilities/import with {"{\"facilities\":[...]}"} (authorised, verified coordinates required).</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
