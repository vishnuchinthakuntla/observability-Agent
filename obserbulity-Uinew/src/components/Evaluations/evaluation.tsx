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

interface WeeklyMetric {
  metric: string
  value: number
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
  const [decisionRecords, setDecisionRecords] = useState<SummaryRecord[]>([])
  const [rcaWeekly, setRcaWeekly] = useState<WeeklyMetric[]>([])
  const [decisionWeekly, setDecisionWeekly] = useState<WeeklyMetric[]>([])

  const apiBase = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

  useEffect(() => {
    const fetchSummary = async () => {
      setLoading(true)
      setError(null)

      try {
        const base = apiBase || ''
        const rcaSummaryUrl = `${base}/custom-api/v1/rca/summary`
        const decisionSummaryUrl = `${base}/custom-api/v1/decision/summary`
        const rcaWeeklyUrl = `${base}/custom-api/v1/rca/weekly`
        const decisionWeeklyUrl = `${base}/custom-api/v1/decision/weekly`

        const [rcaRes, decisionRes, rcaWeeklyRes, decisionWeeklyRes] = await Promise.all([
          fetch(rcaSummaryUrl),
          fetch(decisionSummaryUrl),
          fetch(rcaWeeklyUrl),
          fetch(decisionWeeklyUrl),
        ])

        if (!rcaRes.ok || !decisionRes.ok || !rcaWeeklyRes.ok || !decisionWeeklyRes.ok) {
          throw new Error('Failed to load evaluation data')
        }

        const rcaJson = await rcaRes.json()
        const decisionJson = await decisionRes.json()
        const rcaWeeklyJson = await rcaWeeklyRes.json()
        const decisionWeeklyJson = await decisionWeeklyRes.json()

        const parseItems = (json: any) => {
          if (Array.isArray(json)) return json
          if (json?.data && Array.isArray(json.data)) return json.data
          if (json?.item) return [json.item]
          if (json?.id) return [json]
          return []
        }

        const parsedRca = parseItems(rcaJson).map(normalizeSummary)
        const parsedDecision = parseItems(decisionJson).map(normalizeSummary)

        const parseWeekly = (json: any): WeeklyMetric[] => {
          const item = Array.isArray(json) ? json[0] : json
          if (!item || typeof item !== 'object') return []

          return [
            { metric: 'Relevancy', value: Number(item.relevancy_avg ?? item.relevancy ?? 0) },
            { metric: 'Safety', value: Number(item.safety_avg ?? item.safety ?? 0) },
            { metric: 'Coherence', value: Number(item.coherence_avg ?? item.coherence ?? 0) },
            { metric: 'Helpfulness', value: Number(item.helpfulness_avg ?? item.helpfulness ?? 0) },
            { metric: 'Toxicity', value: Number(item.toxicity_avg ?? item.toxicity ?? 0) },
          ]
        }

        const sortByDate = (items: SummaryRecord[]) =>
          [...items].sort((a, b) => new Date(a.evaluation_date).getTime() - new Date(b.evaluation_date).getTime())

        setRcaRecords(sortByDate(parsedRca))
        setDecisionRecords(sortByDate(parsedDecision))
        setRcaWeekly(parseWeekly(rcaWeeklyJson))
        setDecisionWeekly(parseWeekly(decisionWeeklyJson))
      } catch (err: any) {
        setError(err.message || 'Unable to load evaluation data')
      } finally {
        setLoading(false)
      }
    }

    fetchSummary()
  }, [apiBase])

  const chartDataRca = useMemo(
    () =>
      rcaRecords.map((record) => ({
        date: new Date(record.evaluation_date).toLocaleDateString(),
        relevancy: Number(record.relevancy_avg.toFixed(2)),
        safety: Number(record.safety_avg.toFixed(2)),
        coherence: Number(record.coherence_avg.toFixed(2)),
        helpfulness: Number(record.helpfulness_avg.toFixed(2)),
        toxicity: Number(record.toxicity_avg.toFixed(2)),
      })),
    [rcaRecords],
  )

  const chartDataDecision = useMemo(
    () =>
      decisionRecords.map((record) => ({
        date: new Date(record.evaluation_date).toLocaleDateString(),
        relevancy: Number(record.relevancy_avg.toFixed(2)),
        safety: Number(record.safety_avg.toFixed(2)),
        coherence: Number(record.coherence_avg.toFixed(2)),
        helpfulness: Number(record.helpfulness_avg.toFixed(2)),
        toxicity: Number(record.toxicity_avg.toFixed(2)),
      })),
    [decisionRecords],
  )

  const rcaWeeklyData = useMemo(
    () => rcaWeekly.map((point) => ({
      metric: point.metric,
      value: Number(point.value.toFixed(2)),
    })),
    [rcaWeekly],
  )

  const decisionWeeklyData = useMemo(
    () => decisionWeekly.map((point) => ({
      metric: point.metric,
      value: Number(point.value.toFixed(2)),
    })),
    [decisionWeekly],
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
          <span>RCA Records</span>
          <h3>{rcaRecords.length}</h3>
        </div>
        <div className="evaluation-card">
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
        </div>
      </div>

      {loading ? (
        <div className="loading">Loading evaluation data…</div>
      ) : error ? (
        <div className="error">{error}</div>
      ) : (
        <div className="charts-grid">
          <div className="chart-panel">
            <div className="chart-title">RCA Evaluation</div>
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={chartDataRca} margin={{ top: 16, right: 24, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} />
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

          <div className="chart-panel">
            <div className="chart-title">Decision Evaluation</div>
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={chartDataDecision} margin={{ top: 16, right: 24, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} />
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
            <div className="chart-title">RCA Weekly Average</div>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={rcaWeeklyData} margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="metric" tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={48} />
                <YAxis domain={[0, 1]} tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip wrapperStyle={{ borderRadius: 12, border: '1px solid #e5e7eb', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)' }} />
                <Bar dataKey="value" fill="#2563eb" radius={[10, 10, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-panel small">
            <div className="chart-title">Decision Weekly Average</div>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={decisionWeeklyData} margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="metric" tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={48} />
                <YAxis domain={[0, 1]} tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip wrapperStyle={{ borderRadius: 12, border: '1px solid #e5e7eb', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)' }} />
                <Bar dataKey="value" fill="#16a34a" radius={[10, 10, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}

export default EvaluationPage
