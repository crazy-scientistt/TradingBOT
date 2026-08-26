import React, { useState } from 'react';
import { ChevronDown, Bell, Settings } from 'lucide-react';

interface TopHeaderProps {
  currentPair?: string;
  onSelectPair?: (pair: string) => void;
  isPaperMode?: boolean;
  onToggleMode?: () => void;
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  currentPair = 'PAXG / USDT',
  onSelectPair,
  isPaperMode = true,
  onToggleMode
}) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const pairs = ['PAXG / USDT', 'BTC / USDT', 'ETH / USDT', 'SOL / USDT'];

  return (
    <header style={{
      height: '52px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 16px',
      borderBottom: '1px solid #181a1f',
      backgroundColor: '#08090b',
      userSelect: 'none'
    }}>
      {/* Left side: Mode Pill + Pair Selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', position: 'relative' }}>
        {/* Paper Mode Pill */}
        <button
          onClick={onToggleMode}
          className="badge-paper"
          style={{
            cursor: 'pointer',
            border: '1px solid rgba(240, 185, 11, 0.45)',
            backgroundColor: 'rgba(240, 185, 11, 0.06)',
            color: '#f0b90b',
            padding: '5px 12px',
            borderRadius: '4px',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.06em',
            transition: 'all 0.15s ease'
          }}
          title="Switch Trading Mode"
        >
          {isPaperMode ? 'PAPER MODE' : 'LIVE MODE'}
        </button>

        {/* Pair Selector Dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: 'transparent',
              border: 'none',
              color: '#f8fafc',
              fontSize: '13.5px',
              fontWeight: 600,
              cursor: 'pointer',
              padding: '4px 6px',
              borderRadius: '4px'
            }}
          >
            <span>{currentPair}</span>
            <ChevronDown size={14} color="#9498a4" />
          </button>

          {/* Dropdown Menu */}
          {dropdownOpen && (
            <div style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              marginTop: '6px',
              backgroundColor: '#141518',
              border: '1px solid #22242a',
              borderRadius: '6px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.8)',
              zIndex: 50,
              minWidth: '130px',
              overflow: 'hidden'
            }}>
              {pairs.map((p) => (
                <div
                  key={p}
                  onClick={() => {
                    if (onSelectPair) onSelectPair(p);
                    setDropdownOpen(false);
                  }}
                  style={{
                    padding: '8px 12px',
                    fontSize: '13px',
                    color: p === currentPair ? '#f0b90b' : '#cbd5e1',
                    fontWeight: p === currentPair ? 600 : 400,
                    cursor: 'pointer',
                    backgroundColor: p === currentPair ? 'rgba(240, 185, 11, 0.08)' : 'transparent',
                    transition: 'background-color 0.15s ease'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.06)'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = p === currentPair ? 'rgba(240, 185, 11, 0.08)' : 'transparent'}
                >
                  {p}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right side: System Status, UTC Time, Notifications, Settings */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
        {/* System Healthy Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
          <span style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            backgroundColor: '#22c55e',
            boxShadow: '0 0 8px #22c55e'
          }} />
          <span style={{ fontSize: '12.5px', color: '#e2e4e8', fontWeight: 500 }}>
            System Healthy
          </span>
        </div>

        {/* Real-time UTC clock */}
        <div style={{
          fontSize: '12.5px',
          color: '#9498a4',
          fontFamily: 'var(--font-mono)',
          fontWeight: 400,
          letterSpacing: '0.02em'
        }}>
          2025-05-20 14:32:18 UTC
        </div>

        {/* Action icons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', color: '#9498a4' }}>
          {/* Bell Icon with dot */}
          <div style={{ position: 'relative', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
            <Bell size={17} />
            <span style={{
              position: 'absolute',
              top: '-1px',
              right: '-1px',
              width: '5px',
              height: '5px',
              backgroundColor: '#f0b90b',
              borderRadius: '50%'
            }} />
          </div>

          {/* Settings Cog */}
          <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
            <Settings size={17} />
          </div>
        </div>
      </div>
    </header>
  );
};
