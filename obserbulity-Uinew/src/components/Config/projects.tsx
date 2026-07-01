import React, { useEffect, useState } from 'react'
import { apiFetch } from '../../utils/apiClient'

type Project = {
  id: string
  name: string
  description?: string
  is_active?: boolean
  created_at?: string
}

const Projects: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Project | null>(null)
  const [editing, setEditing] = useState<Project | null>(null)

  const apiBase = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')
  const adminKey = String(import.meta.env.VITE_ADMIN_KEY || '').trim()

  const fetchProjects = async () => {
    try {
      setLoading(true)
      setError(null)
      const url = apiBase ? `${apiBase}/api/v1/admin/projects/list` : '/api/v1/admin/projects/list'
      console.log('Fetching projects:', url)
      const headers: Record<string, string> = {}
      if (adminKey) headers['x-admin-key'] = adminKey
      const res = await apiFetch(url, { headers })
      const ct = res.headers.get('content-type') || ''
      const body = await res.text()
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${body.slice(0,300)}`)
      if (!ct.includes('application/json')) throw new Error(`Expected JSON response but received ${ct || 'unknown'}. Response body: ${body.slice(0,300)}`)
      const json = JSON.parse(body)
      const list: Project[] = Array.isArray(json.projects) ? json.projects : json.data ?? []
      setProjects(list)
    } catch (err: any) {
      console.error(err)
      setError(err?.message || String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjects() }, [])

  const viewProject = (p: Project) => setSelected(p)

  const closeView = () => setSelected(null)

  const startEdit = (p: Project) => setEditing(p)

  const closeEdit = () => setEditing(null)

  const saveEdit = async (updated: Project) => {
    try {
      const url = apiBase ? `${apiBase}/api/v1/admin/projects/${encodeURIComponent(updated.id)}` : `/api/v1/admin/projects/${encodeURIComponent(updated.id)}`
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (adminKey) headers['x-admin-key'] = adminKey
      const res = await apiFetch(url, { method: 'PUT', headers, body: JSON.stringify(updated) })
      const text = await res.text()
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${text.slice(0,300)}`)
      closeEdit()
      fetchProjects()
    } catch (err: any) {
      alert('Update failed: ' + (err?.message || String(err)))
    }
  }

  const deleteProject = async (p: Project) => {
    if (!confirm(`Delete project "${p.name}"? This cannot be undone.`)) return
    try {
      const url = apiBase ? `${apiBase}/api/v1/admin/projects/${encodeURIComponent(p.id)}` : `/api/v1/admin/projects/${encodeURIComponent(p.id)}`
      const headers: Record<string, string> = {}
      if (adminKey) headers['x-admin-key'] = adminKey
      const res = await apiFetch(url, { method: 'DELETE', headers })
      const text = await res.text()
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${text.slice(0,300)}`)
      fetchProjects()
    } catch (err: any) {
      alert('Delete failed: ' + (err?.message || String(err)))
    }
  }

  return (
    <div className="page-shell">
      <h1>Projects</h1>

      {loading && <div>Loading projects…</div>}
      {error && <div style={{ color: 'red' }}>{error}</div>}

      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: 8 }}>Name</th>
            <th style={{ textAlign: 'left', padding: 8 }}>Description</th>
            <th style={{ textAlign: 'left', padding: 8 }}>Active</th>
            <th style={{ textAlign: 'left', padding: 8 }}>Created</th>
            <th style={{ textAlign: 'left', padding: 8 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((p) => (
            <tr key={p.id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: 8 }}>{p.name}</td>
              <td style={{ padding: 8 }}>{p.description || '-'}</td>
              <td style={{ padding: 8 }}>{p.is_active ? 'Yes' : 'No'}</td>
              <td style={{ padding: 8 }}>{p.created_at ? new Date(p.created_at).toLocaleString() : '-'}</td>
              <td style={{ padding: 8 }}>
                <button onClick={() => viewProject(p)} style={{ marginRight: 8 }}>View</button>
                <button onClick={() => startEdit(p)} style={{ marginRight: 8 }}>Update</button>
                <button onClick={() => deleteProject(p)} style={{ color: 'crimson' }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && (
        <div style={{ position: 'fixed', right: 20, top: 80, width: 420, background: '#fff', boxShadow: '0 8px 32px rgba(0,0,0,0.12)', padding: 16, zIndex: 1200 }}>
          <h3>Project: {selected.name}</h3>
          <div><strong>ID:</strong> {selected.id}</div>
          <div><strong>Description:</strong> {selected.description || '-'}</div>
          <div><strong>Active:</strong> {selected.is_active ? 'Yes' : 'No'}</div>
          <div style={{ marginTop: 12 }}>
            <button onClick={() => { startEdit(selected); closeView(); }} style={{ marginRight: 8 }}>Edit</button>
            <button onClick={closeView}>Close</button>
          </div>
        </div>
      )}

      {editing && (
        <EditModal project={editing} onClose={closeEdit} onSave={saveEdit} />
      )}
    </div>
  )
}

const EditModal: React.FC<{ project: Project; onClose: () => void; onSave: (p: Project) => void }> = ({ project, onClose, onSave }) => {
  const [form, setForm] = useState<Project>(project)
  return (
    <div style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1300 }}>
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.35)' }} onClick={onClose} />
      <div style={{ background: '#fff', padding: 16, width: 560, borderRadius: 8, boxShadow: '0 8px 40px rgba(0,0,0,0.16)', zIndex: 1400 }}>
        <h3>Edit Project</h3>
        <label style={{ display: 'block', marginBottom: 8 }}>
          Name
          <input style={{ width: '100%' }} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label style={{ display: 'block', marginBottom: 8 }}>
          Description
          <input style={{ width: '100%' }} value={form.description || ''} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </label>
        <label style={{ display: 'block', marginBottom: 8 }}>
          Active
          <input type="checkbox" checked={!!form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
        </label>
        <div style={{ marginTop: 12 }}>
          <button onClick={() => onSave(form)} style={{ marginRight: 8 }}>Save</button>
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default Projects
