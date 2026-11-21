import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test } from 'vitest';
import { SourceLink } from './SourceLink';

afterEach(cleanup);

test('定位原文链接携带页码、切分块与跨页信息', () => {
  render(
    <MemoryRouter>
      <SourceLink documentId="d1" page={3} pageEnd={5} chunkId="c1" />
    </MemoryRouter>,
  );

  const link = screen.getByRole('link', { name: '定位原文第 3-5 页' });
  expect(link).toHaveAttribute('href', '/documents/d1?page=3&chunk_id=c1&page_end=5');
});
