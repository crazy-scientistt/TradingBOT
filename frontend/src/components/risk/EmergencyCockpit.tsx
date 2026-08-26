import React, { useState } from 'react';
import {
  ShieldAlert,
  AlertTriangle,
  RotateCcw,
  PauseCircle,
  Activity,
  Check,
  X,
} from 'lucide-react';
import { BotStateStatus } from '../../types';

interface EmergencyCockpitProps {
  status: BotStateStatus;
  onEmergencyHalt?: () => void;
  onRevokeAutonomy?: () => void;
  onRevertBaseline?: () => void;
}

export const EmergencyCockpit: React.FC<EmergencyCockpitProps> = ({
  status,
  onEmergencyHalt,
  onRevokeAutonomy,
  onRevertBaseline,
}) => {
  const [confirmAction, setConfirmAction] = useState<string | null>(null);

  const getStateColor = (st: string) => {
    switch (st) {
      case 'NORMAL':
        return '#10b981';
      case 'RESEARCH_ACTIVE':
        return '#60a5fa';
      case 'AUTONOMY_SUSPENDED':
        return '#f0b90b';
      case 'QUARANTINE':
      case 'KILL_SWITCH_ACTIVE':
        return '#ef4444';
      default:
        return '#9498a4';
    }
  };

  const handleConfirm = () => {
    if (confirmAction === 'kill' && onEmergencyHalt) onEmergencyHalt();
    if (confirmAction === 'revoke' && onRevokeAutonomy) onRevokeAutonomy();
    if (confirmAction === 'revert' && onRevertBaseline) onRevertBaseline();
    setConfirmAction(null);
  };

  const stateColor = getStateColor(status.state);
  const lossPct = Math.min(100, Math.round((status.daily_loss_percent / status.daily_loss_limit) * 100));

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        width: '100%',
        color: '#e2e4e8',
      }}
    >
      {/* BotState Banner */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#0d0e12',
          padding: '14px 18px',
          borderRadius: '8px',
          border: `1px solid ${stateColor}44`,
          boxShadow: `0 0 15px ${stateColor}11`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              backgroundColor: stateColor,
              boxShadow: `0 0 8px ${stateColor}`,
            }}
          />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                System State: {status.state}
              </h2>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  padding: '2px 6px',
                  borderRadius: '3px',
                  backgroundColor: status.full_autonomy ? 'rgba(16, 185, 129, 0.15)' : 'rgba(240, 185, 11, 0.15)',
                  color: status.full_autonomy ? '#10b981' : '#f0b90b',
                }}
              >
                {status.full_autonomy ? 'FULL AUTONOMY' : 'HUMAN APPROVAL MODE'}
              </span>
            </div>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Active Strategy Genome: <strong style={{ color: '#e2e4e8' }}>{status.active_genome_id}</strong>
            </span>
          </div>
        </div>

        {/* Daily Loss Progress */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '180px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
            <span style={{ color: '#9498a4' }}>24h Rolling Loss</span>
            <span style={{ fontWeight: 700, color: lossPct > 70 ? '#ef4444' : '#e2e4e8' }}>
              {status.daily_loss_percent.toFixed(2)}% / {status.daily_loss_limit.toFixed(2)}%
            </span>
          </div>
          <div style={{ width: '100%', height: '6px', backgroundColor: '#181a20', borderRadius: '3px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${lossPct}%`,
                height: '100%',
                backgroundColor: lossPct > 70 ? '#ef4444' : '#10b981',
              }}
            />
          </div>
        </div>
      </div>

      {/* Action Buttons Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '12px' }}>
        {/* Kill Switch */}
        <div
          style={{
            backgroundColor: '#0d0e12',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            padding: '14px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <ShieldAlert size={16} color="#ef4444" />
              <span style={{ fontSize: '14px', fontWeight: 700, color: '#ef4444' }}>
                Emergency Kill Switch
              </span>
            </div>
            <span style={{ fontSize: '11.5px', color: '#9498a4' }}>
              Immediately liquidate all active positions, cancel open orders, and halt all trading.
            </span>
          </div>

          <button
            type="button"
            onClick={() => setConfirmAction('kill')}
            style={{
              padding: '8px 12px',
              backgroundColor: '#ef4444',
              color: '#fff',
              fontWeight: 700,
              fontSize: '12.5px',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            Trigger Kill Switch
          </button>
        </div>

        {/* Revoke Autonomy */}
        <div
          style={{
            backgroundColor: '#0d0e12',
            border: '1px solid rgba(240, 185, 11, 0.3)',
            borderRadius: '8px',
            padding: '14px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <PauseCircle size={16} color="#f0b90b" />
              <span style={{ fontSize: '14px', fontWeight: 700, color: '#f0b90b' }}>
                Revoke Autonomy
              </span>
            </div>
            <span style={{ fontSize: '11.5px', color: '#9498a4' }}>
              Suspend autonomous Hermes strategy research and require manual human approval for all mutations.
            </span>
          </div>

          <button
            type="button"
            onClick={() => setConfirmAction('revoke')}
            style={{
              padding: '8px 12px',
              backgroundColor: 'rgba(240, 185, 11, 0.15)',
              color: '#f0b90b',
              border: '1px solid rgba(240, 185, 11, 0.4)',
              fontWeight: 700,
              fontSize: '12.5px',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Revoke Autonomy
          </button>
        </div>

        {/* Revert to Baseline */}
        <div
          style={{
            backgroundColor: '#0d0e12',
            border: '1px solid rgba(96, 165, 250, 0.3)',
            borderRadius: '8px',
            padding: '14px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <RotateCcw size={16} color="#60a5fa" />
              <span style={{ fontSize: '14px', fontWeight: 700, color: '#60a5fa' }}>
                Revert to Baseline Genome
              </span>
            </div>
            <span style={{ fontSize: '11.5px', color: '#9498a4' }}>
              Instantly demote current candidate and promote vetted safe-default-v1 baseline strategy.
            </span>
          </div>

          <button
            type="button"
            onClick={() => setConfirmAction('revert')}
            style={{
              padding: '8px 12px',
              backgroundColor: 'rgba(96, 165, 250, 0.15)',
              color: '#60a5fa',
              border: '1px solid rgba(96, 165, 250, 0.4)',
              fontWeight: 700,
              fontSize: '12.5px',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Revert to Baseline
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      {confirmAction && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '20px',
          }}
        >
          <div
            style={{
              backgroundColor: '#121418',
              border: '1px solid #2d3139',
              borderRadius: '8px',
              padding: '20px',
              maxWidth: '420px',
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <AlertTriangle size={22} color="#ef4444" />
              <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                Confirm Emergency Action
              </h3>
            </div>

            <p style={{ margin: 0, fontSize: '13px', color: '#9498a4', lineHeight: 1.4 }}>
              Are you sure you want to execute this emergency override? This will alter active bot execution state immediately.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
              <button
                type="button"
                onClick={() => setConfirmAction(null)}
                style={{
                  padding: '7px 12px',
                  backgroundColor: '#181a20',
                  color: '#e2e4e8',
                  border: '1px solid #2d3139',
                  borderRadius: '5px',
                  fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                style={{
                  padding: '7px 14px',
                  backgroundColor: '#ef4444',
                  color: '#fff',
                  fontWeight: 700,
                  border: 'none',
                  borderRadius: '5px',
                  fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                Confirm Override
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
