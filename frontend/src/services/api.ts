// Typed REST client. Never holds API keys - only the user's session token
// (Supabase mode) is attached.
import type { ApiErrorBody } from "../types/api";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

let tokenProvider: () => Promise<string | null> = async () => null;

export function setTokenProvider(fn: () => Promise<string | null>): void {
  tokenProvider = fn;
}

export async function currentToken(): Promise<string | null> {
  return tokenProvider();
}

export class ApiError extends Error {
  readonly code: string;
  readonly reason: string | null;
  readonly nextStep: string | null;
  readonly status: number;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message);
    this.code = body.code;
    this.reason = body.reason ?? null;
    this.nextStep = body.next_step ?? null;
    this.status = status;
  }

  static from(err: unknown): ApiError {
    if (err instanceof ApiError) return err;
    if (err instanceof TypeError) {
      return new ApiError(
        {
          code: "network_error",
          message: "Can't reach the NEXUS backend.",
          reason: "The server isn't running or the network is down.",
          next_step: "Start the backend (see README) and try again.",
        },
        0,
      );
    }
    return new ApiError({ code: "unknown", message: err instanceof Error ? err.message : String(err) }, 0);
  }
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

async function request<T>(method: string, path: string, body?: unknown, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = await tokenProvider();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { ...init, method, headers, body: payload });
  } catch (err) {
    throw ApiError.from(err);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const err = (data as { error?: ApiErrorBody } | null)?.error;
    throw new ApiError(err ?? { code: `http_${res.status}`, message: `Request failed (${res.status}).` }, res.status);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  del: <T = void>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, form),
  async blob(path: string, body?: unknown): Promise<Blob> {
    const headers = new Headers({ "Content-Type": "application/json" });
    const token = await tokenProvider();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(apiUrl(path), { method: "POST", headers, body: JSON.stringify(body ?? {}) });
    if (!res.ok) {
      const data = (await res.json().catch(() => null)) as { error?: ApiErrorBody } | null;
      throw new ApiError(data?.error ?? { code: `http_${res.status}`, message: "Request failed." }, res.status);
    }
    return res.blob();
  },
  async fileObjectUrl(fileId: string): Promise<string> {
    const headers = new Headers();
    const token = await tokenProvider();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(apiUrl(`/api/files/${fileId}/content`), { headers });
    if (!res.ok) throw new ApiError({ code: "file_unavailable", message: "Could not load the file." }, res.status);
    return URL.createObjectURL(await res.blob());
  },
};
