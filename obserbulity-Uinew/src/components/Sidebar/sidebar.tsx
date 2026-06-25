import "../../layout/dashboard.css";
import { NavLink } from 'react-router-dom'
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

const Sidebar = () => {
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
        <div className="avatar">AK</div>
        <div className="user-info">
          <div className="user-name">Arjun Kumar</div>
          <div className="user-org">acme-prod · admin</div>
        </div>
        <button className="logout-btn" title="Logout">
          <LogOut size={18} />
        </button>
      </div>
    </nav>
  );
};

export default Sidebar;
