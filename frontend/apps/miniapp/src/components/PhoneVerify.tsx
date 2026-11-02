import { iraqiMobileE164 } from "@sop/shared";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError } from "../api";
import { useSession } from "../session";
import { haptic } from "../telegram";
import { Button, Field, Input } from "./ui";

/** True when `phone` (as typed) is the customer's WhatsApp-verified number. */
export function useIsVerified(phone: string): boolean {
  const { customer } = useSession();
  return customer.phone_verified && iraqiMobileE164(phone) === customer.phone;
}

/** WhatsApp code step under a phone input. Renders nothing when the shop does not require it. */
export function PhoneVerify({ phone }: { phone: string }) {
  const { api, business, setCustomer, t } = useSession();
  const e164 = iraqiMobileE164(phone);
  const verified = useIsVerified(phone);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (resendAt <= now) return;
    const id = setTimeout(() => setNow(Date.now()), 1000);
    return () => clearTimeout(id);
  }, [resendAt, now]);

  const fail = (e: unknown) => {
    haptic.error();
    setErr(e instanceof ApiError ? e.message : t("error_title"));
  };
  const send = useMutation({
    mutationFn: () => api.sendPhoneCode(phone),
    onSuccess: (r) => {
      haptic.success();
      setSentTo(r.phone);
      setCode("");
      setErr(null);
      setResendAt(Date.now() + r.resend_in * 1000);
      setNow(Date.now());
    },
    onError: (e) => {
      fail(e);
      const wait = e instanceof ApiError ? Number(e.details?.retry_after) : NaN;
      if (wait > 0) { setResendAt(Date.now() + wait * 1000); setNow(Date.now()); }
    },
  });
  const confirm = useMutation({
    mutationFn: () => api.confirmPhoneCode(code),
    onSuccess: (c) => { haptic.success(); setCustomer(c); setSentTo(null); setErr(null); },
    onError: fail,
  });

  if (!business.phone_verification_required || !e164) return null;
  if (verified) {
    return <p className="flex items-center gap-1.5 text-[13px] font-medium text-success">
      <span aria-hidden>✅</span>{t("phone_verified")}</p>;
  }

  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const awaiting = sentTo === e164;
  return (
    <div className="space-y-3 rounded-xl bg-accent/5 p-3">
      {!awaiting ? (
        <>
          <p className="text-[13px] text-hint">{t("why_verify")}</p>
          <Button type="button" variant="soft" className="w-full"
            disabled={send.isPending || wait > 0} onClick={() => send.mutate()}>
            💬 {wait > 0 ? t("resend_in", { s: wait }) : t("verify_whatsapp")}</Button>
        </>
      ) : (
        <form className="space-y-3" onSubmit={(ev) => {
          ev.preventDefault();
          if (code.length >= 4 && !confirm.isPending) confirm.mutate();
        }}>
          <p className="text-[13px]">{t("code_sent_to")} <bdi dir="ltr" className="font-semibold">{sentTo}</bdi></p>
          <Field label={t("code_label")}>
            <div className="flex gap-2">
              <Input value={code} inputMode="numeric" autoComplete="one-time-code" dir="ltr"
                maxLength={6} className="min-w-0 flex-1 px-2 text-center text-[17px] tracking-[0.15em]" autoFocus
                onChange={(ev) => { setCode(ev.target.value.replace(/[^\d٠-٩]/g, "")); setErr(null); }} />
              <Button type="submit" className="shrink-0"
                disabled={code.length < 6 || confirm.isPending}>{t("confirm_code")}</Button>
            </div>
          </Field>
          <button type="button" className="text-[13px] font-semibold text-link disabled:text-hint"
            disabled={wait > 0 || send.isPending} onClick={() => send.mutate()}>
            {wait > 0 ? t("resend_in", { s: wait }) : t("resend_code")}</button>
        </form>
      )}
      {err && <p role="alert" className="text-[13px] text-danger">{err}</p>}
    </div>
  );
}
