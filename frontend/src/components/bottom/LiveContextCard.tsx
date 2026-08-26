import React from 'react';
import { Landmark, TrendingUp, ArrowRight } from 'lucide-react';
import { BinanceIcon } from '../common/Icons';
import { NewsItem } from '../../types/dashboard';

interface LiveContextCardProps {
  items: NewsItem[];
}

export const LiveContextCard: React.FC<LiveContextCardProps> = ({ items }) => {
  const getIcon = (category: string) => {
    switch (category) {
      case 'fed':
        return (
          <div style={{
            width: '26px',
            height: '26px',
            borderRadius: '50%',
            backgroundColor: '#122338',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <Landmark size={13} color="#38bdf8" />
          </div>
        );
      case 'yields':
        return (
          <div style={{
            width: '26px',
            height: '26px',
            borderRadius: '50%',
            backgroundColor: '#122338',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <TrendingUp size={13} color="#38bdf8" />
          </div>
        );
      case 'exchange':
        return (
          <div style={{
            width: '26px',
            height: '26px',
            borderRadius: '50%',
            backgroundColor: 'rgba(240, 185, 11, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <BinanceIcon size={15} />
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="dashboard-card" style={{ flex: 1.15, padding: '10px 14px', minHeight: '175px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      {/* Header */}
      <div style={{ fontSize: '11px', fontWeight: 700, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase', marginBottom: '6px' }}>
        LIVE CONTEXT
      </div>

      {/* News Items List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {items.map((item) => (
          <div key={item.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '9px' }}>
            {getIcon(item.category)}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
              <div style={{ fontSize: '11.5px', fontWeight: 500, color: '#f8fafc', lineHeight: 1.25 }}>
                {item.title}
              </div>
              <div style={{ fontSize: '10.5px', color: '#38bdf8' }}>
                <span style={{ cursor: 'pointer' }}>{item.source}</span>
                <span style={{ color: '#676b78', margin: '0 4px' }}>·</span>
                <span style={{ color: '#38bdf8' }}>{item.time}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer Link */}
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: '6px' }}>
        <button
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
          <span>VIEW ALL CONTEXT</span>
          <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
};
