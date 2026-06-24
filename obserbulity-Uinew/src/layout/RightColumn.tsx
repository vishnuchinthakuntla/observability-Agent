import React from 'react'
import './dashboard.css'

const RightColumn: React.FC<{children?: React.ReactNode}> = ({ children }) => {
  return (
    <aside className="right-column">
      {children}
    </aside>
  )
}

export default RightColumn
