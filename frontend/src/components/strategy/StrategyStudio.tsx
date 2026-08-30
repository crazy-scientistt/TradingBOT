import React, { useState } from 'react';
import {
  Play,
  CheckCircle,
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
  onPromote?: (genomeId: string) => void;
}

export const StrategyStudio: React.FC<StrategyStudioProps> = ({
  initialGenomes,
  activeGenomeId: propActiveGenomeId,
  onPromote: propOnPromote,
}) => {
  let botContext: ReturnType<typeof useBot> | null = null;
  try {
    botContext = useBot();
  } catch {
    // Isolated test environment
  }

  const genomesList = initialGenomes || (botContext ? botContext.genomes : []);
  const [genomes, setGenomes] = useState<StrategyGenome[]>(genomesList);
  const activeId = propActiveGenomeId || (botContext ? botContext.activeGenomeId : 'trend-pullback-v1');
  const [selectedId, setSelectedId] = useState<string>(activeId);
  const [isRunningBacktest, setIsRunningBacktest] = useState(false);
  const [backtestMetrics, setBacktestMetrics] = useState<BacktestPerformance | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const activeGenome = genomes.find((g) => g.genome_id === activeId) || genomes[0];
  const selectedGenome = genomes.find((g) => g.genome_id === selectedId) || activeGenome;
  const isCandidate = selectedGenome && activeGenome && selectedGenome.genome_id !== activeGenome.genome_id;

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

  const handleSave = async (updated: StrategyGenome) => {
    const next = genomes.map((g) => (g.genome_id === updated.genome_id ? updated : g));
    setGenomes(next);
    try {
      await api.saveGenome(updated);
      if (botContext) {
        botContext.addToast('success', 'Genome Saved', `Saved configuration for ${updated.genome_id}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      if (botContext) botContext.addToast('error', 'Save failed', msg);
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
          <Sparkles size={20} color="var(--gold-primary)" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Strategy Studio &amp; Genome Lab
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Edit the live genome Hermes mutates. Compare indicators, backtest, then promote a candidate.
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
            {isRunningBacktest ? 'Simulating Engine...' : 'Run Backtest'}
          </button>
          {isCandidate && selectedGenome && (
            <button
              type="button"
              onClick={() => {
                if (propOnPromote) propOnPromote(selectedGenome.genome_id);
                else if (botContext) void botContext.promoteGenome(selectedGenome.genome_id);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                backgroundColor: '#181a20',
                color: '#e2e4e8',
                fontWeight: 700,
                fontSize: '13px',
                borderRadius: '6px',
                border: '1px solid #2d3139',
                cursor: 'pointer',
              }}
            >
              Promote candidate
            </button>
          )}

        </div>
      </div>

      {/* Main Grid: Left (Genome selector) + Right (Editor & Backtest) */}
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

        {/* Right Column: Editor + Diff + Performance */}
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
                Refinements bounded by Domain Bounds
              </span>
            </div>
          )}

          {/* Genome Editor */}
          <GenomeEditor
            genome={selectedGenome}
            onChange={(updated) => handleSave(updated)}
          />

          {/* Performance & Metrics Section */}
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
                  Deterministic Backtest Metrics (IS &amp; OOS Friction Included)
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

              {/* Inline Simulated Curve */}
              <div style={{ marginTop: '6px' }}>
                <span style={{ fontSize: '11.5px', color: '#676b78', marginBottom: '6px', display: 'block' }}>
                  Equity Progression (Simulated Friction)
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
