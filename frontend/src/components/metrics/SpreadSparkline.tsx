import React from 'react';

export const SpreadSparkline: React.FC<{ width?: number; height?: number }> = ({
  width = 110,
  height = 24
}) => {
  // A smooth sine-wave-like curve matching the image
  const pathD = "M 0 16 C 18 20, 24 8, 38 12 C 52 16, 60 4, 76 8 C 90 12, 98 6, 110 5";
  const fillD = `${pathD} L 110 24 L 0 24 Z`;

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: 'visible' }}
    >
      <defs>
        <linearGradient id="spreadGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.0" />
        </linearGradient>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="1.5" result="glow" />
          <feComposite in="SourceGraphic" in2="glow" operator="over" />
        </filter>
      </defs>
      <path
        d={fillD}
        fill="url(#spreadGradient)"
      />
      <path
        d={pathD}
        fill="none"
        stroke="#38bdf8"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        filter="url(#glow)"
      />
    </svg>
  );
};
