import { Link } from 'react-router-dom';

export function SourceLink({
  documentId,
  page,
  chunkId,
}: {
  documentId: string;
  page: number;
  chunkId?: string | null;
}) {
  const query = new URLSearchParams({ document: documentId, page: String(page) });
  if (chunkId) query.set('chunkId', chunkId);
  return <Link to={`/documents?${query.toString()}`}>查看原文第 {page} 页</Link>;
}
