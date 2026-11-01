// Connection helpers for the extension's full pages (journal, replay).
// Extension pages have the chrome-extension:// origin, so they may talk to the
// backend directly (REST with the bearer token, WebSocket with auth message).
import { BackendClient, type BackendConfig } from "../shared/backendClient";
import type { ConnState, ServerMessage } from "../shared/protocol";
import { DEFAULT_BACKEND, KEYS, chromeStore } from "../shared/storage";

export async function loadConfig(): Promise<BackendConfig> {
  try {
    return { ...DEFAULT_BACKEND, ...((await chromeStore.get<BackendConfig>(KEYS.backend)) ?? {}) };
  } catch {
    // dev preview outside the extension
    const token = new URLSearchParams(location.search).get("token") ?? localStorage.getItem("copilot.devToken") ?? "";
    return { ...DEFAULT_BACKEND, token };
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(cfg: BackendConfig, path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(`${cfg.url.replace(/\/$/, "")}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${cfg.token}`, "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!r.ok) {
    let msg = `Feil ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* not json */
    }
    throw new ApiError(r.status, msg);
  }
  return (await r.json()) as T;
}

export function connect(cfg: BackendConfig, onMessage: (m: ServerMessage) => void, onState: (s: ConnState) => void): BackendClient {
  const c = new BackendClient({ onMessage, onState });
  c.start(cfg);
  return c;
}
