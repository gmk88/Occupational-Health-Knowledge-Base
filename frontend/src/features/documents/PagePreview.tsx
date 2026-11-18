import { useEffect, useState } from 'react';
import { getPage } from '../../services/documents';
import { Button } from '../../components/ui';

export function PagePreview({ documentId, pageCount }: { documentId: string; pageCount: number }) {
  const [pageNumber, setPageNumber] = useState(1);
  const [text, setText] = useState('');

  async function load(page: number) {
    const response = await getPage(documentId, page);
    setText(response.data.text);
    setPageNumber(page);
  }
  useEffect(() => {
    const id = window.setTimeout(() => void load(1), 0);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId]);

  return (
    <div className="detail-block" aria-label="页面预览">
      <div className="row">
        <Button variant="secondary" disabled={pageNumber <= 1} onClick={() => void load(pageNumber - 1)}>
          上一页
        </Button>
        <span aria-live="polite">
          {pageNumber} / {pageCount}
        </span>
        <Button variant="secondary" disabled={pageNumber >= pageCount} onClick={() => void load(pageNumber + 1)}>
          下一页
        </Button>
      </div>
      <pre className="page-text">{text}</pre>
    </div>
  );
}
