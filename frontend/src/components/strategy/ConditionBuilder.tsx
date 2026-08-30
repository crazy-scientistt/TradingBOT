import React from 'react';
import { Trash2, AlertTriangle } from 'lucide-react';
import { Condition, IndicatorSpec } from '../../types';

interface ConditionBuilderProps {
  conditions: Condition[];
  onChange: (conditions: Condition[]) => void;
  disabled?: boolean;
}

const isSpec = (value: unknown): value is IndicatorSpec =>
  typeof value === 'object' && value !== null && 'indicator' in value;

const INDICATORS: Array<IndicatorSpec['indicator']> = [
  'rsi',
  'ema',
  'ema_slope',
  'volume_ratio',
  'atr_ratio',
];

const OperandField: React.FC<{
  value: Condition['left'] | Condition['right'];
  disabled?: boolean;
  onChange: (next: IndicatorSpec | string) => void;
}> = ({ value, disabled, onChange }) => {
  if (isSpec(value)) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <select
          disabled={disabled}
          value={value.indicator}
          onChange={(e) =>
            onChange({ ...value, indicator: e.target.value as IndicatorSpec['indicator'] })
          }
          style={selectStyle}
        >
          {INDICATORS.map((name) => (
            <option key={name} value={name}>
              {name.replace('_', ' ').toUpperCase()}
            </option>
          ))}
        </select>
        <select
          disabled={disabled}
          value={value.timeframe}
          onChange={(e) =>
            onChange({ ...value, timeframe: e.target.value as IndicatorSpec['timeframe'] })
          }
          style={{ ...selectStyle, color: '#9498a4' }}
        >
          <option value="15m">15m</option>
          <option value="1h">1h</option>
        </select>
        <input
          disabled={disabled}
          type="number"
          value={value.period}
          onChange={(e) => onChange({ ...value, period: parseInt(e.target.value, 10) || 1 })}
          style={periodStyle}
        />
      </div>
    );
  }
  return (
    <input
      disabled={disabled}
      type="text"
      value={String(value ?? '')}
      onChange={(e) => onChange(e.target.value)}
      style={numberStyle}
    />
  );
};

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
    onChange(conditions.filter((_, i) => i !== index));
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
    if (isSpec(cond.right)) return null;
    const val = parseFloat(String(cond.right));
    if (isNaN(val)) return 'Enter a number, or compare two indicators';
    if (isSpec(cond.left) && cond.left.indicator === 'rsi' && (val < 20 || val > 90)) {
      return 'RSI outside [20, 90] bounds';
    }
    if (isSpec(cond.left) && cond.left.indicator === 'volume_ratio' && (val < 0 || val > 5)) {
      return 'Volume ratio outside [0, 5] bounds';
    }
    return null;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {conditions.map((cond, idx) => {
        const warning = isOutOfBounds(cond);
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
              <OperandField
                value={cond.left}
                disabled={disabled}
                onChange={(left) => handleUpdate(idx, { ...cond, left })}
              />
              <select
                disabled={disabled}
                value={cond.op}
                onChange={(e) =>
                  handleUpdate(idx, { ...cond, op: e.target.value as Condition['op'] })
                }
                style={{ ...selectStyle, color: '#60a5fa', fontWeight: 600 }}
              >
                <option value=">">{'>'}</option>
                <option value="<">{'<'}</option>
                <option value=">=">{'>='}</option>
                <option value="<=">{'<='}</option>
                <option value="==">==</option>
                <option value="crosses_above">crosses above</option>
                <option value="crosses_below">crosses below</option>
              </select>
              <OperandField
                value={cond.right}
                disabled={disabled}
                onChange={(right) => handleUpdate(idx, { ...cond, right })}
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

const selectStyle: React.CSSProperties = {
  backgroundColor: '#121418',
  color: 'var(--gold-primary)',
  border: '1px solid #2d3139',
  borderRadius: '4px',
  padding: '4px 6px',
  fontSize: '12px',
};

const periodStyle: React.CSSProperties = {
  width: '45px',
  backgroundColor: '#121418',
  color: '#e2e4e8',
  border: '1px solid #2d3139',
  borderRadius: '4px',
  padding: '4px',
  fontSize: '12px',
  textAlign: 'center',
};

const numberStyle: React.CSSProperties = {
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
};
