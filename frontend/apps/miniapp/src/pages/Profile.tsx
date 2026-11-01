import { looksLikeIraqiMobile } from "@sop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api";
import { Page } from "../components/Layout";
import { Button, Card, Field, Input, Segmented, TextArea } from "../components/ui";
import type { TKey } from "../i18n";
import { useSession } from "../session";
import { haptic } from "../telegram";

export function ProfilePage() {
  const { api, customer, setCustomer, t, lang, setLang } = useSession();
  const qc = useQueryClient();
  const [name, setName] = useState(customer.full_name || customer.first_name);
  const [phone, setPhone] = useState(customer.phone ? `0${customer.phone.slice(4)}` : "");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const addresses = useQuery({ queryKey: ["addresses"], queryFn: api.addresses });

  const save = useMutation({
    mutationFn: () => api.updateMe({ full_name: name.trim(), phone }),
    onSuccess: (c) => { setCustomer(c); setMsg(t("saved")); setErr(null); haptic.success(); },
    onError: (e) => { setErr(e instanceof ApiError ? e.message : t("error_title")); },
  });
  const changeLang = useMutation({
    mutationFn: (l: "ar" | "en") => api.updateMe({ language: l }),
    onSuccess: (c) => { setCustomer(c); setLang(c.language); qc.invalidateQueries(); },
  });
  const removeAddress = useMutation({
    mutationFn: (id: string) => api.deleteAddress(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["addresses"] }),
  });

  return (
    <Page title={t("profile")}>
      <div className="space-y-4">
        <Card className="space-y-3 p-4">
          <Field label={t("name")}>
            <Input value={name} maxLength={150} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t("phone")} hint={t("phone_hint")}
            error={phone && !looksLikeIraqiMobile(phone) ? t("invalid_phone") : undefined}>
            <Input value={phone} inputMode="tel" dir="ltr" className="text-start"
              onChange={(e) => setPhone(e.target.value)} />
          </Field>
          {err && <p role="alert" className="text-[13px] text-danger">{err}</p>}
          <Button className="w-full" disabled={save.isPending || (Boolean(phone) &&
            !looksLikeIraqiMobile(phone))} onClick={() => { setMsg(null); save.mutate(); }}>
            {msg ?? t("save")}</Button>
        </Card>

        <Card className="p-4">
          <p className="mb-2 text-[13px] font-medium text-hint">{t("language")}</p>
          <Segmented value={lang} onChange={(l) => changeLang.mutate(l)}
            options={[{ value: "ar", label: "العربية" }, { value: "en", label: "English" }]} />
        </Card>

        <Card className="p-4">
          <p className="mb-2 font-semibold">{t("addresses")}</p>
          {!addresses.data?.length ? <p className="text-[14px] text-hint">
            {t("no_addresses")}</p> : (
            <ul className="divide-y divide-line">
              {addresses.data.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0 text-[14px]">
                    <p className="font-medium">{t(`label_${a.label}` as TKey)}</p>
                    <p className="truncate text-hint">{[a.area, a.street, a.landmark]
                      .filter(Boolean).join(" · ")}</p>
                  </div>
                  <button type="button" className="text-[13px] font-semibold text-danger"
                    onClick={() => removeAddress.mutate(a.id)}>{t("remove")}</button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Link to="/support" className="block"><Button variant="soft" className="w-full">
          💬 {t("support")}</Button></Link>
      </div>
    </Page>
  );
}

export function SupportPage() {
  const { api, t, business } = useSession();
  const [text, setText] = useState("");
  const send = useMutation({ mutationFn: () => api.support(text.trim()),
    onSuccess: () => { haptic.success(); setText(""); } });
  return (
    <Page title={t("support")}>
      <Card className="space-y-3 p-4">
        <p className="text-[14px] text-hint">{t("support_hint")}</p>
        <Field label={t("message")}>
          <TextArea value={text} maxLength={1000} onChange={(e) => {
            setText(e.target.value); send.reset(); }} />
        </Field>
        {send.isError && <p role="alert" className="text-[13px] text-danger">
          {send.error instanceof ApiError ? send.error.message : t("error_title")}</p>}
        <Button className="w-full" disabled={text.trim().length < 2 || send.isPending}
          onClick={() => send.mutate()}>{send.isSuccess ? t("sent") : t("send")}</Button>
      </Card>
      {business.phone && (
        <a href={`tel:${business.phone}`} className="mt-4 block text-center font-semibold
          text-link">📞 {t("call_shop")} · <span dir="ltr">{business.phone}</span></a>
      )}
    </Page>
  );
}
