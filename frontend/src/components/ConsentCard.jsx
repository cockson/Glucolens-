import React, { useMemo, useState } from "react";
import consentData from "../consent/consent.json";

export default function ConsentCard({ country="NG", lang="en", onChange }){
  const cfg = useMemo(()=>consentData?.[country]?.[lang] || consentData?.NG?.en, [country, lang]);
  const [checks, setChecks] = useState({});

  function toggle(id, val){
    const next = { ...checks, [id]: val };
    setChecks(next);
    const ok = (cfg.checkboxes || []).every(c => !c.required || next[c.id] === true);
    onChange?.({ ok, checks: next, version: cfg.version, country, lang });
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{cfg.title}</h3>
      <p className="small">{cfg.body}</p>
      <div style={{ display:"grid", gap:10 }}>
        {(cfg.checkboxes || []).map(c=>(
          <label key={c.id} className="small" style={{ display:"flex", gap:10, alignItems:"start" }}>
            <input type="checkbox" onChange={e=>toggle(c.id, e.target.checked)} />
            <span>{c.label}{c.required ? " *" : ""}</span>
          </label>
        ))}
      </div>
    </div>
  );
}