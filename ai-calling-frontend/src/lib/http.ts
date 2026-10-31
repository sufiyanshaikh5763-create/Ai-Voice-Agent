/**
 * Unified HTTP helper for frontend API communication.
 * Features:
 * - Bearer authorization from localStorage
 * - X-Admin-Session header for staff elevation token
 * - Automatic 401 token refresh queue & retry
 * - Role mapping and cookie sync for middleware navigation
 * - Clean session termination on refresh failure or logout
 */

import { AUTH_CHANNEL, AUTH_LOGOUT_KEY } from './auth-channel';

export type AppRole = 'admin' | 'staff' | 'super_admin';

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 500, code = 'API_ERROR') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

const STORAGE_KEYS = {
  ACCESS_TOKEN: 'tk_access_token',
  REFRESH_TOKEN: 'tk_refresh_token',
  ELEVATION_TOKEN: 'tk_elevation_token',
  USER_DATA: 'tk_user',
};

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
}

export function getElevationToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEYS.ELEVATION_TOKEN);
}

export function setTokens(accessToken: string, refreshToken?: string | null): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, accessToken);
  if (refreshToken) {
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
  }
}

export function setElevationToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  if (token) {
    localStorage.setItem(STORAGE_KEYS.ELEVATION_TOKEN, token);
  } else {
    localStorage.removeItem(STORAGE_KEYS.ELEVATION_TOKEN);
  }
}

export function mapRole(backendRole: string): AppRole {
  const r = backendRole?.toLowerCase();
  if (r === 'super_admin') return 'super_admin';
  if (r === 'client_admin' || r === 'admin') return 'admin';
  return 'staff';
}

export function getUserRole(): AppRole | null {
  if (typeof window === 'undefined') return null;
  const userStr = localStorage.getItem(STORAGE_KEYS.USER_DATA);
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      return mapRole(user.role);
    } catch {}
  }
  return null;
}

export function setSessionCookies(user: { id?: string | number; role: string; access_status?: string | null }): void {
  if (typeof document === 'undefined') return;
  const role = mapRole(user.role);
  let userHint = user.id ? String(user.id) : 'active_user';
  if (user.access_status === 'suspended') {
    userHint = 'suspended';
  } else if (user.access_status && user.access_status !== 'active') {
    userHint = 'pending';
  }

  document.cookie = `tk_role=${role}; path=/; SameSite=Lax; max-age=604800`;
  document.cookie = `tk_session_user=${userHint}; path=/; SameSite=Lax; max-age=604800`;

  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(STORAGE_KEYS.USER_DATA, JSON.stringify(user));
    } catch {}
  }
}

export function clearAuth(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.ELEVATION_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USER_DATA);
  }
  if (typeof document !== 'undefined') {
    document.cookie = 'tk_role=; path=/; max-age=0; SameSite=Lax';
    document.cookie = 'tk_session_user=; path=/; max-age=0; SameSite=Lax';
  }
}

let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];
let refreshFailureSubscribers: ((err: any) => void)[] = [];

function subscribeTokenRefresh(onSuccess: (token: string) => void, onFailure: (err: any) => void) {
  refreshSubscribers.push(onSuccess);
  refreshFailureSubscribers.push(onFailure);
}

function onRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
  refreshFailureSubscribers = [];
}

function onRefreshFailed(err: any) {
  refreshFailureSubscribers.forEach((cb) => cb(err));
  refreshSubscribers = [];
  refreshFailureSubscribers = [];
}

export interface RequestOptions extends RequestInit {
  requiresAuth?: boolean;
  retryOnExpire?: boolean;
  unwrapResponse?: boolean;
}

