import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { AuthGate } from '../features/auth/AuthGate';
import { Button } from '../components/ui';
import { api } from '../services/http';
import { subscribePendingJobs } from '../services/pendingJobs';
import { DashboardPage } from '../pages/DashboardPage';
import { DocumentsPage } from '../pages/DocumentsPage';
import { SearchPage } from '../pages/SearchPage';
import { AdminPage } from '../pages/AdminPage';
import { AccessPage } from '../pages/AccessPage';
import { ChunkReviewPage } from '../pages/ChunkReviewPage';

function PendingReviewBadge() {
  const [count, setCount] = useState(0);
  useEffect(() => subscribePendingJobs((jobs) => setCount(jobs.length)), []);
  return count > 0 ? <span className="nav-badge" aria-label={`${count} 个任务待确认`}>{count}</span> : null;
}

export function App() {
  return (
    <AuthGate>
      {(principal) => (
        <div className="app-shell">
          <a className="skip-link" href="#main-content">跳到主要内容</a>
          <aside className="app-sidebar">
            <NavLink className="sidebar-brand" to="/" aria-label="职业健康知识库首页">
              职业健康知识库
            </NavLink>
            <nav className="sidebar-nav" aria-label="主导航">
              <NavLink to="/" end>首页</NavLink>
              <NavLink to="/documents">文档与质量</NavLink>
              <NavLink to="/review" className="nav-with-badge">切分确认<PendingReviewBadge /></NavLink>
              <NavLink to="/search">混合检索</NavLink>
              {principal.role === 'admin' && <NavLink to="/admin">运营管理</NavLink>}
              {principal.role === 'admin' && <NavLink to="/access">接入管理</NavLink>}
            </nav>
            <div className="sidebar-footer">
              <span className="sidebar-user">
                {principal.name}
                {principal.role === 'admin' && principal.name !== '管理员' ? '（管理员）' : ''}
              </span>
              <Button variant="secondary" onClick={() => void api('/auth/logout', { method: 'POST' }).then(() => window.location.reload())}>退出登录</Button>
            </div>
          </aside>
          <main className="app-main" id="main-content">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/documents/:documentId" element={<DocumentsPage />} />
              <Route path="/review" element={<ChunkReviewPage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="/access" element={<AccessPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      )}
    </AuthGate>
  );
}
