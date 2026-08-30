import React from 'react';
import { Landmark, TrendingUp, ArrowRight } from 'lucide-react';
import { BinanceIcon } from '../common/Icons';
import { NewsItem } from '../../types/dashboard';

interface LiveContextCardProps {
  items: NewsItem[];
  onViewAll?: () => void;
}

export const LiveContextCard: React.FC<LiveContextCardProps> = ({ items, onViewAll }) => {
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
            backgroundColor: 'rgba(61, 126, 255, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <BinanceIcon size={15} />
          </div>
        );
      default:
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
    }
  };

  return (
    <div className="dashboard-card" style={{ flex: 1.15, padding: '10px 14px', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: '11px', fontWeight: 700, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase', marginBottom: '6px', flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>LIVE CONTEXT</span>
        {items.length > 0 && (
          <span style={{ fontSize: '10px', color: '#676b78', letterSpacing: 0, fontWeight: 500 }}>
            {items.length} observations
          </span>
        )}
      </div>

      <div className="gg-scroll" style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingRight: '4px' }}>
        {items.length === 0 ? (
          <div style={{ color: '#676b78', fontSize: '12px', padding: '12px 4px' }}>
            No live quotes or calendar rows yet.
          </div>
        ) : items.map((item) => (
          <div key={item.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '9px' }}>
            {getIcon(item.category)}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', minWidth: 0 }}>
              <div style={{ fontSize: '11.5px', fontWeight: 500, color: '#f8fafc', lineHeight: 1.25 }}>
                {item.title}
              </div>
              <div style={{ fontSize: '10.5px', color: '#38bdf8' }}>
                <span>{item.source}</span>
                <span style={{ color: '#676b78', margin: '0 4px' }}>·</span>
                <span style={{ color: '#38bdf8' }}>{item.time}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

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
          <span>VIEW ALL CONTEXT</span>
          <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
};
