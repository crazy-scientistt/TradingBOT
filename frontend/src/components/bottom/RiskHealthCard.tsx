import React from 'react';
import { Database, FileText, Link2, ArrowRight } from 'lucide-react';
import { HermesIcon } from '../common/Icons';
import { HealthStatusItem } from '../../types/dashboard';

interface RiskHealthCardProps {
  items: HealthStatusItem[];
  onViewAll?: () => void;
}

export const RiskHealthCard: React.FC<RiskHealthCardProps> = ({ items, onViewAll }) => {
  const getIcon = (iconType: string) => {
    switch (iconType) {
      case 'database':
        return <Database size={14} color="#9498a4" />;
      case 'lease':
        return <FileText size={14} color="#9498a4" />;
      case 'gemini':
        return <Link2 size={14} color="#9498a4" />;
      case 'hermes':
        return <HermesIcon size={14} className="text-secondary" />;
      default:
        return null;
    }
  };

  return (
    <div className="dashboard-card" style={{ flex: 1, padding: '10px 14px', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: '11px', fontWeight: 700, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase', marginBottom: '6px', flexShrink: 0 }}>
        RISK & HEALTH
      </div>

      <div className="gg-scroll" style={{ display: 'flex', flexDirection: 'column', gap: '9px', paddingRight: '4px' }}>
        {items.map((item) => {
          const isOk = item.status === 'OK';
          const isInfo = item.status === 'INFO';

          return (
            <div
              key={item.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.03em'
              }}
            >
              {/* Left icon + label */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '9px', color: '#e2e4e8' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '16px' }}>
                  {getIcon(item.icon)}
                </div>
                <span>{item.label}</span>
              </div>

              {/* Right status badge */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                color: isOk ? '#22c55e' : isInfo ? '#38bdf8' : '#f59e0b',
                fontWeight: 700,
                fontSize: '10.5px'
              }}>
                <span style={{
                  width: '5px',
                  height: '5px',
                  borderRadius: '50%',
                  backgroundColor: isOk ? '#22c55e' : isInfo ? '#38bdf8' : '#f59e0b',
                  boxShadow: isOk ? '0 0 6px rgba(34, 197, 94, 0.6)' : '0 0 6px rgba(56, 189, 248, 0.6)'
                }} />
                <span>{item.status}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Link */}
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: '6px', flexShrink: 0 }}>
        <button
          type="button"
          onClick={onViewAll}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#38bdf8',
            fontSize: '11px',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            cursor: 'pointer',
            letterSpacing: '0.04em'
          }}
          onMouseEnter={(e) => e.currentTarget.style.color = '#7dd3fc'}
          onMouseLeave={(e) => e.currentTarget.style.color = '#38bdf8'}
        >
          <span>VIEW SYSTEM STATUS</span>
          <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
};
