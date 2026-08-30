import React, { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { api, DiagnosticsData } from '../../api/client';
import { useBot } from '../../context/BotContext';

export const QualifyView: React.FC = () => {
  const { preflight, runtimeStatus } = useBot();
  const [diag, setDiag] = useState<DiagnosticsData | null>(null);

  useEffect(() => {
    void api.getDiagnostics().then(setDiag).catch(() => setDiag(null));
  }, []);

  const named = (name: string) => diag?.checks.find((item) => item.name === name);
  const pass = (name: string) => named(name)?.status === 'pass';

  const gates = [
    {
      name: 'Paper desk',
      hold: false,
      note: 'Preview and local stack stay paper-only.',
    },
    {
      name: 'Public market feed',
      hold: !(preflight?.ready || pass('binance_public')),
      note: named('binance_public')?.detail || 'Waiting for Binance public data.',
    },
    {
      name: 'Hermes researcher',
      hold: !pass('hermes_http') && named('hermes_http')?.status !== 'pass',
      note: named('hermes_http')?.detail || named('hermes_proposal')?.detail || 'Hermes HTTP not proven.',
    },
    {
      name: 'Learning path',
      hold: named('reflection_persist')?.status !== 'pass',
      note: named('reflection_persist')?.detail || 'No closed-trade lesson yet.',
    },
    {
      name: 'Dataset',
      hold: named('dataset_verified')?.status !== 'pass',
      note: named('dataset_verified')?.detail || runtimeStatus?.datasetStatus || 'Not verified.',
    },
    {
      name: 'Live capability',
      hold: true,
      note: 'Live stays locked. No Binance trade keys in this session.',
    },
    {
      name: 'Live canary',
      hold: true,
      note: 'ready_for_live remains false until operator gates exist.',
    },
  ];

  const ready = gates.every((gate) => !gate.hold);

  return (
    <div className="dashboard-card" style={{ padding: '16px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldCheck size={16} color="var(--gold-primary)" />
          <span style={{ fontSize: '13px', fontWeight: 700, letterSpacing: '0.04em' }}>QUALIFY</span>
        </div>
        <span style={{ color: ready ? '#22c55e' : '#ef4444', fontSize: '11px', fontWeight: 700 }}>
          {ready ? 'READY FOR LIVE CANARY' : 'NOT READY FOR LIVE'}
        </span>
      </div>
      {gates.map((gate) => (
        <div
          key={gate.name}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: '16px',
            borderTop: '1px solid #1c2330',
            padding: '10px 0',
          }}
        >
          <div>
            <div style={{ fontSize: '13px', color: '#f8fafc' }}>{gate.name}</div>
            <div style={{ fontSize: '11px', color: '#676b78', marginTop: '2px' }}>{gate.note}</div>
          </div>
          <span style={{ fontSize: '11px', fontWeight: 700, color: gate.hold ? '#ef4444' : '#22c55e' }}>
            {gate.hold ? 'HOLD' : 'PASS'}
          </span>
        </div>
      ))}
    </div>
  );
};
