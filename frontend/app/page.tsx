"use client";
import useSWR from "swr";
import Link from "next/link";
import { useState } from "react";
import MetricHelp from "../components/MetricHelp";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const fetcher = (url: string) => fetch(url).then((r) => r.json());

function useMetrics(symbol: string) {
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const { data, error, isLoading } = useSWR(`${API_BASE}/metrics/${symbol}`, async (url) => {
    const t0 = performance.now();
    const res = await fetch(url);
    const json = await res.json();
    setLatencyMs(Math.round(performance.now() - t0));
    return json;
  }, { refreshInterval: 10000 });
  return { data, error, isLoading, latencyMs };
}

export default function Home() {
  const { data: symbols, mutate: mutateSymbols } = useSWR(`${API_BASE}/symbols`, fetcher);
  const { data: mode } = useSWR(`${API_BASE}/debug/mode`, fetcher);
  const { data: available } = useSWR(`${API_BASE}/symbols/available?include_spot=true`, fetcher);
  const list: string[] = symbols?.watchlist || [];
  const [newSym, setNewSym] = useState("");

  async function addSymbol(sym: string) {
    const symbol = sym.trim().toUpperCase();
    if (!symbol) return;
    await fetch(`${API_BASE}/symbols`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    setNewSym("");
    await mutateSymbols();
  }

  async function removeSymbol(sym: string) {
    const symbol = sym.trim().toUpperCase();
    await fetch(`${API_BASE}/symbols`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    await mutateSymbols();
  }

  return (
    <main className="p-4 space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Short‑Risk Radar</h1>
        <span className="text-sm text-slate-400 flex items-center gap-3">
          <span>MVP</span>
          {mode && (
            <span
              className={`px-2 py-0.5 rounded-full border ${mode.use_ws ? 'border-emerald-500 text-emerald-300' : 'border-sky-500 text-sky-300'}`}
              title="Backend ingestion mode"
            >
              {mode.use_ws ? 'WS' : 'REST'}
            </span>
          )}
        </span>
      </header>

      <section>
        <h2 className="text-sm text-slate-300 mb-2">Watchlist</h2>
        <form
          className="flex items-center gap-2 mb-2"
          onSubmit={(e) => {
            e.preventDefault();
            addSymbol(newSym);
          }}
        >
          <input
            value={newSym}
            onChange={(e) => setNewSym(e.target.value.toUpperCase())}
            placeholder="e.g., BTCUSDT"
            className="px-2 py-1 bg-slate-900 border border-slate-700 rounded text-sm text-slate-200 placeholder-slate-500"
          />
          <button
            type="submit"
            className="px-3 py-1 rounded border border-slate-600 text-sm bg-slate-800 hover:bg-slate-700"
          >
            Add
          </button>
        </form>

        {list.length > 0 ? (
          <div className="flex flex-wrap gap-2 mb-3">
            {list.map((s) => (
              <span key={s} className="text-xs px-2 py-0.5 rounded-full border border-slate-600 text-slate-300 bg-slate-800/50 flex items-center gap-2">
                {s}
                <button
                  onClick={() => removeSymbol(s)}
                  className="text-slate-400 hover:text-red-400"
                  title="Remove"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : (
          <div className="text-slate-400 text-sm mb-3">No symbols in watchlist.</div>
        )}

        <MetricHelp />
      </section>

      <section className="grid gap-4">
        {list.length === 0 ? (
          <div className="text-slate-400 text-sm">No symbols in watchlist.</div>
        ) : (
          list.map((s) => <Tile key={s} symbol={s} onRemove={() => removeSymbol(s)} />)
        )}
      </section>

      <section>
        <details className="rounded border border-slate-700 bg-slate-900/40">
          <summary className="cursor-pointer select-none p-3 text-sky-300">Available contracts (USDT‑M Perpetual)</summary>
          <div className="p-3">
            {!available ? (
              <div className="text-slate-400 text-sm">Loading…</div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(available.symbols as Array<{symbol:string; has_spot?: boolean}>).slice(0, 300).map((o) => (
                  <button key={o.symbol} onClick={() => addSymbol(o.symbol)} className={`text-xs px-2 py-0.5 rounded border ${o.has_spot ? 'border-slate-600' : 'border-red-600'} text-slate-300 bg-slate-800/50 hover:bg-slate-700`} title={o.has_spot ? 'Spot available' : 'No spot market'}>
                    + {o.symbol}{!o.has_spot ? ' (no spot)' : ''}
                  </button>
                ))}
              </div>
            )}
          </div>
        </details>
      </section>
    </main>
  );
}

function Tile({ symbol, onRemove }: { symbol: string; onRemove: () => void }) {
  const { data, isLoading, latencyMs } = useMetrics(symbol);
  if (!data || isLoading) return <div className="rounded border border-slate-700 p-4">Loading {symbol}…</div>;

  const ageSec = data?.ts ? Math.max(0, Math.round((Date.now() - data.ts) / 1000)) : null;
  const light = String(data.traffic_light || "YELLOW").toUpperCase();
  const lightColor = light === "RED" ? "bg-red-500" : light === "GREEN" ? "bg-emerald-500" : "bg-amber-500";
  const srs = Number(data.srs) || 0;
  const srsBand = srs >= 70 ? "RED" : srs >= 40 ? "YELLOW" : "GREEN";
  const srsColor = srsBand === "RED" ? "bg-red-500" : srsBand === "YELLOW" ? "bg-amber-500" : "bg-emerald-500";
  const actionText = light === "RED" ? "DO NOT SHORT" : light === "GREEN" ? "SHORT WINDOW" : "BASIS-ONLY";
  const actionBorder = light === "RED" ? "border-red-500 text-red-300" : light === "GREEN" ? "border-emerald-500 text-emerald-300" : "border-amber-500 text-amber-300";
  const fmtCompact = (x: any) => {
    const n = Number(x);
    if (!isFinite(n)) return String(x);
    const abs = Math.abs(n);
    if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
    if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
    if (abs >= 1_000) return `${(n / 1_000).toFixed(2)}K`;
    return String(n);
  };

  return (
    <div className="rounded border border-slate-700 p-4 grid grid-cols-2 gap-2">
      <div className="col-span-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${lightColor}`} />
          <Link className="font-medium text-sky-400" href={`/symbol/${data.symbol}`}>{data.symbol}</Link>
        </div>
        <div className="text-xs flex items-center gap-3">
          <div className="flex items-center gap-2" title="SRS: composite squeeze risk (0 low, 100 high). Bands: ≤39 GREEN, 40–69 YELLOW, ≥70 RED.">
            <div className="w-20 h-1.5 bg-slate-800 rounded">
              <div className={`h-1.5 ${srsColor} rounded`} style={{ width: `${Math.min(100, Math.max(0, srs))}%` }} />
            </div>
            <span className="font-mono">SRS {srs}</span>
          </div>
          <span className={`px-2 py-0.5 rounded-full border ${actionBorder}`} title="Action from rules engine">
            {actionText}
          </span>
          {ageSec !== null && <span className="text-slate-400">age {ageSec}s</span>}
          {typeof latencyMs === "number" && <span className="text-slate-400">api {latencyMs}ms</span>}
          <button onClick={onRemove} className="px-2 py-0.5 rounded border border-slate-600 hover:bg-red-500/10 hover:border-red-500">Remove</button>
        </div>
      </div>

      <Field k="Mark" v={data.mark} />
      <Field k="Index" v={data.index} />
      <Field k="Basis%" v={data.basis_pct} />
      <Field k="TWAP15%" v={data.basis_twap15_pct} />

      <div>
        <div className="text-slate-400 text-sm">Funding 1h%</div>
        <div className="font-mono">{String(data.funding_1h_pct)}</div>
        {data.funding_interval_hours ? (
          <div className="text-xs text-slate-500 mt-0.5">interval: {data.funding_interval_hours}h</div>
        ) : null}
      </div>
      <Field k="Daily Est%" v={data.funding_daily_est_pct} />

      <Field k="OI (USDT)" v={data.oi_usdt} />
      <Field k="ΔOI 1h" v={data.delta_oi_1h_usdt} />
      <div>
        <div className="text-slate-400 text-sm">Dom%</div>
        <div className="font-mono">
          {data.dominance_unknown ? <span className="text-slate-500">unknown</span> : String(data.perp_dominance_pct)}
        </div>
        <div className="text-xs text-slate-500 mt-0.5">Perp24h {fmtCompact(data.fut_vol24_usdt)} / Spot24h {fmtCompact(data.spot_vol24_usdt)}</div>
      </div>
      <Field k="OB Imb" v={data.orderbook_imbalance} />

      <div>
        <div className="text-slate-400 text-sm">Spot Market</div>
        <div className={`font-mono ${data.has_spot ? 'text-emerald-400' : 'text-red-400'}`}>{data.has_spot ? 'Available' : 'Not available'}</div>
      </div>

      {Array.isArray(data.rule_reasons) && data.rule_reasons.length > 0 && (
        <div className="col-span-2 mt-2 flex flex-wrap gap-1">
          {data.rule_reasons.map((r: string, i: number) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded-full border border-slate-600 text-slate-300 bg-slate-800/50">{r}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ k, v }: { k: string; v: any }) {
  function fmtNumber(x: any) {
    const n = Number(x);
    if (!isFinite(n)) return String(x);
    const abs = Math.abs(n);
    if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
    if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
    if (abs >= 1_000) return `${(n / 1_000).toFixed(2)}K`;
    return String(n);
  }
  return (
    <div className="text-sm">
      <div className="text-slate-400">{k}</div>
      <div className="font-mono">{fmtNumber(v)}</div>
    </div>
  );
}
