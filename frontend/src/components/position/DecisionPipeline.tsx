import React from 'react';
import { PipelineStep } from '../../types/dashboard';
import { Check } from 'lucide-react';

interface DecisionPipelineProps {
  steps: PipelineStep[];
}

export const DecisionPipeline: React.FC<DecisionPipelineProps> = ({ steps }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '9px', marginTop: '10px' }}>
      <div style={{
        fontSize: '11px',
        fontWeight: 600,
        color: '#9498a4',
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        marginBottom: '2px'
      }}>
        DECISION PIPELINE
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {steps.map((step) => {
          const isCompleted = step.status === 'completed';
          const isActive = step.status === 'active';
          const isPending = step.status === 'pending';

          return (
            <div
              key={step.stepNumber}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '12px',
                color: isPending ? '#555963' : isActive ? '#f8fafc' : '#e2e4e8'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {/* Number Circle Badge */}
                {isActive ? (
                  <div style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--gold-primary)',
                    color: '#0a0a0c',
                    fontSize: '11px',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    {step.stepNumber}
                  </div>
                ) : (
                  <div style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    border: isCompleted ? '1.5px solid var(--gold-dark)' : '1.5px solid #33363f',
                    color: isCompleted ? 'var(--gold-primary)' : '#555963',
                    fontSize: '10.5px',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    {step.stepNumber}
                  </div>
                )}

                {/* Label */}
                <span style={{
                  fontWeight: isActive ? 600 : isCompleted ? 500 : 400,
                  color: isActive ? '#f8fafc' : isCompleted ? '#e2e4e8' : '#555963'
                }}>
                  {step.label}
                </span>
              </div>

              {/* Status checkmark on right */}
              {isCompleted && (
                <Check size={15} color="#22c55e" strokeWidth={2.5} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
