import type { QualityReport as Quality } from '../../services/documents';

export function QualityReport({ report }: { report: Quality }) {
  return (
    <div className="detail-block" aria-label="质量报告">
      <dl className="stats">
        <div><dt>页数</dt><dd>{report.page_count}</dd></div>
        <div><dt>有效字符</dt><dd>{report.effective_char_count}</dd></div>
        <div><dt>文本块</dt><dd>{report.chunk_count}</dd></div>
        <div><dt>OCR 页占比</dt><dd>{(report.ocr_page_ratio * 100).toFixed(1)}%</dd></div>
        <div><dt>平均置信度</dt><dd>{report.average_ocr_confidence ?? '—'}</dd></div>
      </dl>
      {report.low_quality_pages.length > 0 && <p className="hint">低质量页：{report.low_quality_pages.join('、')}</p>}
      {report.failed_pages.length > 0 && <p className="hint">失败页：{report.failed_pages.length} 页</p>}
    </div>
  );
}
