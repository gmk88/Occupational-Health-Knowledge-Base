import { Link } from 'react-router-dom';

export function SourceLink({ documentId, page }: { documentId: string; page: number }) {
  return <Link to={`/documents/${documentId}?page=${page}`}>查看原文第 {page} 页</Link>;
}
