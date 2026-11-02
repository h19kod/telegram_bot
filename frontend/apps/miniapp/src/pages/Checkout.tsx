import { localIraqiPhone, looksLikeIraqiMobile, newIdempotencyKey } from "@sop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError, type CheckoutBody } from "../api";
import { ActionBar, Page } from "../components/Layout";
import { PhoneVerify, useIsVerified } from "../components/PhoneVerify";
import { Button, Card, cx, Field, Input, Segmented, Skeleton, TextArea } from "../components/ui";
import { useCart } from "../hooks/queries";
import { useMainButton } from "../hooks/telegram";
import { useSession } from "../session";
import { getTable, haptic } from "../telegram";

type Errors = Partial<Record<keyof CheckoutBody | "form", string>>;

export function CheckoutPage() {
  const { api, business, customer, t, money } = useSession();
  const table = business.accepts_dine_in ? getTable() : "";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const cart = useCart();
  const zones = useQuery({ queryKey: ["zones"], queryFn: api.zones,
    enabled: business.accepts_delivery });
  const addresses = useQuery({ queryKey: ["addresses"], queryFn: api.addresses });

  const [form, setForm] = useState<CheckoutBody>({
    fulfilment: table ? "dine_in" : business.accepts_delivery ? "delivery" : "pickup",
    table_label: table,
    customer_name: customer.full_name || customer.first_name || "",
    customer_phone: customer.phone ? localIraqiPhone(customer.phone) : "",
    zone_id: null, address_area: "", address_street: "", address_landmark: "",
    address_building: "", notes: "",
  });
  const [errors, setErrors] = useState<Errors>({});
  const fulfilmentOptions: { value: CheckoutBody["fulfilment"]; label: string }[] = [
    ...(table ? [{ value: "dine_in" as const, label: `🍽 ${t("table_n", { n: table })}` }] : []),
    ...(business.accepts_delivery ? [{ value: "delivery" as const, label: `🛵 ${t("delivery")}` }] : []),
    ...(business.accepts_pickup ? [{ value: "pickup" as const, label: `🏪 ${t("pickup")}` }] : []),
  ];
  const phoneVerified = useIsVerified(form.customer_phone);
  const [couponInput, setCouponInput] = useState("");
  const [coupon, setCoupon] = useState("");
  // One key per checkout screen: retries and double taps cannot create two orders.
  const idemKey = useRef(newIdempotencyKey());
  const set = <K extends keyof CheckoutBody>(k: K, v: CheckoutBody[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setErrors((e) => ({ ...e, [k]: undefined, form: undefined }));
  };

  useEffect(() => {
    const def = addresses.data?.find((a) => a.is_default) ?? addresses.data?.[0];
    if (def && !form.address_area) {
      setForm((f) => ({ ...f, zone_id: def.zone ?? f.zone_id, address_area: def.area,
        address_street: def.street, address_landmark: def.landmark,
        address_building: def.building }));
    }
  }, [addresses.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const atCounter = form.fulfilment !== "delivery";
  const quoteBody = useMemo(() => form.fulfilment !== "delivery"
    ? { ...form, zone_id: null } : form, [form]);
  const canQuote = atCounter || Boolean(form.zone_id);
  const quote = useQuery({
    queryKey: ["quote", form.fulfilment, form.zone_id, cart.data?.subtotal, coupon],
    queryFn: () => api.quote({ fulfilment: quoteBody.fulfilment, zone_id: quoteBody.zone_id,
      table_label: quoteBody.fulfilment === "dine_in" ? quoteBody.table_label : "",
      customer_name: "", customer_phone: "", coupon_code: coupon }),
    enabled: canQuote && Boolean(cart.data?.lines.length), retry: false,
  });

  const place = useMutation({
    mutationFn: () => api.checkout({ ...quoteBody, coupon_code: coupon,
      ...(form.fulfilment === "dine_in" ? { customer_phone: "" } : { table_label: "" }) },
    idemKey.current),
    onSuccess: (order) => {
      haptic.success();
      qc.invalidateQueries({ queryKey: ["cart"] });
      qc.invalidateQueries({ queryKey: ["orders"] });
      navigate(`/placed/${order.id}`, { replace: true });
    },
    onError: (e) => {
      haptic.error();
      if (e instanceof ApiError) {
        setErrors({ ...e.fieldErrors(), form: e.message });
        if (e.status >= 500) idemKey.current = newIdempotencyKey();
      } else setErrors({ form: t("error_title") });
    },
  });

  function validate(): boolean {
    const e: Errors = {};
    if (form.customer_name.trim().length < 2) e.customer_name = t("required_field");
    if (form.fulfilment === "dine_in") { /* at the table: no phone needed */ }
    else if (!looksLikeIraqiMobile(form.customer_phone)) e.customer_phone = t("invalid_phone");
    else if (business.phone_verification_required && !phoneVerified) {
      e.customer_phone = t("verify_phone_first");
    }
    if (form.fulfilment === "delivery") {
      if (!form.zone_id) e.zone_id = t("required_field");
      if (!form.address_area?.trim()) e.address_area = t("required_field");
      if (!form.address_landmark?.trim() && !form.address_street?.trim()) {
        e.address_landmark = t("required_field");
      }
    }
    setErrors(e);
    if (Object.keys(e).length) haptic.error();
    return !Object.keys(e).length;
  }

  const total = quote.data?.total ?? cart.data?.subtotal ?? 0;
  const label = place.isPending ? t("placing") : t("place_order", { total: money(total) });
  const submit = () => { if (!place.isPending && validate()) place.mutate(); };
  const mainButton = useMainButton({ text: label, visible: true, progress: place.isPending,
    active: !place.isPending, onClick: submit });

  if (cart.isSuccess && !cart.data.lines.length && !place.isSuccess) {
    return <Navigate to="/cart" replace />;
  }

  return (
    <Page title={t("checkout")}>
      <div className="space-y-4">
        <Card className="space-y-3 p-4">
          <h2 className="font-semibold">{t("your_details")}</h2>
          <Field label={t("name")} error={errors.customer_name}>
            <Input value={form.customer_name} autoComplete="name" maxLength={150}
              invalid={Boolean(errors.customer_name)}
              onChange={(e) => set("customer_name", e.target.value)} />
          </Field>
          {form.fulfilment !== "dine_in" && <>
            <Field label={t("phone")} error={errors.customer_phone} hint={t("phone_hint")}>
              <Input value={form.customer_phone} inputMode="tel" autoComplete="tel" dir="ltr"
                invalid={Boolean(errors.customer_phone)} className="text-start"
                onChange={(e) => set("customer_phone", e.target.value)} />
            </Field>
            <PhoneVerify phone={form.customer_phone} />
          </>}
        </Card>

        {fulfilmentOptions.length > 1 && (
          <Segmented value={form.fulfilment} onChange={(v) => set("fulfilment", v)}
            options={fulfilmentOptions} />
        )}
        {form.fulfilment === "dine_in" && (
          <Card className="p-4">
            <p className="font-semibold">🍽 {t("dine_in_table", { n: table })}</p>
            <p className="text-[13px] text-hint">{t("dine_in_hint")}</p>
          </Card>
        )}

        {form.fulfilment === "delivery" && (
          <Card className="space-y-3 p-4">
            <h2 className="font-semibold">{t("zone")}</h2>
            {zones.isPending ? <Skeleton className="h-12" /> : (
              <div className="grid gap-2" role="radiogroup" aria-label={t("choose_zone")}>
                {(zones.data ?? []).map((z) => (
                  <button key={z.id} type="button" role="radio" aria-checked={form.zone_id === z.id}
                    onClick={() => set("zone_id", z.id)}
                    className={cx("flex items-center justify-between rounded-xl border px-3.5 py-3",
                      "text-start transition", form.zone_id === z.id
                        ? "border-accent bg-accent/5" : "border-line")}>
                    <span>
                      <span className="block font-medium">{z.name}</span>
                      {z.eta_min && z.eta_max ? <span className="text-[12px] text-hint">
                        {t("eta", { a: z.eta_min, b: z.eta_max })}</span> : null}
                    </span>
                    <span className="tabular text-[14px] font-semibold">
                      {z.fee ? money(z.fee) : t("free")}</span>
                  </button>
                ))}
              </div>
            )}
            {errors.zone_id && <p role="alert" className="text-[13px] text-danger">
              {errors.zone_id}</p>}
            <Field label={t("area")} error={errors.address_area}>
              <Input value={form.address_area} maxLength={120}
                invalid={Boolean(errors.address_area)}
                onChange={(e) => set("address_area", e.target.value)} />
            </Field>
            <Field label={t("street")}>
              <Input value={form.address_street} maxLength={200}
                onChange={(e) => set("address_street", e.target.value)} />
            </Field>
            <Field label={t("landmark")} error={errors.address_landmark}
              hint={t("landmark_hint")}>
              <Input value={form.address_landmark} maxLength={200}
                invalid={Boolean(errors.address_landmark)}
                onChange={(e) => set("address_landmark", e.target.value)} />
            </Field>
            <Field label={t("building")}>
              <Input value={form.address_building} maxLength={120}
                onChange={(e) => set("address_building", e.target.value)} />
            </Field>
          </Card>
        )}

        {business.allow_order_notes && (
          <Card className="p-4">
            <Field label={t("notes")}>
              <TextArea value={form.notes} maxLength={500}
                onChange={(e) => set("notes", e.target.value)} />
            </Field>
          </Card>
        )}

        <Card className="p-4">
          <Field label={t("coupon")}>
            <div className="flex gap-2">
              <Input value={coupon || couponInput} disabled={Boolean(coupon)} dir="ltr"
                className="uppercase" maxLength={32}
                onChange={(e) => setCouponInput(e.target.value)} />
              {coupon ? (
                <Button type="button" variant="ghost" className="shrink-0"
                  onClick={() => { setCoupon(""); setCouponInput(""); }}>{t("remove_coupon")}</Button>
              ) : (
                <Button type="button" variant="soft" className="shrink-0"
                  disabled={couponInput.trim().length < 3}
                  onClick={() => { setCoupon(couponInput.trim()); haptic.tap(); }}>{t("apply")}</Button>
              )}
            </div>
          </Field>
        </Card>

        <Card className="space-y-2 p-4 text-[15px]">
          <Row label={t("subtotal")} value={money(quote.data?.subtotal ?? cart.data?.subtotal
            ?? 0)} />
          {form.fulfilment === "delivery" && (
            <Row label={t("delivery_fee")} value={quote.data ? (quote.data.delivery_fee
              ? money(quote.data.delivery_fee) : t("free")) : "—"} />
          )}
          {quote.data?.discount_total ? <Row label={t("discount")}
            value={`-${money(quote.data.discount_total)}`} /> : null}
          <div className="border-t border-line pt-2">
            <Row bold label={t("total")} value={money(total)} />
          </div>
          <p className="pt-1 text-[13px] text-hint">💵 {t(form.fulfilment === "delivery"
            ? "cash_on_delivery" : "pay_at_pickup")}</p>
          {quote.isError && quote.error instanceof ApiError && (
            <p role="alert" className="text-[13px] text-danger">{quote.error.message}</p>
          )}
        </Card>

        {errors.form && <p role="alert" className="rounded-xl bg-danger/10 p-3 text-[14px]
          text-danger">{errors.form}</p>}
      </div>
      {!mainButton && (
        <ActionBar>
          <Button className="w-full" disabled={place.isPending} onClick={submit}>{label}</Button>
        </ActionBar>
      )}
    </Page>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={cx("flex justify-between", bold && "text-[17px] font-bold")}>
      <span className={bold ? "" : "text-hint"}>{label}</span>
      <span className="tabular">{value}</span>
    </div>
  );
}
