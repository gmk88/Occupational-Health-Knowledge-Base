import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test } from 'vitest';
import { SearchResults } from './SearchResults';
import type { SearchResult } from '../../services/search';

const result: SearchResult = {
  chunk_id: 'c1',
  text: '',
  document_id: 'd1',
  document_name: '测试文档',
  version_number: 1,
  page_start: 1,
  page_end: 1,
  category: null,
  tags: [],
  lifecycle_status: 'current',
  document_role: 'main',
  scores: { rrf: 1 },
  recall_sources: ['keyword'],
  highlights: [],
  kind: 'table',
  table: {
    id: 't1',
    caption: '表 1 职业接触限值',
    header: null,
    total_rows: 2,
    rows: [
      [
        { text: '中文名', rowspan: 1, colspan: 1 },
        { text: '英文名', rowspan: 1, colspan: 1 },
      ],
      [
        { text: '粉尘\n纤维', rowspan: 1, colspan: 1 },
        { text: 'Asbestos dust\nAsbestos fibre', rowspan: 1, colspan: 1 },
      ],
    ],
  },
};

afterEach(cleanup);

test('表格单元格内的子行按换行分行显示', () => {
  const { container } = render(
    <MemoryRouter>
      <SearchResults results={[result]} degraded={false} tookMs={1} />
    </MemoryRouter>,
  );

  expect(container.querySelectorAll('td br')).toHaveLength(2);
  expect(screen.getByText('粉尘')).toBeInTheDocument();
  expect(screen.getByText('纤维')).toBeInTheDocument();
  expect(screen.getByText('Asbestos dust')).toBeInTheDocument();
  expect(screen.getByText('Asbestos fibre')).toBeInTheDocument();
});
