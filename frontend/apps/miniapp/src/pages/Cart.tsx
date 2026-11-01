import { useNavigate } from "react-router-dom";

import { Page } from "../components/Layout";
import { Button, cx, Empty, ErrorState, Skeleton, Stepper } from "../components/ui";
import { useCart, useCartMutations } from "../hooks/queries";
import { useMainButton } from "../hooks/telegram";
import { useSession } from "../session";
import { confirmDialog } from "../telegram";

export function CartPage() {
  const { t, money } = useSession();
  const navigate = useNavigate();
  const cart = useCart();
  const { setQty, clear } = useCartMutations();
  const data = cart.data;
  const canCheckout = Boolean(data && data.lines.length && !data.has_problems);
  const mainButton = useMainButton({
    text: data ? `${t("checkout")} · ${money(data.subtotal)}` : t("checkout"),
    visible: canCheckout,
    onClick: () => navigate("/checkout"),
  });

  if (cart.isPending) return <Page title={t("cart")}><Skeleton className="h-24" />
    <Skeleton className="mt-3 h-24" /></Page>;
  if (cart.isError) return <Page title={t("cart")}><ErrorState message={t("error_title")}
    retryLabel={t("retry")} onRetry={() => cart.refetch()} /></Page>;
  if (!data?.lines.length) {
    return (
      <Page title={t("cart")}>
        <Empty icon="🛒" title={t("cart_empty")} hint={t("cart_empty_hint")}
          action={<Button onClick={() => navigate("/")}>{t("browse_menu")}</Button>} />
      </Page>
    );
  }

  return (
    <Page title={t("cart")} actions={
      <button type="button" className="text-[14px] font-semibold text-danger"
        disabled={clear.isPending}
        onClick={async () => { if (await confirmDialog(t("confirm_clear"))) clear.mutate(); }}>
        {t("clear_cart")}
      </button>
    }>
      <ul className="space-y-3">
        {data.lines.map((line) => (
          <li key={line.id} className={cx("animate-rise flex gap-3 rounded-card bg-card p-3",
            !line.available && "ring-1 ring-danger/50")}>
            <div className="size-20 shrink-0 overflow-hidden rounded-xl bg-bg2">
              {line.image ? <img src={line.image} alt="" className="h-full w-full object-cover" />
                : <div className="grid h-full place-items-center text-2xl">🍽</div>}
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
              <p className="truncate font-semibold">{line.name}</p>
              {line.options.length > 0 && (
                <p className="truncate text-[13px] text-hint">
                  {line.options.map((o) => o.name).join("، ")}</p>
              )}
              {line.note && <p className="truncate text-[12px] text-hint">📝 {line.note}</p>}
              {!line.available && <p className="text-[13px] font-semibold text-danger">
                {t("unavailable")}</p>}
              <div className="mt-auto flex items-center justify-between pt-2">
                <span className="tabular font-bold">{money(line.line_total || line.unit_price *
                  line.quantity)}</span>
                {line.available ? (
                  <Stepper size="sm" value={line.quantity} min={0} busy={setQty.isPending}
                    onChange={(q) => setQty.mutate({ itemId: line.id, quantity: q })} />
                ) : (
                  <Button variant="danger" className="px-3 py-1.5 text-[13px]"
                    onClick={() => setQty.mutate({ itemId: line.id, quantity: 0 })}>
                    {t("remove")}</Button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <div className="mt-4 rounded-card bg-card p-4">
        <div className="flex justify-between text-[16px] font-bold">
          <span>{t("subtotal")}</span>
          <span className="tabular">{money(data.subtotal)}</span>
        </div>
        {data.has_problems && <p className="mt-2 text-[13px] text-danger">
          {t("cart_problem")}</p>}
      </div>

      {!mainButton && canCheckout && (
        <Button className="mt-4 w-full" onClick={() => navigate("/checkout")}>
          {t("checkout")} · {money(data.subtotal)}</Button>
      )}
    </Page>
  );
}
