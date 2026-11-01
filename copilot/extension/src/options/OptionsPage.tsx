import { useEffect, useState } from "react";
import { toWsUrl, type BackendConfig } from "../shared/backendClient";
import { DEFAULT_BACKEND, KEYS, chromeStore } from "../shared/storage";

type TestResult = { ok: boolean; text: string } | null;

export function OptionsPage() {
  const [cfg, setCfg] = useState<BackendConfig>(DEFAULT_BACKEND);
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState<TestResult>(null);

  useEffect(() => {
    void chromeStore.get<BackendConfig>(KEYS.backend).then((c) => c && setCfg({ ...DEFAULT_BACKEND, ...c }));
  }, []);

  const save = async () => {
    try {
      toWsUrl(cfg.url);
    } catch (e) {
      setTest({ ok: false, text: (e as Error).message });
      return;
    }
    await chromeStore.set(KEYS.backend, { url: cfg.url.trim().replace(/\/$/, ""), token: cfg.token.trim() });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const runTest = async () => {
    setTest(null);
    try {
      const base = cfg.url.trim().replace(/\/$/, "");
      const r = await fetch(`${base}/api/status`, { headers: { Authorization: `Bearer ${cfg.token.trim()}` } });
      if (r.status === 401) return setTest({ ok: false, text: "Backend svarer, men tokenet er feil." });
      if (!r.ok) return setTest({ ok: false, text: `Backend svarte ${r.status}.` });
      const s = await r.json();
      setTest({ ok: true, text: `OK – versjon ${s.version}, modus ${s.feed.mode}, feed ${s.feed.state}, kun lesing: ${s.readOnly ? "ja" : "nei"}` });
    } catch {
      setTest({ ok: false, text: "Får ikke kontakt. Kjører backend? (python -m app i copilot/backend)" });
    }
  };

  return (
    <div className="copilot-root mx-auto max-w-xl space-y-5 p-8">
      <h1 className="text-lg font-semibold text-tv-text">AI Trading Copilot – Innstillinger</h1>

      <label className="block space-y-1">
        <span className="text-xs text-tv-muted">Backend-URL (kun localhost)</span>
        <input
          className="w-full rounded border border-tv-border bg-tv-panel px-2 py-1.5 font-mono text-sm text-tv-text outline-none focus:border-tv-blue"
          value={cfg.url}
          onChange={(e) => setCfg({ ...cfg, url: e.target.value })}
        />
      </label>

      <label className="block space-y-1">
        <span className="text-xs text-tv-muted">Tilgangstoken (skrives ut når backend starter, lagret i copilot/backend/data/auth_token)</span>
        <input
          type="password"
          autoComplete="off"
          className="w-full rounded border border-tv-border bg-tv-panel px-2 py-1.5 font-mono text-sm text-tv-text outline-none focus:border-tv-blue"
          value={cfg.token}
          onChange={(e) => setCfg({ ...cfg, token: e.target.value })}
        />
      </label>

      <div className="flex gap-2">
        <button onClick={save} className="rounded bg-tv-blue px-3 py-1.5 text-sm text-white hover:opacity-90">
          {saved ? "Lagret ✓" : "Lagre"}
        </button>
        <button onClick={runTest} className="rounded border border-tv-border px-3 py-1.5 text-sm text-tv-text hover:bg-tv-hover">
          Test tilkobling
        </button>
      </div>
      {test && <p className={`text-sm ${test.ok ? "text-tv-up" : "text-tv-down"}`}>{test.text}</p>}

      <div className="space-y-1 rounded border border-tv-border p-3 text-xs text-tv-muted">
        <p>Utvidelses-ID: <code className="text-tv-text">{chrome.runtime.id}</code></p>
        <p>
          For strengere sikkerhet: legg ID-en inn i <code>copilot/backend/.env</code> som
          <code> COPILOT_ALLOWED_EXTENSION_IDS=["{chrome.runtime.id}"]</code>.
        </p>
        <p>Første versjon er kun lesende. Den plasserer, endrer eller lukker aldri handler.</p>
      </div>
    </div>
  );
}
