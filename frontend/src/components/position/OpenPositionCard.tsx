import React from 'react';
import { Maximize2 } from 'lucide-react';
import { PositionDetails, PipelineStep } from '../../types/dashboard';
import { DecisionPipeline } from './DecisionPipeline';

interface OpenPositionCardProps {
  position: PositionDetails;
  pipelineSteps: PipelineStep[];
}

export const OpenPositionCard: React.FC<OpenPositionCardProps> = ({ position, pipelineSteps }) => {
  return (
    <div className="dashboard-card" style={{
      width: '310px',
      minWidth: '290px',
      padding: '12px 14px',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between'
    }}>
      {/* Top Section */}
      <div>
        {/* Header: OPEN POSITION + LIVE badge + Expand */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '8px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              OPEN POSITION
            </span>
            <span className={position.isLive ? 'badge-live' : 'badge-paper'}>
              {position.isLive ? 'LIVE' : 'PAPER'}
            </span>
          </div>
          <button style={{
            background: 'transparent',
            border: 'none',
            color: '#9498a4',
            cursor: 'pointer',
            padding: '2px',
            display: 'flex',
            alignItems: 'center'
          }} title="Expand Position">
            <Maximize2 size={14} />
          </button>
        </div>

        {/* Direction Indicator */}
        <div style={{
          fontSize: '18px',
          fontWeight: 800,
          color: '#22c55e',
          letterSpacing: '0.02em',
          marginBottom: '10px'
        }}>
          {position.direction}
        </div>

        {/* Position Details List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {/* ENTRY */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
            <span style={{ color: '#9498a4', fontWeight: 500 }}>ENTRY</span>
            <span style={{ color: '#f8fafc', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              {position.entry.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </span>
          </div>

          {/* STOP */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
            <span style={{ color: '#9498a4', fontWeight: 500 }}>STOP</span>
            <span style={{ color: '#ef4444', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              {position.stop != null
                ? position.stop.toLocaleString('en-US', { minimumFractionDigits: 2 })
                : '—'}
            </span>
          </div>

          {/* TARGET */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
            <span style={{ color: '#9498a4', fontWeight: 500 }}>TARGET</span>
            <span style={{ color: '#22c55e', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              {position.target != null
                ? position.target.toLocaleString('en-US', { minimumFractionDigits: 2 })
                : '—'}
            </span>
          </div>

          {/* QUANTITY */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
            <span style={{ color: '#9498a4', fontWeight: 500 }}>QUANTITY</span>
            <span style={{ color: '#f8fafc', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              {position.quantity}
            </span>
          </div>

          {/* RISK */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
            <span style={{ color: '#9498a4', fontWeight: 500 }}>RISK</span>
            <span style={{ color: '#f8fafc', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              {position.riskPercent != null ? `${position.riskPercent.toFixed(2)}%` : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div style={{
        height: '1px',
        backgroundColor: 'rgba(255, 255, 255, 0.06)',
        margin: '8px 0 2px 0'
      }} />

      {/* Bottom Section: Decision Pipeline */}
      <DecisionPipeline steps={pipelineSteps} />
    </div>
  );
};
