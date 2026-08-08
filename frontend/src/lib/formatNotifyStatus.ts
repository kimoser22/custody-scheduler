import type { NotifyStatus } from "@/lib/types";

/** Quiet delivery line for the requester's pending card. Null while still queued. */
export function formatNotifyStatus(
  emailStatus: NotifyStatus | null | undefined,
  smsStatus: NotifyStatus | null | undefined,
): string | null {
  const email = emailStatus ?? null;
  const sms = smsStatus ?? null;

  if (
    (email == null || email === "queued") &&
    (sms == null || sms === "queued")
  ) {
    return null;
  }

  if (email === "sent" && sms === "sent") {
    return "Notified by email and SMS";
  }
  if (email === "sent" && sms === "skipped_opt_out") {
    return "Emailed · SMS skipped (opted out)";
  }
  if (email === "sent" && sms === "skipped_no_phone") {
    return "Emailed · no phone on file";
  }
  if (sms === "sent" && email === "skipped_no_address") {
    return "SMS sent · no email on file";
  }
  if (email === "skipped_no_address" && sms === "skipped_opt_out") {
    return "Couldn't notify — other parent opted out of SMS and has no email";
  }
  if (email === "skipped_no_address" && sms === "skipped_no_phone") {
    return "Couldn't notify — no email or phone on file";
  }
  if (email === "sent" && (sms == null || sms === "queued")) {
    return "Notified by email";
  }
  if (sms === "sent" && (email == null || email === "queued")) {
    return "Notified by SMS";
  }
  if (email === "failed" && sms === "failed") {
    return "Email and SMS may not have arrived";
  }
  if (email === "failed" && sms === "sent") {
    return "SMS sent · email may not have arrived";
  }
  if (sms === "failed" && email === "sent") {
    return "Emailed · SMS may not have arrived";
  }
  if (email === "failed") {
    return "Email may not have arrived";
  }
  if (sms === "failed") {
    return "SMS may not have arrived";
  }
  if (sms === "skipped_opt_out") {
    return "SMS skipped (opted out)";
  }
  if (email === "skipped_no_address") {
    return "No email on file";
  }
  if (sms === "skipped_no_phone") {
    return "No phone on file";
  }
  return null;
}

/** Soft create-time notice when the counterparty may not get a ping. */
export function formatNotifyCreateNotice(
  emailStatus: NotifyStatus | null | undefined,
  smsStatus: NotifyStatus | null | undefined,
): string | null {
  const emailOk =
    emailStatus === "sent" ||
    emailStatus === "queued" ||
    emailStatus === "unconfigured";
  const smsOptOut = smsStatus === "skipped_opt_out";
  const emailMissing = emailStatus === "skipped_no_address";
  const smsMissing =
    smsStatus === "skipped_no_phone" || smsStatus === "skipped_opt_out";

  if (smsOptOut && emailOk) {
    return "The other parent opted out of SMS; we emailed them instead.";
  }
  if (emailMissing && smsMissing) {
    return "They won't get an automatic ping—tell them in person or update contacts.";
  }
  return null;
}
