// Small key/value abstraction: chrome.storage.local in the extension,
// localStorage in the dev harness.
import type { BackendConfig } from "./backendClient";

export interface KVStore {
  get<T>(key: string): Promise<T | undefined>;
  set<T>(key: string, value: T): Promise<void>;
}

export const chromeStore: KVStore = {
  async get<T>(key: string) {
    const r = await chrome.storage.local.get(key);
    return r[key] as T | undefined;
  },
  async set<T>(key: string, value: T) {
    await chrome.storage.local.set({ [key]: value });
  },
};

export const localStore: KVStore = {
  async get<T>(key: string) {
    try {
      const v = localStorage.getItem(key);
      return v == null ? undefined : (JSON.parse(v) as T);
    } catch {
      return undefined;
    }
  },
  async set<T>(key: string, value: T) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable */
    }
  },
};

export const KEYS = {
  backend: "copilot.backend",
  geom: "copilot.panelGeom",
  tab: "copilot.activeTab",
  visible: "copilot.visible",
} as const;

export const DEFAULT_BACKEND: BackendConfig = { url: "http://127.0.0.1:8765", token: "" };
