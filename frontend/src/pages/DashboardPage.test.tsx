import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { DashboardPage } from './DashboardPage';
import type { Document } from '../services/documents';
import { getDashboardSummary, type DashboardSummary } from '../services/dashboard';

vi.mock('../services/dashboard', () => ({
  getDashboardSummary: vi.fn(),
}));

vi.mock('../services/pendingJobs', () => ({
  subscribePendingJobs: vi.fn(() => () => {}),
}));

const summaryQuery = vi.mocked(getDashboardSummary);

function envelope<T>(data: T) {
  return { code: 'OK', message: 'success', data, request_id: 'test' };
}

const document: Document = {
  id: 'd1',
  title: '测试文档',
  original_filename: 'test.pdf',
  status: 'searchable',
  category: null,
  tags: [],
  source: null,
  notes: null,
  uploader_id: 'u1',
  current_version: null,
  created_at: '2026-11-16T00:00:00Z',
  updated_at: '2026-11-16T00:00:00Z',
};

const summary: DashboardSummary = {
  total: 150,
  status_counts: { searchable: 120, processing: 5, needs_review: 25 },
  categories: [
    { id: 'c1', code: 'chem', name: '化学品', active: true, count: 150 },
  ],
  tags: [{ id: 't1', name: '苯', count: 3 }],
  recent_documents: [document],
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

test('汇总接口一次渲染总数、分类与最近文档', async () => {
  summaryQuery.mockResolvedValue(envelope(summary));

  renderPage();

  expect(await screen.findByText('测试文档')).toBeInTheDocument();
  expect(screen.queryByText('正在载入')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '导出文档清单' })).toBeInTheDocument();
  expect(screen.getByText(/150 篇文档/)).toBeInTheDocument();
  // 分类计数来自汇总接口，不再受“只取前 100 篇”影响。
  expect(screen.getByText('化学品')).toBeInTheDocument();
  expect(screen.getAllByText('120').length).toBeGreaterThan(0);
});

test('汇总接口失败时显示错误与重试按钮，不永久停在正在载入', async () => {
  summaryQuery.mockRejectedValue(new Error('服务暂时不可用'));

  renderPage();

  expect(await screen.findByText('数据加载失败')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  expect(screen.queryByText('正在载入')).not.toBeInTheDocument();
});
