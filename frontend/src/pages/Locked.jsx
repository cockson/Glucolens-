import React from "react";
import { Link } from "react-router-dom";

export default function Locked({ message }){
  return (
    <div className="container">
      <div className="card" style={{ maxWidth: 720, margin: "40px auto" }}>
        <h2>Subscription Required</h2>
        <p className="small">
          {message || "Your subscription is inactive. Please renew to continue using GlucoLens business features."}
        </p>
        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          <Link className="btn" to="/billing">Renew subscription</Link>
          <Link className="btn secondary" to="/dashboard">Back</Link>
        </div>
      </div>
    </div>
  );
}