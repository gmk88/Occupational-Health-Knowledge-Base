import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { DocumentsPage } from './DocumentsPage';
import {
  getDocument,
  getPage,
  getQualityReport,
  listDocuments,
  type Document,
  type PageText,
  type QualityReport,
} from '../services/documents';

vi.mock('../services/documents', () => ({
  getDocument: vi.fn(),
  getPage: vi.fn(),
  getQualityReport: vi.fn(),
  listDocuments: vi.fn(),
}));
vi.mock('../features/documents/UploadForm', () => ({ UploadForm: () => null }));
vi.mock('../features/documents/DocumentDetail', () => ({ DocumentDetail: () => null }));
vi.mock('../features/documents/QualityReport', () => ({ QualityReport: () => null }));

const doc: Document = {
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
  created_at: '2026-11-21T00:00:00Z',
  updated_at: '2026-11-21T00:00:00Z',
};
const report: QualityReport = {
  document_id: 'd1',
  version_id: 'v1',
  job_id: 'j1',
  page_count: 5,
  effective_char_count: 100,
  chunk_count: 2,
  ocr_page_ratio: 0,
  average_ocr_confidence: null,
  noise_char_count: 0,
  low_quality_pages: [],
  failed_pages: [],
  processing_duration_ms: 10,
  created_at: '2026-11-21T00:00:00Z',
};
const chunk = '噪声作业劳动者应当佩戴护耳器。';
const pageTextValue = `前言\n${chunk}\n附则`;
const page: PageText = {
  document_id: 'd1',
  version_number: 1,
  page_number: 3,
  source_type: 'text_layer',
  view: 'masked',
  text: pageTextValue,
  spans: [
    {
      start_offset: pageTextValue.indexOf(chunk),
      end_offset: pageTextValue.indexOf(chunk) + chunk.length,
      type: 'chunk',
    },
  ],
  quality_warnings: [],
};

function envelope<T>(data: T) {
  return { code: 'OK', message: 'success', data, request_id: 'test' };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getDocument).mockResolvedValue(envelope(doc));
  vi.mocked(getQualityReport).mockResolvedValue(envelope(report));
  vi.mocked(getPage).mockResolvedValue(envelope(page));
  vi.mocked(listDocuments).mockResolvedValue(envelope({
    items: [doc],
    meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
  }));
});

afterEach(cleanup);

test('检索结果深链自动打开指定文档、页码并凸显切分块', async () => {
  render(
    <MemoryRouter initialEntries={['/documents/d1?page=3&chunk_id=c1&page_end=4']}>
      <Routes>
        <Route path="/documents/:documentId" element={<DocumentsPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText(chunk, { selector: 'mark' })).toBeInTheDocument();
  expect(getDocument).toHaveBeenCalledWith('d1');
  expect(getPage).toHaveBeenCalledWith('d1', 3, 'masked', 'c1');
  expect(screen.getByRole('tab', { name: '页面预览' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText(/该切分块跨至第 4 页/)).toBeInTheDocument();
});
