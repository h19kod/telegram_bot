/** Dashboard API client. Access token lives in memory only; the refresh token is an
 * HttpOnly cookie rotated by POST /auth/refresh (double-submit CSRF header). */
import { ApiError, type components, newIdempotencyKey, parseResponse } from "@sop/shared";

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
// From the backend OpenAPI schema (`make schema`): they cannot drift from what the API sends.

type S = components["schemas"];
export type User = S["User"];
export type Membership = S["Membership"];
export interface Paginated<T> { count: number; next: string | null; previous: string | null;
  results: T[] }
export type OrderStatus = S["OrderStatusEnum"];
export type OrderRow = S["OrderList"];
export type OrderDetail = S["OrderDetail"] & { applied?: boolean };
export type Category = S["Category"];
export type Option = S["Option"];
export type OptionGroup = S["OptionGroup"];
export type Product = S["Product"];
export type Customer = S["Customer"];
export type Zone = S["DeliveryZone"];
export type Role = S["Role"];
export type Member = S["Member"];
export type Invitation = S["Invitation"];
export type Business = S["Business"];
export type Settings = S["Settings"];
export type Branch = S["Branch"];
export type Overview = S["Overview"];
export type SalesPoint = S["SalesPoint"];
export type TopProduct = S["TopProduct"];
export type Coupon = S["Coupon"];
export type Review = S["Review"];
export type LoyaltyEntry = S["LoyaltyEntry"];
export type ReviewSummary = S["ReviewSummary"];
export type TelegramOverview = S["TelegramOverview"];
export type SubscriptionOverview = S["SubscriptionOverview"];
export type SupportTicket = S["SupportTicket"];
export type PlatformBusiness = S["PlatformBusiness"];
export type Plan = S["Plan"];
export type Feature = S["Feature"];
