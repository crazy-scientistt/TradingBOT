import React, { useState } from 'react';
import { FlaskConical, Sparkles, BookOpen } from 'lucide-react';
import { ResearchQuota, TradeReflection } from '../../types';
import { useBot } from '../../context/BotContext';

interface ResearchLabProps {
  quota?: ResearchQuota;
  reflections?: TradeReflection[];
  isRunning?: boolean;
  onRunStep?: () => void;
}

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

  const backtestPct = Math.min(100, Math.round(((quota?.backtests_used || 0) / (quota?.backtests_limit || 8)) * 100));
  const webPct = Math.min(100, Math.round(((quota?.web_calls_used || 0) / (quota?.web_calls_limit || 50)) * 100));

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
      {/* Header */}
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
          <FlaskConical size={20} color="var(--gold-primary)" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Hermes Autonomous Research Laboratory
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Self-directed hypothesis testing, bounded mutations &amp; memory bank reflections
              {lastStep ? ` · last step: ${lastStep}` : ' · also runs in the background, 8/day'}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={handleStep}
          disabled={isRunning}
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
            cursor: isRunning ? 'not-allowed' : 'pointer',
            opacity: isRunning ? 0.7 : 1,
          }}
        >
          <Sparkles size={14} fill="#000" />
          {isRunning ? 'Hermes Reasoning...' : 'Trigger Hermes Step'}
        </button>
      </div>

      {/* Daily Quota Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
        <div
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
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
              Daily Backtest Engine Quota
            </span>
            <span style={{ fontSize: '12.5px', fontWeight: 700, color: 'var(--gold-primary)', fontFamily: 'monospace' }}>
              {quota?.backtests_used || 0} / {quota?.backtests_limit || 8}
            </span>
          </div>
          {/* Progress Bar */}
          <div style={{ width: '100%', height: '6px', backgroundColor: '#181a20', borderRadius: '3px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${backtestPct}%`,
                height: '100%',
                backgroundColor: backtestPct > 80 ? '#ef4444' : 'var(--gold-primary)',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <span style={{ fontSize: '11px', color: '#676b78' }}>
            Protects CPU &amp; database capacity from runaway exploration
          </span>
        </div>

        <div
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
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
              Daily Web Search Quota (Gemini Grounding)
            </span>
            <span style={{ fontSize: '12.5px', fontWeight: 700, color: '#60a5fa', fontFamily: 'monospace' }}>
              {quota?.web_calls_used || 0} / {quota?.web_calls_limit || 50}
            </span>
          </div>
          <div style={{ width: '100%', height: '6px', backgroundColor: '#181a20', borderRadius: '3px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${webPct}%`,
                height: '100%',
                backgroundColor: webPct > 80 ? '#ef4444' : '#60a5fa',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <span style={{ fontSize: '11px', color: '#676b78' }}>
            Tiered macro citations &amp; conflict resolution requests
          </span>
        </div>
      </div>

      {/* Trade Reflections & Memory Bank */}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BookOpen size={16} color="var(--gold-primary)" />
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
            Recent Trade Post-Mortems &amp; Memory Bank Lessons
          </h3>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {(reflections || []).map((ref) => {
            const badgeStyle = getLessonBadgeStyle(ref.lesson_code);
            const isProfit = parseFloat(ref.net_pnl) > 0;
            return (
              <div
                key={ref.id}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  padding: '10px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#121418',
                  border: '1px solid #1c2028',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 700,
                        padding: '2px 7px',
                        borderRadius: '4px',
                        backgroundColor: badgeStyle.bg,
                        color: badgeStyle.color,
                        border: badgeStyle.border,
                        fontFamily: 'monospace',
                      }}
                    >
                      {ref.lesson_code}
                    </span>
                    <span style={{ fontSize: '12px', color: '#9498a4', fontFamily: 'monospace' }}>
                      Trade: {ref.trade_id} ({ref.exit_reason})
                    </span>
                  </div>

                  <span
                    style={{
                      fontSize: '13px',
                      fontWeight: 700,
                      color: isProfit ? '#10b981' : '#ef4444',
                      fontFamily: 'monospace',
                    }}
                  >
                    {isProfit ? `+${ref.net_pnl}` : ref.net_pnl} USDT
                  </span>
                </div>

                <p style={{ margin: 0, fontSize: '12.5px', color: '#e2e4e8', lineHeight: 1.4 }}>
                  {ref.lesson}
                </p>

                <div style={{ display: 'flex', gap: '6px', marginTop: '2px' }}>
                  {(ref.regime_tags || []).map((tag, i) => (
                    <span
                      key={i}
                      style={{
                        fontSize: '10.5px',
                        color: '#676b78',
                        backgroundColor: '#181a20',
                        padding: '2px 6px',
                        borderRadius: '3px',
                      }}
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
