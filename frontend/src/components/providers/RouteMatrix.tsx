import React from 'react';
import { Cpu, Zap, Key, ShieldCheck, RefreshCw } from 'lucide-react';
import { AIProvider, OpenCodexModel, ProviderRoute } from '../../types';
import { useBot } from '../../context/BotContext';

interface RouteMatrixProps {
  providers?: AIProvider[];
  catalog?: OpenCodexModel[];
  initialRoutes?: ProviderRoute[];
  onRouteChange?: (role: 'decision' | 'context' | 'hermes', providerName: string) => void;
  onRefreshLatency?: () => void;
}

export const RouteMatrix: React.FC<RouteMatrixProps> = ({
  providers: propProviders,
  catalog: propCatalog,
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
  const catalog = propCatalog || (botContext ? botContext.catalog : []);
  const routes = propRoutes || (botContext ? botContext.routes : []);

  const handleRouteChange = (role: 'decision' | 'context' | 'hermes', value: string) => {
    const isModel = catalog.some((model) => model.id === value);
    const provider = isModel ? 'opencodex' : value;
    const model = isModel ? value : undefined;
    if (propOnChange) {
      propOnChange(role, provider);
    } else if (botContext) {
      void botContext.updateRoute(role, provider, model);
    }
  };

  const handleProbe = () => {
    if (propOnRefresh) {
      propOnRefresh();
    } else if (botContext) {
      void botContext.probeLatencies();
    }
  };

  const roles: Array<{ role: 'decision' | 'context' | 'hermes'; label: string; desc: string }> = [
    {
      role: 'decision',
      label: 'Trade veto',
      desc: 'Second opinion before a buy. Never sizes the trade.',
    },
    {
      role: 'context',
      label: 'News reader',
      desc: 'What the agent reads (calendar, headlines, citations).',
    },
    {
      role: 'hermes',
      label: 'Hermes researcher',
      desc: 'Invent / test strategy changes in the background.',
    },
  ];

  const gateway = providers.find((p) => p.name === 'opencodex');
  const gatewayOk = gateway?.status === 'active' || gateway?.probe_status === 'ok';

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
              Providers
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Keys live in OpenCodex. Here you only pick which model each job uses.
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
          <RefreshCw size={13} /> Test connection
        </button>
      </div>

      {catalog.length === 0 && (
        <div
          role="status"
          style={{
            padding: '12px 14px',
            borderRadius: '8px',
            border: '1px solid rgba(240,185,11,0.35)',
            backgroundColor: 'rgba(240,185,11,0.08)',
            color: '#f0b90b',
            fontSize: '13px',
          }}
        >
          OpenCodex has not listed any models yet. After the second Railway service is up,
          add Gemini / Antigravity in the OpenCodex dashboard. They will appear here automatically.
        </div>
      )}

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
                    {p.latency_ms != null ? `${p.latency_ms} ms` : '—'}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

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
          Which model does each job use?
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {roles.map(({ role, label, desc }) => {
            const currentRoute = routes.find((r) => r.role === role);
            const selectValue = catalog.length
              ? (currentRoute?.model || catalog[0]?.id || '')
              : (currentRoute?.provider || providers[0]?.name || 'opencodex');
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
                  {currentRoute?.model && (
                    <span style={{ fontSize: '11px', color: '#9498a4', fontFamily: 'monospace' }}>
                      {currentRoute.model}
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <select
                    data-testid={`route-select-${role}`}
                    value={selectValue}
                    onChange={(e) => handleRouteChange(role, e.target.value)}
                    style={{
                      backgroundColor: '#0d0e12',
                      color: '#f8fafc',
                      border: '1px solid #2d3139',
                      borderRadius: '5px',
                      padding: '6px 10px',
                      fontSize: '12.5px',
                      fontWeight: 500,
                      minWidth: '220px',
                    }}
                  >
                    {catalog.length > 0
                      ? catalog.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.name || model.id}
                          </option>
                        ))
                      : providers.map((p) => (
                          <option key={p.name} value={p.name}>
                            {p.name}
                          </option>
                        ))}
                  </select>

                  <span
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '11px',
                      color: gatewayOk ? '#10b981' : '#9498a4',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      backgroundColor: gatewayOk ? 'rgba(16, 185, 129, 0.1)' : 'rgba(148,152,164,0.08)',
                      border: gatewayOk ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid #2d3139',
                    }}
                  >
                    <ShieldCheck size={13} /> {gatewayOk ? 'Gateway up' : 'Waiting'}
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
