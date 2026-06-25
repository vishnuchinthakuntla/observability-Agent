import React from "react";
import './Traces.css'

interface Observation {
  id: string;
  name: string;
  type: string;
  status: string;
  latency_ms: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  trace: any;
}

const TraceDrawer: React.FC<Props> = ({
  open,
  onClose,
  trace,
}) => {
  if (!open || !trace) return null;

  return (
    <div
      className="drawer-overlay"
      onClick={onClose}
    >
      <div
        className="trace-drawer"
        onClick={(e) =>
          e.stopPropagation()
        }
      >
        {/* Header */}
        <div className="drawer-header">
          <div>
            <h3>{trace.name}</h3>
          </div>

          <button onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Trace Summary */}
        <div className="trace-meta">
          <div className="meta-card">
            <div className="meta-label">
              Trace ID
            </div>

            <div className="meta-value">
              {trace.trace_id?.slice(
                0,
                12
              )}
              ...
            </div>
          </div>

          <div className="meta-card">
            <div className="meta-label">
              Status
            </div>

            <div
              className={
                trace.status ===
                "success"
                  ? "status-success"
                  : "status-failed"
              }
            >
              {trace.status}
            </div>
          </div>

          <div className="meta-card">
            <div className="meta-label">
              Tokens
            </div>

            <div className="meta-value">
              {trace.total_tokens?.toLocaleString()}
            </div>
          </div>

          <div className="meta-card">
            <div className="meta-label">
              Cost
            </div>

            <div className="meta-value">
              $
              {trace.total_cost_usd?.toFixed(
                5
              )}
            </div>
          </div>

          <div className="meta-card">
            <div className="meta-label">
              Latency
            </div>

            <div className="meta-value">
              {trace.total_latency_ms}
              ms
            </div>
          </div>

          <div className="meta-card">
            <div className="meta-label">
              Project
            </div>

            <div className="meta-value">
              {trace.project_id}
            </div>
          </div>
        </div>

        {/* Observation Flow */}
        <div className="flow-section">
          <div className="flow-title">
            Observation Flow
          </div>

          {trace.observations &&
          trace.observations.length >
            0 ? (
            trace.observations.map(
              (
                obs: Observation,
                index: number
              ) => (
                <div
                  className="flow-node"
                  key={obs.id}
                >
                  <div className="circle">
                    {index + 1}
                  </div>

                  <div className="node-content">
                    <div className="node-name">
                      {obs.name}
                    </div>

                    <div className="node-meta">
                      <span
                        className={`badge ${obs.type.toLowerCase()}`}
                      >
                        {obs.type}
                      </span>

                      <span className="latency">
                        {obs.latency_ms} ms
                      </span>

                      <span
                        className={
                          obs.status ===
                          "success"
                            ? "status-success"
                            : "status-failed"
                        }
                      >
                        {obs.status}
                      </span>
                    </div>
                  </div>
                </div>
              )
            )
          ) : (
            <div
              style={{
                textAlign: "center",
                padding: "30px",
                color: "#64748b",
              }}
            >
              No observations found
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TraceDrawer;