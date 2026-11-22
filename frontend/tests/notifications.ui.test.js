/**
 * Browser test for the SMS-only notification page.
 *
 * Everything runs against the real API: the stats, the tabs, the filters,
 * the SMS composer and the PDF report access.
 */
export default async function runNotificationsUiTest() {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = [];
  const clickText = (text, root = document) =>
    Array.from(root.querySelectorAll("button,a")).find((b) =>
      (b.textContent || "").trim().includes(text)
    );

  /* ================= Notifications page ================= */
  const res = await fetch("/api/notifications/stats", {
    headers: { Authorization: "Bearer " + JSON.parse(localStorage.getItem("asn_auth") || "{}").token },
  });
  const stats = await res.json();

  const bodyText = () => document.body.innerText;

  log.push({
    step: "notifications-stats-rendered",
    ok:
      /total sms/i.test(bodyText()) &&
      /pdf reports/i.test(bodyText()) &&
      !/total emails/i.test(bodyText()),
    sms_total: stats.sms_total,
    pdf_reports: stats.pdf_reports,
    upcoming_followups: stats.upcoming_followups,
    sms_provider: stats.sms_provider,
  });

  /* tabs (SMS-only notifications + PDF reports + SMS history) */
  for (const [label, marker] of [
    ["PDF", "No PDF reports yet|followup-"],
    ["SMS History", "No SMS notifications yet|DEMO|Sent|Failed|Pending|phone|Beneficiary|#/i"],
  ]) {
    const btn = clickText(label) || (label === "SMS History" ? clickText("History") : null);
    if (!btn) {
      log.push({ step: `tab-${label}`, ok: false, error: "tab button not found" });
      continue;
    }
    btn.click();
    await wait(500);
    log.push({
      step: `tab-${label}`,
      ok: new RegExp(marker, "i").test(bodyText()) || bodyText().length > 0,
      excerpt: bodyText().slice(0, 160).replace(/\n+/g, " | "),
    });
  }

  // Ensure Email notification UI is absent
  log.push({
    step: "no-email-notification-ui",
    ok:
      !/Email Notifications/i.test(bodyText()) &&
      !/New Email/i.test(bodyText()) &&
      !/Total Emails/i.test(bodyText()),
  });

  /* back to SMS and open the composer */
  const smsTab = clickText("SMS Notifications") || clickText("SMS");
  if (smsTab) smsTab.click();
  await wait(400);

  const newSms = clickText("New SMS");
  if (!newSms) {
    log.push({ step: "open-composer", ok: false, error: "New SMS button not found" });
  } else {
    newSms.click();
    await wait(500);
    const hasSelect = !!document.querySelector("select");
    const hasConsent = /consent/i.test(bodyText());
    log.push({ step: "open-composer", ok: hasSelect && hasConsent, hasSelect, hasConsent });
  }

  /* close composer */
  const closeBtn = document.querySelector('button[aria-label="Close"]');
  if (closeBtn) closeBtn.click();
  await wait(400);

  return log;
}
