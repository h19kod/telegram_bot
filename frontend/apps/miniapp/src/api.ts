/** Storefront API client. Every price shown comes from these responses — never computed
 * from user input. */
import {
  ApiError,
  type components,
  newIdempotencyKey,
  parseResponse,
  type RequestOptions,
} from "@sop/shared";

const BASE = import.meta.env.VITE_API_BASE ?? "";

// Response/request shapes come from the backend OpenAPI schema (`make schema`), so they cannot
// drift from what the server sends.
type S = components["schemas"];
export type BusinessInfo = S["StoreInfo"];
export type Customer = S["StoreMe"];
export type Category = S["StoreCategory"];
export type Option = S["StoreOption"];
export type OptionGroup = S["StoreOptionGroup"];
export type ProductImage = S["StoreImage"];
export type Product = S["StoreProductList"];
export type ProductDetail = S["StoreProduct"];
export type Page = S["ProductPage"];
export type CartLine = S["CartLine"];
export type Cart = S["CartResponse"];
export type Zone = S["StoreZone"];
export type CheckoutBody = S["CheckoutRequest"];
export type Quote = S["QuoteResponse"];
export type OrderStatus = S["OrderStatusEnum"];
export type Order = S["StoreOrder"];
export type Address = S["Address"];
export type AddressBody = S["AddressRequest"];
export type PhoneCodeSent = S["PhoneCodeSent"];
type SessionResponse = S["SessionResponse"];

export class StoreApi {
  private token: string | null = null;
  private refreshing: Promise<void> | null = null;
  lang: "ar" | "en" = "ar";

  constructor(
    readonly slug: string,
    private readonly initData: string,
  ) {}

  private url(path: string): string {
    return `${BASE}/api/v1/store/${encodeURIComponent(this.slug)}${path}`;
  }

  async openSession(): Promise<SessionResponse> {
    const res = await fetch(this.url("/session"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept-Language": this.lang },
      body: JSON.stringify({ init_data: this.initData }),
    });
    const data = await parseResponse<SessionResponse>(res);
    this.token = data.token;
    return data;
  }

  private async request<T>(path: string, opts: RequestOptions = {}, retry = true): Promise<T> {
    if (!this.token) await this.reauth();
    const res = await fetch(this.url(path), {
      method: opts.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
        "Accept-Language": this.lang,
        Authorization: `Customer ${this.token}`,
        ...opts.headers,
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
    if (res.status === 401 && retry) {
      await this.reauth();
      return this.request<T>(path, opts, false);
    }
    return parseResponse<T>(res);
  }

  private async reauth(): Promise<void> {
    this.refreshing ??= this.openSession().then(() => undefined).finally(() => {
      this.refreshing = null;
    });
    await this.refreshing;
  }

  info = () => this.request<BusinessInfo>("/");
  categories = () => this.request<Category[]>("/categories");
  products = (params: Record<string, string | undefined>, cursor?: string | null) => {
    if (cursor) {
      const u = new URL(cursor, location.origin);
      return this.request<Page>(`/products${u.search}`);
    }
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
    const qs = q.toString();
    return this.request<Page>(`/products${qs ? `?${qs}` : ""}`);
  };
  product = (id: string) => this.request<ProductDetail>(`/products/${id}`);
  zones = () => this.request<Zone[]>("/delivery-zones");

  cart = () => this.request<Cart>("/cart");
  clearCart = () => this.request<Cart>("/cart", { method: "DELETE" });
  addToCart = (product_id: string, option_ids: string[], quantity: number, note = "") =>
    this.request<Cart>("/cart/items", { method: "POST",
      body: { product_id, option_ids, quantity, note } });
  setQuantity = (itemId: string, quantity: number) =>
    this.request<Cart>(`/cart/items/${itemId}`, { method: "PATCH", body: { quantity } });

  quote = (body: CheckoutBody) =>
    this.request<Quote>("/checkout/quote", { method: "POST", body });
  checkout = (body: CheckoutBody, key: string = newIdempotencyKey()) =>
    this.request<Order>("/checkout", { method: "POST", body,
      headers: { "Idempotency-Key": key } });

  orders = () => this.request<Order[]>("/orders");
  order = (id: string) => this.request<Order>(`/orders/${id}`);
  reviewOrder = (id: string, rating: number, comment: string) =>
    this.request<Order>(`/orders/${id}/review`, { method: "POST", body: { rating, comment } });
  cancelOrder = (id: string) =>
    this.request<Order>(`/orders/${id}/cancel`, { method: "POST", body: {} });

  me = () => this.request<Customer>("/me");
  updateMe = (body: Partial<Pick<Customer, "full_name" | "phone" | "language">> & {
    branch_id?: string }) =>
    this.request<Customer>("/me", { method: "PATCH", body });
  sendPhoneCode = (phone: string) =>
    this.request<PhoneCodeSent>("/me/phone/code", { method: "POST", body: { phone } });
  confirmPhoneCode = (code: string) =>
    this.request<Customer>("/me/phone/confirm", { method: "POST", body: { code } });
  addresses = () => this.request<Address[]>("/me/addresses");
  addAddress = (body: AddressBody) =>
    this.request<Address>("/me/addresses", { method: "POST", body });
  deleteAddress = (id: string) =>
    this.request<void>(`/me/addresses/${id}`, { method: "DELETE" });
  support = (message: string) =>
    this.request<{ sent: boolean }>("/support", { method: "POST", body: { message } });
}

export { ApiError };
