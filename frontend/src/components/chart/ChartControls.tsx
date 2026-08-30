import React from 'react';

interface ChartControlsProps {
  activeTimeframe?: string;
  onSelectTimeframe?: (tf: string) => void;
  activeScaleMode?: string;
  onSelectScaleMode?: (mode: string) => void;
}

export const ChartControls: React.FC<ChartControlsProps> = ({
  activeTimeframe = '15m',
  onSelectTimeframe,
  activeScaleMode = 'auto',
  onSelectScaleMode
}) => {
  const timeframes = ['1m', '5m', '15m', '1h', '4h', '1D'];
  const scaleModes = ['%', 'log', 'auto'];

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '4px 14px 8px 14px',
      borderTop: '1px solid #181a1f',
      backgroundColor: '#121316'
    }}>
      {/* Timeframe buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {timeframes.map((tf) => {
          const isActive = tf === activeTimeframe;
          return (
            <button
              key={tf}
              onClick={() => onSelectTimeframe && onSelectTimeframe(tf)}
              style={{
                background: 'transparent',
                border: 'none',
                color: isActive ? 'var(--gold-primary)' : '#9498a4',
                fontSize: '12px',
                fontWeight: isActive ? 600 : 400,
                cursor: 'pointer',
                padding: '4px 0',
                position: 'relative',
                transition: 'color 0.15s ease'
              }}
            >
              {tf}
              {isActive && (
                <span style={{
                  position: 'absolute',
                  bottom: '-4px',
                  left: 0,
                  right: 0,
                  height: '2px',
                  backgroundColor: 'var(--gold-primary)',
                  borderRadius: '1px'
                }} />
              )}
            </button>
          );
        })}
      </div>

      {/* Scale mode buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {scaleModes.map((mode) => {
          const isActive = mode === activeScaleMode;
          return (
            <button
              key={mode}
              onClick={() => onSelectScaleMode && onSelectScaleMode(mode)}
              style={{
                background: 'transparent',
                border: 'none',
                color: isActive ? 'var(--gold-primary)' : '#676b78',
                fontSize: '11.5px',
                fontWeight: isActive ? 600 : 400,
                cursor: 'pointer',
                padding: '2px 4px',
                borderRadius: '3px'
              }}
            >
              {mode}
            </button>
          );
        })}
      </div>
    </div>
  );
};
