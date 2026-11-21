import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { PagePreview } from './PagePreview';
import { getPage, type PageText } from '../../services/documents';

vi.mock('../../services/documents', () => ({ getPage: vi.fn() }));

const getPageMock = vi.mocked(getPage);
const chunk = '噪声作业劳动者应当佩戴护耳器。';
const pageTextValue = `前言\n${chunk}\n附则`;

function envelope<T>(data: T) {
  return { code: 'OK', message: 'success', data, request_id: 'test' };
}

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

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

test('按 chunk_id 请求页面并高亮命中的切分块', async () => {
  getPageMock.mockResolvedValue(envelope(page));

  render(<PagePreview documentId="d1" pageCount={5} initialPage={3} chunkId="c1" />);

  const mark = await screen.findByText(chunk, { selector: 'mark' });
  expect(mark).toHaveClass('page-chunk-highlight');
  expect(getPageMock).toHaveBeenCalledWith('d1', 3, 'masked', 'c1');
  expect(screen.getByRole('status')).toHaveTextContent('已定位检索命中的切分块');
});

test('无法定位时显示整页原文并给出提示', async () => {
  getPageMock.mockResolvedValue(envelope({ ...page, spans: [] }));

  render(<PagePreview documentId="d1" pageCount={5} chunkId="c1" />);

  expect(await screen.findByText(/未能在该页定位到切分块/)).toBeInTheDocument();
  expect(screen.getByLabelText('页面预览').querySelector('pre')?.textContent).toBe(pageTextValue);
});

test('翻页时继续携带 chunk_id', async () => {
  getPageMock.mockResolvedValue(envelope(page));

  render(<PagePreview documentId="d1" pageCount={5} initialPage={3} chunkId="c1" />);
  await screen.findByText(chunk, { selector: 'mark' });
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));

  await waitFor(() => {
    expect(getPageMock).toHaveBeenLastCalledWith('d1', 4, 'masked', 'c1');
  });
});
