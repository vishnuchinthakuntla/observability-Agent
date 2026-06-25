import React, { useEffect, useState } from 'react'
import './generations.css'

interface GenerationRecord {
  id: string
  observation_id: string
  project_id: string
  model: string
  provider: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
  finish_reason: string
  created_at: string
  trace_id: string
}

const Generations: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [generations, setGenerations] = useState<GenerationRecord[]>([])
  const [filters, setFilters] = useState({ model: '', provider: '', project: '' })

  const apiBase = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

  useEffect(() => {
    const fetchGenerations = async () => {
      setLoading(true)
      setError(null)

      try {
        const url = apiBase ? `${apiBase}/custom-api/v1/llm-spans` : '/custom-api/v1/llm-spans'
        const response = await fetch(url)

        if (!response.ok) {
          throw new Error('Failed to fetch generations')
        }

        const data = await response.json()
        const items = Array.isArray(data) ? data : data?.data || data?.items || []
        setGenerations(items)
      } catch (err: any) {
        setError(err.message || 'Unable to load generations')
      } finally {
        setLoading(false)
      }
    }

    fetchGenerations()
  }, [apiBase])

  const filteredGenerations = generations.filter((gen) => {
    if (filters.model && !gen.model.toLowerCase().includes(filters.model.toLowerCase())) return false
    if (filters.provider && !gen.provider.toLowerCase().includes(filters.provider.toLowerCase())) return false
    if (filters.project && !gen.project_id.toLowerCase().includes(filters.project.toLowerCase())) return false
    return true
  })

  const stats = {
    totalGenerations: generations.length,
    totalTokens: generations.reduce((sum, g) => sum + g.total_tokens, 0),
    totalCost: generations.reduce((sum, g) => sum + g.cost_usd, 0),
    avgCost: generations.length > 0 ? (generations.reduce((sum, g) => sum + g.cost_usd, 0) / generations.length).toFixed(6) : '0',
  }

  return (
    <div className="generations-page">
      <div className="page-header">
        <div>
          <h2>Generations</h2>
          <p>LLM generation records and token usage analytics</p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Total Generations</span>
          <h3 className="stat-value">{stats.totalGenerations}</h3>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Tokens</span>
          <h3 className="stat-value">{stats.totalTokens.toLocaleString()}</h3>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Cost</span>
          <h3 className="stat-value">${stats.totalCost.toFixed(4)}</h3>
        </div>
        <div className="stat-card">
          <span className="stat-label">Avg Cost</span>
          <h3 className="stat-value">${stats.avgCost}</h3>
        </div>
      </div>

      <div className="filter-section">
        <h3>Filters</h3>
        <div className="filter-row">
          <input
            type="text"
            placeholder="Filter by model..."
            value={filters.model}
            onChange={(e) => setFilters({ ...filters, model: e.target.value })}
            className="filter-input"
          />
          <input
            type="text"
            placeholder="Filter by provider..."
            value={filters.provider}
            onChange={(e) => setFilters({ ...filters, provider: e.target.value })}
            className="filter-input"
          />
          <input
            type="text"
            placeholder="Filter by project..."
            value={filters.project}
            onChange={(e) => setFilters({ ...filters, project: e.target.value })}
            className="filter-input"
          />
        </div>
      </div>

      {loading ? (
        <div className="loading">Loading generations…</div>
      ) : error ? (
        <div className="error">{error}</div>
      ) : (
        <div className="generations-container">
          <div className="table-wrapper">
            <table className="generations-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Provider</th>
                  <th>Project</th>
                  <th>Prompt Tokens</th>
                  <th>Completion Tokens</th>
                  <th>Total Tokens</th>
                  <th>Cost (USD)</th>
                  <th>Status</th>
                  <th>Created At</th>
                </tr>
              </thead>
              <tbody>
                {filteredGenerations.length > 0 ? (
                  filteredGenerations.map((gen) => (
                    <tr key={gen.id}>
                      <td className="model-cell">{gen.model}</td>
                      <td className="provider-cell">
                        <span className={`provider-badge ${gen.provider}`}>{gen.provider}</span>
                      </td>
                      <td className="project-cell">{gen.project_id}</td>
                      <td className="tokens-cell">{gen.prompt_tokens.toLocaleString()}</td>
                      <td className="tokens-cell">{gen.completion_tokens.toLocaleString()}</td>
                      <td className="tokens-cell highlight">{gen.total_tokens.toLocaleString()}</td>
                      <td className="cost-cell">${gen.cost_usd.toFixed(6)}</td>
                      <td className="status-cell">
                        <span className="status-badge finish-success">{gen.finish_reason}</span>
                      </td>
                      <td className="date-cell">{new Date(gen.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9} className="empty-state">
                      No generations found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export default Generations
