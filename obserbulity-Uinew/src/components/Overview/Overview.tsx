import React, { useEffect, useState } from "react";
import {
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  CartesianGrid,
  Area,
} from "recharts";

import "./Overview.css";
import { apiFetch } from '../../utils/apiClient';

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

type TraceFlowStep = {
  id: string;
  trace_id: string;
  type: string;
  name: string;
  status: string;
  latency_ms: number;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  created_at: string;
  model: string | null;
  provider: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
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

type ModelUsageShareItem = {
  model: string;
  provider: string;
  llm_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  usage_share_pct: number;
};

type ModelUsageShareResponse = {
  from_time: string | null;
  to_time: string | null;
  data: ModelUsageShareItem[];
};

const nf = new Intl.NumberFormat("en-US");
const compactFormatter = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

const formatNumber = (n?: number | null) => (n == null ? "—" : nf.format(n));
const formatCompact = (n?: number | null) => (n == null ? "—" : compactFormatter.format(n));
const formatLatency = (ms?: number | null) => (ms == null ? "—" : `${nf.format(ms)} ms`);

const summarizeValue = (value: unknown): string => {
  if (value == null) return "—";
  if (typeof value === "string") {
    return value.length > 140 ? `${value.slice(0, 137)}...` : value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.length ? `${value.length} item${value.length === 1 ? "" : "s"}` : "No items";
  }
  if (typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).slice(0, 4);
    return keys.length ? `${keys.join(", ")}${Object.keys(value as Record<string, unknown>).length > 4 ? ", …" : ""}` : "Empty object";
  }
  return "—";
};

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
  const [modelUsageShare, setModelUsageShare] = useState<ModelUsageShareItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedTraceSteps, setSelectedTraceSteps] = useState<TraceFlowStep[]>([]);
  const [selectedTraceLoading, setSelectedTraceLoading] = useState(false);
  const [selectedTraceError, setSelectedTraceError] = useState<string | null>(null);

  const apiBase = String(import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");

  const openTraceFlow = async (traceId: string) => {
    setSelectedTraceId(traceId);
    setSelectedTraceLoading(true);
    setSelectedTraceError(null);
    setSelectedTraceSteps([]);

    try {
      const detailPath = `/custom-api/v1/traces/${encodeURIComponent(traceId)}`;
      const detailUrl = apiBase ? `${apiBase}${detailPath}` : detailPath;
      const res = await apiFetch(detailUrl);
      const bodyText = await res.text();

      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}: ${bodyText}`);
      }

      const parsed = JSON.parse(bodyText);
      const steps = Array.isArray(parsed) ? parsed : parsed?.data || [];
      setSelectedTraceSteps(steps as TraceFlowStep[]);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unable to load trace flow.";
      setSelectedTraceError(message);
      setSelectedTraceSteps([]);
    } finally {
      setSelectedTraceLoading(false);
    }
  };

  const closeTraceFlow = () => {
    setSelectedTraceId(null);
    setSelectedTraceSteps([]);
    setSelectedTraceError(null);
    setSelectedTraceLoading(false);
  };

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    const metricsPath = "/custom-api/v1/dashboard/overview/metrics";
    const tracePath = "/custom-api/v1/dashboard/overview/trace-volume";
    const recentPath = "/custom-api/v1/dashboard/overview/recent-traces?limit=10";
    const tokenPath = "/custom-api/v1/dashboard/overview/token-distribution";
    const modelUsagePath = "/custom-api/v1/dashboard/overview/model-usage-share";
    const metricsUrl = apiBase ? `${apiBase}${metricsPath}` : metricsPath;
    const traceUrl = apiBase ? `${apiBase}${tracePath}` : tracePath;
    const recentUrl = apiBase ? `${apiBase}${recentPath}` : recentPath;
    const tokenUrl = apiBase ? `${apiBase}${tokenPath}` : tokenPath;
    const modelUsageUrl = apiBase ? `${apiBase}${modelUsagePath}` : modelUsagePath;

    const fetchJson = async <T,>(url: string): Promise<T> => {
      const res = await apiFetch(url);
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
      fetchJson<ModelUsageShareResponse>(modelUsageUrl),
    ])
      .then(([metricsJson, traceJson, recentJson, tokenJson, modelUsageJson]) => {
        if (!mounted) return;
        setData(metricsJson);
        setTraceVolume(traceJson.data || []);
        setRecentTraces(recentJson.data || []);
        setTokenDistribution(tokenJson.data || []);
        setModelUsageShare(modelUsageJson.data || []);
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

  const fallbackModelUsageRows = [
    { model: "gpt-4o", provider: "openai", llm_calls: 0, total_tokens: 0, total_cost_usd: 0, usage_share_pct: 62 },
    { model: "claude-3-5-sonnet", provider: "anthropic", llm_calls: 0, total_tokens: 0, total_cost_usd: 0, usage_share_pct: 24 },
    { model: "gemini-2.0-flash", provider: "gemini", llm_calls: 0, total_tokens: 0, total_cost_usd: 0, usage_share_pct: 10 },
    { model: "gpt-4o-mini", provider: "openai", llm_calls: 0, total_tokens: 0, total_cost_usd: 0, usage_share_pct: 4 },
  ];

  const modelUsageRows = modelUsageShare.length ? modelUsageShare : fallbackModelUsageRows;

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
  <ResponsiveContainer width="100%" height={320}>
    <AreaChart
      data={chartData.length ? chartData : lineData}
      margin={{
        top: 20,
        right: 25,
        left: 5,
        bottom: 5,
      }}
    >
      <defs>
        <linearGradient id="traceGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor="#2563EB" stopOpacity={0.35} />
          <stop offset="95%" stopColor="#2563EB" stopOpacity={0} />
        </linearGradient>
      </defs>

      <CartesianGrid
        strokeDasharray="4 4"
        stroke="#E5E7EB"
        vertical={false}
      />

      <XAxis
        dataKey="time"
        tick={{
          fill: "#6B7280",
          fontSize: 12,
        }}
        axisLine={false}
        tickLine={false}
      />

      <YAxis
        tick={{
          fill: "#6B7280",
          fontSize: 12,
        }}
        axisLine={false}
        tickLine={false}
      />

      <Tooltip
        cursor={{
          stroke: "#2563EB",
          strokeDasharray: "5 5",
        }}
        contentStyle={{
          borderRadius: "12px",
          border: "none",
          boxShadow: "0 10px 25px rgba(0,0,0,0.12)",
        }}
      />

      <Area
        type="monotone"
        dataKey="traces"
        stroke="none"
        fill="url(#traceGradient)"
      />

      <Line
        type="monotone"
        dataKey="traces"
        stroke="#2563EB"
        strokeWidth={3}
        dot={{
          r: 4,
          fill: "#ffffff",
          stroke: "#2563EB",
          strokeWidth: 3,
        }}
        activeDot={{
          r: 7,
          fill: "#2563EB",
          stroke: "#fff",
          strokeWidth: 3,
        }}
        animationDuration={1200}
      />
    </AreaChart>
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
                 
                  <th>Name</th>
                   <th>Trace ID</th>
                  <th>Status</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
              {(recentTraces.length ? recentTraces : []).map((trace) => (
                <tr key={trace.trace_id} onClick={() => openTraceFlow(trace.trace_id)} style={{ cursor: "pointer" }}>
                  <td>{trace.name}</td>
                  <td className="trace-id trace-id-link" onClick={(event) => { event.stopPropagation(); openTraceFlow(trace.trace_id); }}>
                    {trace.trace_id}
                  </td>
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
                  {tokenPieData.map((_, index) => (
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
            {modelUsageRows.map((item, index) => {
              const pct = item.usage_share_pct ?? 0;
              return (
                <div className="model-row" key={`${item.model}-${index}`}>
                  <div className="model-name">{item.model}</div>
                  <div className="model-bar-wrap">
                    <div className="model-bar" style={{ width: `${Math.max(pct, 4)}%`, background: COLORS[index % COLORS.length] }} />
                  </div>
                  <div className="model-pct">{pct.toFixed(1)}%</div>
                </div>
              );
            })}
          </div>

        </div>
      </div>

      <div className={`trace-detail-backdrop ${selectedTraceId ? "open" : ""}`} onClick={closeTraceFlow} />
      <aside className={`trace-detail-drawer ${selectedTraceId ? "open" : ""}`}>
        <div className="trace-detail-header">
          <div>
            <div className="trace-detail-title">Trace Flow</div>
            <div className="trace-detail-subtitle">{selectedTraceId || "Select a trace"}</div>
          </div>
          <button className="trace-detail-close" onClick={closeTraceFlow} aria-label="Close trace flow">
            ✕
          </button>
        </div>

        <div className="trace-detail-content">
          {selectedTraceLoading ? (
            <div className="trace-detail-state">Loading trace flow...</div>
          ) : selectedTraceError ? (
            <div className="trace-detail-state error">{selectedTraceError}</div>
          ) : selectedTraceSteps.length ? (
            <div className="trace-flow-list">
              {selectedTraceSteps.map((step, index) => (
                <div className="trace-flow-item" key={step.id || `${step.trace_id}-${index}`}>
                  <div className="trace-flow-node">
                    <div className="trace-flow-index">{index + 1}</div>
                    <div className="trace-flow-body">
                      <div className="trace-flow-top">
                        <div className="trace-flow-name">{step.name}</div>
                        <span className={`trace-flow-badge ${step.status}`}>{step.status}</span>
                      </div>
                      <div className="trace-flow-meta">
                        {step.type} • {step.latency_ms} ms • {step.created_at ? new Date(step.created_at).toLocaleString() : "—"}
                      </div>
                      <div className="trace-flow-summary">
                        {step.input?.state && typeof step.input.state === "object" ? (
                          <div>
                            <strong>Input:</strong> {summarizeValue((step.input as Record<string, unknown>).state)}
                          </div>
                        ) : null}
                        {step.output ? (
                          <div>
                            <strong>Output:</strong> {summarizeValue(step.output)}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="trace-detail-state">Select a trace to inspect its flow.</div>
          )}
        </div>
      </aside>

    </div>
  );
};

export default Overview;