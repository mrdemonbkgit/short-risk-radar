export default function MetricHelp() {
  return (
    <section className="mt-6">
      <details className="rounded border border-slate-700 bg-slate-900/40">
        <summary className="cursor-pointer select-none p-3 text-sky-300">Metrics guide</summary>
        <div className="p-4 text-sm text-slate-300 space-y-2">
          <p className="text-slate-400">Key definitions used by the dashboard:</p>
          <ul className="list-disc list-inside space-y-1">
            <li><b>Basis%</b>: (mark − index) / index × 100</li>
            <li><b>TWAP(w)</b>: average of per‑minute basis over the last w minutes (e.g., TWAP15)</li>
            <li><b>Funding 1h%</b>: per‑hour funding rate; <b>Daily Est%</b> = funding_1h × 24</li>
            <li><b>Perp Dominance%</b>: fut_vol24 / (fut_vol24 + spot_vol24_agg) × 100</li>
            <li><b>ΔOI</b>: OI_now − OI_{'{'}t−window{'}'} (1h/4h/24h windows)</li>
            <li><b>Orderbook Imbalance</b>: Σ bid_qty(≤+2%) / Σ ask_qty(≤+2%) around mid</li>
            <li><b>OI/PerpVol</b>: OI_usdt / fut_vol24_usdt (stickiness proxy)</li>
            <li><b>SRS</b>: Squeeze Risk Score (0–100). Higher = greater squeeze risk.</li>
          </ul>
          <p className="text-slate-400">Tip: hover tiles for recent readings; click a symbol for charts.</p>
        </div>
      </details>
    </section>
  );
}
