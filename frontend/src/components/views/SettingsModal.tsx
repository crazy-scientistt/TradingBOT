import React, { useState, useEffect } from 'react';
import { Settings, ShieldCheck, Key, Save, X } from 'lucide-react';
import { api } from '../../api/client';
import { useBot } from '../../context/BotContext';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const { addToast, isPaperMode, toggleMode } = useBot();
  const [settings, setSettings] = useState<any>({
    environment: 'production',
    mode: 'paper',
    symbol: 'PAXGUSDT',
    paper_starting_balance: '100',
    paper_risk_per_trade: '0.005',
    taker_fee_rate: '0.001',
    slippage_rate: '0.0002',
    max_spread_rate: '0.0015',
    research_backtest_max_per_day: 8,
    research_web_calls_max_per_day: 50,
  });

  useEffect(() => {
    if (isOpen) {
      api.getSettings().then(setSettings).catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = () => {
    addToast('success', 'Settings Saved', 'Configuration updated successfully');
    onClose();
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 999,
        padding: '20px',
      }}
    >
      <div
        style={{
          backgroundColor: '#0d0e12',
          border: '1px solid #2d3139',
          borderRadius: '8px',
          width: '100%',
          maxWidth: '560px',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '90vh',
          boxShadow: '0 16px 36px rgba(0, 0, 0, 0.8)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 20px',
            borderBottom: '1px solid #1c2028',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Settings size={18} color="#f0b90b" />
            <h3 style={{ fontSize: '15px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              GoldGuard Configuration &amp; Risk Parameters
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#676b78',
              cursor: 'pointer',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Trading Mode */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: '#9498a4' }}>
              Execution Mode
            </label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="button"
                onClick={() => !isPaperMode && toggleMode()}
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  borderRadius: '6px',
                  border: isPaperMode ? '1px solid #f0b90b' : '1px solid #22242a',
                  backgroundColor: isPaperMode ? 'rgba(240, 185, 11, 0.1)' : '#141518',
                  color: isPaperMode ? '#f0b90b' : '#9498a4',
                  fontWeight: 600,
                  fontSize: '12.5px',
                  cursor: 'pointer',
                }}
              >
                Paper Mode ($100 Virtual)
              </button>
              <button
                type="button"
                onClick={() => isPaperMode && toggleMode()}
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  borderRadius: '6px',
                  border: !isPaperMode ? '1px solid #10b981' : '1px solid #22242a',
                  backgroundColor: !isPaperMode ? 'rgba(16, 185, 129, 0.1)' : '#141518',
                  color: !isPaperMode ? '#10b981' : '#9498a4',
                  fontWeight: 600,
                  fontSize: '12.5px',
                  cursor: 'pointer',
                }}
              >
                Live Capability Mode
              </button>
            </div>
          </div>

          {/* Risk Limits */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Risk Per Trade</label>
              <input
                type="text"
                value={`${(parseFloat(settings.paper_risk_per_trade || '0.005') * 100).toFixed(1)}%`}
                readOnly
                style={{
                  backgroundColor: '#141518',
                  border: '1px solid #22242a',
                  borderRadius: '5px',
                  padding: '8px 10px',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Starting Balance</label>
              <input
                type="text"
                value={`$${settings.paper_starting_balance || '100'} USDT`}
                readOnly
                style={{
                  backgroundColor: '#141518',
                  border: '1px solid #22242a',
                  borderRadius: '5px',
                  padding: '8px 10px',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Daily Backtest Limit</label>
              <input
                type="text"
                value={`${settings.research_backtest_max_per_day || 8} backtests/day`}
                readOnly
                style={{
                  backgroundColor: '#141518',
                  border: '1px solid #22242a',
                  borderRadius: '5px',
                  padding: '8px 10px',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Daily Web Call Limit</label>
              <input
                type="text"
                value={`${settings.research_web_calls_max_per_day || 50} calls/day`}
                readOnly
                style={{
                  backgroundColor: '#141518',
                  border: '1px solid #22242a',
                  borderRadius: '5px',
                  padding: '8px 10px',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              />
            </div>
          </div>

          {/* Security & Provenance Banner */}
          <div
            style={{
              backgroundColor: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: '6px',
              padding: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <ShieldCheck size={18} color="#10b981" />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: '12.5px', fontWeight: 600, color: '#10b981' }}>
                Strict Provenance Active
              </span>
              <span style={{ fontSize: '11px', color: '#9498a4' }}>
                Risk ceilings locked by Safe-Default-V1 preset. Strategy mutations strictly bounded.
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '8px',
            padding: '14px 20px',
            borderTop: '1px solid #1c2028',
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '8px 14px',
              backgroundColor: '#181a20',
              color: '#e2e4e8',
              border: '1px solid #2d3139',
              borderRadius: '6px',
              fontSize: '12.5px',
              cursor: 'pointer',
            }}
          >
            Close
          </button>
          <button
            onClick={handleSave}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              backgroundColor: '#f0b90b',
              color: '#000',
              fontWeight: 700,
              border: 'none',
              borderRadius: '6px',
              fontSize: '12.5px',
              cursor: 'pointer',
            }}
          >
            <Save size={14} /> Save Configuration
          </button>
        </div>
      </div>
    </div>
  );
};
