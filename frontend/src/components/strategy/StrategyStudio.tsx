import React, { useState } from 'react';
import {
  Play,
  GitCompare,
  TrendingUp,
  Layers,
  Sparkles,
} from 'lucide-react';
import { StrategyGenome, BacktestPerformance } from '../../types';
import { GenomeEditor } from './GenomeEditor';
import { useBot } from '../../context/BotContext';
import { api } from '../../api/client';

interface StrategyStudioProps {
  initialGenomes?: StrategyGenome[];
  activeGenomeId?: string;
}

interface BacktestTrade {
  pnl?: number;
}

export const StrategyStudio: React.FC<StrategyStudioProps> = ({
  initialGenomes,
  activeGenomeId: propActiveGenomeId,
}) => {
  let botContext: ReturnType<typeof useBot> | null = null;
  try {
    botContext = useBot();
  } catch {
    // Isolated test environment
  }

  const genomes = initialGenomes || (botContext ? botContext.genomes : []);
  const activeId = propActiveGenomeId || (botContext ? botContext.activeGenomeId : 'trend-pullback-v1');
  const [selectedId, setSelectedId] = useState<string>(activeId);
  const [isRunningBacktest, setIsRunningBacktest] = useState(false);
  const [backtestMetrics, setBacktestMetrics] = useState<(BacktestPerformance & { trades?: BacktestTrade[] }) | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const activeGenome = genomes.find((g) => g.genome_id === activeId) || genomes[0];
  const selectedGenome = genomes.find((g) => g.genome_id === selectedId) || activeGenome;
  const isCandidate = selectedGenome && activeGenome && selectedGenome.genome_id !== activeGenome.genome_id;
  const autoOn = botContext?.runtimeStatus?.autopromotionEnabled ?? false;

  const handleRunBacktest = async () => {
    setIsRunningBacktest(true);
    setBacktestError(null);
    try {
      const res = await api.runBacktest(selectedGenome);
      setBacktestMetrics(res);
      if (botContext) {
        botContext.addToast('success', 'Backtest Complete', `Simulated ${res.trade_count} trades`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Backtest failed. The server may need more verified candle data.';
      setBacktestError(msg);
      if (botContext) botContext.addToast('error', 'Backtest failed', msg);
    } finally {
      setIsRunningBacktest(false);
    }
  };

  const getStageColor = (status?: string) => {
    switch (status) {
      case 'active':
        return '#10b981';
      case 'shadow':
        return '#60a5fa';
      case 'holdout_passed':
      case 'val_passed':
      case 'dev_passed':
        return 'var(--gold-primary)';
      case 'quarantined':
        return '#ef4444';
      default:
        return '#9498a4';
    }
  };

  const equityPoints = (() => {
    const trades = backtestMetrics?.trades;
    if (!trades || trades.length === 0) return '';
    let equity = 100;
    const values = [equity];
    for (const trade of trades) {
      equity += Number(trade.pnl ?? 0);
      values.push(equity);
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    return values
      .map((value, index) => {
        const x = (index / (values.length - 1)) * 500;
        const y = 70 - ((value - min) / span) * 60;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  })();

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
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
          gap: '12px',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Sparkles size={20} color="var(--gold-primary)" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Strategy Studio & Genome Lab
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Read-only view of the genome Hermes mutates. Hermes researches, shadow-tests,
              and auto-promotes when every gate passes. You only set capital and press Start.
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              fontSize: '10px',
              fontWeight: 700,
              letterSpacing: '0.06em',
              padding: '6px 8px',
              borderRadius: '4px',
              border: autoOn ? '1px solid rgba(16,185,129,0.4)' : '1px solid #2d3139',
              color: autoOn ? '#10b981' : '#9498a4',
              backgroundColor: autoOn ? 'rgba(16,185,129,0.08)' : '#181a20',
              textTransform: 'uppercase',
            }}
          >
            {autoOn ? 'Hermes auto-promotes' : 'Auto-promote after Start'}
          </span>
          <button
            type="button"
            onClick={handleRunBacktest}
            disabled={isRunningBacktest}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              backgroundColor: 'var(--gold-primary)',
              color: '#000',
              fontWeight: 700,
              fontSize: '13px',
              borderRadius: '6px',
              border: 'none',
              cursor: isRunningBacktest ? 'not-allowed' : 'pointer',
              opacity: isRunningBacktest ? 0.7 : 1,
            }}
          >
            <Play size={14} fill="#000" />
            {isRunningBacktest ? 'Simulating Engine...' : 'Inspect backtest'}
          </button>
        </div>
      </div>

      {backtestError && (
        <div role="alert" style={{ color: '#fca5a5', fontSize: '12px' }}>{backtestError}</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '12px' }}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            backgroundColor: '#0d0e12',
            padding: '12px',
            borderRadius: '8px',
            border: '1px solid #1e222b',
            height: 'fit-content',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
            <Layers size={15} color="#9498a4" />
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
              Genome Registry
            </span>
          </div>

          {genomes.map((g) => {
            const isSel = g.genome_id === selectedId;
            const stageColor = getStageColor(g.status);
            return (
              <button
                key={g.genome_id}
                type="button"
                onClick={() => setSelectedId(g.genome_id)}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  padding: '10px 10px',
                  borderRadius: '6px',
                  border: isSel ? '1px solid rgba(61, 126, 255, 0.5)' : '1px solid #1c2028',
                  backgroundColor: isSel ? 'rgba(61, 126, 255, 0.08)' : '#121418',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span
                    style={{
                      fontSize: '12.5px',
                      fontWeight: 600,
                      color: isSel ? 'var(--gold-primary)' : '#e2e4e8',
                    }}
                  >
                    {g.title}
                  </span>
                  <span
                    style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      padding: '2px 5px',
                      borderRadius: '3px',
                      backgroundColor: `${stageColor}22`,
                      color: stageColor,
                      textTransform: 'uppercase',
                    }}
                  >
                    {g.status || 'candidate'}
                  </span>
                </div>
                <span style={{ fontSize: '11px', color: '#676b78', fontFamily: 'monospace' }}>
                  {g.genome_id}
                </span>
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {isCandidate && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                backgroundColor: 'rgba(96, 165, 250, 0.08)',
                border: '1px solid rgba(96, 165, 250, 0.3)',
                padding: '8px 12px',
                borderRadius: '6px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <GitCompare size={16} color="#60a5fa" />
                <span style={{ fontSize: '12.5px', fontWeight: 600, color: '#60a5fa' }}>
                  Diff vs Active ({activeGenome.genome_id})
                </span>
              </div>
              <span style={{ fontSize: '11.5px', color: '#9498a4' }}>
                Hermes owns mutations. Promotion is automatic.
              </span>
            </div>
          )}

          <GenomeEditor genome={selectedGenome} readOnly />

          {backtestMetrics && (
            <div
              style={{
                backgroundColor: '#0d0e12',
                border: '1px solid #1e222b',
                borderRadius: '8px',
                padding: '14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <TrendingUp size={16} color="#10b981" />
                <span style={{ fontSize: '13.5px', fontWeight: 600, color: '#f8fafc' }}>
                  Deterministic Backtest Metrics (IS & OOS Friction Included)
                </span>
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                  gap: '10px',
                }}
              >
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Net Return</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#10b981' }}>
                    {backtestMetrics.net_return}
                  </span>
                </div>
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Win Rate</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--gold-primary)' }}>
                    {backtestMetrics.win_rate}
                  </span>
                </div>
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Profit Factor</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#60a5fa' }}>
                    {backtestMetrics.profit_factor || '—'}
                  </span>
                </div>
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Max Drawdown</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#ef4444' }}>
                    {backtestMetrics.maximum_drawdown}
                  </span>
                </div>
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Sharpe Ratio</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#a78bfa' }}>
                    {backtestMetrics.sharpe_ratio || '—'}
                  </span>
                </div>
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Trades</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#e2e4e8' }}>
                    {backtestMetrics.trade_count}
                  </span>
                </div>
              </div>

              {equityPoints ? (
                <div style={{ marginTop: '6px' }}>
                  <span style={{ fontSize: '11.5px', color: '#676b78', marginBottom: '6px', display: 'block' }}>
                    Equity from this backtest (fees included)
                  </span>
                  <svg
                    viewBox="0 0 500 80"
                    style={{
                      width: '100%',
                      height: '80px',
                      backgroundColor: '#121418',
                      borderRadius: '6px',
                      padding: '6px',
                    }}
                  >
                    <polyline
                      fill="none"
                      stroke="#10b981"
                      strokeWidth="2"
                      points={equityPoints}
                    />
                  </svg>
                </div>
              ) : (
                <div style={{ fontSize: '12px', color: '#676b78' }}>
                  No trade series returned for this backtest, so no equity curve is drawn.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
