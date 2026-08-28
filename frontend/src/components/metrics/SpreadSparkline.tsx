import React from 'react';

export const SpreadSparkline: React.FC<{ values?: number[]; width?: number; height?: number }> = ({
  values = [],
  width = 110,
  height = 24,
}) => {
  if (values.length < 2) {
    return <span style={{ fontSize: '10px', color: '#676b78' }}>waiting for ticks</span>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const pathD = `M ${points.join(' L ')}`;
  const fillD = `${pathD} L ${width} ${height} L 0 ${height} Z`;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
      <path d={fillD} fill="rgba(56, 189, 248, 0.15)" />
      <path d={pathD} fill="none" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
};
