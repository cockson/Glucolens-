import React from "react";

export default function QrImage({ base64, size=220 }){
  if (!base64) return null;
  return (
    <img
      src={`data:image/png;base64,${base64}`}
      alt="Referral QR"
      style={{ width: size, height: size, borderRadius: 14, border: "1px solid rgba(255,255,255,0.16)" }}
    />
  );
}