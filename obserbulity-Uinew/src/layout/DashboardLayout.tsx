import React from 'react'
import './dashboard.css'

interface Props {
  children?: React.ReactNode
}

const DashboardLayout: React.FC<Props> = ({ children }) => {
  return (
    <div className="dashboard-shell">
      {children}
    </div>
  )
}

export default DashboardLayout
