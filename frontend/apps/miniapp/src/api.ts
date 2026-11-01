/** Storefront API client. Every price shown comes from these responses — never computed
 * from user input. */
import { ApiError, newIdempotencyKey, parseResponse, type RequestOptions } from "@sop/shared";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export interface BusinessInfo {
  id: string;
  slug: string;
  name: string;
  description: string;
  business_type: string;
  logo: string | null;
  cover: string | null;
  phone: string;
  currency: string;
  is_open: boolean;
  is_active: boolean;
  accepts_delivery: boolean;
  accepts_pickup: boolean;
  min_order_amount: number;
  payment_methods: string[];
  allow_order_notes: boolean;
  customer_cancel_window_min: number;
  welcome_message: string;
  address: string;
  hours: { weekday: number; opens_at: string; closes_at: string }[];
}

export interface Customer {
  id: string;
  first_name: string;
  full_name: string;
  phone: string;
  language: "ar" | "en";
  orders_count: number;
}

export interface Category {
  id: string;
  name: string;
  image: string | null;
  parent: string | null;
}

export interface Option {
  id: string;
  name: string;
  price_delta: number;
  is_available: boolean;
  is_default: boolean;
}

export interface OptionGroup {
  id: string;
  name: string;
  selection_type: "single" | "multiple";
  is_required: boolean;
  min_select: number;
  max_select: number;
  options: Option[];
}

export interface ProductImage {
  url: string | null;
  thumbnail: string | null;
  width: number;
  height: number;
}

export interface Product {
  id: string;
  category: string;
  category_name: string;
  name: string;
  description: string;
  price: number;
  compare_at_price: number | null;
  discount_percent: number | null;
  is_available: boolean;
  tags: string[];
  prep_time_min: number | null;
  images: ProductImage[];
  option_groups?: OptionGroup[];
  has_options?: boolean;
}

export interface Page<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

export interface CartLine {
  id: string;
  product_id: string;
  name: string;
  image: string | null;
  options: { id: string; name: string; price_delta: number }[];
  quantity: number;
  note: string;
  unit_price: number;
  line_total: number;
  available: boolean;
  warning: string;
}

export interface Cart {
  lines: CartLine[];
  subtotal: number;
  item_count: number;
  has_problems: boolean;
  currency: string;
}

export interface Zone {
  id: string;
  name: string;
  areas: string[];
  fee: number;
  min_order: number | null;
  free_delivery_threshold: number | null;
  eta_min: number | null;
  eta_max: number | null;
}

export interface CheckoutBody {
  fulfilment: "delivery" | "pickup";
  customer_name: string;
  customer_phone: string;
  zone_id?: string | null;
  address_area?: string;
  address_street?: string;
  address_landmark?: string;
  address_building?: string;
  notes?: string;
}

export interface Quote {
  subtotal: number;
  delivery_fee: number;
  discount_total: number;
  total: number;
  currency: string;
  payment_method: string;
  zone: { id: string; name_ar: string; name_en: string; eta_min: number | null;
    eta_max: number | null } | null;
}

export type OrderStatus = "pending" | "confirmed" | "preparing" | "ready" |
  "out_for_delivery" | "delivered" | "cancelled" | "rejected";

export interface Order {
  id: string;
  number: number;
  status: OrderStatus;
  fulfilment: "delivery" | "pickup";
  currency: string;
  subtotal: number;
  delivery_fee: number;
  discount_total: number;
  total: number;
  payment_method: string;
  placed_at: string;
  customer_name: string;
  customer_phone: string;
  zone_name_snapshot: string;
  address_area: string;
  address_street: string;
  address_landmark: string;
  notes: string;
  cancel_reason: string;
  items: { name: string; quantity: number; unit_price: number; line_total: number;
    note: string; options: string[]; product_id: string | null }[];
  can_cancel: boolean;
  timeline: { status: OrderStatus; at: string }[];
}

export interface Address {
  id: string;
  label: "home" | "work" | "other";
  zone: string | null;
  area: string;
  street: string;
  landmark: string;
  building: string;
  is_default: boolean;
}

interface SessionResponse {
  token: string;
  customer: Customer;
  business: BusinessInfo;
}

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

  info = () => this.request<BusinessInfo>("");
  categories = () => this.request<Category[]>("/categories");
  products = (params: Record<string, string | undefined>, cursor?: string | null) => {
    if (cursor) {
      const u = new URL(cursor, location.origin);
      return this.request<Page<Product>>(`/products${u.search}`);
    }
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
    const qs = q.toString();
    return this.request<Page<Product>>(`/products${qs ? `?${qs}` : ""}`);
  };
  product = (id: string) => this.request<Product>(`/products/${id}`);
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
  cancelOrder = (id: string) =>
    this.request<Order>(`/orders/${id}/cancel`, { method: "POST", body: {} });

  me = () => this.request<Customer>("/me");
  updateMe = (body: Partial<Pick<Customer, "full_name" | "phone" | "language">>) =>
    this.request<Customer>("/me", { method: "PATCH", body });
  addresses = () => this.request<Address[]>("/me/addresses");
  addAddress = (body: Omit<Address, "id">) =>
    this.request<Address>("/me/addresses", { method: "POST", body });
  deleteAddress = (id: string) =>
    this.request<void>(`/me/addresses/${id}`, { method: "DELETE" });
  support = (message: string) =>
    this.request<{ sent: boolean }>("/support", { method: "POST", body: { message } });
}

export { ApiError };
