"use client";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const fetcher = (url: string) => fetch(url).then((r) => r.json());

function formatTs(ts: number) {
  const d = new Date(ts);
  return d.toLocaleTimeString();
}

function useSeries(symbol: string, metric: string, window = "6h") {
  return useSWR(`${API_BASE}/timeseries/${symbol}?metric=${metric}&interval=1m&window=${window}`, fetcher, { refreshInterval: 10000 });
}

export default function SymbolDetail() {
  const params = useParams();
  const symbol = String(params?.symbol || "").toUpperCase();
  const { data: snap } = useSWR(`${API_BASE}/metrics/${symbol}`, fetcher, { refreshInterval: 10000 });

  const { data: basis } = useSeries(symbol, "basis");
  const { data: funding } = useSeries(symbol, "funding");
  const { data: oi } = useSeries(symbol, "oi");
  const { data: dom } = useSeries(symbol, "dominance");

  return (
    <main className="p-4 space-y-6">
      <a className="text-sky-400" href="/">← Back</a>
      <h1 className="text-xl font-semibold">{symbol} Detail</h1>
      {snap && (
        <div className="text-sm text-slate-300">SRS {snap.srs} / {snap.traffic_light}</div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        <ChartCard title="Basis (1m)" data={basis?.points || []} color="#60a5fa" />
        <ChartCard title="Funding 1h%" data={funding?.points || []} color="#f59e0b" />
        <ChartCard title="Open Interest (USDT)" data={oi?.points || []} color="#34d399" />
        <ChartCard title="Perp Dominance%" data={dom?.points || []} color="#a78bfa" />
      </div>
    </main>
  );
}

type PointTuple = [number, number];
type PointObj = { ts: number; value?: number; v?: number };

function ChartCard({ title, data, color }: { title: string; data: Array<PointTuple | PointObj>; color: string }) {
  const chartData = (data || []).map((p: any) => {
    if (Array.isArray(p)) {
      const [ts, v] = p as PointTuple;
      return { ts, v };
    }
    const obj = p as PointObj;
    return { ts: Number(obj.ts), v: Number(obj.value ?? obj.v) };
  });
  return (
    <div className="rounded border border-slate-700 p-3">
      <div className="text-sm mb-2 text-slate-300">{title}</div>
      <div style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer>
          <AreaChart data={chartData} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
            <defs>
              <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.4} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="ts" tickFormatter={formatTs} stroke="#64748b" />
            <YAxis stroke="#64748b" />
            <Tooltip labelFormatter={(l) => formatTs(Number(l))} />
            <Area type="monotone" dataKey="v" stroke={color} fillOpacity={1} fill="url(#g)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
