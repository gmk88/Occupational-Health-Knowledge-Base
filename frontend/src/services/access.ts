import { api } from './http';

export interface AccessKey {
  id: string;
  key_prefix: string;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
}

export interface AccessClient {
  id: string;
  name: string;
  status: string;
  scopes: string[];
  rate_limit_per_minute: number;
  upload_limit_per_minute: number;
  created_at: string;
  updated_at: string;
  key_prefix: string | null;
  key_created_at: string | null;
  last_used_at: string | null;
  active_key_count: number;
  keys: AccessKey[];
  key?: string;
}

export interface AccessUser {
  id: string;
  login_name: string;
  display_name: string;
  role: string;
  status: string;
  last_login_at: string | null;
  created_at: string;
}

export interface ClientUsage {
  client_id: string;
  days: number;
  calls: number;
  avg_ms: number;
  p95_ms: number;
  degraded: number;
  success_rate: number;
  daily: { date: string | null; calls: number; avg_ms: number }[];
  modes: { mode: string; calls: number }[];
}

export interface UsageOverviewRow {
  client_id: string;
  name: string;
  status: string;
  calls: number;
  avg_ms: number;
  last_call_at: string | null;
  rate_limit_per_minute: number;
}

export function listAccessClients() {
  return api<AccessClient[]>('/access/clients');
}

export function createAccessClient(input: {
  name: string;
  scopes: string[];
  rate_limit_per_minute: number;
}) {
  return api<AccessClient>('/access/clients', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function updateAccessClient(
  clientId: string,
  patch: {
    name?: string;
    status?: 'active' | 'disabled';
    scopes?: string[];
    rate_limit_per_minute?: number;
  },
) {
  return api<AccessClient>(`/access/clients/${clientId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export function rotateAccessKey(clientId: string) {
  return api<AccessClient>(`/access/clients/${clientId}/keys`, { method: 'POST' });
}

export function revokeAccessKey(clientId: string, keyId: string) {
  return api<AccessClient>(`/access/clients/${clientId}/keys/${keyId}`, {
    method: 'DELETE',
  });
}

export function getClientUsage(clientId: string, days: number) {
  return api<ClientUsage>(`/access/clients/${clientId}/usage?days=${days}`);
}

export interface DailyUsage {
  date: string | null;
  calls: number;
  avg_ms: number;
}

export interface UsageOverview {
  days: number;
  clients: UsageOverviewRow[];
  daily: DailyUsage[];
}

export function getUsageOverview(days: number) {
  return api<UsageOverview>(`/access/usage?days=${days}`);
}

export function listScopes() {
  return api<string[]>('/access/scopes');
}

export function listAccessUsers() {
  return api<AccessUser[]>('/access/users');
}

export function createAccessUser(input: {
  login_name: string;
  display_name: string;
  password: string;
  role: 'admin' | 'viewer';
}) {
  return api<AccessUser>('/access/users', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function updateAccessUser(
  userId: string,
  patch: { display_name?: string; role?: 'admin' | 'viewer'; status?: 'active' | 'disabled' },
) {
  return api<AccessUser>(`/access/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export function resetUserPassword(userId: string, password: string) {
  return api<{ id: string; updated: boolean }>(`/access/users/${userId}/password`, {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}
