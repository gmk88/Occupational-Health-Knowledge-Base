import { api } from './http';
import type { Document } from './documents';

export interface DashboardCategory {
  id: string;
  code: string;
  name: string;
  active: boolean;
  count: number;
}

export interface DashboardTag {
  id: string;
  name: string;
  count: number;
}

export interface DashboardSummary {
  total: number;
  status_counts: Record<string, number>;
  categories: DashboardCategory[];
  tags: DashboardTag[];
  recent_documents: Document[];
}

export function getDashboardSummary() {
  return api<DashboardSummary>('/dashboard/summary');
}
