import { Link } from 'react-router-dom';

interface SourceLinkProps {
  documentId: string;
  page: number;
  pageEnd?: number;
  chunkId: string;
}

export function SourceLink({ documentId, page, pageEnd, chunkId }: SourceLinkProps) {
  const params = new URLSearchParams({ page: String(page), chunk_id: chunkId });
  if (pageEnd && pageEnd > page) params.set('page_end', String(pageEnd));
  const label = pageEnd && pageEnd > page ? `${page}-${pageEnd}` : `${page}`;
  return (
    <Link to={`/documents/${encodeURIComponent(documentId)}?${params.toString()}`}>
      定位原文第 {label} 页
    </Link>
  );
}
