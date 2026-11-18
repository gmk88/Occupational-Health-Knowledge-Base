import { useEffect, useState } from 'react';
import { listVersions, rollbackVersion, type DocumentVersion } from '../../services/documents';
import { Button } from '../../components/ui';

export function VersionHistory({ documentId }: { documentId: string }) {
  const [versions, setVersions] = useState<DocumentVersion[]>([]);

  useEffect(() => {
    const id = window.setTimeout(() => void listVersions(documentId).then((r) => setVersions(r.data)).catch(() => {}), 0);
    return () => window.clearTimeout(id);
  }, [documentId]);

  if (versions.length === 0) return <p className="hint">该文档暂无历史版本。</p>;

  return (
    <ul className="document-list">
      {versions.map((version) => (
        <li key={version.id} className="document-item">
          <span>v{version.version_number} · {version.status}</span>
          <Button variant="secondary" onClick={() => void rollbackVersion(documentId, version.version_number)}>回滚</Button>
        </li>
      ))}
    </ul>
  );
}
