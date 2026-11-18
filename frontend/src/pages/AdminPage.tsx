import { useCallback, useEffect, useState } from 'react';
import { DocumentManagement } from '../features/documents/DocumentManagement';
import { MaskingCorrection } from '../features/documents/MaskingCorrection';
import { QualityExport } from '../features/documents/QualityExport';

import { VersionHistory } from '../features/documents/VersionHistory';
import { JobList } from '../features/jobs/JobList';
import { listDocuments, type Document } from '../services/documents';
import { Card, CardGrid, PageHeader } from '../components/ui';

export function AdminPage() {
  const [documents, setDocuments] = useState<Document[]>([]);

  const refresh = useCallback(async () => {
    const response = await listDocuments({ page_size: 100 });
    setDocuments(response.data.items);
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(id);
  }, [refresh]);

  return (
    <main className="page admin-page">
      <PageHeader
        eyebrow="WORKSPACE / 04"
        title="运营管理"
        description="任务、文档版本、质量导出与标签维护集中在同一套卡片里，左右严格对齐。"
        meta={`${documents.length} 篇文档纳入管理`}
      />

      <CardGrid>
        <Card
          span={7}
          eyebrow="OPS / 01"
          title="处理任务"
          description="查看解析、切分与向量化阶段的任务进度。"
        >
          <JobList />
        </Card>

        <Card
          span={5}
          eyebrow="OPS / 02"
          title="文档管理"
          description="对文档重新处理或移出知识库。"
        >
          <DocumentManagement onChanged={() => void refresh()} />
        </Card>

        {documents[0] && (
          <>
            <Card
              span={6}
              eyebrow="VERSION / 03"
              title="版本历史"
              description={`当前查看：${documents[0].title}`}
            >
              <VersionHistory documentId={documents[0].id} />
            </Card>

            <Card
              span={3}
              eyebrow="EXPORT / 04"
              title="质量导出"
              description="导出最近一次质量报告 JSON。"
            >
              <QualityExport documentId={documents[0].id} />
            </Card>

            <Card
              span={3}
              eyebrow="MASKING / 05"
              title="脱敏修正"
              description="修正专业术语误判后更新索引。"
            >
              <MaskingCorrection documentId={documents[0].id} />
            </Card>
          </>
        )}

      </CardGrid>
    </main>
  );
}
