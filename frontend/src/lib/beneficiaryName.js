const DEFAULT_NAME_VALUES = new Set([
  "",
  "name not mentioned",
  "unnamed",
  "unknown",
  "not mentioned",
]);

export function normalizeExtractedName(value) {
  if (typeof value !== "string") return null;
  const name = value.trim();
  if (!name) return null;
  if (DEFAULT_NAME_VALUES.has(name.toLowerCase())) return null;
  return name;
}

export function selectBeneficiaryName(...sources) {
  for (const source of sources) {
    const name = normalizeExtractedName(source);
    if (name) return name;
  }
  return null;
}

export function formatTaraHeardTranscript(transcript) {
  const spoken = typeof transcript === "string" ? transcript.trim() : "";
  const normalized = spoken.replace(/[.!?]+$/, "").trim();
  return normalized ? `I heard: ${normalized}. Is that correct?` : "";
}

export function mergeExtractedRecord(previous, incoming, { correcting = false } = {}) {
  const base = correcting && previous && typeof previous === "object" ? { ...previous } : {};
  const update = incoming && typeof incoming === "object" ? incoming : {};
  const merged = { ...base, ...update };

  const validIncomingName = selectBeneficiaryName(
    update.beneficiary_name,
    update.personal_details?.name,
    update.raw_structured?.beneficiary_name,
    update.raw_structured?.name,
    update.raw_structured?.personal_details?.name,
    update.name,
  );

  if (validIncomingName) {
    merged.beneficiary_name = validIncomingName;
  } else if (!Object.prototype.hasOwnProperty.call(update, "beneficiary_name") ||
             !normalizeExtractedName(update.beneficiary_name)) {
    // Partial updates and null/default name values never erase a valid name.
    if (correcting && previous) {
      const previousName = selectBeneficiaryName(
        previous.beneficiary_name,
        previous.personal_details?.name,
      );
      if (previousName) merged.beneficiary_name = previousName;
      else delete merged.beneficiary_name;
    } else if (!selectBeneficiaryName(base.beneficiary_name)) {
      delete merged.beneficiary_name;
    }
  }

  if (merged.beneficiary_name) {
    merged.personal_details = {
      ...(merged.personal_details && typeof merged.personal_details === "object" ? merged.personal_details : {}),
      name: merged.beneficiary_name,
    };
  }
  return merged;
}
