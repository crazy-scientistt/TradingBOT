import React, { useState, useEffect } from 'react';
import { Settings, ShieldCheck, X } from 'lucide-react';
import { api, EffectiveSettings } from '../../api/client';
import { useBot } from '../../context/BotContext';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const { isPaperMode } = useBot();
  const [settings, setSettings] = useState<EffectiveSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      setError(null);
      setSettings(null);
      api.getSettings()
        .then(setSettings)
        .catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load effective configuration'))
        .finally(() => setLoading(false));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const riskPerTrade = settings ? Number(settings.paper_risk_per_trade) : Number.NaN;

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
            <div
              style={{
                padding: '10px 12px',
                borderRadius: '6px',
                border: '1px solid rgba(240, 185, 11, 0.45)',
                backgroundColor: 'rgba(240, 185, 11, 0.08)',
                color: '#f0b90b',
                fontWeight: 600,
                fontSize: '12.5px',
              }}
            >
              {isPaperMode ? 'Paper mode (server-controlled)' : 'Live mode reported by server (read-only)'}
            </div>
          </div>

          {loading && <div role="status" style={{ color: '#9498a4', fontSize: '12px' }}>Loading effective configuration…</div>}
          {error && <div role="alert" style={{ color: '#fca5a5', fontSize: '12px' }}>{error}</div>}

          {/* Risk Limits */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Risk Per Trade</label>
              <input
                type="text"
                value={Number.isFinite(riskPerTrade) ? `${(riskPerTrade * 100).toFixed(1)}%` : 'Not observed'}
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
                value={settings ? `$${settings.paper_starting_balance} USDT` : 'Not observed'}
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
                value={settings ? `${settings.research_backtest_max_per_day} backtests/day` : 'Not observed'}
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
                value={settings ? `${settings.research_web_calls_max_per_day} calls/day` : 'Not observed'}
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
          <span style={{ color: '#676b78', fontSize: '11.5px', alignSelf: 'center' }}>
            Read-only · restart with approved server configuration changes
          </span>
        </div>
      </div>
    </div>
  );
};
