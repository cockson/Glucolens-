import React, { useState } from "react";
import { api } from "../lib/api";
import { useNavigate, Link } from "react-router-dom";

export default function RegisterPublic(){
  const nav = useNavigate();
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [err,setErr]=useState("");

  async function submit(e){
    e.preventDefault(); setErr("");
    try{
      await api.post("/api/auth/register-public", {email, password});
      nav("/login");
 } catch (err) {
  console.log("REGISTER RAW ERROR:", err);

  // Axios sometimes has no response on network errors
  const status = err?.response?.status;
  const data = err?.response?.data;

  let message = "Registration failed";

  if (data?.detail) {
    message = Array.isArray(data.detail)
      ? data.detail.map(x => x.msg).join(", ")
      : data.detail;
  } else if (err?.message) {
    message = err.message; // e.g. "Network Error"
  }

  setErr(`${status ? status + " " : ""}${message}`);
}
  }

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: 520, margin:"40px auto" }}>
        <h2>Public Quick-Check Account</h2>
        <p className="small">Rate-limited access for single users.</p>
        <form onSubmit={submit}>
          <input className="input" type="email"  placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} required/>
          <div style={{ height: 10 }} />
          <input className="input" type="password" placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)} required minLength={8}/>
          <div style={{ height: 14 }} />
          <button className="btn" type="submit">Create</button>
        </form>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        <div className="small" style={{ marginTop: 10 }}>
          <Link to="/login">Back to login</Link>
        </div>
      </div>
    </div>
  );
}