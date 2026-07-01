import React, { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer,
  LineChart,
  BarChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts'
import './evaluation.css'

interface SummaryRecord {
  id: string
  evaluation_date: string
  relevancy_avg: number
  safety_avg: number
  coherence_avg: number
  helpfulness_avg: number
  toxicity_avg: number
  created_at: string
}

interface WeeklyRecord {
  week_start: string
  week_end: string
  week_label: string
  relevancy_avg: number
  safety_avg: number
  coherence_avg: number
  helpfulness_avg: number
  toxicity_avg: number
  overall_score: number
  total_evaluated: number
  days_in_week: number
}

const normalizeSummary = (item: any): SummaryRecord => ({
  id: item.id || item._id || String(Math.random()),
  evaluation_date: item.evaluation_date || item.created_at || new Date().toISOString(),
  relevancy_avg: Number(item.relevancy_avg ?? item.relevancy ?? 0),
  safety_avg: Number(item.safety_avg ?? item.safety ?? 0),
  coherence_avg: Number(item.coherence_avg ?? item.coherence ?? 0),
  helpfulness_avg: Number(item.helpfulness_avg ?? item.helpfulness ?? 0),
  toxicity_avg: Number(item.toxicity_avg ?? item.toxicity ?? 0),
  created_at: item.created_at || item.evaluation_date || new Date().toISOString(),
})

const EvaluationPage: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rcaRecords, setRcaRecords] = useState<SummaryRecord[]>([])
  const [rcaWeekly, setRcaWeekly] = useState<WeeklyRecord[]>([])
  const [rcaTotalRecords, setRcaTotalRecords] = useState(0)
  const [rcaWeeklyTotalRecords, setRcaWeeklyTotalRecords] = useState(0)
  const [agentName, setAgentName] = useState('rca_agent')
  const [projectId, setProjectId] = useState('GCP')
  const [days, setDays] = useState(30)
  const [weeks, setWeeks] = useState(4)

  const apiBase = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

  useEffect(() => {
    const fetchSummary = async () => {
      setLoading(true)
      setError(null)

      try {
        const base = apiBase || ''

       const rcaSummaryUrl =
  `${base}/custom-api/v1/api/evaluation/${encodeURIComponent(agentName)}/daily?project_id=${encodeURIComponent(projectId)}&days=${days}`

const rcaWeeklyUrl =
  `${base}/custom-api/v1/api/evaluation/${encodeURIComponent(agentName)}/weekly?project_id=${encodeURIComponent(projectId)}&weeks=${weeks}`

      const fetchJson = async <T,>(url: string): Promise<T> => {
  const res = await fetch(url);

  console.log("URL:", url);
  console.log("Status:", res.status);
  console.log("Content-Type:", res.headers.get("content-type"));

  const bodyText = await res.text(); // Read the response ONLY ONCE

  console.log("Response:", bodyText);

  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}: ${bodyText.slice(0, 300)}`);
  }

  const contentType = res.headers.get("content-type") || "";

  if (!contentType.includes("application/json")) {
    throw new Error(
      `Expected JSON response but received ${contentType}. Response body: ${bodyText.slice(0, 300)}`
    );
  }

  return JSON.parse(bodyText) as T;
};

          const [rcaJson, rcaWeeklyJson] = await Promise.all([
            fetchJson<any>(rcaSummaryUrl),
            fetchJson<any>(rcaWeeklyUrl),
          ])

        const rcaTotal = Number(rcaJson.total_records ?? (Array.isArray(rcaJson?.data) ? rcaJson.data.length : 0))
        const rcaWeeklyTotal = Number(rcaWeeklyJson.total_records ?? (Array.isArray(rcaWeeklyJson?.data) ? rcaWeeklyJson.data.length : 0))

        const parseItems = (json: any) => {
          if (Array.isArray(json)) return json
          if (json?.data && Array.isArray(json.data)) return json.data
          if (json?.item) return [json.item]
          if (json?.id) return [json]
          return []
        }

        const parsedRca = parseItems(rcaJson).map(normalizeSummary)

        const parseWeeklyRecords = (json: any): WeeklyRecord[] => {
          const items = Array.isArray(json) ? json : json?.data ?? []
          if (!Array.isArray(items)) return []

          return items.map((item: any) => ({
            week_start: item.week_start || item.start_date || '',
            week_end: item.week_end || item.end_date || '',
            week_label:
              item.week_start && item.week_end
                ? `${item.week_start} - ${item.week_end}`
                : item.week_start || item.week_end || 'Week',
            relevancy_avg: Number(item.relevancy_avg ?? item.relevancy ?? 0),
            safety_avg: Number(item.safety_avg ?? item.safety ?? 0),
            coherence_avg: Number(item.coherence_avg ?? item.coherence ?? 0),
            helpfulness_avg: Number(item.helpfulness_avg ?? item.helpfulness ?? 0),
            toxicity_avg: Number(item.toxicity_avg ?? item.toxicity ?? 0),
            overall_score: Number(item.overall_score ?? item.score ?? 0),
            total_evaluated: Number(item.total_evaluated ?? item.count ?? 0),
            days_in_week: Number(item.days_in_week ?? item.days ?? 0),
          }))
        }

        const sortByDate = (items: SummaryRecord[]) =>
          [...items].sort((a, b) => new Date(a.evaluation_date).getTime() - new Date(b.evaluation_date).getTime())

        setRcaRecords(sortByDate(parsedRca))
        setRcaWeekly(parseWeeklyRecords(rcaWeeklyJson))
        setRcaTotalRecords(rcaTotal)
        setRcaWeeklyTotalRecords(rcaWeeklyTotal)
      } catch (err: any) {
        setError(err.message || 'Unable to load evaluation data')
      } finally {
        setLoading(false)
      }
    }

    fetchSummary()
  }, [apiBase, agentName, projectId, days, weeks])

  const chartDataRca = useMemo(
    () =>
      rcaRecords.map((record) => ({
        date: record.evaluation_date,
        label: new Date(record.evaluation_date).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
        }),
        relevancy: Number(record.relevancy_avg.toFixed(2)),
        safety: Number(record.safety_avg.toFixed(2)),
        coherence: Number(record.coherence_avg.toFixed(2)),
        helpfulness: Number(record.helpfulness_avg.toFixed(2)),
        toxicity: Number(record.toxicity_avg.toFixed(2)),
      })),
    [rcaRecords],
  )

  const rcaWeeklyData = useMemo(
    () =>
      rcaWeekly.map((point) => ({
        week: point.week_label,
        relevancy: Number(point.relevancy_avg.toFixed(2)),
        safety: Number(point.safety_avg.toFixed(2)),
        coherence: Number(point.coherence_avg.toFixed(2)),
        helpfulness: Number(point.helpfulness_avg.toFixed(2)),
        overall_score: Number(point.overall_score.toFixed(2)),
      })),
    [rcaWeekly],
  )

  return (
    <div className="evaluation-page">
      <div className="evaluation-header">
        <div>
          <h2>Evaluation Summary</h2>
          <p>Separate trend views for RCA and Decision evaluation metrics.</p>
        </div>
      </div>

      <div className="evaluation-cards">
        <div className="evaluation-card">
          <span>RCA Daily Total</span>
          <h3>{rcaTotalRecords}</h3>
        </div>
        <div className="evaluation-card">
          <span>RCA Weekly Total</span>
          <h3>{rcaWeeklyTotalRecords}</h3>
        </div>
        {/* <div className="evaluation-card">
          <span>Decision Records</span>
          <h3>{decisionRecords.length}</h3>
        </div>
        <div className="evaluation-card">
          <span>Latest RCA Relevancy</span>
          <h3>{rcaRecords.length ? rcaRecords[rcaRecords.length - 1].relevancy_avg.toFixed(2) : '—'}</h3>
        </div>
        <div className="evaluation-card">
          <span>Latest Decision Relevancy</span>
          <h3>{decisionRecords.length ? decisionRecords[decisionRecords.length - 1].relevancy_avg.toFixed(2) : '—'}</h3>
        </div> */}
      </div>

      {loading ? (
        <div className="loading">Loading evaluation data…</div>
      ) : error ? (
        <div className="error">{error}</div>
      ) : (
        <>
          <div className="filter-card">
            <div className="filter-row">
              <label>
                Agent Name
                <input
                  type="text"
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                  placeholder="rca_agent"
                />
              </label>
              <label>
                Project ID
                <input
                  type="text"
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  placeholder="GCP"
                />
              </label>
              <label>
                Days
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value) || 1)}
                />
              </label>
              <label>
                Weeks
                <input
                  type="number"
                  min={1}
                  max={52}
                  value={weeks}
                  onChange={(e) => setWeeks(Number(e.target.value) || 1)}
                />
              </label>
            </div>
          </div>

          <div className="charts-grid">
          <div className="chart-panel">
            <div className="chart-title">Daily Evaluation Trend</div>
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={chartDataRca} margin={{ top: 16, right: 24, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e5e7eb" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value) =>
                    new Date(value).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    })
                  }
                  interval={0}
                  allowDuplicatedCategory
                  tick={{ fill: '#475569', fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis domain={[0, 1]} tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip wrapperStyle={{ borderRadius: 12, border: '1px solid #e5e7eb', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)' }} />
                <ReferenceLine y={0.5} stroke="#cbd5e1" strokeDasharray="5 5" />
                <Legend verticalAlign="top" height={28} iconType="circle" />
                <Line type="monotone" dataKey="relevancy" name="Relevancy" stroke="#2563eb" strokeWidth={3} dot={{ r: 4, stroke: '#2563eb', fill: '#2563eb' }} activeDot={{ r: 6, strokeWidth: 2, stroke: '#2563eb', fill: '#fff' }} />
                <Line type="monotone" dataKey="safety" name="Safety" stroke="#16a34a" strokeWidth={3} dot={{ r: 4, stroke: '#16a34a', fill: '#16a34a' }} activeDot={{ r: 6, strokeWidth: 2, stroke: '#16a34a', fill: '#fff' }} />
                <Line type="monotone" dataKey="coherence" name="Coherence" stroke="#7c3aed" strokeWidth={3} dot={{ r: 4, stroke: '#7c3aed', fill: '#7c3aed' }} activeDot={{ r: 6, strokeWidth: 2, stroke: '#7c3aed', fill: '#fff' }} />
                <Line type="monotone" dataKey="helpfulness" name="Helpfulness" stroke="#f97316" strokeWidth={3} dot={{ r: 4, stroke: '#f97316', fill: '#f97316' }} activeDot={{ r: 6, strokeWidth: 2, stroke: '#f97316', fill: '#fff' }} />
                <Line type="monotone" dataKey="toxicity" name="Toxicity" stroke="#ef4444" strokeWidth={3} dot={{ r: 4, stroke: '#ef4444', fill: '#ef4444' }} activeDot={{ r: 6, strokeWidth: 2, stroke: '#ef4444', fill: '#fff' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-panel small">
            <div className="chart-title">Weekly Evaluation</div>
            <ResponsiveContainer width="100%" height={360}>
              <BarChart data={rcaWeeklyData} margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="week" tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={48} />
                <YAxis domain={[0, 1]} tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip wrapperStyle={{ borderRadius: 12, border: '1px solid #e5e7eb', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)' }} />
                <Legend verticalAlign="top" height={28} iconType="circle" />
                <Bar dataKey="relevancy" name="Relevancy" fill="#2563eb" radius={[10, 10, 0, 0]} />
                <Bar dataKey="safety" name="Safety" fill="#16a34a" radius={[10, 10, 0, 0]} />
                <Bar dataKey="coherence" name="Coherence" fill="#7c3aed" radius={[10, 10, 0, 0]} />
                <Bar dataKey="helpfulness" name="Helpfulness" fill="#f97316" radius={[10, 10, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </>
      )}
    </div>
  )
}

export default EvaluationPage
