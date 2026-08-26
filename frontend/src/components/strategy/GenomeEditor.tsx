import React, { useState } from 'react';
import { Code, Eye, Shield, Target, Award, Hash, Copy, Check } from 'lucide-react';
import { StrategyGenome } from '../../types';
import { ConditionBuilder } from './ConditionBuilder';

interface GenomeEditorProps {
  genome: StrategyGenome;
  onChange?: (updated: StrategyGenome) => void;
  readOnly?: boolean;
}

export const GenomeEditor: React.FC<GenomeEditorProps> = ({
  genome,
  onChange,
  readOnly = false,
}) => {
  const [viewMode, setViewMode] = useState<'visual' | 'json'>('visual');
  const [copied, setCopied] = useState(false);

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(genome, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        backgroundColor: '#0d0e12',
        border: '1px solid #1e222b',
        borderRadius: '8px',
        padding: '16px',
      }}
    >
      {/* Header controls & Mode Switch */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
            {genome.title}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
            <span style={{ fontSize: '11px', color: '#9498a4', fontFamily: 'monospace' }}>
              ID: {genome.genome_id}
            </span>
            {genome.parent_id && (
              <span style={{ fontSize: '11px', color: '#60a5fa', fontFamily: 'monospace' }}>
                Parent: {genome.parent_id}
              </span>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            type="button"
            onClick={() => setViewMode('visual')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '5px 9px',
              borderRadius: '5px',
              fontSize: '12px',
              border: 'none',
              backgroundColor: viewMode === 'visual' ? 'rgba(240, 185, 11, 0.15)' : '#181a20',
              color: viewMode === 'visual' ? '#f0b90b' : '#9498a4',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            <Eye size={13} /> Visual
          </button>
          <button
            type="button"
            onClick={() => setViewMode('json')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '5px 9px',
              borderRadius: '5px',
              fontSize: '12px',
              border: 'none',
              backgroundColor: viewMode === 'json' ? 'rgba(240, 185, 11, 0.15)' : '#181a20',
              color: viewMode === 'json' ? '#f0b90b' : '#9498a4',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            <Code size={13} /> JSON
          </button>
        </div>
      </div>

      {viewMode === 'json' ? (
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={handleCopyJson}
            style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              padding: '4px 8px',
              fontSize: '11px',
              backgroundColor: '#1e222b',
              border: '1px solid #2d3139',
              borderRadius: '4px',
              color: '#e2e4e8',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy JSON'}
          </button>
          <pre
            style={{
              backgroundColor: '#090a0d',
              padding: '12px',
              borderRadius: '6px',
              border: '1px solid #1b1e26',
              color: '#34d399',
              fontSize: '11.5px',
              lineHeight: 1.4,
              overflowX: 'auto',
              maxHeight: '420px',
            }}
          >
            {JSON.stringify(genome, null, 2)}
          </pre>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Hypothesis & Scientific Evidence */}
          <div style={{ backgroundColor: '#121418', padding: '10px 12px', borderRadius: '6px', border: '1px solid #1c2028' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
              <Award size={14} color="#f0b90b" />
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#e2e4e8' }}>Scientific Hypothesis</span>
            </div>
            <p style={{ margin: 0, fontSize: '12.5px', color: '#9498a4', lineHeight: 1.4 }}>
              {genome.hypothesis}
            </p>
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px', flexWrap: 'wrap' }}>
              {genome.evidence_refs.map((ref, idx) => (
                <span
                  key={idx}
                  style={{
                    fontSize: '11px',
                    padding: '2px 7px',
                    borderRadius: '4px',
                    backgroundColor: 'rgba(96, 165, 250, 0.1)',
                    color: '#60a5fa',
                    border: '1px solid rgba(96, 165, 250, 0.3)',
                    fontFamily: 'monospace',
                  }}
                >
                  {ref}
                </span>
              ))}
            </div>
          </div>

          {/* Guard Bounds Section */}
          <div style={{ backgroundColor: '#121418', padding: '10px 12px', borderRadius: '6px', border: '1px solid #1c2028' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
              <Shield size={14} color="#10b981" />
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#e2e4e8' }}>Guard Rails & Macro Bounds</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px' }}>
              <div>
                <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Min ATR Rate</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#e2e4e8', fontFamily: 'monospace' }}>
                  {(parseFloat(genome.guard.min_atr_rate) * 100).toFixed(2)}%
                </span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Max ATR Rate</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#e2e4e8', fontFamily: 'monospace' }}>
                  {(parseFloat(genome.guard.max_atr_rate) * 100).toFixed(2)}%
                </span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Max Spread Rate</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#e2e4e8', fontFamily: 'monospace' }}>
                  {(parseFloat(genome.guard.max_spread_rate) * 100).toFixed(2)}%
                </span>
              </div>
            </div>
          </div>

          {/* Entry Conditions Section */}
          <div style={{ backgroundColor: '#121418', padding: '10px 12px', borderRadius: '6px', border: '1px solid #1c2028' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <Target size={14} color="#60a5fa" />
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#e2e4e8' }}>Entry Conditions (ALL Required)</span>
            </div>
            <ConditionBuilder
              conditions={genome.entry}
              onChange={(updated) => onChange && onChange({ ...genome, entry: updated })}
              disabled={readOnly}
            />
          </div>

          {/* Exit Rules Section */}
          <div style={{ backgroundColor: '#121418', padding: '10px 12px', borderRadius: '6px', border: '1px solid #1c2028' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <Shield size={14} color="#ef4444" />
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#e2e4e8' }}>Exit & Invalidation Rules</span>
            </div>
            <div style={{ display: 'flex', gap: '14px', marginBottom: '10px' }}>
              <div>
                <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Take Profit</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#10b981', fontFamily: 'monospace' }}>
                  {genome.exit.take_profit_r_multiple} R
                </span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Stop Loss</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#ef4444', fontFamily: 'monospace' }}>
                  {genome.exit.stop_loss_atr_multiple} ATR
                </span>
              </div>
            </div>
            <ConditionBuilder
              conditions={genome.exit.invalidation}
              onChange={(updated) =>
                onChange &&
                onChange({
                  ...genome,
                  exit: { ...genome.exit, invalidation: updated },
                })
              }
              disabled={readOnly}
            />
          </div>
        </div>
      )}
    </div>
  );
};
