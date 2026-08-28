import React from 'react';
import { KpiMetrics } from '../../types/dashboard';
import { SpreadSparkline } from './SpreadSparkline';

interface KpiCardsRowProps {
  data: KpiMetrics;
  spreadHistory?: number[];
}

export const KpiCardsRow: React.FC<KpiCardsRowProps> = ({ data, spreadHistory = [] }) => {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(5, 1fr)',
      gap: '10px',
      width: '100%'
    }}>
      {/* 1. EQUITY */}
      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          EQUITY
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {data.equity.toFixed(2)}
          </span>
          <span style={{ fontSize: '11.5px', fontWeight: 500, color: '#9498a4' }}>
            {data.equityCurrency}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11.5px' }}>
          <span style={{ color: '#22c55e', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '2px' }}>
            <span style={{ fontSize: '9px' }}>▲</span> {data.equityChangePercent.toFixed(2)}%
          </span>
          <span style={{ color: '#676b78' }}>
            {data.equityChangePeriod}
          </span>
        </div>
      </div>

      {/* 2. CASH */}
      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          CASH
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {data.cash.toFixed(2)}
          </span>
          <span style={{ fontSize: '11.5px', fontWeight: 500, color: '#9498a4' }}>
            {data.cashCurrency}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11.5px', color: '#676b78' }}>
          <span>—</span>
          <span>{data.cashChangeNote}</span>
        </div>
      </div>

      {/* 3. TOTAL PNL */}
      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          TOTAL PNL
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            +{data.totalPnl.toFixed(2)}
          </span>
          <span style={{ fontSize: '11.5px', fontWeight: 500, color: '#9498a4' }}>
            {data.totalPnlCurrency}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11.5px' }}>
          <span style={{ color: '#22c55e', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '2px' }}>
            <span style={{ fontSize: '9px' }}>▲</span> {data.totalPnlChangePercent.toFixed(2)}%
          </span>
          <span style={{ color: '#676b78' }}>
            {data.totalPnlChangePeriod}
          </span>
        </div>
      </div>

      {/* 4. MAX DRAWDOWN */}
      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          MAX DRAWDOWN
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {data.maxDrawdown.toFixed(1)}%
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11.5px', color: '#676b78' }}>
          <span>—</span>
          <span>{data.maxDrawdownPeriod}</span>
        </div>
      </div>

      {/* 5. LIVE SPREAD */}
      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          LIVE SPREAD
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {data.liveSpread.toFixed(2)}
          </span>
          <span style={{ fontSize: '11.5px', fontWeight: 500, color: '#9498a4' }}>
            {data.liveSpreadCurrency}
          </span>
        </div>
        <div style={{ width: '100%', height: '16px', display: 'flex', alignItems: 'center' }}>
          <SpreadSparkline height={16} values={spreadHistory} />
        </div>
      </div>
    </div>
  );
};
