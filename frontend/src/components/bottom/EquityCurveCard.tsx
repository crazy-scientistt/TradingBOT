import React, { useMemo, useState } from 'react';
import { EquityDataPoint } from '../../types/dashboard';

interface EquityCurveCardProps {
  data: EquityDataPoint[];
}

const RANGE_DAYS: Record<string, number | null> = {
  '7D': 7,
  '30D': 30,
  '90D': 90,
  ALL: null,
};

function stamp(point: EquityDataPoint): number {
  const parsed = Date.parse(point.date);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatTick(iso: string): string {
  const parsed = Date.parse(iso);
  if (!Number.isFinite(parsed)) return iso.slice(0, 10);
  return new Date(parsed).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export const EquityCurveCard: React.FC<EquityCurveCardProps> = ({ data }) => {
  const [activeRange, setActiveRange] = useState('30D');
  const ranges = ['7D', '30D', '90D', 'ALL'];

  const series = useMemo(() => {
    const days = RANGE_DAYS[activeRange];
    if (days == null) return data;
    const cutoff = Date.now() - days * 86400000;
    return data.filter((point) => stamp(point) >= cutoff);
  }, [activeRange, data]);

  const width = 380;
  const height = 135;
  const rightAxisWidth = 32;
  const bottomAxisHeight = 20;
  const chartHeight = height - bottomAxisHeight;
  const chartWidth = width - rightAxisWidth;

  const values = series.map((point) => point.value).filter((value) => Number.isFinite(value));
  const yMinRaw = values.length ? Math.min(...values) : 0;
  const yMaxRaw = values.length ? Math.max(...values) : 1;
  const pad = Math.max((yMaxRaw - yMinRaw) * 0.08, 0.5);
  const yMin = yMinRaw - pad;
  const yMax = yMaxRaw + pad;
  const yLevels = [yMax, (yMin + yMax) / 2, yMin];

  const getX = (index: number) => {
    if (series.length <= 1) return 12;
    return 12 + (index / (series.length - 1)) * (chartWidth - 24);
  };
  const getY = (val: number) =>
    chartHeight - ((val - yMin) / (yMax - yMin || 1)) * (chartHeight - 12) - 4;

  const linePath = series.reduce((acc, pt, idx, arr) => {
    const x = getX(idx);
    const y = getY(pt.value);
    if (idx === 0) return `M ${x} ${y}`;
    const prevX = getX(idx - 1);
    const prevY = getY(arr[idx - 1].value);
    const cp1x = prevX + (x - prevX) / 2;
    return `${acc} C ${cp1x} ${prevY}, ${cp1x} ${y}, ${x} ${y}`;
  }, '');

  const dateLabels =
    series.length === 0
      ? []
      : series.length === 1
        ? [{ label: formatTick(series[0].date), idx: 0 }]
        : [
            { label: formatTick(series[0].date), idx: 0 },
            { label: formatTick(series[Math.floor(series.length / 2)].date), idx: Math.floor(series.length / 2) },
            { label: formatTick(series[series.length - 1].date), idx: series.length - 1 },
          ];

  return (
    <div className="dashboard-card" style={{ flex: 1.15, padding: '10px 14px', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', flexShrink: 0 }}>
        <span style={{ fontSize: '11px', fontWeight: 700, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          EQUITY CURVE (PAPER)
        </span>
        <div style={{ display: 'flex', gap: '10px' }}>
          {ranges.map((r) => {
            const isActive = r === activeRange;
            return (
              <button
                key={r}
                type="button"
                onClick={() => setActiveRange(r)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: isActive ? 'var(--gold-primary)' : '#676b78',
                  fontSize: '11px',
                  fontWeight: isActive ? 700 : 500,
                  cursor: 'pointer',
                  padding: '2px 0',
                  position: 'relative',
                }}
              >
                {r}
                {isActive && (
                  <span style={{
                    position: 'absolute',
                    bottom: '-2px',
                    left: 0,
                    right: 0,
                    height: '2px',
                    backgroundColor: 'var(--gold-primary)',
                    borderRadius: '1px',
                  }} />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {series.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#676b78', fontSize: '12px', textAlign: 'center', padding: '18px 8px' }}>
          No paper equity snapshots yet. The curve appears after the bot records real account marks.
        </div>
      ) : (
        <div style={{ width: '100%', height: '135px' }}>
          <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: '100%', overflow: 'visible' }}>
            {yLevels.map((lvl) => {
              const y = getY(lvl);
              return (
                <g key={`eq-lvl-${lvl}`}>
                  <line x1={12} y1={y} x2={chartWidth - 5} y2={y} stroke="#151619" strokeWidth="1" />
                  <text x={width - 24} y={y + 3.5} fill="#676b78" fontSize="9.5" fontFamily="var(--font-mono)" textAnchor="start">
                    {lvl.toFixed(lvl >= 100 ? 0 : 2)}
                  </text>
                </g>
              );
            })}
            <path
              d={linePath}
              fill="none"
              stroke="var(--gold-primary)"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {series.length === 1 && (
              <>
                <line
                  x1={12}
                  y1={getY(series[0].value)}
                  x2={chartWidth - 5}
                  y2={getY(series[0].value)}
                  stroke="var(--gold-primary)"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
                <circle
                  cx={getX(0)}
                  cy={getY(series[0].value)}
                  r={3}
                  fill="var(--gold-primary)"
                />
              </>
            )}
            {dateLabels.map((d) => (
              <text
                key={`eq-date-${d.label}-${d.idx}`}
                x={getX(d.idx)}
                y={height - 2}
                fill="#676b78"
                fontSize="9.5"
                fontFamily="var(--font-sans)"
                textAnchor="middle"
              >
                {d.label}
              </text>
            ))}
          </svg>
        </div>
      )}
    </div>
  );
};
