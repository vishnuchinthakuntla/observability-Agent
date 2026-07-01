import { useEffect, useMemo, useState } from "react";
import "./observations.css";

interface Observation {
  id: string;
  trace_id: string;
  trace_name: string;
  project_id: string;
  name: string;
  type: string;
  status: string;
  latency_ms: number;
  model?: string;
  provider?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  created_at: string;
  input?: any;
  output?: any;
}

const Observations = () => {
  const [loading, setLoading] = useState(true);

  const [observations, setObservations] = useState<
    Observation[]
  >([]);

  // Filters

  const [search, setSearch] = useState("");

  const [traceId, setTraceId] = useState("");

  const [agentName, setAgentName] =
    useState("");

  const [obsType, setObsType] =
    useState("");

  const [status, setStatus] =
    useState("");

  const [dateRange, setDateRange] = useState("");

  const [fromTime, setFromTime] =
    useState("");

  const [toTime, setToTime] =
    useState("");

  // API

  const fetchObservations = async () => {
    try {
      setLoading(true);

      const apiBase = String(
        import.meta.env.VITE_API_BASE || ""
      ).replace(/\/+$/, "");

      const params =
        new URLSearchParams();

      if (traceId)
        params.append("trace_id", traceId);

      if (agentName)
        params.append(
          "agent_name",
          agentName
        );

      if (dateRange)
        params.append("date_range", dateRange);

      if (obsType)
        params.append("obs_type", obsType);

      if (status)
        params.append("status", status);

      if (fromTime)
        params.append(
          "from_time",
          fromTime
        );

      if (toTime)
        params.append("to_time", toTime);

      params.append("page", "1");
      params.append("page_size", "100");

      const url = apiBase ? `${apiBase}/custom-api/v1/observations?${params.toString()}` : `/custom-api/v1/observations?${params.toString()}`;

      console.log("Fetching observations:", url);

      const res = await fetch(url);
      const contentType = res.headers.get("content-type") || "";
      const bodyText = await res.text();

      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}: ${bodyText.slice(0, 300)}`);
      }

      if (!contentType.includes("application/json")) {
        throw new Error(`Expected JSON response but received ${contentType || "unknown"}. Response body: ${bodyText.slice(0, 300)}`);
      }

      const json = JSON.parse(bodyText);
      setObservations(json.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchObservations();
  }, []);

  const filteredData = useMemo(() => {
    return observations.filter((item) => {
      return (
        item.name
          ?.toLowerCase()
          .includes(search.toLowerCase()) ||
        item.trace_name
          ?.toLowerCase()
          .includes(search.toLowerCase()) ||
        item.project_id
          ?.toLowerCase()
          .includes(search.toLowerCase())
      );
    });
  }, [observations, search]);

  const totalObservations =
    observations.length;

  const llmCount =
    observations.filter(
      (x) => x.type === "LLM"
    ).length;

  const chainCount =
    observations.filter(
      (x) => x.type === "CHAIN"
    ).length;

  const successCount =
    observations.filter(
      (x) => x.status === "success"
    ).length;

  return (
    <div className="observations-page">
      <div className="page-header">
        <h2>Observations</h2>
        <p>
          Monitor all agent executions and
          LLM calls
        </p>
      </div>

      {/* Stats */}

      <div className="stats-grid">
        <div className="stat-card">
          <span>Total</span>

          <h3>{totalObservations}</h3>
        </div>

        <div className="stat-card">
          <span>LLM</span>

          <h3>{llmCount}</h3>
        </div>

        <div className="stat-card">
          <span>CHAIN</span>

          <h3>{chainCount}</h3>
        </div>

        <div className="stat-card">
          <span>Success</span>

          <h3>{successCount}</h3>
        </div>
      </div>

      {/* Filters */}

      <div className="filter-card">
        <div className="filter-grid">

          <input
            placeholder="Trace ID"
            value={traceId}
            onChange={(e) =>
              setTraceId(e.target.value)
            }
          />

          <input
            placeholder="Agent Name"
            value={agentName}
            onChange={(e) =>
              setAgentName(
                e.target.value
              )
            }
          />

          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
          >
            <option value="">Date Range</option>
            <option value="5m">5m</option>
            <option value="30m">30m</option>
            <option value="1h">1h</option>
            <option value="3h">3h</option>
            <option value="1d">1d</option>
            <option value="7d">7d</option>
            <option value="30d">30d</option>
            <option value="90d">90d</option>
            <option value="1y">1y</option>
          </select>

          <select
            value={obsType}
            onChange={(e) =>
              setObsType(
                e.target.value
              )
            }
          >
            <option value="">
              All Types
            </option>

            <option value="CHAIN">
              CHAIN
            </option>

            <option value="LLM">
              LLM
            </option>
          </select>

          <select
            value={status}
            onChange={(e) =>
              setStatus(
                e.target.value
              )
            }
          >
            <option value="">
              All Status
            </option>

            <option value="success">
              Success
            </option>

            <option value="error">
              Error
            </option>
          </select>

          <input
            type="datetime-local"
            value={fromTime}
            onChange={(e) =>
              setFromTime(
                e.target.value
              )
            }
          />

          <input
            type="datetime-local"
            value={toTime}
            onChange={(e) =>
              setToTime(
                e.target.value
              )
            }
          />
        </div>

        <div className="filter-actions">
          <div className="filter-buttons">
            <button
              className="apply-btn"
              onClick={fetchObservations}
            >
              Apply Filters
            </button>

            <button
              className="clear-btn"
              onClick={() => {
                setTraceId("");
                setAgentName("");
                setDateRange("");
                setObsType("");
                setStatus("");
                setFromTime("");
                setToTime("");
                fetchObservations();
              }}
            >
              Clear
            </button>
          </div>

          <input
            className="search-box"
            placeholder="Search by name, trace, or project"
            value={search}
            onChange={(e) =>
              setSearch(
                e.target.value
              )
            }
          />
        </div>
      </div>

      {/* Table */}

      <div className="table-container">
        {loading ? (
          <div className="loading">
            Loading...
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Trace</th>
                <th>Project</th>
                <th>Model</th>
                <th>Provider</th>
                <th>Tokens</th>
                <th>Latency</th>
                <th>Cost</th>
                <th>Created</th>
              </tr>
            </thead>

            <tbody>
              {filteredData.map(
                (obs) => (
                  <tr key={obs.id}>
                    <td>{obs.name}</td>

                    <td>
                      <span className={`type-badge ${obs.type === "CHAIN" ? "type-chain" : obs.type === "LLM" ? "type-llm" : ""}`}>
                        {obs.type || "-"}
                      </span>
                    </td>

                    <td>
                      <span
                        className={`status ${obs.status}`}
                      >
                        {obs.status}
                      </span>
                    </td>

                    <td>
                      {obs.trace_name}
                    </td>

                    <td>
                      {obs.project_id}
                    </td>

                    <td>
                      {obs.model ||
                        "-"}
                    </td>

                    <td>
                      {obs.provider ||
                        "-"}
                    </td>

                    <td>
                      {obs.total_tokens ??
                        "-"}
                    </td>

                    <td>
                      {
                        obs.latency_ms
                      }
                      ms
                    </td>

                    <td>
                      $
                      {obs.cost_usd?.toFixed(
                        5
                      ) || "-"}
                    </td>

                    <td>
                      {new Date(
                        obs.created_at
                      ).toLocaleString()}
                    </td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default Observations;