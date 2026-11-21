import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { getPage, type PageSpan } from '../../services/documents';
import { Button } from '../../components/ui';

interface PagePreviewProps {
  documentId: string;
  pageCount: number;
  initialPage?: number;
  chunkId?: string;
  chunkPageEnd?: number;
}

function normalizeSpans(spans: PageSpan[], length: number) {
  const ranges = spans
    .map(({ start_offset, end_offset }) => ({
      start: Math.max(0, Math.min(start_offset, length)),
      end: Math.max(0, Math.min(end_offset, length)),
    }))
    .filter((range) => range.end > range.start)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: { start: number; end: number }[] = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range.start <= last.end) {
      last.end = Math.max(last.end, range.end);
    } else {
      merged.push({ ...range });
    }
  }
  return merged;
}

function renderHighlighted(text: string, spans: PageSpan[]): ReactNode[] {
  // 后端按 Unicode code point 计算偏移，Array.from 保证 emoji 等字符不错位。
  const chars = Array.from(text);
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const range of normalizeSpans(spans, chars.length)) {
    if (range.start > cursor) nodes.push(chars.slice(cursor, range.start).join(''));
    nodes.push(
      <mark key={`chunk-${range.start}-${range.end}`} className="page-chunk-highlight">
        {chars.slice(range.start, range.end).join('')}
      </mark>,
    );
    cursor = range.end;
  }
  if (cursor < chars.length) nodes.push(chars.slice(cursor).join(''));
  return nodes;
}

export function PagePreview({
  documentId,
  pageCount,
  initialPage = 1,
  chunkId,
  chunkPageEnd,
}: PagePreviewProps) {
  const startPage = Math.min(Math.max(initialPage || 1, 1), Math.max(pageCount, 1));
  const [pageNumber, setPageNumber] = useState(startPage);
  const [text, setText] = useState('');
  const [spans, setSpans] = useState<PageSpan[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const requestRef = useRef(0);
  const containerRef = useRef<HTMLPreElement>(null);

  const load = useCallback(async (page: number) => {
    const requestId = ++requestRef.current;
    setLoading(true);
    setError('');
    try {
      const response = await getPage(documentId, page, 'masked', chunkId);
      if (requestId !== requestRef.current) return;
      setText(response.data.text);
      setSpans(response.data.spans ?? []);
      setPageNumber(page);
    } catch {
      if (requestId !== requestRef.current) return;
      setError('页面原文加载失败，请稍后重试');
      setText('');
      setSpans([]);
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }, [documentId, chunkId]);

  useEffect(() => {
    const id = window.setTimeout(() => { void load(startPage); }, 0);
    return () => window.clearTimeout(id);
  }, [load, startPage]);

  useEffect(() => {
    if (loading || spans.length === 0) return;
    const mark = containerRef.current?.querySelector('.page-chunk-highlight');
    if (mark && typeof mark.scrollIntoView === 'function') {
      mark.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [loading, spans, text]);

  return (
    <div className="detail-block" aria-label="页面预览">
      <div className="row">
        <Button
          variant="secondary"
          disabled={loading || pageNumber <= 1}
          onClick={() => void load(pageNumber - 1)}
        >
          上一页
        </Button>
        <span aria-live="polite">
          {pageNumber} / {Math.max(pageCount, 1)}
        </span>
        <Button
          variant="secondary"
          disabled={loading || pageNumber >= pageCount}
          onClick={() => void load(pageNumber + 1)}
        >
          下一页
        </Button>
      </div>
      {chunkId && !loading && !error && (
        <p className="hint" role="status">
          {spans.length > 0
            ? '已定位检索命中的切分块（高亮部分）'
            : '未能在该页定位到切分块，已显示整页原文'}
          {chunkPageEnd && chunkPageEnd > pageNumber && ` · 该切分块跨至第 ${chunkPageEnd} 页`}
        </p>
      )}
      {error && <p className="hint" role="alert">{error}</p>}
      <pre className="page-text" ref={containerRef}>
        {spans.length > 0 ? renderHighlighted(text, spans) : text}
      </pre>
    </div>
  );
}
