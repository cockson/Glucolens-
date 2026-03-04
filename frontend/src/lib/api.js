import axios from "axios";

const rawApiUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_URL = rawApiUrl.replace(/\/+$/, "");
const DEFAULT_TIMEOUT_MS = 30000;
const DEFAULT_SCREENING_TIMEOUT_MS = 180000;

function parseTimeout(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

export const API_TIMEOUT_MS = parseTimeout(import.meta.env.VITE_API_TIMEOUT_MS, DEFAULT_TIMEOUT_MS);
export const SCREENING_TIMEOUT_MS = parseTimeout(
  import.meta.env.VITE_SCREENING_TIMEOUT_MS,
  DEFAULT_SCREENING_TIMEOUT_MS
);

export const api = axios.create({
  baseURL: API_URL,
  timeout: API_TIMEOUT_MS,
});

if (!import.meta.env.VITE_API_URL) {
  console.warn("VITE_API_URL is not set. Falling back to http://127.0.0.1:8000");
}

export function setAuthHeader(token) {
  if (token) api.defaults.headers.common.Authorization = `Bearer ${token}`;
  else delete api.defaults.headers.common.Authorization;
}
