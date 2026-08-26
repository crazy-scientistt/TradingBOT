import React, { useState, useEffect } from 'react';
import { ChevronDown, Bell, Settings, Play, Square, ShieldCheck, ShieldAlert } from 'lucide-react';
import { useBot } from '../../context/BotContext';

interface TopHeaderProps {
  onOpenSettings?: () => void;
}

export const TopHeader: React.FC<TopHeaderProps> = ({ onOpenSettings }) => {
  const {
    botRunning,
    isPaperMode,
    selectedPair,
    setSelectedPair,
    toggleBot,
    toggleMode,
    systemHealthy,
    addToast,
  } = useBot();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [utcTime, setUtcTime] = useState<string>('');

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setUtcTime(
        now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
      );
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const pairs = ['PAXG / USDT', 'BTC / USDT', 'ETH / USDT', 'SOL / USDT'];

  return (
    <header
      style={{
        height: '52px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        borderBottom: '1px solid #181a1f',
        backgroundColor: '#08090b',
        userSelect: 'none',
      }}
    >
      {/* Left side: Mode Pill + Pair Selector + Bot Run Toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', position: 'relative' }}>
        {/* Paper Mode Pill */}
        <button
          onClick={toggleMode}
          className="badge-paper"
          style={{
            cursor: 'pointer',
            border: isPaperMode ? '1px solid rgba(240, 185, 11, 0.45)' : '1px solid rgba(16, 185, 129, 0.45)',
            backgroundColor: isPaperMode ? 'rgba(240, 185, 11, 0.08)' : 'rgba(16, 185, 129, 0.08)',
            color: isPaperMode ? '#f0b90b' : '#10b981',
            padding: '5px 12px',
            borderRadius: '4px',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.06em',
            transition: 'all 0.15s ease',
          }}
          title="Click to Switch Trading Mode"
        >
          {isPaperMode ? 'PAPER MODE ($100)' : 'LIVE CAPABILITY'}
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
              borderRadius: '4px',
            }}
          >
            <span>{selectedPair}</span>
            <ChevronDown size={14} color="#9498a4" />
          </button>

          {/* Dropdown Menu */}
          {dropdownOpen && (
            <div
              style={{
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
                overflow: 'hidden',
              }}
            >
              {pairs.map((p) => (
                <div
                  key={p}
                  onClick={() => {
                    setSelectedPair(p);
                    setDropdownOpen(false);
                  }}
                  style={{
                    padding: '8px 12px',
                    fontSize: '13px',
                    color: p === selectedPair ? '#f0b90b' : '#cbd5e1',
                    fontWeight: p === selectedPair ? 600 : 400,
                    cursor: 'pointer',
                    backgroundColor: p === selectedPair ? 'rgba(240, 185, 11, 0.08)' : 'transparent',
                    transition: 'background-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.06)')}
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.backgroundColor =
                      p === selectedPair ? 'rgba(240, 185, 11, 0.08)' : 'transparent')
                  }
                >
                  {p}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Start / Stop Trading Bot Button */}
        <button
          onClick={toggleBot}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 12px',
            borderRadius: '4px',
            border: botRunning ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(16, 185, 129, 0.4)',
            backgroundColor: botRunning ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)',
            color: botRunning ? '#ef4444' : '#10b981',
            fontSize: '11.5px',
            fontWeight: 700,
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
          title={botRunning ? 'Click to Stop Autonomous Loop' : 'Click to Start Autonomous Loop'}
        >
          {botRunning ? (
            <>
              <Square size={11} fill="#ef4444" />
              <span>BOT RUNNING (15m)</span>
            </>
          ) : (
            <>
              <Play size={11} fill="#10b981" />
              <span>START AUTONOMOUS BOT</span>
            </>
          )}
        </button>
      </div>

      {/* Right side: System Status, UTC Time, Notifications, Settings */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
        {/* System Healthy Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
          <span
            style={{
              width: '7px',
              height: '7px',
              borderRadius: '50%',
              backgroundColor: systemHealthy ? '#22c55e' : '#ef4444',
              boxShadow: systemHealthy ? '0 0 8px #22c55e' : '0 0 8px #ef4444',
            }}
          />
          <span style={{ fontSize: '12px', color: '#e2e4e8', fontWeight: 500 }}>
            {systemHealthy ? 'System Healthy' : 'Degraded'}
          </span>
        </div>

        {/* Real-time UTC clock */}
        <div
          style={{
            fontSize: '12px',
            color: '#9498a4',
            fontFamily: 'monospace',
            fontWeight: 500,
            letterSpacing: '0.02em',
          }}
        >
          {utcTime || '2026-08-27 00:00:00 UTC'}
        </div>

        {/* Action icons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', color: '#9498a4' }}>
          {/* Bell Icon with dot */}
          <div
            onClick={() => addToast('info', 'System Operational', 'All risk bounds & single execution lease valid')}
            style={{ position: 'relative', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
            title="Notifications"
          >
            <Bell size={17} />
            <span
              style={{
                position: 'absolute',
                top: '-1px',
                right: '-1px',
                width: '5px',
                height: '5px',
                backgroundColor: '#f0b90b',
                borderRadius: '50%',
              }}
            />
          </div>

          {/* Settings Cog */}
          <div
            onClick={onOpenSettings}
            style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}
            title="System Settings"
          >
            <Settings size={17} />
          </div>
        </div>
      </div>
    </header>
  );
};
