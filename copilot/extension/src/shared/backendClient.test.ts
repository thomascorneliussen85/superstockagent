import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backoffMs, BackendClient, toWsUrl } from "./backendClient";
import type { ConnState, ServerMessage } from "./protocol";

class FakeWS {
  static OPEN = 1;
  static instances: FakeWS[] = [];
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeWS.instances.push(this);
  }
  send(d: string) {
    this.sent.push(d);
  }
  close(code = 1000) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  recv(m: unknown) {
    this.onmessage?.({ data: JSON.stringify(m) });
  }
}

const hello = { type: "hello", data: { serverVersion: "0.1.0", protocol: 1, mode: "demo", readOnly: true, symbol: "XAUUSD" } };

describe("toWsUrl", () => {
  it("maps http to ws /ws and rejects non-local hosts", () => {
    expect(toWsUrl("http://127.0.0.1:8765")).toBe("ws://127.0.0.1:8765/ws");
    expect(() => toWsUrl("http://example.com:8765")).toThrow();
  });
  it("backoff grows and caps", () => {
    expect(backoffMs(0)).toBeLessThanOrEqual(1200);
    expect(backoffMs(20)).toBeLessThanOrEqual(36_000);
  });
});

describe("BackendClient", () => {
  let states: ConnState[];
  let msgs: ServerMessage[];
  let client: BackendClient;
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWS.instances = [];
    states = [];
    msgs = [];
    client = new BackendClient(
      { onMessage: (m) => msgs.push(m), onState: (s) => states.push(s) },
      FakeWS as unknown as typeof WebSocket,
    );
  });
  afterEach(() => {
    client.stop();
    vi.useRealTimers();
  });

  it("authenticates with the token as first message, not in the URL", () => {
    client.start({ url: "http://127.0.0.1:8765", token: "secret" });
    const ws = FakeWS.instances[0];
    expect(ws.url).not.toContain("secret");
    ws.open();
    expect(JSON.parse(ws.sent[0])).toEqual({ type: "auth", token: "secret" });
    ws.recv(hello);
    expect(client.state).toBe("connected");
    expect(msgs[0].type).toBe("hello");
  });

  it("reconnects with backoff after an unexpected close", () => {
    client.start({ url: "http://127.0.0.1:8765", token: "t" });
    FakeWS.instances[0].open();
    FakeWS.instances[0].close(1006);
    expect(client.state).toBe("error");
    vi.advanceTimersByTime(1500);
    expect(FakeWS.instances).toHaveLength(2);
  });

  it("marks unauthorized and slows retries on 4401", () => {
    client.start({ url: "http://127.0.0.1:8765", token: "bad" });
    FakeWS.instances[0].open();
    FakeWS.instances[0].close(4401);
    expect(client.state).toBe("unauthorized");
    vi.advanceTimersByTime(10_000);
    expect(FakeWS.instances).toHaveLength(1);
    vi.advanceTimersByTime(25_000);
    expect(FakeWS.instances).toHaveLength(2);
  });

  it("does not connect without a token", () => {
    client.start({ url: "http://127.0.0.1:8765", token: "" });
    expect(FakeWS.instances).toHaveLength(0);
    expect(client.state).toBe("unauthorized");
  });

  it("forces reconnect when the connection goes silent", () => {
    client.start({ url: "http://127.0.0.1:8765", token: "t" });
    const ws = FakeWS.instances[0];
    ws.open();
    ws.recv(hello);
    vi.advanceTimersByTime(60_000);
    expect(ws.readyState).toBe(3);
  });

  it("ignores malformed frames", () => {
    client.start({ url: "http://127.0.0.1:8765", token: "t" });
    const ws = FakeWS.instances[0];
    ws.open();
    ws.onmessage?.({ data: "not json" });
    ws.recv({ type: "unknown", data: {} });
    expect(msgs).toHaveLength(0);
  });
});
