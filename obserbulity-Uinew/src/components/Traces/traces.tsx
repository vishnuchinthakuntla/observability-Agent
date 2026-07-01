import React, { useEffect, useState } from 'react'
import './Traces.css'
import TraceDrawer from './TraceDrawer'
import { apiFetch } from '../../utils/apiClient'

interface Observation {
  id: string
  name: string
  type: string
  status: string
  latency_ms: number
}

interface Trace {
  trace_id: string
  project_id: string
  name: string
  status: string
  total_tokens: number
  total_cost_usd: number
  total_latency_ms: number
  created_at: string
  observations?: Observation[]
}

const Traces: React.FC = () => {
  const [traces, setTraces] = useState<Trace[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    let mounted = true

    const fetchTraces = async () => {
      try {
        setLoading(true)

        const apiBase = String(
          import.meta.env.VITE_API_BASE || ''
        ).replace(/\/+$/, '')

        const tracesPath = '/custom-api/v1/traces'

        const tracesUrl = apiBase
          ? `${apiBase}${tracesPath}`
          : tracesPath

        console.log('Fetching Traces:', tracesUrl)

        const res = await apiFetch(tracesUrl)

        const contentType =
          res.headers.get('content-type') || ''

        const bodyText = await res.text()

        if (!res.ok) {
          throw new Error(
            `${res.status} ${res.statusText}: ${bodyText}`
          )
        }

        if (!contentType.includes('application/json')) {
          throw new Error(
            `Expected JSON but received ${contentType}`
          )
        }

        const parsed = JSON.parse(bodyText)

        if (mounted) {
          setTraces(parsed.data || [])
        }
      } catch (err) {
        console.error('Error fetching traces:', err)

        if (mounted) {
          setTraces([])
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    fetchTraces()

    return () => {
      mounted = false
    }
  }, [])

  const filteredTraces = traces.filter(
    (trace) =>
      trace.name?.toLowerCase().includes(search.toLowerCase()) ||
      trace.project_id?.toLowerCase().includes(search.toLowerCase())
  )

  const totalTraces = traces.length
  const successTraces = traces.filter(
    (t) => t.status === 'success'
  ).length

  const totalTokens = traces.reduce(
    (sum, t) => sum + (t.total_tokens || 0),
    0
  )

  const totalCost = traces.reduce(
    (sum, t) => sum + (t.total_cost_usd || 0),
    0
  )

  return (
    <div className="traces-page">
      <div className="page-header">
        <h2>Traces</h2>
        <p>Monitor and analyze AI application traces</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span>Total Traces</span>
          <h3>{totalTraces}</h3>
        </div>

        <div className="stat-card">
          <span>Success Traces</span>
          <h3>{successTraces}</h3>
        </div>

        <div className="stat-card">
          <span>Total Tokens</span>
          <h3>{totalTokens.toLocaleString()}</h3>
        </div>

        <div className="stat-card">
          <span>Total Cost</span>
          <h3>${totalCost.toFixed(4)}</h3>
        </div>
      </div>

      <div className="toolbar">
        <input
          type="text"
          placeholder="Search traces..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="table-container">
        {loading ? (
          <div className="loading">Loading traces...</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Trace Name</th>
                <th>Project</th>
                <th>Status</th>
                <th>Tokens</th>
                <th>Cost</th>
                <th>Latency</th>
                <th>Created</th>
              </tr>
            </thead>

            <tbody>
              {filteredTraces.map((trace) => (
                <tr
                  key={trace.trace_id}
                  onClick={() => {
                    setSelectedTrace(trace)
                    setDrawerOpen(true)
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{trace.name}</td>
                  <td>{trace.project_id}</td>

                  <td>
                    <span
                      className={`status-badge ${trace.status}`}
                    >
                      {trace.status}
                    </span>
                  </td>

                  <td>{trace.total_tokens}</td>

                  <td>
                    ${trace.total_cost_usd?.toFixed(4)}
                  </td>

                  <td>
                    {trace.total_latency_ms} ms
                  </td>

                  <td>
                    {new Date(
                      trace.created_at
                    ).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <TraceDrawer
  open={drawerOpen}
  onClose={() => setDrawerOpen(false)}
  trace={selectedTrace}
/>
    </div>
    
  )
}

export default Traces