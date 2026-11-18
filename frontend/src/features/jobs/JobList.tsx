import { useEffect, useState } from 'react';
import {
  jobDisplayName,
  JOB_STAGE_LABELS,
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  listJobs,
  type Job,
} from '../../services/jobs';
import { StatusBadge } from '../../components/ui';

export function JobList() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [keyword, setKeyword] = useState('');

  useEffect(() => {
    const id = window.setTimeout(() => void listJobs({ page_size: 50 }).then((r) => setJobs(r.data.items)).catch(() => {}), 0);
    return () => window.clearTimeout(id);
  }, []);

  if (jobs.length === 0) return <p className="hint">暂无处理任务</p>;

  const query = keyword.trim().toLowerCase();
  const visible = query
    ? jobs.filter((job) => {
        const type = JOB_TYPE_LABELS[job.job_type] ?? job.job_type;
        const status = JOB_STATUS_LABELS[job.status] ?? job.status;
        return `${jobDisplayName(job)} ${type} ${status}`.toLowerCase().includes(query);
      })
    : jobs;

  return (
    <>
      <div className="list-toolbar">
        <input
          className="list-search"
          type="search"
          autoComplete="off"
          spellCheck={false}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索文件名 / 类型 / 状态"
          aria-label="搜索处理任务"
        />
        <span className="hint">{visible.length}/{jobs.length}</span>
      </div>
      {visible.length === 0 ? (
        <p className="hint">没有匹配的任务</p>
      ) : (
        <ul className="document-list is-scrollable" aria-live="polite">
          {visible.map((job) => {
            const name = jobDisplayName(job);
            return (
              <li key={job.id} className="document-item">
                <span className="job-item-main">
                  <strong className="job-item-name" title={name}>{name}</strong>
                  <span className="job-item-meta">
                    {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
                    {' · 阶段 '}{JOB_STAGE_LABELS[job.current_stage] ?? job.current_stage}
                    {` · ${job.processed_pages}/${job.total_pages} 页`}
                  </span>
                </span>
                <StatusBadge value={job.status} />
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
