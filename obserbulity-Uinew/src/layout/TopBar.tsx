import React from 'react'
import './dashboard.css'

const TopBar: React.FC = () => {
  return (
    <div className="topbar">
      {/* Left */}
      <div className="breadcrumb">
        {/* <span className="breadcrumb-org">acme-production</span>
        <span className="breadcrumb-sep">/</span> */}
        <span className="breadcrumb-page">Overview</span>
      </div>

      {/* Center */}
     <div className="topbar-title">
  <span className="topbar-main-title">SystemHealth</span>
  <span className="topbar-divider">|</span>
  <span className="topbar-sub-title">Observability Platform</span>
</div>

      {/* Right */}
      <div className="topbar-spacer" />
    </div>
  )
}

export default TopBar