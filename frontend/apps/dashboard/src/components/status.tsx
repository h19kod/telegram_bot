import type { OrderStatus } from "../lib/api";
import type { TKey } from "../lib/i18n";
import { useSession } from "../lib/session";
import { Badge } from "./ui";

const TONE: Record<OrderStatus, "warn" | "info" | "success" | "danger" | "neutral"> = {
  pending: "warn", confirmed: "info", preparing: "info", ready: "success",
  out_for_delivery: "success", delivered: "neutral", cancelled: "danger", rejected: "danger",
};
const ICON: Record<OrderStatus, string> = { pending: "⏳", confirmed: "✓", preparing: "👨‍🍳",
  ready: "📦", out_for_delivery: "🛵", delivered: "🎉", cancelled: "✕", rejected: "⛔" };

export function StatusBadge({ status }: { status: OrderStatus }) {
  const { t } = useSession();
  return <Badge tone={TONE[status]}><span aria-hidden>{ICON[status]}</span>{t(`status_${status}` as TKey)}</Badge>;
}

export const STATUSES: OrderStatus[] = ["pending", "confirmed", "preparing", "ready",
  "out_for_delivery", "delivered", "cancelled", "rejected"];
