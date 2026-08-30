import React from 'react';
import { Trash2, AlertTriangle } from 'lucide-react';
import { Condition, IndicatorSpec } from '../../types';

interface ConditionBuilderProps {
  conditions: Condition[];
  onChange: (conditions: Condition[]) => void;
  disabled?: boolean;
}

export const ConditionBuilder: React.FC<ConditionBuilderProps> = ({
  conditions,
  onChange,
  disabled = false,
}) => {
  const handleUpdate = (index: number, updated: Condition) => {
    const next = [...conditions];
    next[index] = updated;
    onChange(next);
  };

  const handleRemove = (index: number) => {
    const next = conditions.filter((_, i) => i !== index);
    onChange(next);
  };

  const handleAdd = () => {
    onChange([
      ...conditions,
      {
        left: { indicator: 'rsi', timeframe: '15m', period: 14 },
        op: '>',
        right: '50',
      },
    ]);
  };

  const isOutOfBounds = (cond: Condition): string | null => {
    const val = parseFloat(String(cond.right));
    if (isNaN(val)) return 'Invalid number';
    if (typeof cond.left === 'object') {
      if (cond.left.indicator === 'rsi' && (val < 20 || val > 90)) {
        return 'RSI outside [20, 90] bounds';
      }
      if (cond.left.indicator === 'volume_ratio' && (val < 0 || val > 5)) {
        return 'Volume ratio outside [0, 5] bounds';
      }
    }
    return null;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {conditions.map((cond, idx) => {
        const warning = isOutOfBounds(cond);
        const isIndicator = typeof cond.left === 'object';
        const indicator = isIndicator ? (cond.left as IndicatorSpec) : null;

        return (
          <div
            key={idx}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              padding: '8px 10px',
              borderRadius: '6px',
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              border: warning ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid #23272e',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              {/* Left operand */}
              {isIndicator && indicator ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <select
                    disabled={disabled}
                    value={indicator.indicator}
                    onChange={(e) =>
                      handleUpdate(idx, {
                        ...cond,
                        left: { ...indicator, indicator: e.target.value as any },
                      })
                    }
                    style={{
                      backgroundColor: '#121418',
                      color: 'var(--gold-primary)',
                      border: '1px solid #2d3139',
                      borderRadius: '4px',
                      padding: '4px 6px',
                      fontSize: '12px',
                    }}
                  >
                    <option value="rsi">RSI</option>
                    <option value="volume_ratio">Volume Ratio</option>
                    <option value="ema_slope">EMA Slope</option>
                    <option value="atr_ratio">ATR Ratio</option>
                  </select>

                  <select
                    disabled={disabled}
                    value={indicator.timeframe}
                    onChange={(e) =>
                      handleUpdate(idx, {
                        ...cond,
                        left: { ...indicator, timeframe: e.target.value as any },
                      })
                    }
                    style={{
                      backgroundColor: '#121418',
                      color: '#9498a4',
                      border: '1px solid #2d3139',
                      borderRadius: '4px',
                      padding: '4px 6px',
                      fontSize: '12px',
                    }}
                  >
                    <option value="15m">15m</option>
                    <option value="1h">1h</option>
                  </select>

                  <input
                    disabled={disabled}
                    type="number"
                    value={indicator.period}
                    onChange={(e) =>
                      handleUpdate(idx, {
                        ...cond,
                        left: { ...indicator, period: parseInt(e.target.value) || 14 },
                      })
                    }
                    style={{
                      width: '45px',
                      backgroundColor: '#121418',
                      color: '#e2e4e8',
                      border: '1px solid #2d3139',
                      borderRadius: '4px',
                      padding: '4px',
                      fontSize: '12px',
                      textAlign: 'center',
                    }}
                  />
                </div>
              ) : (
                <span
                  style={{
                    color: 'var(--gold-primary)',
                    fontSize: '12px',
                    fontFamily: 'monospace',
                    padding: '4px 6px',
                    backgroundColor: '#121418',
                    borderRadius: '4px',
                  }}
                >
                  {String(cond.left)}
                </span>
              )}

              {/* Operator */}
              <select
                disabled={disabled}
                value={cond.op}
                onChange={(e) => handleUpdate(idx, { ...cond, op: e.target.value as any })}
                style={{
                  backgroundColor: '#121418',
                  color: '#60a5fa',
                  border: '1px solid #2d3139',
                  borderRadius: '4px',
                  padding: '4px 8px',
                  fontSize: '12px',
                  fontWeight: 600,
                }}
              >
                <option value=">">&gt;</option>
                <option value="<">&lt;</option>
                <option value=">=">&gt;=</option>
                <option value="<=">&lt;=</option>
                <option value="==">==</option>
                <option value="crosses_above">crosses above</option>
                <option value="crosses_below">crosses below</option>
              </select>

              {/* Right operand */}
              <input
                disabled={disabled}
                type="text"
                value={String(cond.right)}
                onChange={(e) => handleUpdate(idx, { ...cond, right: e.target.value })}
                style={{
                  width: '70px',
                  backgroundColor: '#121418',
                  color: '#10b981',
                  border: '1px solid #2d3139',
                  borderRadius: '4px',
                  padding: '4px 6px',
                  fontSize: '12px',
                  fontWeight: 600,
                  fontFamily: 'monospace',
                  textAlign: 'center',
                }}
              />

              {!disabled && (
                <button
                  type="button"
                  onClick={() => handleRemove(idx)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#ef4444',
                    cursor: 'pointer',
                    padding: '4px',
                    marginLeft: 'auto',
                  }}
                  title="Remove condition"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>

            {warning && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#ef4444', fontSize: '11px' }}>
                <AlertTriangle size={12} />
                <span>{warning}</span>
              </div>
            )}
          </div>
        );
      })}

      {!disabled && (
        <button
          type="button"
          onClick={handleAdd}
          style={{
            alignSelf: 'flex-start',
            padding: '4px 10px',
            backgroundColor: 'rgba(61, 126, 255, 0.1)',
            border: '1px dashed rgba(61, 126, 255, 0.4)',
            color: 'var(--gold-primary)',
            borderRadius: '4px',
            fontSize: '11px',
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          + Add Condition
        </button>
      )}
    </div>
  );
};
