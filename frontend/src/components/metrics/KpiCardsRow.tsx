import React from 'react';
import { KpiMetrics } from '../../types/dashboard';
import { SpreadSparkline } from './SpreadSparkline';

interface KpiCardsRowProps {
  data: KpiMetrics;
  spreadHistory?: number[];
}

function fmt(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function changeColor(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) return '#676b78';
  return value > 0 ? '#22c55e' : '#ef4444';
}

function changeArrow(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) return '';
  return value > 0 ? '▲' : '▼';
}

export const KpiCardsRow: React.FC<KpiCardsRowProps> = ({ data, spreadHistory = [] }) => {
  return (
    <div className="gg-kpis">
      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          EQUITY
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {fmt(data.equity)}
          </span>
          <span style={{ fontSize: '11.5px', fontWeight: 500, color: '#9498a4' }}>
            {data.equityCurrency}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11.5px' }}>
          <span style={{ color: changeColor(data.equityChangePercent), fontWeight: 600 }}>
            {changeArrow(data.equityChangePercent)} {data.equityChangePercent == null ? '—' : `${fmt(data.equityChangePercent)}%`}
          </span>
          <span style={{ color: '#676b78' }}>{data.equityChangePeriod}</span>
        </div>
      </div>

      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          CASH
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {fmt(data.cash)}
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

      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          TOTAL PNL
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: changeColor(data.totalPnl), letterSpacing: '-0.02em' }}>
            {data.totalPnl == null ? '—' : `${data.totalPnl >= 0 ? '+' : ''}${fmt(data.totalPnl)}`}
          </span>
          <span style={{ fontSize: '11.5px', fontWeight: 500, color: '#9498a4' }}>
            {data.totalPnlCurrency}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11.5px' }}>
          <span style={{ color: changeColor(data.totalPnlChangePercent), fontWeight: 600 }}>
            {data.totalPnlChangePercent == null ? '—' : `${fmt(data.totalPnlChangePercent)}%`}
          </span>
          <span style={{ color: '#676b78' }}>{data.totalPnlChangePeriod}</span>
        </div>
      </div>

      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          MAX DRAWDOWN
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {data.maxDrawdown == null ? '—' : `${fmt(data.maxDrawdown, 1)}%`}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11.5px', color: '#676b78' }}>
          <span>—</span>
          <span>{data.maxDrawdownPeriod || 'No marks yet'}</span>
        </div>
      </div>

      <div className="dashboard-card" style={{ padding: '12px 14px', minHeight: '82px', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#9498a4', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          LIVE SPREAD
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '2px 0' }}>
          <span style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {fmt(data.liveSpread)}
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
