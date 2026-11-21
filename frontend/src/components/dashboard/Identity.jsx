import React, { useMemo, useState } from "react";
import { CheckCircle2, HelpCircle, UserPlus, AlertTriangle, Users, Search } from "lucide-react";
import { useI18n } from "../../lib/i18n.jsx";

/**
 * Small badge showing how the identity of one extracted visit was resolved.
 *   resolved   - matched to exactly one registered beneficiary
 *   ambiguous  - several candidates, the worker must choose
 *   unresolved - nobody identified, the worker must supply a name
 *   new        - no match, the worker may register a new beneficiary
 */
export function IdentityBadge({ visit }) {
  const { t } = useI18n();
  const status = visit?.identity_status || "unresolved";

  if (status === "resolved" && !visit?.clarification_required) {
    return (
      <span className="chip bg-mint/20 text-[0.65rem] font-bold text-teal-deep">
        <CheckCircle2 size={10} /> {t("vv.identityResolved", "Matched")}
      </span>
    );
  }
  if (status === "ambiguous") {
    return (
      <span className="chip bg-lavender/25 text-[0.65rem] font-bold text-midnight">
        <HelpCircle size={10} /> {t("vv.identityAmbiguous", "Choose beneficiary")}
      </span>
    );
  }
  if (status === "new") {
    return (
      <span className="chip bg-lavender/25 text-[0.65rem] font-bold text-midnight">
        <UserPlus size={10} /> {t("vv.identityNew", "Register new")}
      </span>
    );
  }
  if (visit?.clarification_required) {
    return (
      <span className="chip bg-coral/15 text-[0.65rem] font-bold text-coral">
        <AlertTriangle size={10} /> {t("vv.identityCheck", "Check details")}
      </span>
    );
  }
  return (
    <span className="chip bg-coral/15 text-[0.65rem] font-bold text-coral">
      <AlertTriangle size={10} /> {t("vv.identityUnresolved", "No beneficiary named")}
    </span>
  );
}

/**
 * Lets the ASHA worker attach this visit to the right person.
 *
 * Shows the candidates the backend proposed. The worker can also register a
 * new beneficiary or pick any other registered person.
 */
export function IdentityPicker({ visit, benList = [], onPick, onRegister }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const status = visit?.identity_status || "unresolved";
  const candidates = visit?.candidateMatches || [];
  const matched = visit?.matchedBeneficiary;

  const allOptions = useMemo(() => {
    const base = candidates.length
      ? candidates
      : (benList || []).map((b) => ({ id: b.id, name: b.name, village: b.village, age: b.age, household_id: b.household_id, qr_id: b.qr_id }));
    const term = q.trim().toLowerCase();
    if (!term) return base.slice(0, 8);
    return base.filter((b) => [b.name, b.village, b.qr_id, b.id, b.household_id].filter(Boolean).join(" ").toLowerCase().includes(term)).slice(0, 8);
  }, [candidates, benList, q]);

  if (status === "resolved" && matched) {
    return (
      <div className="mt-2 rounded-xl bg-mint-soft/50 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <CheckCircle2 size={13} className="text-teal-deep" />
          <span className="text-[0.7rem] font-bold text-teal-deep">
            {t("vv.matchFound", "Match found")}: {matched.name}
          </span>
          <button
            onClick={() => onPick && onPick(null)}
            className="ml-auto text-[0.65rem] font-bold text-teal-deep/60 underline-offset-2 hover:underline"
          >
            {t("vv.change", "Change")}
          </button>
        </div>
        <p className="mt-1 text-[0.65rem] font-medium text-teal-deep/70">
          {t("vv.beneficiaryId", "Beneficiary ID")}: {matched.id}
          {matched.household_id ? ` | ${t("vv.household", "Household")}: ${matched.household_id}` : ""}
          {matched.village ? ` | ${matched.village}` : ""}
        </p>
      </div>
    );
  }

  // Extraction-first manual linking: no automatic DB search/candidates.
  if (status === "extracted_unlinked" || status === "name_missing" || ((status === "unresolved" || status === "new") && !matched && candidates.length === 0)) {
    return (
      <div className="mt-2 rounded-xl bg-ivory/80 px-3 py-2.5 border border-teal-deep/10">
        <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/60">
          {t("vv.databaseLinking", "Database linking (manual)")}
        </p>
        <p className="mt-1 text-xs font-semibold text-teal-deep/75">
          {(status === "name_missing" || (!(visit?.beneficiary_name || visit?.spokenName) && status !== "extracted_unlinked"))
            ? t("vv.nameNotExtracted", "Beneficiary name not extracted.")
            : t("vv.nameExtractedManualLink", "Name extracted from transcript. Link manually only if needed before saving.")}
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            onClick={() => onPick && onPick({ __action: "link" })}
            className="chip bg-white text-[0.68rem] font-bold text-teal-deep shadow-soft transition hover:bg-mint-soft"
          >
            <Search size={10} /> {t("vv.linkExisting", "Link to existing beneficiary")}
          </button>
          {onRegister && (
            <button
              onClick={onRegister}
              className="chip bg-lavender/25 text-[0.68rem] font-bold text-midnight transition hover:bg-lavender/40"
            >
              <UserPlus size={10} /> {t("vv.registerNew", "Register new beneficiary")}
            </button>
          )}
        </div>
      </div>
    );
  }

  if (!allOptions.length && !onRegister && !q.trim()) return null;

  return (
    <div className="mt-2 rounded-xl bg-lavender/10 px-3 py-2.5">
      <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-midnight/70">
        {status === "ambiguous"
          ? t("vv.chooseWho", "Who is this visit for?")
          : status === "new" || status === "unresolved"
            ? t("vv.noMatchYet", "No existing beneficiary matched this name.")
            : t("vv.confirmIdentity", "Confirm beneficiary identity")}
      </p>
      <div className="mt-2 flex items-center gap-2 rounded-lg border border-teal-deep/10 bg-white px-2 py-1.5">
        <Search size={12} className="text-teal-deep/45" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("vv.searchBeneficiary", "Search existing beneficiaries")}
          className="w-full bg-transparent text-xs outline-none text-teal-deep placeholder:text-teal-deep/40"
        />
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {allOptions.map((c) => (
          <button
            key={c.id}
            onClick={() => onPick && onPick(c)}
            className="chip bg-white text-[0.68rem] font-bold text-teal-deep shadow-soft transition hover:bg-mint-soft"
          >
            <Users size={10} /> {c.name}
            {c.age != null ? ` | ${c.age}` : ""}
            {c.village ? ` | ${c.village}` : ""}
          </button>
        ))}
        {onRegister && (
          <button
            onClick={onRegister}
            className="chip bg-lavender/25 text-[0.68rem] font-bold text-midnight transition hover:bg-lavender/40"
          >
            <UserPlus size={10} /> {t("vv.registerNew", "Register new beneficiary")}
          </button>
        )}
      </div>
    </div>
  );
}

export default IdentityBadge;
