import { useEffect, useState } from 'react';
import { search, type SearchResult } from '../services/search';
import { SearchFilters } from '../features/search/SearchFilters';
import { SearchForm, type Mode } from '../features/search/SearchForm';
import { SearchResults } from '../features/search/SearchResults';
import { loadSearchState, saveSearchState } from '../features/search/searchState';
import { Alert, Card, CardGrid, CardSection, PageHeader } from '../components/ui';

const MODE_TIPS: Record<Mode, string> = {
  hybrid: '同时结合语义向量与关键词召回，适合大多数查证场景。',
  semantic: '按语义相似度召回，适合描述性提问与同义表述。',
  keyword: '按精确词语匹配，适合法规编号、化学品名称等。',
};

export function SearchPage() {
  const initial = loadSearchState();
  const [query, setQuery] = useState(initial?.query ?? '');
  const [mode, setMode] = useState<Mode>(initial?.mode ?? 'hybrid');
  const [categoryId, setCategoryId] = useState(initial?.categoryId ?? '');
  const [tagId, setTagId] = useState(initial?.tagId ?? '');
  const [blockType, setBlockType] = useState(initial?.blockType ?? '');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [degraded, setDegraded] = useState(false);
  const [tookMs, setTookMs] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { saveSearchState({ query, mode, categoryId, tagId, blockType }); }, [query, mode, categoryId, tagId, blockType]);

  async function run() {
    setBusy(true);
    setError('');
    try {
      const filters = {
        ...(categoryId ? { category_ids: [categoryId] } : {}),
        ...(tagId ? { tag_ids: [tagId] } : {}),
        ...(blockType ? { block_types: [blockType] } : {}),
      };
      const response = await search({ query, mode, top_k: 5, filters });
      setResults(response.data.items);
      setDegraded(response.data.degraded);
      setTookMs(response.data.took_ms);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '检索失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page search-page">
      <PageHeader
        eyebrow="WORKSPACE / 03"
        title="混合检索"
        description="在同一张卡片里完成条件设置、过滤与结果核对，减少来回跳转。"
        meta={tookMs > 0 ? `上次检索 ${tookMs} ms` : '支持语义 / 关键词 / 混合三种模式'}
      />

      <CardGrid>
        <Card
          span={8}
          eyebrow="QUERY / 01"
          title="检索条件"
          description="输入问题或关键词，选择召回模式后可进一步限定职业病场景与标签。"
        >
          {error && <Alert tone="danger">{error}</Alert>}
          <SearchForm query={query} mode={mode} busy={busy} onQuery={setQuery} onMode={setMode} onSubmit={() => void run()} />
          <CardSection
            title="过滤条件"
            description="不选择时检索全部已发布文档"
          >
            <SearchFilters
              selectedCategory={categoryId}
              onCategory={setCategoryId}
              selectedTag={tagId}
              onTag={setTagId}
              selectedBlockType={blockType}
              onBlockType={setBlockType}
            />
          </CardSection>
        </Card>

        <Card
          span={4}
          eyebrow="GUIDE / 02"
          title="当前模式"
          description={MODE_TIPS[mode]}
          tone="muted"
        >
          <ul className="tip-list">
            <li><strong>语义</strong>适合「噪声作业如何防护」这类描述性问题。</li>
            <li><strong>关键词</strong>适合查 GBZ 编号、化学式或专有名词。</li>
            <li><strong>混合</strong>会用 RRF 融合两路召回，结果更稳健。</li>
          </ul>
          <p className="hint">检索结果中的页码可直接跳转到对应文档页面。</p>
        </Card>

        <Card
          span={12}
          eyebrow="RESULTS / 03"
          title="检索结果"
          description="结果按融合得分排序；命中表格时按整表展示并高亮命中行。"
          actions={results.length > 0 ? <span className="chart-note">{results.length} 条命中</span> : undefined}
        >
          <SearchResults results={results} degraded={degraded} tookMs={tookMs} />
        </Card>
      </CardGrid>
    </main>
  );
}
