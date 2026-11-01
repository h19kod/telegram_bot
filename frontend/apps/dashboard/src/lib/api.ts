/** Dashboard API client. Access token lives in memory only; the refresh token is an
 * HttpOnly cookie rotated by POST /auth/refresh (double-submit CSRF header). */
import { ApiError, newIdempotencyKey, parseResponse } from "@sop/shared";

export { ApiError, newIdempotencyKey };

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onLogout: (() => void) | null = null;
let lang: "ar" | "en" = "ar";

export function setLang(l: "ar" | "en") {
  lang = l;
}

export function onSessionExpired(cb: () => void) {
  onLogout = cb;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

function csrf(): string {
  return document.cookie.split("; ").find((c) => c.startsWith("sop_csrf="))?.slice(9) ?? "";
}

export async function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const res = await fetch("/api/v1/auth/refresh", {
        method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf() },
      });
      if (!res.ok) return false;
      accessToken = (await res.json()).access;
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => { refreshing = null; }, 0);
    }
  })();
  return refreshing;
}

export interface Req {
  method?: string;
  body?: unknown;
  form?: FormData;
  headers?: Record<string, string>;
  raw?: boolean;
}

export async function request<T>(path: string, opts: Req = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { "Accept-Language": lang, ...opts.headers };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api/v1${path}`, {
    method: opts.method ?? "GET",
    headers,
    credentials: "include",
    body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
  });
  if (res.status === 401 && retry && !path.startsWith("/auth/login")) {
    if (await refreshSession()) return request<T>(path, opts, false);
    onLogout?.();
  }
  if (opts.raw) {
    if (!res.ok) await parseResponse(res);
    return res as unknown as T;
  }
  return parseResponse<T>(res);
}

export const get = <T>(p: string) => request<T>(p);
export const post = <T>(p: string, body?: unknown, headers?: Record<string, string>) =>
  request<T>(p, { method: "POST", body: body ?? {}, headers });
export const patch = <T>(p: string, body: unknown) => request<T>(p, { method: "PATCH", body });
export const put = <T>(p: string, body: unknown) => request<T>(p, { method: "PUT", body });
export const del = <T = void>(p: string) => request<T>(p, { method: "DELETE" });
export const upload = <T>(p: string, form: FormData) =>
  request<T>(p, { method: "POST", form });

export function qs(params: Record<string, string | number | undefined | null | string[]>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export async function download(path: string, filename: string) {
  const res = await request<Response>(path, { raw: true });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---- Types ---------------------------------------------------------------------------

export interface User {
  id: string; email: string | null; phone: string | null; full_name: string;
  language: "ar" | "en"; is_platform_admin: boolean; totp_enabled: boolean;
  has_telegram: boolean;
}
export interface Membership {
  id: string; business_id: string; business_slug: string; business_name_ar: string;
  business_name_en: string; business_status: string; role: string; is_owner: boolean;
  permissions: string[];
}
export interface Paginated<T> { count: number; next: string | null; previous: string | null;
  results: T[] }

export type OrderStatus = "pending" | "confirmed" | "preparing" | "ready" |
  "out_for_delivery" | "delivered" | "cancelled" | "rejected";

export interface OrderRow {
  id: string; number: number; status: OrderStatus; version: number;
  fulfilment: "delivery" | "pickup"; channel: string; customer: string; customer_name: string;
  customer_phone: string; zone_name_snapshot: string; currency: string; subtotal: number;
  delivery_fee: number; discount_total: number; total: number; payment_method: string;
  payment_status: string; placed_at: string; assigned_driver: string | null;
  items_count: number | null;
}
export interface OrderDetail extends OrderRow {
  notes: string; address: Record<string, string> | null; cancel_reason: string;
  confirmed_at: string | null; delivered_at: string | null;
  items: { id: string; product_name_ar: string; product_name_en: string; unit_price: number;
    quantity: number; line_total: number; note: string;
    options: { option_name_ar: string; option_name_en: string; price_delta: number }[] }[];
  events: { from_status: string; to_status: string; source: string; reason: string;
    actor: string; created_at: string }[];
  allowed_actions: OrderStatus[];
  applied?: boolean;
}
export interface Category { id: string; name_ar: string; name_en: string; image: string | null;
  parent: string | null; sort_order: number; is_active: boolean; products_count: number }
export interface Option { id: string; name_ar: string; name_en: string; price_delta: number;
  is_available: boolean; is_default: boolean; sort_order: number }
export interface OptionGroup { id: string; name_ar: string; name_en: string;
  selection_type: "single" | "multiple"; is_required: boolean; min_select: number;
  max_select: number; sort_order: number; options: Option[] }
export interface Product {
  id: string; category: string; name_ar: string; name_en: string; description_ar: string;
  description_en: string; sku: string; price: number; compare_at_price: number | null;
  availability: "available" | "out_of_stock" | "hidden"; track_stock: boolean;
  stock_quantity: number | null; prep_time_min: number | null; tags: string[];
  sort_order: number; images: { id: string; image: string; thumbnail: string }[];
  option_groups: OptionGroup[];
}
export interface Customer { id: string; display_name: string; full_name: string;
  telegram_username: string; phone: string; language: string; is_blocked: boolean;
  blocked_reason: string; orders_count: number; total_spent: number;
  last_order_at: string | null; created_at: string }
export interface Zone { id: string; branch: string; name_ar: string; name_en: string;
  governorate: string | null; areas: string[]; fee: number; min_order: number | null;
  free_delivery_threshold: number | null; eta_min: number | null; eta_max: number | null;
  is_active: boolean; sort_order: number }
export interface Role { id: string; name: string; is_owner: boolean; is_system: boolean;
  permissions: string[]; members_count: number }
export interface Member { id: string; email: string | null; phone: string | null;
  full_name: string; role: string; role_name: string; is_active: boolean;
  has_telegram: boolean }
export interface Invitation { id: string; email: string; phone: string; role: string;
  expires_at: string; accept_url: string | null }
export interface Business { id: string; slug: string; name_ar: string; name_en: string;
  description_ar: string; description_en: string; business_type: string;
  logo: string | null; cover: string | null; phone: string; whatsapp: string;
  currency: string; default_language: string; timezone: string; status: string }
export interface Settings { min_order_amount: number; customer_cancel_window_min: number;
  auto_reject_after_min: number | null; allow_order_notes: boolean; payment_methods: string[];
  ai_enabled: boolean; ai_persona_note: string; welcome_message_ar: string;
  welcome_message_en: string; notification_chat_ids: number[] }
export interface Branch { id: string; name_ar: string; address: string; is_default: boolean;
  is_temporarily_closed: boolean; accepts_delivery: boolean; accepts_pickup: boolean;
  hours: { weekday: number; opens_at: string; closes_at: string }[]; is_open_now: boolean }
export interface Overview { currency: string; total_orders: number; completed_orders: number;
  cancelled_orders: number; total_sales: number; average_order_value: number;
  today_orders: number; today_sales: number; pending_orders: number; open_orders: number;
  new_customers: number; status_breakdown: Record<string, number> }
export interface SalesPoint { date: string; orders: number; sales: number }
export interface TopProduct { product_id: string | null; name_ar: string; name_en: string;
  quantity: number; revenue: number }
