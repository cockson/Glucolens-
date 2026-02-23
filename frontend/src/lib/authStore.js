import { api, setAuthHeader } from "./api";

const KEY = "glucolens_auth_v1";

export function getAuth() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; }
  catch { return null; }
}

export function setAuth(auth) {
  localStorage.setItem(KEY, JSON.stringify(auth));
  setAuthHeader(auth?.access_token);
}

export function clearAuth() {
  localStorage.removeItem(KEY);
  setAuthHeader(null);
}

export async function refreshToken() {
  const auth = getAuth();
  if (!auth?.refresh_token) throw new Error("No refresh token");

  const res = await api.post("/api/auth/refresh", { refresh_token: auth.refresh_token });
  const next = { ...auth, ...res.data };
  setAuth(next);
  return next;
}

// Axios interceptor: auto-refresh once on 401
let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const status = err?.response?.status;
    const url = err?.config?.url || "";
    const isRefreshCall = url.includes("/api/auth/refresh");
    const isLoginCall = url.includes("/api/auth/login");
    const isRegisterCall = url.includes("/api/auth/register-");
    const isLogoutCall = url.includes("/api/auth/logout");
    const hasRefreshToken = !!getAuth()?.refresh_token;

    if (status === 401 && !isRefreshCall && !isLoginCall && !isRegisterCall && !isLogoutCall && hasRefreshToken) {
      try {
        if (!refreshing) refreshing = refreshToken().finally(() => (refreshing = null));
        await refreshing;
        err.config.headers.Authorization = api.defaults.headers.common.Authorization;
        return api.request(err.config);
      } catch {
        clearAuth();
      }
    }

    return Promise.reject(err);
  }
);
