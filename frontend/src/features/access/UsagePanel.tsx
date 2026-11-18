import { useCallback, useEffect, useState } from 'react';
import { Alert } from '../../components/ui';
import {
  getClientUsage,
  getUsageOverview,
  type ClientUsage,
  type DailyUsage,
  type UsageOverview,
} from '../../services/access';

function formatTime(value: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN');
}

function formatDay(value: string | null) {
  if (!value) return '';
  return value.slice(5).replace('-', '/');
}

function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
    date.getDate(),
  ).padStart(2, '0')}`;
}

// 后端只返回有调用的日期，这里补齐零值，曲线才能体现完整趋势。
function buildSeries(days: number, daily: DailyUsage[]): DailyUsage[] {
  const byDate = new Map(daily.map((item) => [item.date, item]));
  const series: DailyUsage[] = [];
  const today = new Date();
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const date = new Date(today);
    date.setDate(today.getDate() - offset);
    const key = localDateKey(date);
    series.push(byDate.get(key) ?? { date: key, calls: 0, avg_ms: 0 });
  }
  return series;
}

function TrendChart({ points, caption }: { points: DailyUsage[]; caption: string }) {
  if (points.length === 0 || points.every((item) => item.calls === 0)) {
    return <p className="hint usage-chart-empty">该时间段还没有调用记录</p>;
  }
  const width = 720;
  const height = 190;
  const padX = 42;
  const padY = 26;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const max = Math.max(1, ...points.map((item) => item.calls));
  const step = points.length > 1 ? innerW / (points.length - 1) : 0;
  const coords = points.map((item, index) => {
    const x = points.length > 1 ? padX + index * step : padX + innerW / 2;
    const y = padY + innerH - (item.calls / max) * innerH;
    return [x, y] as const;
  });
  const line = coords
    .map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  const [firstX] = coords[0] ?? [padX];
  const [lastX, lastY] = coords[coords.length - 1] ?? [padX, padY + innerH];
  const area = `${line} L${lastX.toFixed(1)},${(padY + innerH).toFixed(1)} L${firstX.toFixed(1)},${(padY + innerH).toFixed(1)} Z`;
  const gridValues = [max, Math.round(max / 2), 0];
  const marks = points.length > 1 ? [0, Math.floor((points.length - 1) / 2), points.length - 1] : [0];

  return (
    <div className="usage-chart">
      <div className="usage-chart-head">
        <strong>调用趋势</strong>
        <span className="hint">{caption}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={caption}>
        <defs>
          <linearGradient id="usage-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0f6b53" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#0f6b53" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {gridValues.map((value) => {
          const y = padY + innerH - (value / max) * innerH;
          return (
            <g key={value}>
              <line
                x1={padX}
                x2={width - padX}
                y1={y}
                y2={y}
                stroke="var(--color-border, #d8e3de)"
                strokeDasharray={value === 0 ? undefined : '4 6'}
              />
              <text x={padX - 10} y={y + 4} textAnchor="end" className="usage-chart-axis">
                {value}
              </text>
            </g>
          );
        })}
        <path d={area} fill="url(#usage-area)" />
        <path d={line} fill="none" stroke="#0f6b53" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {coords.map(([x, y], index) => (
          <circle key={index} cx={x} cy={y} r={3.5} fill="#fff" stroke="#0f6b53" strokeWidth="2" />
        ))}
        <circle cx={lastX} cy={lastY} r={4.5} fill="#0f6b53" />
        {marks.map((index) => {
          const point = points[index];
          const [x] = coords[index] ?? [padX];
          return (
            <text key={index} x={x} y={height - 6} textAnchor="middle" className="usage-chart-axis">
              {formatDay(point?.date ?? null)}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

export function UsagePanel() {
  const [days, setDays] = useState(7);
  const [overview, setOverview] = useState<UsageOverview | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClientUsage | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const response = await getUsageOverview(days);
    setOverview(response.data);
  }, [days]);

  useEffect(() => {
    void load().catch((caught) =>
      setError(caught instanceof Error ? caught.message : '加载用量失败'),
    );
  }, [load]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let active = true;
    void getClientUsage(selected, days)
      .then((response) => {
        if (active) setDetail(response.data);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : '加载明细失败');
      });
    return () => {
      active = false;
    };
  }, [selected, days]);

  const clients = overview?.clients ?? [];
  const totalCalls = clients.reduce((sum, row) => sum + row.calls, 0);
  const weightedMs = clients.reduce((sum, row) => sum + row.avg_ms * row.calls, 0);
  const averageMs = totalCalls ? Math.round(weightedMs / totalCalls) : 0;
  const chartPoints = buildSeries(days, detail?.daily ?? overview?.daily ?? []);
  const chartCaption = detail
    ? `当前查看：${clients.find((row) => row.client_id === detail.client_id)?.name ?? '该接入方'}`
    : `全部接入方 · 最近 ${days} 天`;

  return (
    <div className="access-panel">
      {error && <Alert tone="danger">{error}</Alert>}

      <div className="usage-toolbar">
        <label className="field">
          <span>统计范围</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={7}>最近 7 天</option>
            <option value={14}>最近 14 天</option>
            <option value={30}>最近 30 天</option>
          </select>
        </label>
        <div className="usage-metrics">
          <span>调用 {detail?.calls ?? totalCalls} 次</span>
          <span>平均 {detail?.avg_ms ?? averageMs} ms</span>
          {detail && <span>P95 {detail.p95_ms} ms</span>}
          {detail && <span>命中率 {detail.success_rate}%</span>}
          {detail && <span>降级 {detail.degraded} 次</span>}
        </div>
        {selected && (
          <button type="button" className="link-button" onClick={() => setSelected(null)}>
            返回全部
          </button>
        )}
      </div>

      <TrendChart points={chartPoints} caption={chartCaption} />

      <div className="access-table-wrap">
        <table className="access-table">
          <thead>
            <tr>
              <th>接入方</th>
              <th>调用次数</th>
              <th>平均耗时</th>
              <th>限额/分钟</th>
              <th>最近调用</th>
            </tr>
          </thead>
          <tbody>
            {clients.length === 0 && (
              <tr>
                <td colSpan={5} className="hint">
                  还没有接入方
                </td>
              </tr>
            )}
            {clients.map((row) => (
              <tr
                key={row.client_id}
                className={selected === row.client_id ? 'is-selected' : undefined}
                onClick={() => setSelected(row.client_id)}
              >
                <td>
                  <strong>{row.name}</strong>
                  {row.status !== 'active' && <span className="hint">（已停用）</span>}
                </td>
                <td>{row.calls}</td>
                <td>{row.calls ? `${row.avg_ms} ms` : '—'}</td>
                <td>{row.rate_limit_per_minute}</td>
                <td>{formatTime(row.last_call_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
