import { useEffect, useState, type CSSProperties } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { NavLink } from 'react-router-dom';
import {
  autoClassifyDocuments,
  exportDocuments,
  type Category,
  type Document,
  type Tag,
} from '../services/documents';
import { getDashboardSummary } from '../services/dashboard';
import {
  Alert,
  Button,
  Card,
  CardGrid,
  EmptyState,
  Metric,
  PageHeader,
  StatusBadge,
} from '../components/ui';
import { subscribePendingJobs } from '../services/pendingJobs';
import { jobDisplayName, type Job } from '../services/jobs';

interface TagGroup {
  tag: Tag;
  documents: Document[];
}

const TAG_COLORS = ['#0f6b53', '#2a8f74', '#b8860b', '#7c3aed', '#0e7c86', '#c2410c', '#be185d'];

function colorFor(index: number): string {
  return TAG_COLORS[index % TAG_COLORS.length] ?? '#0f6b53';
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const [pendingJobs, setPendingJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  useEffect(() => subscribePendingJobs(setPendingJobs), []);

  // 汇总接口一次返回总数、状态、分类、标签与最近文档，避免多请求互相拖累。
  const summaryQuery = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: getDashboardSummary,
    staleTime: 20_000,
    retry: false,
  });

  const summary = summaryQuery.data?.data;
  const documents: Document[] = summary?.recent_documents ?? [];
  const categories: Category[] = summary?.categories ?? [];
  const tags: Tag[] = summary?.tags ?? [];

  async function runAutoClassify() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await autoClassifyDocuments();
      setNotice(
        `已检查 ${response.data.documents} 篇文档：更新场景 ${response.data.category_updated} 篇，新增标签 ${response.data.tags_linked ?? 0} 个`,
      );
      await queryClient.invalidateQueries();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '自动归类失败');
    } finally {
      setBusy(false);
    }
  }

  async function runExport() {
    setExporting(true);
    setError('');
    try {
      const blob = await exportDocuments();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const stamp = new Date().toISOString().slice(0, 10).replaceAll('-', '');
      link.href = url;
      link.download = `职业健康知识库文档清单-${stamp}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice('文档清单已导出，可用 Excel 直接打开。');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '文档清单导出失败');
    } finally {
      setExporting(false);
    }
  }

  const total = summary?.total ?? documents.length;
  const statusCounts = summary?.status_counts ?? {};
  const searchable = statusCounts.searchable ?? 0;
  const processing = statusCounts.processing ?? 0;
  const needsReview = statusCounts.needs_review ?? 0;

  const categoryRows = (summary?.categories ?? [])
    .filter((category) => category.active && category.count > 0)
    .sort((a, b) => b.count - a.count)
    .map((category) => ({ category, count: category.count }));

  const tagGroups: TagGroup[] = tags
    .map((tag) => ({
      tag,
      documents: documents
        .filter((d) => d.tags.some((t) => t.id === tag.id))
        .sort((a, b) => (b.updated_at < a.updated_at ? -1 : 1)),
    }))
    .filter((group) => group.documents.length > 0)
    .sort((a, b) => b.documents.length - a.documents.length);

  const untagged = documents
    .filter((d) => d.tags.length === 0)
    .sort((a, b) => (b.updated_at < a.updated_at ? -1 : 1));

  const maxCategory = categoryRows.reduce((max, row) => Math.max(max, row.count), 0);
  const statusRows = [
    { label: '可检索', value: searchable, tone: 'ready' },
    { label: '待确认', value: pendingJobs.length, tone: 'active' },
    { label: '处理中', value: processing, tone: 'active' },
    { label: '需复核', value: needsReview, tone: 'review' },
  ];

  return (
    <main className="page dashboard">
      <PageHeader
        eyebrow="WORKSPACE / 01"
        title="知识库概览"
        description="按职业病场景、危害因素与作业环节快速浏览知识库。"
        actions={
          <div className="page-head-actions">
            <Button variant="secondary" loading={exporting} onClick={() => void runExport()}>
              导出文档清单
            </Button>
            <NavLink className="button button-primary" to="/documents">上传文档</NavLink>
          </div>
        }
        meta={`${total} 篇文档 · ${categories.length} 个场景 · ${tags.length} 个标签`}
      />

      {pendingJobs.length > 0 && (
        <div className="review-banner" role="status">
          <span className="review-banner-badge" aria-hidden="true">{pendingJobs.length}</span>
          <span className="review-banner-text">
            <strong>有 {pendingJobs.length} 个文档等待确认切分</strong>
            <span className="review-banner-files">
              {pendingJobs.slice(0, 2).map((job) => jobDisplayName(job)).join('、')}
              {pendingJobs.length > 2 ? ` 等 ${pendingJobs.length} 个文件` : ''}
            </span>
          </span>
          <NavLink
            className="button button-primary review-banner-action"
            to={`/review${pendingJobs[0] ? `?job=${pendingJobs[0].id}` : ''}`}
          >
            去确认切分
          </NavLink>
        </div>
      )}

      {error && <Alert tone="danger">{error}</Alert>}

      {summaryQuery.isPending ? (
        <Card title="正在载入"><p className="hint">正在同步文档、分类与标签…</p></Card>
      ) : summaryQuery.isError ? (
        <Card title="无法加载知识库">
          <EmptyState title="数据加载失败">
            {summaryQuery.error instanceof Error
              ? summaryQuery.error.message
              : '加载失败，请稍后重试。'}
          </EmptyState>
          <Button variant="secondary" onClick={() => void summaryQuery.refetch()}>
            重试
          </Button>
        </Card>
      ) : total === 0 ? (
        <Card
          span={12}
          eyebrow="COLLECTION OVERVIEW"
          title="资料总览"
          description="文档完成解析、切分与向量化后，统计与标签分区会自动出现在这里。"
        >
          <EmptyState title="知识库还是空的">
            上传第一份职业健康文档，即可开始建立可检索的专业资料库。
          </EmptyState>
        </Card>
      ) : (
        <CardGrid>
          <Card
            span={12}
            tone="accent"
            eyebrow="COLLECTION OVERVIEW"
            title="资料总览"
            description="所有文档均经过解析、切分、向量化与质量门禁后进入检索。"
            className="hero-card"
          >
            <div className="hero-layout">
              <div>
                <div className="hero-total">
                  <strong>{total}</strong>
                  <span>篇已归档文档</span>
                </div>
                <p className="hero-note">
                  当前索引覆盖 {categoryRows.length} 个场景、{tagGroups.length + (untagged.length ? 1 : 0)} 个标签分区。
                </p>
              </div>
              <div className="metric-row">
                <Metric label="可检索" value={searchable} hint="已完成向量化" />
                <Metric
                  label="待确认"
                  value={pendingJobs.length}
                  hint="需人工确认切分"
                  emphasis={pendingJobs.length > 0}
                />
                <Metric label="处理中" value={processing} hint="解析或向量化" />
                <Metric
                  label="需复核"
                  value={needsReview}
                  hint="质量门禁未通过"
                  emphasis={needsReview > 0}
                />
              </div>
            </div>
          </Card>

          <Card
            span={7}
            eyebrow="DISTRIBUTION / 02"
            title="场景分布"
            description={`${categoryRows.length} 个职业病场景包含文档，按数量降序排列`}
            actions={<span className="chart-note">单位：篇</span>}
          >
            {categoryRows.length === 0 ? (
              <p className="hint">暂无场景数据，上传后系统会自动归类到职业病场景。</p>
            ) : (
              <ol className="category-bars" role="img" aria-label={`场景分布，共 ${total} 篇文档`}>
                {categoryRows.map((row) => (
                  <li key={row.category.id} className="category-bar">
                    <span className="category-name">{row.category.name}</span>
                    <span className="category-track">
                      <span
                        className="category-fill"
                        style={{ width: `${maxCategory ? (row.count / maxCategory) * 100 : 0}%` }}
                      />
                    </span>
                    <span className="category-count">{row.count}</span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card
            span={5}
            eyebrow="PIPELINE / 03"
            title="处理状态"
            description="从上传到可检索的流转情况"
            actions={<span className="chart-note">占总文档比例</span>}
          >
            <ol className="category-bars" aria-label="文档处理状态分布">
              {statusRows.map((row) => (
                <li key={row.label} className="category-bar">
                  <span className="category-name">{row.label}</span>
                  <span className="category-track">
                    <span
                      className={`category-fill status-fill-${row.tone}`}
                      style={{ width: `${total ? (row.value / total) * 100 : 0}%` }}
                    />
                  </span>
                  <span className="category-count">{row.value}</span>
                </li>
              ))}
            </ol>
            <p className="hint">切分完成后需人工确认，确认后才会向量化并加入检索索引。</p>
          </Card>

          <Card
            span={12}
            eyebrow="LIBRARY / 04"
            title="按标签浏览"
            description="同一标签下的文档按更新时间排列，点击可前往文档与质量页查看详情。"
            actions={
              <Button variant="secondary" loading={busy} onClick={() => void runAutoClassify()}>
                自动归类现有文档
              </Button>
            }
          >
            {notice && <Alert tone="info">{notice}</Alert>}
            {untagged.length > 0 && (
              <TagSection label="未分类" documents={untagged} color="#64748b" />
            )}
            {tagGroups.map((group, index) => (
              <TagSection
                key={group.tag.id}
                label={group.tag.name}
                documents={group.documents}
                color={colorFor(index)}
              />
            ))}
          </Card>
        </CardGrid>
      )}
    </main>
  );
}

function TagSection({
  label,
  documents,
  color,
}: {
  label: string;
  documents: Document[];
  color: string;
}) {
  return (
    <section className="tag-section card-section" style={{ '--tag-color': color } as CSSProperties}>
      <header className="tag-section-head">
        <span className="tag-marker" aria-hidden="true" />
        <h3 className="card-section-title">{label}</h3>
        <span className="tag-count">{documents.length}</span>
      </header>
      <ul className="doc-rows">
        {documents.map((doc) => (
          <li key={doc.id}>
            <NavLink className="doc-row" to="/documents">
              <span className="doc-title">{doc.title}</span>
              <span className="doc-meta">
                {doc.category?.name && <span className="doc-category">{doc.category.name}</span>}
                <StatusBadge value={doc.status} />
                {doc.updated_at && <time className="doc-date">{formatDate(doc.updated_at)}</time>}
              </span>
            </NavLink>
          </li>
        ))}
      </ul>
    </section>
  );
}
