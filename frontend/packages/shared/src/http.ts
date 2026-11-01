export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.code);
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? {};
  }

  /** Flatten DRF field errors into {field: "message"}. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(this.details)) {
      if (Array.isArray(v) && v.length) out[k] = String(v[0]);
      else if (typeof v === "string") out[k] = v;
    }
    return out;
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export async function parseResponse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const body: ApiErrorBody = data?.error ?? { code: "network_error", message: res.statusText };
    throw new ApiError(res.status, body);
  }
  return data as T;
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
