import React, { useState } from 'react';
import {
  Play,
  CheckCircle,
  AlertCircle,
  GitCompare,
  TrendingUp,
  Activity,
  Layers,
  Sparkles,
} from 'lucide-react';
import { StrategyGenome, BacktestPerformance } from '../../types';
import { GenomeEditor } from './GenomeEditor';

interface StrategyStudioProps {
  initialGenomes: StrategyGenome[];
  activeGenomeId?: string;
  onPromote?: (genomeId: string) => void;
}

const mockBacktestResult: BacktestPerformance = {
  net_pnl: '+24.50',
  gross_pnl: '+28.20',
  fee_drag: '3.70',
  net_return: '+24.5%',
  annualized_return: '+38.2%',
  trade_count: 42,
  win_rate: '57.1%',
  profit_factor: '1.85',
  maximum_drawdown: '4.8%',
  sharpe_ratio: '2.14',
  sortino_ratio: '3.20',
  calmar_ratio: '7.95',
};

export const StrategyStudio: React.FC<StrategyStudioProps> = ({
  initialGenomes,
  activeGenomeId = 'trend-pullback-v1',
  onPromote,
}) => {
  const [genomes, setGenomes] = useState<StrategyGenome[]>(initialGenomes);
  const [selectedId, setSelectedId] = useState<string>(activeGenomeId);
  const [isRunningBacktest, setIsRunningBacktest] = useState(false);
  const [backtestMetrics, setBacktestMetrics] = useState<BacktestPerformance | null>(null);

  const activeGenome = genomes.find((g) => g.genome_id === activeGenomeId) || genomes[0];
  const selectedGenome = genomes.find((g) => g.genome_id === selectedId) || genomes[0];
  const isCandidate = selectedGenome.genome_id !== activeGenome.genome_id;

  const handleRunBacktest = () => {
    setIsRunningBacktest(true);
    setTimeout(() => {
      setIsRunningBacktest(false);
      setBacktestMetrics(mockBacktestResult);
    }, 400);
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
        return '#f0b90b';
      case 'quarantined':
        return '#ef4444';
      default:
        return '#9498a4';
    }
  };

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
      {/* Top Banner: Strategy Studio Title & Action Header */}
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
          <Sparkles size={20} color="#f0b90b" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Strategy Studio & Genome Lab
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Deterministic Strategy DSL, Parameter Bounds & Multi-Gate Promotion
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            onClick={handleRunBacktest}
            disabled={isRunningBacktest}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              backgroundColor: '#f0b90b',
              color: '#000',
              fontWeight: 700,
              fontSize: '13px',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              opacity: isRunningBacktest ? 0.7 : 1,
            }}
          >
            <Play size={14} fill="#000" />
            {isRunningBacktest ? 'Simulating...' : 'Run Backtest'}
          </button>

          {isCandidate && selectedGenome.status !== 'active' && (
            <button
              type="button"
              onClick={() => onPromote && onPromote(selectedGenome.genome_id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                color: '#10b981',
                border: '1px solid rgba(16, 185, 129, 0.4)',
                fontWeight: 600,
                fontSize: '13px',
                borderRadius: '6px',
                cursor: 'pointer',
              }}
            >
              <CheckCircle size={14} /> Promote Candidate
            </button>
          )}
        </div>
      </div>

      {/* Main Grid: Left (Genome selector & diff) + Right (Editor & Backtest) */}
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '12px' }}>
        {/* Left Column: Genome List */}
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
                  border: isSel ? '1px solid rgba(240, 185, 11, 0.5)' : '1px solid #1c2028',
                  backgroundColor: isSel ? 'rgba(240, 185, 11, 0.08)' : '#121418',
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
                      color: isSel ? '#f0b90b' : '#e2e4e8',
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

        {/* Right Column: Editor + Diff + Performance Inline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Diff vs Active Banner if candidate is selected */}
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
                Refinements bounded by Domain Bounds
              </span>
            </div>
          )}

          {/* Genome Editor */}
          <GenomeEditor
            genome={selectedGenome}
            onChange={(updated) => {
              const next = genomes.map((g) => (g.genome_id === updated.genome_id ? updated : g));
              setGenomes(next);
            }}
          />

          {/* Performance & Equity Curve Section */}
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
                  Deterministic Backtest Metrics (IS &amp; OOS)
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
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#f0b90b' }}>
                    {backtestMetrics.win_rate}
                  </span>
                </div>
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Profit Factor</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#60a5fa' }}>
                    {backtestMetrics.profit_factor}
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
                    {backtestMetrics.sharpe_ratio}
                  </span>
                </div>
                <div style={{ backgroundColor: '#121418', padding: '8px 10px', borderRadius: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#676b78', display: 'block' }}>Trades</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#e2e4e8' }}>
                    {backtestMetrics.trade_count}
                  </span>
                </div>
              </div>

              {/* Inline SVG Equity Curve */}
              <div style={{ marginTop: '6px' }}>
                <span style={{ fontSize: '11.5px', color: '#676b78', marginBottom: '6px', display: 'block' }}>
                  Equity Progression (Simulated Realistic Friction)
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
                    points="0,70 50,65 100,58 150,62 200,45 250,48 300,32 350,35 400,20 450,22 500,10"
                  />
                </svg>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
