import React, { useState } from 'react';
import { Maximize2 } from 'lucide-react';
import { Candle } from '../../types/dashboard';
import { ChartControls } from './ChartControls';

interface CandlestickChartProps {
  candles: Candle[];
}

export const CandlestickChart: React.FC<CandlestickChartProps> = ({ candles }) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [activeTf, setActiveTf] = useState('15m');
  const [scaleMode, setScaleMode] = useState('auto');

  const width = 840;
  const height = 310;
  const rightAxisWidth = 65;
  const bottomAxisHeight = 24;
  const volumeHeight = 55;
  const mainChartHeight = height - bottomAxisHeight - volumeHeight - 12;

  const lows = candles.map((c) => c.low);
  const highs = candles.map((c) => c.high);
  const minPrice = lows.length ? Math.min(...lows) : 0;
  const maxPrice = highs.length ? Math.max(...highs) : 0;
  const priceRange = maxPrice - minPrice || 1;
  const maxVolume = Math.max(...candles.map((c) => c.volume), 1);

  const currentCandle = hoverIndex !== null ? candles[hoverIndex] : candles[candles.length - 1];
  const lastCandle = candles[candles.length - 1];

  const getX = (index: number) => {
    const usableWidth = width - rightAxisWidth - 24;
    return 16 + (index / (candles.length - 1)) * usableWidth;
  };

  const getY = (price: number) => {
    return mainChartHeight - ((price - minPrice) / priceRange) * mainChartHeight + 8;
  };

  const getVolY = (volume: number) => {
    const volTop = height - bottomAxisHeight - volumeHeight;
    const h = (volume / maxVolume) * volumeHeight;
    return volTop + (volumeHeight - h);
  };

  const safeEmaPoints = (field: 'ema20' | 'ema50'): string => candles
    .map((c, idx) => ({ v: c[field], idx }))
    .filter((p) => p.v != null)
    .map((p) => ({ x: getX(p.idx), y: getY(p.v as number) }))
    .reduce((acc, p, i) => (i === 0 ? 'M ' + p.x + ' ' + p.y : acc + ' L ' + p.x + ' ' + p.y), '');

  const ema20Path = safeEmaPoints('ema20');
  const ema50Path = safeEmaPoints('ema50');

  const priceLevels = Array.from({ length: 6 }, (_, i) => minPrice + (priceRange * i) / 5);

  const timeTicks = [
    { label: '18:00', idx: 4 },
    { label: '21:00', idx: 10 },
    { label: '20', idx: 16, isDay: true },
    { label: '03:00', idx: 22 },
    { label: '06:00', idx: 28 },
    { label: '09:00', idx: 34 },
    { label: '12:00', idx: 40 },
    { label: '15:00', idx: candles.length - 1 }
  ];

  const currentPriceY = getY(lastCandle.close);

  return (
    <div className="dashboard-card" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      {/* Chart Top Header & Legend */}
      <div style={{
        padding: '10px 16px 6px 16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        borderBottom: '1px solid rgba(255, 255, 255, 0.04)'
      }}>
        <div>
          {/* Symbol Title & Timeframe */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
            <span style={{ fontSize: '14.5px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.01em' }}>
              PAXG / USDT · {activeTf}
            </span>
          </div>

          {/* OHLC and Change Summary */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            color: '#9498a4'
          }}>
            <span>O <span style={{ color: '#d1d5db' }}>{currentCandle.open.toFixed(2)}</span></span>
            <span>H <span style={{ color: '#d1d5db' }}>{currentCandle.high.toFixed(2)}</span></span>
            <span>L <span style={{ color: '#d1d5db' }}>{currentCandle.low.toFixed(2)}</span></span>
            <span>C <span style={{ color: '#22c55e', fontWeight: 600 }}>{currentCandle.close.toFixed(2)}</span></span>
          </div>

          {/* Indicators Legend */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            marginTop: '3px'
          }}>
            <span style={{ color: '#38bdf8', fontWeight: 500 }}>
              EMA 20 <span style={{ color: '#38bdf8' }}>{currentCandle.ema20 != null ? currentCandle.ema20.toFixed(2) : '—'}</span>
            </span>
            <span style={{ color: '#f59e0b', fontWeight: 500 }}>
              EMA 50 <span style={{ color: '#f59e0b' }}>{currentCandle.ema50 != null ? currentCandle.ema50.toFixed(2) : '—'}</span>
            </span>
          </div>
        </div>

        {/* Right side: Large Price Display + Expand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '17px',
            fontWeight: 700,
            color: '#f8fafc',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '-0.02em'
          }}>
            {lastCandle.close.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <button style={{
            background: 'transparent',
            border: 'none',
            color: '#9498a4',
            cursor: 'pointer',
            padding: '4px',
            display: 'flex',
            alignItems: 'center',
            borderRadius: '4px'
          }} title="Fullscreen Chart">
            <Maximize2 size={15} />
          </button>
        </div>
      </div>

      {/* Main SVG Candlestick Canvas */}
      <div style={{ position: 'relative', width: '100%', height: '310px', backgroundColor: '#0b0c0e' }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ width: '100%', height: '100%', display: 'block', overflow: 'hidden' }}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const mouseX = ((e.clientX - rect.left) / rect.width) * width;
            const usableWidth = width - rightAxisWidth - 24;
            const approxIdx = Math.round(((mouseX - 16) / usableWidth) * (candles.length - 1));
            if (approxIdx >= 0 && approxIdx < candles.length) {
              setHoverIndex(approxIdx);
            }
          }}
          onMouseLeave={() => setHoverIndex(null)}
        >
          {/* Grid Lines - pure neutral dark */}
          {priceLevels.map((lvl) => {
            const y = getY(lvl);
            return (
              <g key={`grid-lvl-${lvl}`}>
                <line
                  x1={10}
                  y1={y}
                  x2={width - rightAxisWidth}
                  y2={y}
                  stroke="#17181c"
                  strokeWidth="1"
                  strokeDasharray="2 3"
                />
                {/* Price Axis Labels on Right */}
                <text
                  x={width - rightAxisWidth + 8}
                  y={y + 3.5}
                  fill="#676b78"
                  fontSize="10"
                  fontFamily="var(--font-mono)"
                >
                  {lvl.toFixed(2)}
                </text>
              </g>
            );
          })}

          {/* Vertical Grid Lines */}
          {timeTicks.map((t) => {
            const x = getX(t.idx);
            return (
              <line
                key={`vgrid-${t.label}`}
                x1={x}
                y1={8}
                x2={x}
                y2={height - bottomAxisHeight}
                stroke="#151619"
                strokeWidth="1"
                strokeDasharray="2 3"
              />
            );
          })}

          {/* Current Live Price Line */}
          <line
            x1={10}
            y1={currentPriceY}
            x2={width - rightAxisWidth}
            y2={currentPriceY}
            stroke="#22c55e"
            strokeWidth="1"
            strokeDasharray="3 3"
            opacity="0.8"
          />

          {/* Current Live Price Badge on Right Y-Axis */}
          <g transform={`translate(${width - rightAxisWidth + 4}, ${currentPriceY - 9})`}>
            <rect
              width="58"
              height="18"
              rx="2"
              fill="#22c55e"
            />
            <text
              x="29"
              y="12.5"
              fill="#062e12"
              fontSize="10"
              fontWeight="700"
              fontFamily="var(--font-mono)"
              textAnchor="middle"
            >
              {lastCandle.close.toFixed(2)}
            </text>
          </g>

          {/* Volume sub-pane divider */}
          <line
            x1={10}
            y1={height - bottomAxisHeight - volumeHeight}
            x2={width - rightAxisWidth}
            y2={height - bottomAxisHeight - volumeHeight}
            stroke="#17181c"
            strokeWidth="1"
          />

          {/* Volume Label */}
          <text
            x={16}
            y={height - bottomAxisHeight - volumeHeight + 13}
            fill="#22c55e"
            fontSize="9.5"
            fontWeight="600"
            fontFamily="var(--font-mono)"
          >
            Volume 1.245K
          </text>

          {/* Volume Axis Labels on Right */}
          <text
            x={width - rightAxisWidth + 8}
            y={height - bottomAxisHeight - volumeHeight + 11}
            fill="#525661"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            10K
          </text>
          <text
            x={width - rightAxisWidth + 8}
            y={height - bottomAxisHeight - (volumeHeight / 2) + 3}
            fill="#525661"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            5K
          </text>
          <text
            x={width - rightAxisWidth + 8}
            y={height - bottomAxisHeight - 4}
            fill="#525661"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            0
          </text>

          {/* Volume Bars */}
          {candles.map((c, idx) => {
            const x = getX(idx);
            const isBull = c.close >= c.open;
            const barWidth = 7;
            const y = getVolY(c.volume);
            const h = height - bottomAxisHeight - y;
            return (
              <rect
                key={`vol-${idx}`}
                x={x - barWidth / 2}
                y={y}
                width={barWidth}
                height={Math.max(h, 1)}
                fill={isBull ? '#26a69a' : '#ef5350'}
                opacity={isBull ? '0.5' : '0.5'}
              />
            );
          })}

          {/* EMA 50 Line (Gold/Amber) */}
          <path
            d={ema50Path}
            fill="none"
            stroke="#f59e0b"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* EMA 20 Line (Cyan) */}
          <path
            d={ema20Path}
            fill="none"
            stroke="#38bdf8"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Candlesticks (Wicks and Bodies) */}
          {candles.map((c, idx) => {
            const x = getX(idx);
            const isBull = c.close >= c.open;
            const candleColor = isBull ? '#26a69a' : '#ef5350';
            const bodyTop = getY(Math.max(c.open, c.close));
            const bodyBottom = getY(Math.min(c.open, c.close));
            const bodyHeight = Math.max(bodyBottom - bodyTop, 1.5);
            const wickHigh = getY(c.high);
            const wickLow = getY(c.low);
            const candleWidth = 7.5;

            return (
              <g key={`candle-${idx}`}>
                {/* Wick */}
                <line
                  x1={x}
                  y1={wickHigh}
                  x2={x}
                  y2={wickLow}
                  stroke={candleColor}
                  strokeWidth="1.2"
                />
                {/* Body */}
                <rect
                  x={x - candleWidth / 2}
                  y={bodyTop}
                  width={candleWidth}
                  height={bodyHeight}
                  fill={candleColor}
                  rx="0.5"
                />
              </g>
            );
          })}

          {/* Crosshair when hovering */}
          {hoverIndex !== null && (
            <g>
              <line
                x1={getX(hoverIndex)}
                y1={8}
                x2={getX(hoverIndex)}
                y2={height - bottomAxisHeight}
                stroke="#676b78"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <line
                x1={10}
                y1={getY(candles[hoverIndex].close)}
                x2={width - rightAxisWidth}
                y2={getY(candles[hoverIndex].close)}
                stroke="#676b78"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
            </g>
          )}

          {/* Bottom X-Axis Time Ticks */}
          {timeTicks.map((t) => {
            const x = getX(t.idx);
            return (
              <g key={`time-${t.label}`}>
                <text
                  x={x}
                  y={height - 7}
                  fill={t.isDay ? '#ffffff' : '#676b78'}
                  fontSize={t.isDay ? '10.5' : '9.5'}
                  fontWeight={t.isDay ? '700' : '400'}
                  fontFamily="var(--font-mono)"
                  textAnchor="middle"
                >
                  {t.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Chart Bottom Controls */}
      <ChartControls
        activeTimeframe={activeTf}
        onSelectTimeframe={setActiveTf}
        activeScaleMode={scaleMode}
        onSelectScaleMode={setScaleMode}
      />
    </div>
  );
};
