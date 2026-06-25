import "../../layout/dashboard.css";
import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Zap,
  Eye,
  Clock,
  Wand2,
  Wrench,
  MessageSquare,
  Database,
  Award,
  Server,
  AlertTriangle,
  ShieldAlert,
  FolderOpen,
  Users,
  Settings,
  LogOut,
} from "lucide-react";

const decodeJwtPayload = (token: string) => {
  try {
    const base64Url = token.split('.')[1]
    if (!base64Url) return null
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => `%${(`00${c.charCodeAt(0).toString(16)}`).slice(-2)}`)
        .join(''),
    )
    return JSON.parse(jsonPayload)
  } catch {
    return null
  }
}

const Sidebar = () => {
  const [userName, setUserName] = useState('User')
  const [userRole, setUserRole] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    const token = localStorage.getItem('authToken')
    if (!token) return

    const payload = decodeJwtPayload(token)
    if (!payload) return

    const name = payload.username || payload.name || payload.sub || payload.user || 'User'
    const role = payload.role || payload.roles || payload.user_role || ''

    setUserName(name)
    if (typeof role === 'string') {
      setUserRole(role)
    } else if (Array.isArray(role) && role.length > 0) {
      setUserRole(role[0])
    }
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('authToken')
    window.location.href = '/'
  }

  return (
    <nav className="sidebar">
      <div className="logo">
        <div className="logo-mark">SH</div>
        <div>
          <div className="logo-text">SystemHealth</div>
          <div className="logo-sub">Observability Platform</div>
        </div>
      </div>

      <div className="nav">
        <div className="nav-section">
          <div className="nav-label">Core</div>
          <NavLink to="/overview" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <LayoutDashboard size={18} className="icon icon-blue" />
            Overview
          </NavLink>
          <NavLink to="/traces" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Zap size={18} className="icon icon-amber" />
            Traces
          </NavLink>
          <NavLink to="/observations" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Eye size={18} className="icon icon-purple" />
            Observations
          </NavLink>
          <NavLink to="/evaluations" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Eye size={18} className="icon icon-purple" />
            Evaluations
          </NavLink>
          <NavLink to="/sessions" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Clock size={18} className="icon icon-green" />
            Sessions
          </NavLink>
        </div>

        <div className="nav-section">
          <div className="nav-label">LLM</div>
          <NavLink to="/generations" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Wand2 size={18} className="icon icon-purple" />
            Generations
          </NavLink>
          <NavLink to="/tool-calls" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Wrench size={18} className="icon icon-amber" />
            Tool Calls
          </NavLink>
          <NavLink to="/prompts" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <MessageSquare size={18} className="icon icon-blue" />
            Prompts
          </NavLink>
        </div>

        <div className="nav-section">
          <div className="nav-label">Evaluation</div>
          <NavLink to="/datasets" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Database size={18} className="icon icon-blue" />
            Datasets
          </NavLink>
          <NavLink to="/scores" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Award size={18} className="icon icon-green" />
            Scores
          </NavLink>
        </div>

        <div className="nav-section">
          <div className="nav-label">Infrastructure</div>
          <NavLink to="/mcp-servers" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Server size={18} className="icon icon-green" />
            MCP Servers
          </NavLink>
          <NavLink to="/drift-alerts" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <AlertTriangle size={18} className="icon icon-red" />
            Drift Alerts <span className="nav-badge">3</span>
          </NavLink>
          <NavLink to="/circuit-breakers" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <ShieldAlert size={18} className="icon icon-amber" />
            Circuit Breakers <span className="nav-badge amber">1</span>
          </NavLink>
        </div>

        <div className="nav-section">
          <div className="nav-label">Config</div>
          <NavLink to="/projects" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <FolderOpen size={18} className="icon icon-amber" />
            Projects
          </NavLink>
          <NavLink to="/users" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Users size={18} className="icon icon-purple" />
            Users
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <Settings size={18} className="icon icon-blue" />
            Settings
          </NavLink>
        </div>
      </div>

      <div className="sidebar-footer">
        <div className="avatar">{userName.charAt(0).toUpperCase() || 'U'}</div>
        <div className="user-info">
          <div className="user-name">{userName}</div>
          {userRole && <div className="user-org">{userRole}</div>}
        </div>
        <button className="logout-btn" title="Logout" onClick={handleLogout}>
          <LogOut size={18} />
        </button>
      </div>
    </nav>
  );
};

export default Sidebar;
