import React from 'react';
import { PipelineStep } from '../../types/dashboard';
import { Check } from 'lucide-react';

interface DecisionPipelineProps {
  steps: PipelineStep[];
}

export const DecisionPipeline: React.FC<DecisionPipelineProps> = ({ steps }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '9px', marginTop: '12px' }}>
      <div style={{
        fontSize: '11px',
        fontWeight: 600,
        color: '#94a3b8',
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
                fontSize: '12.5px',
                color: isPending ? '#64748b' : isActive ? '#f8fafc' : '#e2e8f0'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {/* Number Circle Badge */}
                {isActive ? (
                  <div style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    backgroundColor: '#f59e0b',
                    color: '#0a0c10',
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
                    border: isCompleted ? '1.5px solid #d4a017' : '1.5px solid #334155',
                    color: isCompleted ? '#f59e0b' : '#64748b',
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
                  color: isActive ? '#f8fafc' : isCompleted ? '#e2e8f0' : '#64748b'
                }}>
                  {step.label}
                </span>
              </div>

              {/* Status indicator on right */}
              {isCompleted && (
                <Check size={16} color="#22c55e" strokeWidth={2.5} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
