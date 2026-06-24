import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

import "./Overview.css";

const lineData = [
  { time: "00:00", traces: 1000 },
  { time: "04:00", traces: 1400 },
  { time: "08:00", traces: 2200 },
  { time: "12:00", traces: 2600 },
  { time: "16:00", traces: 3100 },
  { time: "20:00", traces: 2900 },
  { time: "Now", traces: 3400 },
];

const fallbackPieData = [
  { name: "gpt-4o", value: 37.9, displayValue: "37.9M" },
  { name: "claude-3-5", value: 25.3, displayValue: "25.3M" },
  { name: "gemini-2.0", value: 12.6, displayValue: "12.6M" },
  { name: "other", value: 8.4, displayValue: "8.4M" },
];

const COLORS = ["#2563EB", "#7C3AED", "#059669", "#D97706", "#8B5CF6", "#EF4444", "#14B8A6"];

type Metrics = {
  total_traces: number;
  success_rate: number | null;
  avg_latency_ms: number | null;
  total_tokens: number;
  estimated_cost_usd?: number;
};

type Deltas = {
  total_traces_pct: number | null;
  success_rate_pp: number | null;
  avg_latency_ms_delta: number | null;
  total_tokens_pct: number | null;
  estimated_cost_usd_pct: number | null;
};

type OverviewApiResponse = {
  from_time: string | null;
  to_time: string | null;
  current: Metrics;
  previous: Partial<Metrics>;
  deltas: Deltas;
};

type TraceVolumeBucket = {
  bucket: string;
  trace_count: number;
};

type TraceVolumeResponse = {
  granularity: string;
  from_time: string | null;
  to_time: string | null;
  data: TraceVolumeBucket[];
};

type RecentTrace = {
  trace_id: string;
  name: string;
  status: string;
  created_at: string;
  total_latency_ms: number;
  total_cost_usd: number;
  span_count: number;
};

type RecentTraceResponse = {
  data: RecentTrace[];
};

type TokenDistributionItem = {
  model: string;
  provider: string;
  total_tokens: number;
  token_share_pct: number;
};

type TokenDistributionResponse = {
  from_time: string | null;
  to_time: string | null;
  grand_total_tokens: number;
  data: TokenDistributionItem[];
};

const nf = new Intl.NumberFormat("en-US");
const compactFormatter = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

const formatNumber = (n?: number | null) => (n == null ? "—" : nf.format(n));
const formatCompact = (n?: number | null) => (n == null ? "—" : compactFormatter.format(n));
const formatLatency = (ms?: number | null) => (ms == null ? "—" : `${nf.format(ms)} ms`);

const deltaNode = (delta: number | null | undefined, opts?: { unit?: string }) => {
  if (delta == null) return <span>—</span>;
  const abs = Math.abs(delta);
  const arrow = delta > 0 ? "▲" : delta < 0 ? "▼" : "";
  const cls = delta > 0 ? "up" : delta < 0 ? "down" : "";
  let value = String(abs);
  if (opts?.unit === "pp") value = `${abs}pp`;
  else if (opts?.unit === "ms") value = `${abs}ms`;
  else if (opts?.unit === "%") value = `${abs}%`;
  return <span className={cls}>{arrow} {value}</span>;
};