export async function http<T = any>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const {
    requiresAuth = true, retryOnExpire = true, unwrapResponse = true,
    headers: customHeaders, ...fetchOpts
  } = options;

  const url = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const headers = new Headers(customHeaders || {});

  if (!headers.has('Content-Type') && !(fetchOpts.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (requiresAuth) {
    const token = getAccessToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    const elevation = getElevationToken();
    if (elevation) {
      headers.set('X-Admin-Session', elevation);
    }
  }

  let response: Response;
  const timeoutSignal =
    fetchOpts.signal || (typeof AbortSignal !== 'undefined' && 'timeout' in AbortSignal ? AbortSignal.timeout(10000) : undefined);

  try {
    response = await fetch(url, {
      ...fetchOpts,
      signal: timeoutSignal,
      headers,
    });
  } catch (err: any) {
    if (err?.name === 'TimeoutError') {
      throw new ApiError('Request timed out after 10 seconds. Please check if the backend is running.', 408, 'REQUEST_TIMEOUT');
    }
    throw new ApiError('Unable to connect to server. Please check your network connection.', 0, 'NETWORK_ERROR');
  }

  // Handle 401 & Token Refresh
  if (response.status === 401 && retryOnExpire) {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const refreshRes = await fetch('/api/v1/auth/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });

          if (!refreshRes.ok) {
            clearAuth();
            if (typeof window !== 'undefined') {
              window.location.href = '/login?expired=1';
            }
            const err = new ApiError('Session expired. Please log in again.', 401, 'TOKEN_EXPIRED');
            onRefreshFailed(err);
            throw err;
          }

          const refreshData = await refreshRes.json();
          // Extract new token from plain response or ApiResponse envelope
          const newAccessToken =
            refreshData.access_token ||
            refreshData.data?.access_token ||
            refreshData.tokens?.access_token;
          const newRefreshToken =
            refreshData.refresh_token ||
            refreshData.data?.refresh_token ||
            refreshData.tokens?.refresh_token;

          if (newAccessToken) {
            setTokens(newAccessToken, newRefreshToken);
          }
          isRefreshing = false;
          onRefreshed(newAccessToken);

          headers.set('Authorization', `Bearer ${newAccessToken}`);
          return http<T>(endpoint, { ...options, retryOnExpire: false });
        } catch (err) {
          isRefreshing = false;
          onRefreshFailed(err);
          clearAuth();
          if (typeof window !== 'undefined') {
            window.location.href = '/login?expired=1';
          }
          throw err;
        }
      } else {
        // Queue concurrent requests while refresh in progress
        return new Promise<T>((resolve, reject) => {
          subscribeTokenRefresh(
            (newToken: string) => {
              headers.set('Authorization', `Bearer ${newToken}`);
              http<T>(endpoint, { ...options, retryOnExpire: false })
                .then(resolve)
                .catch(reject);
            },
            (err: any) => reject(err)
          );
        });
      }
    } else {
      clearAuth();
      if (typeof window !== 'undefined') {
        window.location.href = '/login?expired=1';
      }
    }
  }

  const contentType = response.headers.get('content-type');
  let data: any;
  if (contentType && contentType.includes('application/json')) {
    data = await response.json().catch(() => ({}));
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const errorMsg =
      (typeof data === 'object' && (data.detail || data.message || data.error)) ||
      `Request failed with status ${response.status}`;
    const errorCode = (typeof data === 'object' && (data.code || data.error_code)) || 'API_ERROR';
    if (response.status === 403 && (errorCode === 'CLIENT_SUSPENDED' || String(errorMsg).toLowerCase().includes('suspended'))) {
      if (typeof document !== 'undefined') {
        document.cookie = 'tk_session_user=suspended; path=/; max-age=604800; SameSite=Lax';
      }
      if (typeof window !== 'undefined') {
        window.location.href = '/login?error=account_suspended';
      }
    }
    throw new ApiError(errorMsg, response.status, errorCode);
  }

  if (!unwrapResponse) {
    return data as T;
  }

  // Unwrap ApiResponse envelope if present
  if (data && typeof data === 'object' && 'data' in data && data.data !== undefined) {
    return data.data as T;
  }
  return data as T;
}

export async function logoutUser(broadcast = true): Promise<void> {
  const refreshToken = getRefreshToken();
  try {
    if (refreshToken) {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    }
  } catch {
    // Ignore network failures on logout
  } finally {
    if (broadcast) {
      if (typeof BroadcastChannel !== 'undefined') {
        try {
          const bc = new BroadcastChannel(AUTH_CHANNEL);
          bc.postMessage({ type: 'logout', reason: 'manual', at: Date.now() });
          bc.close();
        } catch {}
      }
      try {
        localStorage.setItem(AUTH_LOGOUT_KEY, JSON.stringify({ type: 'logout', at: Date.now() }));
      } catch {}
    }

    clearAuth();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  }
}
