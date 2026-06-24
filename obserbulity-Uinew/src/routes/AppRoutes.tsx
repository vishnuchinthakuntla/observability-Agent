import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Overview from '../components/Overview/Overview'
import Traces from '../components/Traces/traces'
import Observations from '../components/Observations/observations'
import Sessions from '../components/Sessions/sessions'
import Generations from '../components/Generations/generations'
import Prompts from '../components/Prompts/prompts'
import ToolCalls from '../components/Tool calls/toolcalls'
import Datasets from '../components/Evaluation/datasets'
import Scores from '../components/Evaluation/scores'
import Projects from '../components/Config/projects'
import Users from '../components/Config/users'
import MCPServers from '../components/Infrastructure/mcpservers'
import DriftAlerts from '../components/Infrastructure/driftalerts'
import CircuitBreakers from '../components/Infrastructure/circuitbreakers'
import SettingsPage from '../components/Settings/settings'

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/overview" element={<Overview />} />
      <Route path="/traces" element={<Traces />} />
      <Route path="/observations" element={<Observations />} />
      <Route path="/sessions" element={<Sessions />} />
      <Route path="/generations" element={<Generations />} />
      <Route path="/prompts" element={<Prompts />} />
      <Route path="/tool-calls" element={<ToolCalls />} />
      <Route path="/datasets" element={<Datasets />} />
      <Route path="/scores" element={<Scores />} />
      <Route path="/projects" element={<Projects />} />
      <Route path="/users" element={<Users />} />
      <Route path="/mcp-servers" element={<MCPServers />} />
      <Route path="/drift-alerts" element={<DriftAlerts />} />
      <Route path="/circuit-breakers" element={<CircuitBreakers />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/" element={<Navigate replace to="/overview" />} />
      <Route path="*" element={<Navigate replace to="/overview" />} />
    </Routes>
  )
}

export default AppRoutes