const Overview: React.FC = () => {
  const [data, setData] = useState<OverviewApiResponse | null>(null);
  const [traceVolume, setTraceVolume] = useState<TraceVolumeBucket[]>([]);
  const [recentTraces, setRecentTraces] = useState<RecentTrace[]>([]);
  const [tokenDistribution, setTokenDistribution] = useState<TokenDistributionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    const apiBase = String(import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");

    const metricsPath = "/custom-api/v1/dashboard/overview/metrics";
    const tracePath = "/custom-api/v1/dashboard/overview/trace-volume";
    const recentPath = "/custom-api/v1/dashboard/overview/recent-traces?limit=10";
    const tokenPath = "/custom-api/v1/dashboard/overview/token-distribution";
    const metricsUrl = apiBase ? `${apiBase}${metricsPath}` : metricsPath;
    const traceUrl = apiBase ? `${apiBase}${tracePath}` : tracePath;
    const recentUrl = apiBase ? `${apiBase}${recentPath}` : recentPath;
    const tokenUrl = apiBase ? `${apiBase}${tokenPath}` : tokenPath;

    const fetchJson = async <T,>(url: string): Promise<T> => {
      const res = await fetch(url);
      const contentType = res.headers.get("content-type") || "";
      const bodyText = await res.text();
      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}: ${bodyText}`);
      }
      if (!contentType.includes("application/json")) {
        throw new Error(`Expected JSON response but received ${contentType || "unknown"}. Response body: ${bodyText.slice(0, 300)}`);
      }
      return JSON.parse(bodyText) as T;
    };

    Promise.all([
      fetchJson<OverviewApiResponse>(metricsUrl),
      fetchJson<TraceVolumeResponse>(traceUrl),
      fetchJson<RecentTraceResponse>(recentUrl),
      fetchJson<TokenDistributionResponse>(tokenUrl),
    ])
      .then(([metricsJson, traceJson, recentJson, tokenJson]) => {
        if (!mounted) return;
        setData(metricsJson);
        setTraceVolume(traceJson.data || []);
        setRecentTraces(recentJson.data || []);
        setTokenDistribution(tokenJson.data || []);
        setError(null);
      })
      .catch((err: any) => {
        if (!mounted) return;
        console.error(err);
        setError(err?.message || String(err));
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });

    return () => { mounted = false; };
  }, []);

  const cur = data?.current;
  const deltas = data?.deltas;

  const chartData = traceVolume.map((bucket) => ({
    time: bucket.bucket,
    traces: bucket.trace_count,
  }));

  const tokenPieData = tokenDistribution.length
    ? tokenDistribution.map((item) => ({
        name: item.model,
        value: item.token_share_pct,
        displayValue: `${item.token_share_pct.toFixed(1)}%`,
      }))
    : fallbackPieData;

  return (
    <div className="overview">

      <div style={{display:'flex', alignItems:'center', gap:12, marginBottom:12}}>
        <div style={{fontWeight:700, fontSize:16}}>Overview</div>
        {loading && <div style={{color:'#6b7280'}}>Loading metrics...</div>}
        {error && <div style={{color:'#DC2626'}}>{error}</div>}
      </div>

      <div className="metrics-grid">
        <div className="metric-card blue">
          <div className="metric-label">Total Traces</div>
          <div className="metric-value blue">{cur ? formatNumber(cur.total_traces) : (loading ? '—' : '—')}</div>
          <div className="metric-delta">{deltas ? <>{deltaNode(deltas.total_traces_pct, {unit: '%'})} vs yesterday</> : '—'}</div>
        </div>

        <div className="metric-card green">
          <div className="metric-label">Success Rate</div>
          <div className="metric-value green">{cur && cur.success_rate != null ? <>{nf.format(cur.success_rate)}<span className="metric-unit">%</span></> : '—'}</div>
          <div className="metric-delta">{deltas ? <>{deltaNode(deltas.success_rate_pp, {unit: 'pp'})} vs yesterday</> : '—'}</div>
        </div>

        <div className="metric-card amber">
          <div className="metric-label">Avg Latency</div>
          <div className="metric-value">{cur ? formatLatency(cur.avg_latency_ms) : '—'}</div>
          <div className="metric-delta">{deltas ? <>{deltaNode(deltas.avg_latency_ms_delta, {unit: 'ms'})} vs previous</> : '—'}</div>
        </div>

        <div className="metric-card purple">
          <div className="metric-label">Total Tokens</div>
          <div className="metric-value purple">{cur ? formatCompact(cur.total_tokens) : '—'}</div>
          <div className="metric-delta">{deltas ? <>{deltaNode(deltas.total_tokens_pct, {unit: '%'})} vs yesterday</> : '—'}</div>
        </div>

        <div className="metric-card red">
          <div className="metric-label">Est. Cost</div>
          <div className="metric-value red">{cur && cur.estimated_cost_usd != null ? `$${cur.estimated_cost_usd.toFixed(2)}` : '—'}</div>
          <div className="metric-delta">{deltas ? <>{deltaNode(deltas.estimated_cost_usd_pct, {unit: '%'})} vs yesterday</> : '—'}</div>
        </div>
      </div>

      <div className="panel-grid">
        <div className="panel">
          <div className="panel-head">
            <span className="panel-icon">📈</span>
            <div className="panel-title">Trace Volume · 24h</div>
            <a className="panel-action" href="#">View all →</a>
          </div>
          <div className="chart-area">
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData.length ? chartData : lineData}>
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="traces" stroke="#2563EB" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <span className="panel-icon">🔔</span>
            <div className="panel-title">Drift Alerts</div>
            <a className="panel-action" href="#">View all →</a>
          </div>
          <div className="alert-strip">
            <div className="alert-item crit">
              <span className="alert-sev crit">CRIT</span>
              <div className="alert-body">
                <div className="alert-title">sql_query tool spike — 3.2× baseline</div>
                <div className="alert-meta">tool_usage_baselines</div>
              </div>
              <span className="alert-time">4m</span>
            </div>
            <div className="alert-item warn">
              <span className="alert-sev warn">WARN</span>
              <div className="alert-body">
                <div className="alert-title">Model drift: gpt-4o → gpt-4o-mini</div>
                <div className="alert-meta">observations</div>
              </div>
              <span className="alert-time">22m</span>
            </div>
            <div className="alert-item warn">
              <span className="alert-sev warn">WARN</span>
              <div className="alert-body">
                <div className="alert-title">Prompt version mismatch in session #9f2a</div>
                <div className="alert-meta">prompt_versions</div>
              </div>
              <span className="alert-time">1h</span>
            </div>
            <div className="alert-item" style={{opacity:0.55}}>
              <span className="alert-sev info">INFO</span>
              <div className="alert-body">
                <div className="alert-title">Circuit breaker reset — openai-api</div>
                <div className="alert-meta">circuit_breaker_states</div>
              </div>
              <span className="alert-time">3h</span>
            </div>
          </div>
        </div>
      </div>

      <div className="panel-grid-3">
        <div className="panel">
          <div className="panel-head">
            <span className="panel-icon">⟳</span>
            <div className="panel-title">Recent Traces</div>
            <a className="panel-action" href="#">All traces →</a>
          </div>
          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Trace ID</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
              {(recentTraces.length ? recentTraces : []).map((trace) => (
                <tr key={trace.trace_id}>
                  <td className="trace-id">{trace.trace_id}</td>
                  <td>{trace.name}</td>
                  <td>
                    <span className={`badge ${trace.status === 'success' ? 'ok' : trace.status === 'error' ? 'err' : 'warn'}`}>
                      <span className="badge-dot"></span>
                      {trace.status}
                    </span>
                  </td>
                  <td className="mono">{trace.total_latency_ms ? `${nf.format(trace.total_latency_ms)}ms` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <span className="panel-icon">🍩</span>
            <div className="panel-title">Token Distribution</div>
            <div className="panel-sub">Last 24h</div>
          </div>
          <div className="donut-wrap">
            <ResponsiveContainer width={160} height={160}>
              <PieChart>
                <Pie data={tokenPieData} dataKey="value" innerRadius={36} outerRadius={72} startAngle={90} endAngle={-270}>
                  {tokenPieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-legend">
              {tokenPieData.map((entry, index) => (
                <div className="legend-item" key={entry.name}>
                  <div className="legend-dot" style={{ background: COLORS[index % COLORS.length] }}></div>
                  <div className="legend-label">{entry.name}</div>
                  <div className="legend-val">{entry.displayValue}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <span className="panel-icon">🖥</span>
            <div className="panel-title">System Status</div>
            <div className="panel-sub">Infrastructure</div>
          </div>
          <div className="mini-stats">
            <div className="mini-stat"><div className="mini-stat-label">MCP Servers</div><div className="mini-stat-val blue">8</div></div>
            <div className="mini-stat"><div className="mini-stat-label">Active Tools</div><div className="mini-stat-val">34</div></div>
            <div className="mini-stat"><div className="mini-stat-label">Queue Depth</div><div className="mini-stat-val amber">1,204</div></div>
            <div className="mini-stat"><div className="mini-stat-label">Circuit Breakers</div><div className="mini-stat-val green">7 OK</div></div>
          </div>

          <div className="section-divider">Model Usage Share</div>
          <div className="model-list">
            <div className="model-row"><div className="model-name">gpt-4o</div><div className="model-bar-wrap"><div className="model-bar" style={{width:'62%', background:'#2563EB'}} /></div><div className="model-pct">62%</div></div>
            <div className="model-row"><div className="model-name">claude-3-5-sonnet</div><div className="model-bar-wrap"><div className="model-bar" style={{width:'24%', background:'#7C3AED'}} /></div><div className="model-pct">24%</div></div>
            <div className="model-row"><div className="model-name">gemini-2.0-flash</div><div className="model-bar-wrap"><div className="model-bar" style={{width:'10%', background:'#059669'}} /></div><div className="model-pct">10%</div></div>
            <div className="model-row"><div className="model-name">gpt-4o-mini</div><div className="model-bar-wrap"><div className="model-bar" style={{width:'4%', background:'#D97706'}} /></div><div className="model-pct">4%</div></div>
          </div>

        </div>
      </div>

    </div>
  );
};

export default Overview;