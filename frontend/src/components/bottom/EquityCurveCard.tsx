import React, { useState } from 'react';
import { EquityDataPoint } from '../../types/dashboard';

interface EquityCurveCardProps {
  data: EquityDataPoint[];
}

export const EquityCurveCard: React.FC<EquityCurveCardProps> = ({ data }) => {
  const [activeRange, setActiveRange] = useState('30D');
  const ranges = ['7D', '30D', '90D', 'ALL'];

  const width = 380;
  const height = 135;
  const rightAxisWidth = 32;
  const bottomAxisHeight = 20;
  const chartHeight = height - bottomAxisHeight;
  const chartWidth = width - rightAxisWidth;

  const yMin = 88;
  const yMax = 112;
  const yLevels = [110, 105, 100, 95, 90];

  const getX = (index: number) => {
    return 12 + (index / (data.length - 1)) * (chartWidth - 24);
  };

  const getY = (val: number) => {
    return chartHeight - ((val - yMin) / (yMax - yMin)) * (chartHeight - 12) - 4;
  };

  // Build path with smooth bezier curves
  const linePath = data.reduce((acc, pt, idx, arr) => {
    const x = getX(idx);
    const y = getY(pt.value);
    if (idx === 0) return `M ${x} ${y}`;
    
    const prevX = getX(idx - 1);
    const prevY = getY(arr[idx - 1].value);
    const cp1x = prevX + (x - prevX) / 2;
    const cp1y = prevY;
    const cp2x = prevX + (x - prevX) / 2;
    const cp2y = y;
    return `${acc} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${x} ${y}`;
  }, '');

  const baseline100Y = getY(100);

  const dateLabels = [
    { label: 'Apr 21', idx: 0 },
    { label: 'Apr 28', idx: 2 },
    { label: 'May 5', idx: 4 },
    { label: 'May 12', idx: 7 },
    { label: 'May 19', idx: 10 }
  ];

  return (
    <div className="dashboard-card" style={{ flex: 1.15, padding: '10px 14px', minHeight: '175px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <span style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          EQUITY CURVE (PAPER)
        </span>
        <div style={{ display: 'flex', gap: '10px' }}>
          {ranges.map((r) => {
            const isActive = r === activeRange;
            return (
              <button
                key={r}
                onClick={() => setActiveRange(r)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: isActive ? '#f0b90b' : '#64748b',
                  fontSize: '11px',
                  fontWeight: isActive ? 700 : 500,
                  cursor: 'pointer',
                  padding: '2px 0',
                  position: 'relative'
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
                    backgroundColor: '#f0b90b',
                    borderRadius: '1px'
                  }} />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* SVG Line Chart */}
      <div style={{ width: '100%', height: '135px' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: '100%', overflow: 'visible' }}>
          <defs>
            <filter id="goldGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="1.2" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Grid lines & Y-Axis Labels */}
          {yLevels.map((lvl) => {
            const y = getY(lvl);
            const is100 = lvl === 100;
            return (
              <g key={`eq-lvl-${lvl}`}>
                <line
                  x1={12}
                  y1={y}
                  x2={chartWidth - 5}
                  y2={y}
                  stroke={is100 ? '#263042' : '#171c26'}
                  strokeWidth="1"
                  strokeDasharray={is100 ? '3 3' : undefined}
                />
                <text
                  x={width - 24}
                  y={y + 3.5}
                  fill="#64748b"
                  fontSize="9.5"
                  fontFamily="var(--font-mono)"
                  textAnchor="start"
                >
                  {lvl}
                </text>
              </g>
            );
          })}

          {/* Baseline 100 line */}
          <line
            x1={12}
            y1={baseline100Y}
            x2={chartWidth - 5}
            y2={baseline100Y}
            stroke="#2c3649"
            strokeWidth="1"
            strokeDasharray="3 3"
          />

          {/* Glowing Golden Equity Line */}
          <path
            d={linePath}
            fill="none"
            stroke="#f0b90b"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#goldGlow)"
          />

          {/* X-Axis Date Ticks */}
          {dateLabels.map((d) => {
            const x = getX(d.idx);
            return (
              <text
                key={`eq-date-${d.label}`}
                x={x}
                y={height - 2}
                fill="#64748b"
                fontSize="9.5"
                fontFamily="var(--font-sans)"
                textAnchor="middle"
              >
                {d.label}
              </text>
            );
          })}
        </svg>
      </div>
    </div>
  );
};
