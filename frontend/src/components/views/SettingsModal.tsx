import React, { useState, useEffect } from 'react';
import { Settings, ShieldCheck, X } from 'lucide-react';
import { api, EffectiveSettings } from '../../api/client';
import { useBot } from '../../context/BotContext';
import { AutonomousSettings } from '../settings/AutonomousSettings';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const { isPaperMode } = useBot();
  const [settings, setSettings] = useState<EffectiveSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [balance, setBalance] = useState('100');
  const [riskPercent, setRiskPercent] = useState('0.5');

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    setSaved(null);
    setSettings(null);
    api.getSettings()
      .then((next) => {
        setSettings(next);
        setBalance(String(Number(next.paper_starting_balance)));
        const risk = Number(next.paper_risk_per_trade);
        setRiskPercent(Number.isFinite(risk) ? (risk * 100).toString() : '0.5');
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load settings'))
      .finally(() => setLoading(false));
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async () => {
    const starting = Number(balance);
    const risk = Number(riskPercent);
    if (!Number.isFinite(starting) || starting <= 0) {
      setError('Starting balance must be a positive number.');
      return;
    }
    if (!Number.isFinite(risk) || risk < 0.05 || risk > 1) {
      setError('Risk per trade must be between 0.05% and 1%.');
      return;
    }
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      const next = await api.saveSettings({
        paper_starting_balance: String(starting),
        paper_risk_per_trade: String(risk / 100),
      });
      setSettings(next);
      setSaved(next.detail || 'Saved. Applied now — no Railway restart.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save settings');
    } finally {
      setSaving(false);
    }
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
            <Settings size={18} color="var(--gold-primary)" />
            <h3 style={{ fontSize: '15px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Paper settings
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: '#676b78', cursor: 'pointer' }}
          >
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: '#9498a4' }}>Execution Mode</label>
            <div
              style={{
                padding: '10px 12px',
                borderRadius: '6px',
                border: '1px solid rgba(61, 126, 255, 0.45)',
                backgroundColor: 'rgba(61, 126, 255, 0.08)',
                color: 'var(--gold-primary)',
                fontWeight: 600,
                fontSize: '12.5px',
              }}
            >
              {isPaperMode ? 'Paper trading — no live orders' : 'Live mode reported by server (read-only)'}
            </div>
          </div>

          {loading && <div role="status" style={{ color: '#9498a4', fontSize: '12px' }}>Loading…</div>}
          {error && <div role="alert" style={{ color: '#fca5a5', fontSize: '12px' }}>{error}</div>}
          {saved && <div role="status" style={{ color: '#10b981', fontSize: '12px' }}>{saved}</div>}

          <AutonomousSettings
            equityUsdt={balance || '100'}
            initialProfile={{
              execution_mode: isPaperMode ? 'paper' : 'live',
              spot_enabled: true,
              futures_enabled: false,
              risk: {
                max_capital_per_trade_rate: String(Number(riskPercent) / 100 || 0.005),
                max_futures_leverage: 5,
                max_total_exposure_rate: '0.20',
                rolling_24h_loss_limit_rate: '0.05',
              },
            }}
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Starting balance (USDT)</label>
              <input
                type="number"
                min={1}
                max={1000000}
                value={balance}
                onChange={(event) => setBalance(event.target.value)}
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
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Risk per trade (%)</label>
              <input
                type="number"
                min={0.05}
                max={1}
                step={0.05}
                value={riskPercent}
                onChange={(event) => setRiskPercent(event.target.value)}
                style={{
                  backgroundColor: '#141518',
                  border: '1px solid #22242a',
                  borderRadius: '5px',
                  padding: '8px 10px',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              />
              <span style={{ fontSize: '10.5px', color: '#676b78' }}>Hard ceiling 1%. Default 0.5%.</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Daily loss halt</label>
              <input
                type="text"
                readOnly
                value={settings ? `${(Number(settings.daily_loss_halt) * 100).toFixed(1)}% locked` : '—'}
                style={{
                  backgroundColor: '#141518',
                  border: '1px solid #22242a',
                  borderRadius: '5px',
                  padding: '8px 10px',
                  color: '#676b78',
                  fontSize: '13px',
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11.5px', color: '#9498a4' }}>Emergency drawdown halt</label>
              <input
                type="text"
                readOnly
                value={settings ? `${(Number(settings.emergency_drawdown_halt) * 100).toFixed(1)}% locked` : '—'}
                style={{
                  backgroundColor: '#141518',
                  border: '1px solid #22242a',
                  borderRadius: '5px',
                  padding: '8px 10px',
                  color: '#676b78',
                  fontSize: '13px',
                }}
              />
            </div>
          </div>

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
                Saves in the app
              </span>
              <span style={{ fontSize: '11px', color: '#9498a4' }}>
                Changing starting balance opens a new paper session. Do not edit Railway env vars for this.
              </span>
            </div>
          </div>
        </div>

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
            onClick={() => void handleSave()}
            disabled={saving || loading || !settings}
            style={{
              padding: '8px 14px',
              backgroundColor: 'var(--gold-primary)',
              color: '#0d0e12',
              border: 'none',
              borderRadius: '6px',
              fontSize: '12.5px',
              fontWeight: 700,
              cursor: saving || loading || !settings ? 'not-allowed' : 'pointer',
              opacity: saving || loading || !settings ? 0.6 : 1,
            }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
};
