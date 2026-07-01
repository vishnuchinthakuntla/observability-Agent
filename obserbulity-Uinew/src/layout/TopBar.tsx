import React from 'react'
import './dashboard.css'

const TopBar: React.FC = () => {
  return (
    <div className="topbar">
      <div className="breadcrumb">
        <span className="breadcrumb-org">acme-production</span>
        <span className="breadcrumb-sep">/</span>
        <span className="breadcrumb-page">Overview</span>
      </div>
      <div className="topbar-spacer" />

      {/* <select className="project-select">
        <option>acme-production</option>
        <option>acme-staging</option>
        <option>demo-project</option>
      </select> */}

      {/* <div className="time-filter">
        <button className="time-btn">1h</button>
        <button className="time-btn active">24h</button>
        <button className="time-btn">7d</button>
        <button className="time-btn">30d</button>
      </div>

      <div className="topbar-sep" />

      <div className="live-indicator">
        <div className="pulse-ring" /> LIVE
      </div>

      <button className="topbar-btn">⬇ Export</button>
      <button className="topbar-btn primary">+ New alert</button> */}
    </div>
  )
}

export default TopBar
