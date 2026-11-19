import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getDocument,
  getQualityReport,
  listDocuments,
  type Document,
  type QualityReport as Quality,
} from '../services/documents';
import { DocumentDetail } from '../features/documents/DocumentDetail';
import { PagePreview } from '../features/documents/PagePreview';
import { QualityReport as QualityReportView } from '../features/documents/QualityReport';
import { UploadForm } from '../features/documents/UploadForm';
import {
  Button,
  Card,
  CardGrid,
  CardStack,
  EmptyState,
  PageHeader,
  Pagination,
  StatusBadge,
} from '../components/ui';

const STATUS_FILTERS = [
  { value: '', label: '全部状态' },
  { value: 'searchable', label: '可检索' },
  { value: 'processing', label: '处理中' },
  { value: 'needs_review', label: '需复核' },
];

const TABS = [
  { value: 'detail', label: '详情' },
  { value: 'quality', label: '质量报告' },
  { value: 'preview', label: '页面预览' },
] as const;

type Tab = (typeof TABS)[number]['value'];

function formatDate(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : `${date.getMonth() + 1}月${date.getDate()}日`;
}

export function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<Document | null>(null);
  const [report, setReport] = useState<Quality | null>(null);
  const [reportError, setReportError] = useState(false);
  const [tab, setTab] = useState<Tab>('detail');
  const [focus, setFocus] = useState<{ page: number; chunkId?: string } | null>(null);
  const focusApplied = useRef('');

  const refresh = useCallback(async () => {
    const response = await listDocuments({ page, status: status || undefined });
    setDocuments(response.data.items);
    setTotal(response.data.meta.total);
    setTotalPages(response.data.meta.total_pages);
  }, [page, status]);

  useEffect(() => {
    const id = window.setTimeout(() => { void refresh().catch(() => {}); }, 0);
    return () => window.clearTimeout(id);
  }, [refresh]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const documentId = params.get('document');
    if (!documentId || focusApplied.current === documentId) return;
    focusApplied.current = documentId;
    const page = Number(params.get('page')) || 1;
    const chunkId = params.get('chunkId') || undefined;
    setFocus({ page, chunkId });
    const activate = async (document: Document) => {
      setSelected(document);
      setTab('preview');
      setReport(null);
      setReportError(false);
      try {
        setReport((await getQualityReport(document.id)).data);
      } catch {
        setReportError(true);
      }
    };
    const fromList = documents.find((item) => item.id === documentId);
    if (fromList) {
      void activate(fromList);
    } else {
      void getDocument(documentId)
        .then((response) => activate(response.data))
        .catch(() => setReportError(true));
    }
  }, [documents]);

  // 只在布尔值变化时重建定时器；15 秒一次并在页面隐藏时暂停，
  // 失败按 15/30/60 秒退避，避免处理期间持续打满限流额度。
  const hasProcessing = documents.some((document) => document.status === 'processing');
  useEffect(() => {
    if (!hasProcessing) return;
    let active = true;
    let timer = 0;
    let failures = 0;
    const tick = async () => {
      if (!active) return;
      if (document.visibilityState === 'hidden') {
        timer = window.setTimeout(() => void tick(), 15000);
        return;
      }
      try {
        await refresh();
        failures = 0;
      } catch {
        failures = Math.min(failures + 1, 3);
      }
      if (active) {
        timer = window.setTimeout(
          () => void tick(),
          Math.min(15000 * 2 ** failures, 120000),
        );
      }
    };
    timer = window.setTimeout(() => void tick(), 15000);
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void tick(), 0);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      active = false;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [hasProcessing, refresh]);

  async function open(document: Document) {
    setSelected(document);
    setTab('detail');
    setFocus(null);
    setReport(null);
    setReportError(false);
    try {
      setReport((await getQualityReport(document.id)).data);
    } catch {
      setReportError(true);
    }
  }

  function close() {
    setSelected(null);
    setReport(null);
    setReportError(false);
    setFocus(null);
  }

  return (
    <main className="page documents-page">
      <PageHeader
        eyebrow="WORKSPACE / 02"
        title="文档与质量"
        description="上传资料、检查处理状态，并在同一视图内核对质量报告与页面原文。"
        actions={
          <label className="field status-filter">
            <span className="sr-only">按状态筛选</span>
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              {STATUS_FILTERS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
        }
        meta={`第 ${page} / ${Math.max(totalPages, 1)} 页 · 共 ${total} 篇`}
      />

      <CardGrid>
        <CardStack span={5}>
          <Card
            eyebrow="INGEST / 01"
            title="上传文档"
            description="默认固定大小切分，可按需调整切分参数。"
          >
            <UploadForm onUploaded={() => void refresh()} />
          </Card>

          <Card
            eyebrow="INDEX / 02"
            title="文档列表"
            description="选择文档后，右侧会展示详情、质量与页面预览。"
            actions={<span className="chart-note">{total} 篇</span>}
          >
            {documents.length === 0 ? (
              <EmptyState title="暂无文档">
                {status ? '该状态下没有文档，换个筛选条件试试。' : '上传第一份职业健康文档开始建立知识库。'}
              </EmptyState>
            ) : (
              <ul className="document-list" aria-live="polite">
                {documents.map((document) => (
                  <li key={document.id}>
                    <button
                      className={`document-item${selected?.id === document.id ? ' is-active' : ''}`}
                      onClick={() => void open(document)}
                      aria-current={selected?.id === document.id ? 'true' : undefined}
                    >
                      <span className="document-item-head">
                        <strong>{document.title}</strong>
                        <StatusBadge value={document.status} />
                      </span>
                      <span className="document-item-meta">
                        {document.category?.name ?? '未设场景'}
                        {document.tags.length > 0 && ` · ${document.tags.map((tag) => tag.name).join('、')}`}
                        {` · ${formatDate(document.created_at)}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
          </Card>
        </CardStack>

        <Card
          span={7}
          eyebrow="INSPECT / 03"
          title={selected ? selected.title : '文档详情'}
          description={selected ? '在同一张卡片内切换详情、质量报告与页面预览。' : '从左侧列表选择一篇文档开始检查。'}
          actions={selected ? <Button variant="secondary" onClick={close}>关闭</Button> : undefined}
        >
          {!selected ? (
            <EmptyState title="未选择文档">
              左侧列表中的每一篇文档都可在此核对切分结果、质量指标与页面文本。
            </EmptyState>
          ) : (
            <>
              <div className="tabs" role="tablist" aria-label="文档信息">
                {TABS.map((item) => (
                  <button
                    key={item.value}
                    role="tab"
                    aria-selected={tab === item.value}
                    className={`tab${tab === item.value ? ' is-active' : ''}`}
                    onClick={() => setTab(item.value)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              {tab === 'detail' && <DocumentDetail document={selected} />}
              {tab === 'quality' && (
                report ? (
                  <QualityReportView report={report} />
                ) : (
                  <p className="hint">{reportError ? '该文档尚未生成质量报告（可能仍在处理中）。' : '加载中…'}</p>
                )
              )}
              {tab === 'preview' && (
                report ? (
                  <PagePreview
                    documentId={selected.id}
                    pageCount={report.page_count}
                    initialPage={focus?.page}
                    chunkId={focus?.chunkId}
                  />
                ) : (
                  <p className="hint">{reportError ? '暂无页面可预览。' : '加载中…'}</p>
                )
              )}
            </>
          )}
        </Card>
      </CardGrid>
    </main>
  );
}
