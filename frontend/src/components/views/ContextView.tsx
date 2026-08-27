import React from 'react';
import { Layers, Globe } from 'lucide-react';
import { useBot } from '../../context/BotContext';

export const ContextView: React.FC = () => {
  const { liveContext } = useBot();

  const getCategoryBadge = (cat: string) => {
    switch (cat) {
      case 'fed':
        return { label: 'Fed Policy', color: '#f0b90b', bg: 'rgba(240, 185, 11, 0.1)' };
      case 'yields':
        return { label: 'Real Yields', color: '#60a5fa', bg: 'rgba(96, 165, 250, 0.1)' };
      case 'exchange':
        return { label: 'Paxos Reserve', color: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' };
      case 'macro':
        return { label: 'Macro', color: '#f0b90b', bg: 'rgba(240, 185, 11, 0.1)' };
      default:
        return { label: cat || 'Context', color: '#a78bfa', bg: 'rgba(167, 139, 250, 0.1)' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e4e8' }}>
      {/* Top Banner */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#0d0e12',
          padding: '12px 16px',
          borderRadius: '8px',
          border: '1px solid #1e222b',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Layers size={20} color="#f0b90b" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Macro Intelligence &amp; Live Context Synthesis
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Real-time central bank feeds, 10Y real yields, and Paxos gold attestations via Gemini Grounding
            </span>
          </div>
        </div>

        <span style={{ fontSize: '11px', color: '#676b78' }}>
          {liveContext.length} observation{liveContext.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Macro Intel Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {liveContext.length === 0 ? (
          <div style={{ padding: '32px', textAlign: 'center', color: '#9498a4', fontSize: '13px' }}>
            No macro context observations yet. The AI context layer will populate here once the agent evaluates market conditions.
          </div>
        ) : liveContext.map((item) => {
          const badge = getCategoryBadge(item.category);
          return (
            <div
              key={item.id}
              style={{
                backgroundColor: '#0d0e12',
                border: '1px solid #1e222b',
                borderRadius: '8px',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '4px',
                      backgroundColor: badge.bg,
                      color: badge.color,
                      textTransform: 'uppercase',
                    }}
                  >
                    {badge.label}
                  </span>
                  <span style={{ fontSize: '12px', color: '#9498a4', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Globe size={12} /> {item.source}
                  </span>
                </div>

                <span style={{ fontSize: '12px', color: '#676b78', fontFamily: 'monospace' }}>
                  {item.time} UTC
                </span>
              </div>

              <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0, lineHeight: 1.4 }}>
                {item.title}
              </h4>
            </div>
          );
        })}
      </div>
    </div>
  );
};
