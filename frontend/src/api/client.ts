import { mockFetch } from "@/mocks/handlers";

/** The real FastAPI backend by default. Unit tests (and VITE_USE_MOCKS=true) use the in-memory mock API. */
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true" || import.meta.env.MODE === "test";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
}

function buildPath(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null) params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Typed fetch wrapper. All paths start with /api. */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = buildPath(path, opts.query);
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  };
  const res = USE_MOCKS ? await mockFetch(url, init) : await fetch(url, init);
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? [String((detail as { message: unknown }).message), ...Object.values((detail as { errors?: Record<string, string> }).errors ?? {})].join(" ")
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(-1)[0] ?? "field"}: ${d.msg}`).join("; ")
            : res.statusText;
    throw new ApiError(res.status, message, data);
  }
  return data as T;
}
