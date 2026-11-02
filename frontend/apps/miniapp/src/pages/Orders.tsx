import { formatDateTime, formatTime } from "@sop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, type Order, type OrderStatus } from "../api";
import { Page } from "../components/Layout";
import { Button, Card, cx, Empty, ErrorState, Skeleton, TextArea } from "../components/ui";
import { useSession } from "../session";
import { confirmDialog, haptic } from "../telegram";
import type { TKey } from "../i18n";

const TONE: Record<OrderStatus, string> = {
  pending: "bg-warn/15 text-warn",
  confirmed: "bg-link/15 text-link",
  preparing: "bg-link/15 text-link",
  ready: "bg-success/15 text-success",
  out_for_delivery: "bg-success/15 text-success",
  delivered: "bg-success/15 text-success",
  cancelled: "bg-danger/10 text-danger",
  rejected: "bg-danger/10 text-danger",
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  const { t } = useSession();
  return <span className={cx("rounded-full px-2.5 py-1 text-[12px] font-semibold",
    TONE[status])}>{t(`status_${status}` as TKey)}</span>;
}

export function OrdersPage() {
  const { api, t, money, lang } = useSession();
  const q = useQuery({ queryKey: ["orders"], queryFn: api.orders, refetchInterval: 30_000 });
  return (
    <Page title={t("my_orders")}>
      {q.isPending ? <div className="space-y-3"><Skeleton className="h-20" />
        <Skeleton className="h-20" /></div>
        : q.isError ? <ErrorState message={t("error_title")} retryLabel={t("retry")}
          onRetry={() => q.refetch()} />
        : !q.data.length ? <Empty icon="📦" title={t("no_orders")} />
        : (
          <ul className="space-y-3">
            {q.data.map((o) => (
              <li key={o.id}>
                <Link to={`/orders/${o.id}`} className="animate-rise block rounded-card bg-card
                  p-4 active:opacity-80">
                  <div className="flex items-center justify-between">
                    <span className="font-bold">{t("order_n", { n: o.number })}</span>
                    <StatusBadge status={o.status} />
                  </div>
                  <div className="mt-2 flex justify-between text-[13px] text-hint">
                    <span>{formatDateTime(o.placed_at, lang)} · {t("items_n", {
                      n: o.items.reduce((s, i) => s + i.quantity, 0) })}</span>
                    <span className="tabular font-semibold text-fg">{money(o.total)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
    </Page>
  );
}

const FLOW: Record<"delivery" | "pickup", OrderStatus[]> = {
  delivery: ["pending", "confirmed", "preparing", "ready", "out_for_delivery", "delivered"],
  pickup: ["pending", "confirmed", "preparing", "ready", "delivered"],
};

function Timeline({ order }: { order: Order }) {
  const { t, lang } = useSession();
  const at = new Map(order.timeline.map((e) => [e.status, e.at]));
  const terminalBad = order.status === "cancelled" || order.status === "rejected";
  const steps = terminalBad ? [...order.timeline.map((e) => e.status)] : FLOW[order.fulfilment];
  const currentIdx = steps.indexOf(order.status);
  return (
    <ol className="relative space-y-4 ps-6">
      <span className="absolute start-[7px] top-1 bottom-1 w-0.5 bg-line" aria-hidden />
      {steps.map((s, i) => {
        const done = i <= currentIdx;
        return (
          <li key={s} className="relative">
            <span className={cx("absolute -start-6 top-0.5 size-4 rounded-full border-2",
              done ? (terminalBad && i === currentIdx ? "border-danger bg-danger"
                : "border-accent bg-accent") : "border-line bg-card",
              i === currentIdx && !terminalBad && order.status !== "delivered" &&
                "ring-4 ring-accent/20")} />
            <div className="flex justify-between">
              <span className={cx("text-[15px]", done ? "font-semibold" : "text-hint")}>
                {t(`status_${s}` as TKey)}</span>
              {at.get(s) && <span className="tabular text-[13px] text-hint">
                {formatTime(at.get(s)!, lang)}</span>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function OrderDetailPage() {
  const { id = "" } = useParams();
  const { api, t, money, business } = useSession();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["order", id], queryFn: () => api.order(id),
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s && ["delivered", "cancelled", "rejected"].includes(s) ? false : 15_000;
    },
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelOrder(id),
    onSuccess: (o) => {
      haptic.success();
      qc.setQueryData(["order", id], o);
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
    onError: () => haptic.error(),
  });

  if (q.isPending) return <Page title="…"><Skeleton className="h-40" /></Page>;
  if (q.isError) return <Page title={t("my_orders")}><ErrorState message={t("error_title")}
    retryLabel={t("retry")} onRetry={() => q.refetch()} /></Page>;
  const o = q.data;
  return (
    <Page title={t("order_n", { n: o.number })} actions={<StatusBadge status={o.status} />}>
      <div className="space-y-4">
        <Card className="p-4"><Timeline order={o} /></Card>
        <Card className="divide-y divide-line px-4">
          {o.items.map((i, idx) => (
            <div key={idx} className="flex justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="font-medium">{i.name} <span className="text-hint">×{i.quantity}</span></p>
                {i.options.length > 0 && <p className="text-[13px] text-hint">
                  {i.options.join("، ")}</p>}
              </div>
              <span className="tabular shrink-0">{money(i.line_total)}</span>
            </div>
          ))}
          <div className="space-y-1 py-3 text-[14px]">
            {o.delivery_fee > 0 && <div className="flex justify-between text-hint">
              <span>{t("delivery_fee")}</span><span className="tabular">
                {money(o.delivery_fee)}</span></div>}
            <div className="flex justify-between text-[16px] font-bold">
              <span>{t("total")}</span><span className="tabular">{money(o.total)}</span></div>
          </div>
        </Card>
        {o.fulfilment === "delivery" && (
          <Card className="p-4 text-[14px]">
            <p className="font-semibold">📍 {o.zone_name_snapshot} — {o.address_area}</p>
            {o.address_street && <p className="text-hint">{o.address_street}</p>}
            {o.address_landmark && <p className="text-hint">🏁 {o.address_landmark}</p>}
          </Card>
        )}
        {o.cancel_reason && ["cancelled", "rejected"].includes(o.status) && (
          <Card className="p-4 text-[14px]"><span className="text-hint">{t("reason")}: </span>
            {o.cancel_reason}</Card>
        )}
        {(o.can_review || o.review) && <ReviewCard order={o} />}
        {o.can_cancel && (
          <Button variant="danger" className="w-full" disabled={cancel.isPending}
            onClick={async () => { if (await confirmDialog(t("confirm_cancel"))) cancel.mutate(); }}>
            {t("cancel_order")}</Button>
        )}
        {business.phone && (
          <a href={`tel:${business.phone}`} className="block text-center text-[14px]
            font-semibold text-link">📞 {t("call_shop")}</a>
        )}
      </div>
    </Page>
  );
}

function ReviewCard({ order }: { order: Order }) {
  const { api, t } = useSession();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(!order.review);
  const [rating, setRating] = useState(order.review?.rating ?? 0);
  const [comment, setComment] = useState(order.review?.comment ?? "");
  const send = useMutation({
    mutationFn: () => api.reviewOrder(order.id, rating, comment.trim()),
    onSuccess: (o) => { haptic.success(); qc.setQueryData(["order", order.id], o); setEditing(false); },
    onError: () => haptic.error(),
  });
  if (!editing && order.review) {
    return (
      <Card className="space-y-2 p-4 text-[14px]">
        <div className="flex items-center justify-between">
          <p className="font-semibold">{t("your_rating")}</p>
          {order.can_review && <button type="button" className="text-[13px] font-semibold
            text-link" onClick={() => setEditing(true)}>{t("edit_rating")}</button>}
        </div>
        <Stars value={order.review.rating} />
        {order.review.comment && <p className="text-hint">{order.review.comment}</p>}
        {order.review.reply && <p className="rounded-xl bg-accent/5 p-3">
          <span className="font-semibold">💬 {t("shop_reply")}: </span>{order.review.reply}</p>}
        {send.isSuccess && <p role="status" className="text-success">{t("thanks_rating")}</p>}
      </Card>
    );
  }
  return (
    <Card className="space-y-3 p-4">
      <div>
        <p className="font-semibold">{t("rate_order")}</p>
        <p className="text-[13px] text-hint">{t("rate_hint")}</p>
      </div>
      <Stars value={rating} onChange={(n) => { setRating(n); haptic.select(); }} />
      <TextArea value={comment} maxLength={500} placeholder={t("review_comment")}
        aria-label={t("review_comment")} className="min-h-20"
        onChange={(e) => setComment(e.target.value)} />
      {send.isError && <p role="alert" className="text-[13px] text-danger">
        {send.error instanceof ApiError ? send.error.message : t("error_title")}</p>}
      <Button className="w-full" disabled={!rating || send.isPending}
        onClick={() => send.mutate()}>{t("send_rating")}</Button>
    </Card>
  );
}

export function Stars({ value, onChange, size = "text-[28px]" }: { value: number;
  onChange?: (n: number) => void; size?: string }) {
  const { t } = useSession();
  if (!onChange) {
    return <p className={cx("tracking-wider", size === "text-[28px]" ? "text-[20px]" : size)}
      role="img" aria-label={t("stars_n", { n: value })}>
      <span className="text-warn">{"★".repeat(value)}</span>
      <span className="text-line">{"★".repeat(5 - value)}</span></p>;
  }
  return (
    <div className="flex justify-center gap-1" role="radiogroup" aria-label={t("rate_order")}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n}
          aria-label={t("stars_n", { n })} onClick={() => onChange(n)}
          className={cx(size, "leading-none transition active:scale-90",
            n <= value ? "text-warn" : "text-line")}>★</button>
      ))}
    </div>
  );
}

export function OrderPlacedPage() {
  const { id = "" } = useParams();
  const { api, t, money } = useSession();
  const q = useQuery({ queryKey: ["order", id], queryFn: () => api.order(id) });
  return (
    <Page bottomPad={false}>
      <div className="flex min-h-dvh flex-col items-center justify-center text-center">
        <div className="animate-rise mb-5 grid size-24 place-items-center rounded-full
          bg-success/15 text-5xl">✓</div>
        <h1 className="text-[24px] font-bold">{t("order_placed")}</h1>
        {q.data && <p className="mt-2 text-[17px]">{t("order_n", { n: q.data.number })} ·
          <span className="tabular font-semibold"> {money(q.data.total)}</span></p>}
        <p className="mt-2 max-w-xs text-[14px] text-hint">{t("order_placed_hint")}</p>
        <div className="mt-8 flex w-full max-w-xs flex-col gap-2">
          <Link to={`/orders/${id}`} replace><Button className="w-full">{t("track_order")}
          </Button></Link>
          <Link to="/" replace><Button variant="ghost" className="w-full">
            {t("back_to_menu")}</Button></Link>
        </div>
      </div>
    </Page>
  );
}
