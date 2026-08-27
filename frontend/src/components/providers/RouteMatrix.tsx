import React from 'react';
import { Cpu, Zap, Key, ShieldCheck, RefreshCw } from 'lucide-react';
import { AIProvider, ProviderRoute } from '../../types';
import { useBot } from '../../context/BotContext';

interface RouteMatrixProps {
  providers?: AIProvider[];
  initialRoutes?: ProviderRoute[];
  onRouteChange?: (role: 'decision' | 'context' | 'hermes', providerName: string) => void;
  onRefreshLatency?: () => void;
}

export const RouteMatrix: React.FC<RouteMatrixProps> = ({
  providers: propProviders,
  initialRoutes: propRoutes,
  onRouteChange: propOnChange,
  onRefreshLatency: propOnRefresh,
}) => {
  let botContext: ReturnType<typeof useBot> | null = null;
  try {
    botContext = useBot();
  } catch {
    // Isolated test environment
  }

  const providers = propProviders || (botContext ? botContext.providers : []);
  const routes = propRoutes || (botContext ? botContext.routes : []);

  const handleRouteChange = (role: 'decision' | 'context' | 'hermes', provider: string) => {
    if (propOnChange) {
      propOnChange(role, provider);
    } else if (botContext) {
      botContext.updateRoute(role, provider);
    }
  };

  const handleProbe = () => {
    if (propOnRefresh) {
      propOnRefresh();
    } else if (botContext) {
      botContext.probeLatencies();
    }
  };

  const roles: Array<{ role: 'decision' | 'context' | 'hermes'; label: string; desc: string }> = [
    {
      role: 'decision',
      label: 'AI Trade Veto Engine',
      desc: 'Real-time trade validation & regime veto before broker execution',
    },
    {
      role: 'context',
      label: 'Live Context & Citations',
      desc: 'Search synthesis, news deduplication, conflict resolution',
    },
    {
      role: 'hermes',
      label: 'Hermes Strategy Researcher',
      desc: 'Autonomous genome mutation, post-mortems, hypothesis generation',
    },
  ];

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
      {/* Header */}
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
          <Cpu size={20} color="#f0b90b" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              AI Provider Hub &amp; Model Routing Matrix
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Multi-provider redundancy via OpenCodex Proxy with fail-closed provenance
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={handleProbe}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            backgroundColor: '#181a20',
            color: '#e2e4e8',
            border: '1px solid #2d3139',
            borderRadius: '6px',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={13} /> Probe Latencies
        </button>
      </div>

      {/* Provider Cards Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '12px',
        }}
      >
        {providers.map((p) => {
          const isOnline = p.status === 'active';
          return (
            <div
              key={p.name}
              style={{
                backgroundColor: '#0d0e12',
                border: '1px solid #1e222b',
                borderRadius: '8px',
                padding: '14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>
                  {p.name}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <span
                    style={{
                      width: '7px',
                      height: '7px',
                      borderRadius: '50%',
                      backgroundColor: isOnline ? '#10b981' : '#ef4444',
                      boxShadow: isOnline ? '0 0 6px #10b981' : 'none',
                    }}
                  />
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      color: isOnline ? '#10b981' : '#ef4444',
                      textTransform: 'uppercase',
                    }}
                  >
                    {p.status}
                  </span>
                </div>
              </div>

              <span style={{ fontSize: '11.5px', color: '#676b78', fontFamily: 'monospace' }}>
                {p.base_url}
              </span>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Key size={12} color="#9498a4" />
                  <span style={{ fontSize: '11px', color: '#9498a4', fontFamily: 'monospace' }}>
                    {p.key_fingerprint}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Zap size={12} color="#f0b90b" />
                  <span style={{ fontSize: '11.5px', fontWeight: 600, color: '#e2e4e8' }}>
                    {p.latency_ms} ms
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Active Route Assignment Table */}
      <div
        style={{
          backgroundColor: '#0d0e12',
          border: '1px solid #1e222b',
          borderRadius: '8px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
          Active Model Routing Matrix
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {roles.map(({ role, label, desc }) => {
            const currentRoute = routes.find((r) => r.role === role);
            return (
              <div
                key={role}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '12px 14px',
                  borderRadius: '6px',
                  backgroundColor: '#121418',
                  border: '1px solid #1c2028',
                  flexWrap: 'wrap',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <span style={{ fontSize: '13.5px', fontWeight: 600, color: '#f0b90b' }}>
                    {label}
                  </span>
                  <span style={{ fontSize: '11.5px', color: '#676b78' }}>
                    {desc}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <select
                    data-testid={`route-select-${role}`}
                    value={currentRoute?.provider || providers[0]?.name || 'opencodex'}
                    onChange={(e) => handleRouteChange(role, e.target.value)}
                    style={{
                      backgroundColor: '#0d0e12',
                      color: '#f8fafc',
                      border: '1px solid #2d3139',
                      borderRadius: '5px',
                      padding: '6px 10px',
                      fontSize: '12.5px',
                      fontWeight: 500,
                    }}
                  >
                    {providers.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.name} ({currentRoute?.model || 'google-antigravity/gemini-3.7-flash'})
                      </option>
                    ))}
                  </select>

                  <span
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '11px',
                      color: '#10b981',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      backgroundColor: 'rgba(16, 185, 129, 0.1)',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                    }}
                  >
                    <ShieldCheck size={13} /> Strict Schema
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
