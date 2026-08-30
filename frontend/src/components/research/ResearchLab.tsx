import React, { useState } from 'react';
import { FlaskConical, Sparkles, BookOpen, FileText, GitBranch } from 'lucide-react';
import { HermesJournal, ResearchQuota, TradeReflection } from '../../types';
import { useBot } from '../../context/BotContext';

interface ResearchLabProps {
  quota?: ResearchQuota;
  reflections?: TradeReflection[];
  isRunning?: boolean;
  onRunStep?: () => void;
}

const gateText = (gates: Record<string, unknown> | undefined): string => {
  if (!gates) return '';
  if (typeof gates.error === 'string') return gates.error;
  if (typeof gates.reason === 'string') return gates.reason;
  if (Array.isArray(gates.reasons)) return gates.reasons.map(String).join(' · ');
  return '';
};

export const ResearchLab: React.FC<ResearchLabProps> = ({
  quota: propQuota,
  reflections: propReflections,
  isRunning: propIsRunning,
  onRunStep: propOnRunStep,
}) => {
  let botContext: ReturnType<typeof useBot> | null = null;
  try {
    botContext = useBot();
  } catch {
    // Isolated test environment
  }

  const quota = propQuota || (botContext ? botContext.quota : null);
  const reflections = propReflections || (botContext ? botContext.reflections : []);
  const journal: HermesJournal | null = botContext?.hermesJournal ?? null;
  const [internalRunning, setInternalRunning] = useState(false);
  const [lastStep, setLastStep] = useState<string | null>(null);
  const isRunning = propIsRunning !== undefined ? propIsRunning : internalRunning;

  const handleStep = async () => {
    if (propOnRunStep) {
      propOnRunStep();
      return;
    }
    if (botContext) {
      setInternalRunning(true);
      try {
        const result = await botContext.triggerHermesStep();
        if (result?.status) {
          const extra = result.candidate_genome_id ? ` · ${result.candidate_genome_id}` : '';
          setLastStep(`${result.status.replace(/_/g, ' ')}${extra}`);
        }
      } finally {
        setInternalRunning(false);
      }
    }
  };

  const getLessonBadgeStyle = (code: string) => {
    switch (code) {
      case 'TP_CLEAN':
      case 'VALID_SETUP_WIN':
        return { bg: 'rgba(16, 185, 129, 0.1)', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.3)' };
      case 'CHOP_WHIPSAW':
      case 'FEE_DRAG_HIGH':
        return { bg: 'rgba(61, 126, 255, 0.1)', color: 'var(--gold-primary)', border: '1px solid rgba(61, 126, 255, 0.3)' };
      case 'STOP_HIT_EXPANSION':
      case 'PROCESS_VIOLATION':
      case 'BLACKOUT_BREACH':
        return { bg: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' };
      default:
        return { bg: 'rgba(96, 165, 250, 0.1)', color: '#60a5fa', border: '1px solid rgba(96, 165, 250, 0.3)' };
    }
  };

  const last = journal?.last;
  const candidates = journal?.candidates ?? [];
  const cycles = journal?.cycles ?? [];
  const backtestPct = Math.min(100, Math.round(((quota?.backtests_used || 0) / (quota?.backtests_limit || 8)) * 100));
  const webPct = Math.min(100, Math.round(((quota?.web_calls_used || 0) / (quota?.web_calls_limit || 50)) * 100));
  const lastLabel = lastStep || (last ? last.status.replace(/_/g, ' ') : null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', width: '100%', color: '#e2e4e8' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        backgroundColor: '#0d0e12', padding: '12px 16px', borderRadius: '8px', border: '1px solid #1e222b',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <FlaskConical size={20} color="var(--gold-primary)" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Hermes Autonomous Research Laboratory
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Hermes already researches after Start. This button is an optional inspect of one cycle, not a required click.
              {lastLabel ? ` · last: ${lastLabel}` : ''}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={handleStep}
          disabled={isRunning}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
            backgroundColor: 'var(--gold-primary)', color: '#000', fontWeight: 700, fontSize: '13px',
            borderRadius: '6px', border: 'none', cursor: isRunning ? 'not-allowed' : 'pointer',
            opacity: isRunning ? 0.7 : 1,
          }}
        >
          <Sparkles size={14} fill="#000" />
          {isRunning ? 'Hermes Reasoning...' : 'Inspect one cycle'}
        </button>
      </div>

      <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
          <FileText size={16} color="var(--gold-primary)" />
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>Last research cycle</h3>
        </div>
        {!last ? (
          <p style={{ margin: 0, fontSize: '13px', color: '#9498a4' }}>
            No cycle recorded yet. Start paper trading, then run research. Quota counters are not a lab notebook.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '12px' }}>
              <Chip label={last.status.replace(/_/g, ' ')} />
              {last.candidate_genome_id && <Chip label={last.candidate_genome_id} />}
              {last.circuit_breaker_tripped && <Chip label="circuit open" tone="warn" />}
            </div>
            {last.hypothesis && (
              <p style={{ margin: 0, fontSize: '13px', color: '#e2e4e8', lineHeight: 1.45 }}>{last.hypothesis}</p>
            )}
            {gateText(last.gate_results) && (
              <p style={{ margin: 0, fontSize: '12px', color: '#f59e0b' }}>{gateText(last.gate_results)}</p>
            )}
            {!!last.evidence_refs?.length && (
              <div style={{ fontSize: '11px', color: '#676b78' }}>
                Evidence: {last.evidence_refs.join(' · ')}
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
          <GitBranch size={16} color="var(--gold-primary)" />
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
            Open candidates ({candidates.length})
          </h3>
        </div>
        {candidates.length === 0 ? (
          <p style={{ margin: 0, fontSize: '13px', color: '#9498a4' }}>
            Hermes has not saved a candidate genome yet. A held candidate still appears here — it does not become active until gates pass.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {candidates.map((item) => (
              <div key={item.genome_id} style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: '#121418', border: '1px solid #1c2028' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', marginBottom: '6px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>{item.title || item.genome_id}</span>
                  <span style={{ fontSize: '11px', color: '#60a5fa', fontFamily: 'monospace' }}>{item.status}</span>
                </div>
                <p style={{ margin: 0, fontSize: '12.5px', color: '#c5c8d0', lineHeight: 1.4 }}>
                  {item.hypothesis || 'No hypothesis text stored.'}
                </p>
                <div style={{ marginTop: '6px', fontSize: '11px', color: '#676b78', fontFamily: 'monospace' }}>
                  {item.genome_id}{item.parent_id ? ` ← ${item.parent_id}` : ''}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {cycles.length > 1 && (
        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '16px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: '0 0 10px' }}>Cycle log</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {cycles.slice(0, 12).map((cycle) => (
              <div key={cycle.iteration_id || cycle.observed_at} style={{ display: 'flex', gap: '10px', fontSize: '12px', color: '#9498a4' }}>
                <span style={{ color: '#f8fafc', minWidth: '140px' }}>{(cycle.status || '').replace(/_/g, ' ')}</span>
                <span style={{ fontFamily: 'monospace' }}>{cycle.candidate_genome_id || '—'}</span>
                <span>{gateText(cycle.gate_results)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
        <QuotaCard title="Daily backtests" used={quota?.backtests_used || 0} limit={quota?.backtests_limit || 8} pct={backtestPct} />
        <QuotaCard title="Daily web search" used={quota?.web_calls_used || 0} limit={quota?.web_calls_limit || 50} pct={webPct} tone="#60a5fa" />
      </div>

      <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BookOpen size={16} color="var(--gold-primary)" />
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
            Closed-trade lessons
          </h3>
        </div>
        {(reflections || []).length === 0 ? (
          <p style={{ margin: 0, fontSize: '13px', color: '#9498a4' }}>
            {journal?.lesson_note || 'No closed paper trades yet. Hermes cannot write a lesson until a position opens and closes.'}
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {(reflections || []).map((ref) => {
              const badgeStyle = getLessonBadgeStyle(ref.lesson_code);
              const isProfit = parseFloat(ref.net_pnl) > 0;
              return (
                <div key={ref.id} style={{ display: 'flex', flexDirection: 'column', gap: '6px', padding: '10px 12px', borderRadius: '6px', backgroundColor: '#121418', border: '1px solid #1c2028' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '11px', fontWeight: 700, padding: '2px 7px', borderRadius: '4px', backgroundColor: badgeStyle.bg, color: badgeStyle.color, border: badgeStyle.border, fontFamily: 'monospace' }}>
                        {ref.lesson_code}
                      </span>
                      <span style={{ fontSize: '12px', color: '#9498a4', fontFamily: 'monospace' }}>
                        Trade: {ref.trade_id} ({ref.exit_reason})
                      </span>
                    </div>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: isProfit ? '#10b981' : '#ef4444', fontFamily: 'monospace' }}>
                      {isProfit ? `+${ref.net_pnl}` : ref.net_pnl} USDT
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: '12.5px', color: '#e2e4e8', lineHeight: 1.4 }}>{ref.lesson}</p>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

const Chip: React.FC<{ label: string; tone?: 'warn' }> = ({ label, tone }) => (
  <span style={{
    fontSize: '11px', fontWeight: 700, padding: '3px 8px', borderRadius: '4px', fontFamily: 'monospace',
    backgroundColor: tone === 'warn' ? 'rgba(245,158,11,0.12)' : 'rgba(61,126,255,0.12)',
    color: tone === 'warn' ? '#f59e0b' : 'var(--gold-primary)',
    border: `1px solid ${tone === 'warn' ? 'rgba(245,158,11,0.35)' : 'rgba(61,126,255,0.35)'}`,
  }}>
    {label}
  </span>
);

const QuotaCard: React.FC<{ title: string; used: number; limit: number; pct: number; tone?: string }> = ({
  title, used, limit, pct, tone,
}) => (
  <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>{title}</span>
      <span style={{ fontSize: '12.5px', fontWeight: 700, color: tone || 'var(--gold-primary)', fontFamily: 'monospace' }}>
        {used} / {limit}
      </span>
    </div>
    <div style={{ width: '100%', height: '6px', backgroundColor: '#181a20', borderRadius: '3px', overflow: 'hidden', marginTop: '8px' }}>
      <div style={{ width: `${pct}%`, height: '100%', backgroundColor: pct > 80 ? '#ef4444' : (tone || 'var(--gold-primary)') }} />
    </div>
  </div>
);
