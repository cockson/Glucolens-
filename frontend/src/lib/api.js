import axios from "axios";

const rawApiUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_URL = rawApiUrl.replace(/\/+$/, "");

export const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
});

if (!import.meta.env.VITE_API_URL) {
  console.warn("VITE_API_URL is not set. Falling back to http://127.0.0.1:8000");
}

export function setAuthHeader(token) {
  if (token) api.defaults.headers.common.Authorization = `Bearer ${token}`;
  else delete api.defaults.headers.common.Authorization;
}
