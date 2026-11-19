import { useEffect, useRef, useState } from 'react';
import { getPage, type PageAnchor } from '../../services/documents';
import { Button } from '../../components/ui';

interface PagePreviewProps {
  documentId: string;
  pageCount: number;
  initialPage?: number;
  chunkId?: string;
}

type HighlightRange = PageAnchor & { start_offset: number; end_offset: number };

function mergeHighlights(anchors: PageAnchor[]): HighlightRange[] {
  const ranges = anchors
    .filter(
      (anchor): anchor is HighlightRange =>
        anchor.start_offset !== null &&
        anchor.end_offset !== null &&
        anchor.end_offset > anchor.start_offset,
    )
    .sort((left, right) => left.start_offset - right.start_offset);
  const merged: HighlightRange[] = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range.start_offset <= last.end_offset) {
      last.end_offset = Math.max(last.end_offset, range.end_offset);
      continue;
    }
    merged.push({ ...range });
  }
  return merged;
}

function renderHighlighted(text: string, highlights: HighlightRange[]) {
  if (!highlights.length) return text;
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  highlights.forEach((highlight, index) => {
    if (highlight.start_offset > cursor) {
      nodes.push(text.slice(cursor, highlight.start_offset));
    }
    nodes.push(
      <mark
        key={`${highlight.chunk_id}-${index}`}
        className="source-anchor"
        title={highlight.quote}
      >
        {text.slice(highlight.start_offset, highlight.end_offset)}
      </mark>,
    );
    cursor = highlight.end_offset;
  });
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

export function PagePreview({
  documentId,
  pageCount,
  initialPage,
  chunkId,
}: PagePreviewProps) {
  const [pageNumber, setPageNumber] = useState(initialPage || 1);
  const [text, setText] = useState('');
  const [anchors, setAnchors] = useState<PageAnchor[]>([]);
  const containerRef = useRef<HTMLPreElement>(null);

  async function load(page: number, focusChunkId?: string) {
    const response = await getPage(documentId, page, 'raw', focusChunkId);
    setText(response.data.text);
    setAnchors(response.data.anchors ?? []);
    setPageNumber(page);
    if (focusChunkId) {
      window.setTimeout(() => {
        containerRef.current?.querySelector('mark.source-anchor')?.scrollIntoView({
          block: 'center',
        });
      }, 80);
    }
  }

  useEffect(() => {
    const target = initialPage && initialPage > 0 ? initialPage : 1;
    const id = window.setTimeout(() => void load(target, chunkId), 0);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, initialPage, chunkId]);

  const highlights = mergeHighlights(anchors);

  return (
    <div className="detail-block" aria-label="页面预览">
      <div className="row">
        <Button
          variant="secondary"
          disabled={pageNumber <= 1}
          onClick={() => void load(pageNumber - 1)}
        >
          上一页
        </Button>
        <span aria-live="polite">
          {pageNumber} / {pageCount}
        </span>
        <Button
          variant="secondary"
          disabled={pageNumber >= pageCount}
          onClick={() => void load(pageNumber + 1)}
        >
          下一页
        </Button>
      </div>
      {chunkId && anchors.length === 0 && (
        <p className="hint">该命中块没有可用文本锚点，已定位到页码。</p>
      )}
      <pre className="page-text" ref={containerRef}>
        {renderHighlighted(text, highlights)}
      </pre>
      {anchors.length > 0 && (
        <div className="anchor-list" aria-label="原文锚点">
          <strong>已定位到 {anchors.length} 个原文片段</strong>
          {anchors.slice(0, 3).map((anchor, index) => (
            <p key={`${anchor.chunk_id}-${index}`} className="hint">
              第 {anchor.page_number} 页 · {anchor.match_method} · {anchor.status} ·{' '}
              {anchor.quote.slice(0, 120)}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
