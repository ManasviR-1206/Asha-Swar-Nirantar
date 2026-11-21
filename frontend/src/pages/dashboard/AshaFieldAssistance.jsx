import React from "react";
import { useI18n } from "../../lib/i18n.jsx";
import { BookOpen, Mic, ClipboardCheck, ShieldAlert, CalendarClock, MapPin, QrCode, Users, CheckCircle2, AlertTriangle } from "lucide-react";

const SECTIONS = [

  {
    icon: Users,
    title: "Households & Beneficiary Records",
    points: [
      "Register and maintain household and beneficiary profiles with accurate details.",
      "Use QR Scanner only for identifying existing beneficiary/household records.",
      "Capture household GPS location with permission, or enter verified manual coordinates.",
      "Do not fabricate locations, visit details, or clinical observations.",
    ],
  },
  {
    icon: ClipboardCheck,
    title: "Pulse Thread (History)",
    points: [
      "Pulse Thread shows chronological recorded visits, measurements, maternal/newborn care, immunisation, and referrals.",
      "Use it before a visit to review prior records and avoid duplicate or conflicting entries.",
      "If data is missing, record 'not recorded' rather than guessing.",
    ],
  },
  {
    icon: CalendarClock,
    title: "Pulse Drift (Follow-ups)",
    points: [
      "Pulse Drift highlights overdue/upcoming follow-ups and pending administrative actions.",
      "Complete, reschedule, or update follow-ups only after actual field action is taken.",
      "Use Smart Reminders and Notifications to track scheduled work; SMS is only sent when compliance is explicitly approved.",
    ],
  },
  {
    icon: ShieldAlert,
    title: "Danger Alerts & Referral",
    points: [
      "Danger Alerts are deterministic, rule-based flags from recorded observations/phrases â€” not diagnoses.",
      "Review trigger evidence, apply approved referral protocol, and document action taken.",
      "Escalate urgent cases through approved channels. Seek emergency care for danger signs.",
    ],
  },
  {
    icon: MapPin,
    title: "GeoPulse Map",
    points: [
      "GeoPulse shows only actual stored household coordinates and verified facility locations.",
      "Households without coordinates appear in the list fallback; capture GPS when possible.",
      "Use filters for pending visits, upcoming follow-ups, maternal/newborn care, and referrals/alerts.",
    ],
  },
];

export default function AshaFieldAssistance() {
  const { t } = useI18n();
  return (
    <div className="space-y-5">
      <div className="card-ivory p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#F4DCE4] text-[#7A1638]">
            <BookOpen size={22} />
          </div>
          <div>
            <h2 className="text-xl font-extrabold text-[#2B1F26]">{t("asha.title")}</h2>
            <p className="mt-1 text-sm font-medium text-[#685B62]">
              Practical workflow support for ASHA field duties. This section does not provide diagnosis, prescriptions, or invented clinical advice.
            </p>
          </div>
        </div>
        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-900">
          <AlertTriangle size={14} className="mr-1 inline" />
          Follow approved public-health protocols and local supervisor/PHC guidance. For danger signs or emergencies, use approved referral/escalation procedures immediately.
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.title} className="card-ivory p-5">
              <div className="mb-3 flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#F4DCE4] text-[#7A1638]">
                  <Icon size={18} />
                </div>
                <h3 className="text-sm font-extrabold text-[#2B1F26]">{s.title}</h3>
              </div>
              <ul className="space-y-2">
                {s.points.map((p) => (
                  <li key={p} className="flex items-start gap-2 text-sm text-[#685B62]">
                    <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-[#7A1638]" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      <div className="card-ivory p-5">
        <div className="mb-2 flex items-center gap-2 text-sm font-extrabold text-[#2B1F26]">
          <QrCode size={16} className="text-[#7A1638]" /> {t("asha.quickChecklist")}
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-sm text-[#685B62]">
          {[
            "Confirm identity before recording or saving.",
            "Review and correct extracted voice fields.",
            "Save only after explicit confirmation.",
            "Record actual observations; do not guess missing values.",
            "Check Pulse Drift before ending field day.",
            "Use GeoPulse to plan visits by location and priority.",
          ].map((item) => (
            <div key={item} className="rounded-xl border border-[#EADCE1] bg-[#FFF7F0] px-3 py-2">{item}</div>
          ))}
        </div>
      </div>
    </div>
  );
}