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
  const { data: symbols } = useSWR(`${API_BASE}/symbols`, fetcher);
  const list: string[] = symbols?.watchlist || [];

  return (
    <main className="p-4 space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Short‑Risk Radar</h1>
        <span className="text-sm text-slate-400">MVP</span>
      </header>

      <section>
        <h2 className="text-sm text-slate-300 mb-2">Watchlist</h2>
        <div className="text-slate-300 text-sm">{JSON.stringify(list)}</div>
        <MetricHelp />
      </section>

      <section className="grid gap-4">
        {list.length === 0 ? (
          <div className="text-slate-400 text-sm">No symbols in watchlist.</div>
        ) : (
          list.map((s) => <Tile key={s} symbol={s} />)
        )}
      </section>
    </main>
  );
}

function Tile({ symbol }: { symbol: string }) {
  const { data, isLoading, latencyMs } = useMetrics(symbol);
  if (!data || isLoading) return <div className="rounded border border-slate-700 p-4">Loading {symbol}…</div>;

  const ageSec = data?.ts ? Math.max(0, Math.round((Date.now() - data.ts) / 1000)) : null;
  const light = String(data.traffic_light || "YELLOW").toUpperCase();
  const lightColor = light === "RED" ? "bg-red-500" : light === "GREEN" ? "bg-emerald-500" : "bg-amber-500";

  return (
    <div className="rounded border border-slate-700 p-4 grid grid-cols-2 gap-2">
      <div className="col-span-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${lightColor}`} />
          <Link className="font-medium text-sky-400" href={`/symbol/${data.symbol}`}>{data.symbol}</Link>
        </div>
        <div className="text-xs flex items-center gap-3">
          <span>SRS: {data.srs} / {light}</span>
          {ageSec !== null && <span className="text-slate-400">age {ageSec}s</span>}
          {typeof latencyMs === "number" && <span className="text-slate-400">api {latencyMs}ms</span>}
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
      <Field k="Dom%" v={data.perp_dominance_pct} />
      <Field k="OB Imb" v={data.orderbook_imbalance} />

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
  return (
    <div className="text-sm">
      <div className="text-slate-400">{k}</div>
      <div className="font-mono">{String(v)}</div>
    </div>
  );
}
