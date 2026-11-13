/**
 * Localises backend-generated status labels and rule messages.
 *
 * The backend stays English-first (its strings are used for logs and for
 * non-UI consumers) but every rule it emits also carries a stable
 * `*_code` plus parameters. The UI renders the code through the active
 * locale so the whole app speaks the worker's language.
 */

/** Maps a raw SMS / follow-up status to a translation key. */
export function statusKey(raw) {
  const s = String(raw || "").toLowerCase();
  if (!s) return "";
  if (s.includes("demo")) return "status.demoSent";
  if (s.includes("deliver")) return "status.delivered";
  if (s.includes("fail")) return "status.failed";
  if (s.includes("cancel")) return "status.cancelled";
  if (s.includes("sent")) return "status.sent";
  if (s.includes("overdue") || s.includes("missed")) return "status.overdue";
  if (s.includes("pending")) return "status.pending";
  if (s.includes("schedul") || s.includes("upcoming")) return "status.scheduled";
  if (s.includes("complete") || s.includes("done")) return "status.completed";
  if (s.includes("process")) return "status.processed";
  if (s.includes("open")) return "status.open";
  if (s.includes("ack")) return "status.acknowledged";
  return "";
}

/** Renders a raw status, falling back to a humanised form of the raw value. */
export function statusLabel(raw, t) {
  const key = statusKey(raw);
  if (key) return t(key);
  const s = String(raw || "").replace(/_/g, " ");
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

/** Localises a Pulse Drift rule message using `issue_code` + `issue_params`. */
export function driftIssue(item, t) {
  const code = item?.issue_code;
  if (!code) return item?.issue || "";
  const params = item?.issue_params || {};
  let text = t(`drift.issue.${code}`);
  if (!text || text === `drift.issue.${code}`) return item?.issue || "";
  Object.keys(params).forEach((k) => {
    text = text.replace(new RegExp(`\\{${k}\\}`, "g"), localiseParam(k, params[k], t));
  });
  return text;
}

/** Translates individual rule parameters (e.g. newborn checkpoint labels). */
function localiseParam(key, value, t) {
  if (key === "label") {
    const map = {
      "day-3": t("drift.day3", "day-3"),
      "day-7": t("drift.day7", "day-7"),
      "day-14": t("drift.day14", "day-14"),
      "6-week": t("drift.week6", "6-week"),
    };
    return map[value] || value;
  }
  return String(value ?? "");
}

/** Localises the recommended next action for a Pulse Drift item. */
export function driftAction(item, t) {
  const code = item?.issue_action_code;
  if (!code) return item?.recommended_action || "";
  const text = t(`drift.action.${code}`);
  if (!text || text === `drift.action.${code}`) return item?.recommended_action || "";
  return text;
}

/** Localises the dashboard's recent-activity sentence. */
export function activityLabel(item, t) {
  const code = item?.action_code;
  if (!code) return item?.action || "";
  const text = t(`dash.action.${code}`);
  if (!text || text === `dash.action.${code}`) return item?.action || "";
  return text;
}

const KNOWN_CATEGORIES = [
  "pregnancy",
  "newborn",
  "child",
  "immunisation",
  "elderly",
  "nutrition",
  "adolescent",
  "community",
  "general",
];

/** Human, translated label for a health category key. */
export function categoryLabel(cat, t) {
  const c = String(cat || "").toLowerCase();
  if (!c) return "—";
  if (KNOWN_CATEGORIES.includes(c)) return t(`cat.${c}`);
  if (c === "household") return t("cat.household");
  return c.charAt(0).toUpperCase() + c.slice(1);
}

const FOLLOWUP_TYPES = [
  "anc",
  "postnatal",
  "newborn",
  "vaccination",
  "nutrition",
  "community",
  "household",
  "growth",
  "followup",
];

/** Human, translated label for a follow-up / reminder type code. */
export function followupTypeLabel(type, t) {
  const c = String(type || "").toLowerCase();
  if (!c) return "—";
  if (FOLLOWUP_TYPES.includes(c)) return t(`ftype.${c}`);
  return c.charAt(0).toUpperCase() + c.slice(1);
}

const RELATIONS = ["head", "spouse", "child", "parent", "sibling", "grandparent", "other"];
const GENDERS = ["male", "female", "other", "transgender"];

/** Translated label for a household member's relation to the head. */
export function relationLabel(relation, t) {
  const c = String(relation || "").toLowerCase();
  if (!c) return "—";
  if (RELATIONS.includes(c)) return t(`rel.${c}`);
  return c.charAt(0).toUpperCase() + c.slice(1);
}

/** Translated label for a household member's gender. */
export function genderLabel(gender, t) {
  const c = String(gender || "").toLowerCase();
  if (!c) return "";
  if (GENDERS.includes(c)) return t(`gender.${c}`);
  return c.charAt(0).toUpperCase() + c.slice(1);
}
