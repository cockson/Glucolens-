import React from "react";

function toLabel(key) {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (s) => s.toUpperCase());
}

function isPrimitive(v) {
  return v == null || ["string", "number", "boolean"].includes(typeof v);
}

function formatPrimitive(v) {
  if (v == null) return "N/A";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return String(v);
}

function Node({ value, depth }) {
  if (isPrimitive(value)) {
    return <span>{formatPrimitive(value)}</span>;
  }

  if (Array.isArray(value)) {
    if (!value.length) return <span>N/A</span>;
    if (value.every(isPrimitive)) {
      return <span>{value.map(formatPrimitive).join(", ")}</span>;
    }
    return (
      <div style={{ display: "grid", gap: 8 }}>
        {value.map((item, idx) => (
          <div key={idx} className="card" style={{ padding: "8px 10px", margin: 0 }}>
            <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Item {idx + 1}</div>
            <Node value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  const entries = Object.entries(value || {});
  if (!entries.length) return <span>N/A</span>;

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {entries.map(([k, v]) => (
        <div key={`${depth}-${k}`} className="card" style={{ padding: "8px 10px", margin: 0 }}>
          <div className="small" style={{ fontWeight: 600, marginBottom: 4 }}>{toLabel(k)}</div>
          <div className="small">
            <Node value={v} depth={depth + 1} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function CleanDataView({ data, emptyText = "No data available." }) {
  if (data == null) return <p className="small">{emptyText}</p>;
  return <Node value={data} depth={0} />;
}

