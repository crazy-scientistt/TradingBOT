import React from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';
import { useBot } from '../../context/BotContext';

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useBot();

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        zIndex: 9999,
        maxWidth: '380px',
        pointerEvents: 'none',
      }}
    >
      {toasts.map((t) => {
        const getStyles = () => {
          switch (t.type) {
            case 'success':
              return { border: '1px solid rgba(16, 185, 129, 0.4)', bg: '#0b1914', color: '#10b981', icon: CheckCircle2 };
            case 'error':
              return { border: '1px solid rgba(239, 68, 68, 0.4)', bg: '#1f0d0e', color: '#ef4444', icon: AlertCircle };
            case 'warning':
              return { border: '1px solid rgba(61, 126, 255, 0.4)', bg: '#0b1018', color: 'var(--gold-primary)', icon: AlertTriangle };
            default:
              return { border: '1px solid rgba(96, 165, 250, 0.4)', bg: '#0d1522', color: '#60a5fa', icon: Info };
          }
        };

        const s = getStyles();
        const Icon = s.icon;

        return (
          <div
            key={t.id}
            style={{
              pointerEvents: 'auto',
              backgroundColor: s.bg,
              border: s.border,
              borderRadius: '8px',
              padding: '12px 14px',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.6)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              animation: 'slideIn 0.2s ease',
            }}
          >
            <Icon size={18} color={s.color} style={{ flexShrink: 0, marginTop: '2px' }} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                  {t.title}
                </span>
                <span style={{ fontSize: '10.5px', color: '#676b78', fontFamily: 'monospace' }}>
                  {t.timestamp}
                </span>
              </div>
              {t.message && (
                <span style={{ fontSize: '12px', color: '#9498a4', lineHeight: 1.3 }}>
                  {t.message}
                </span>
              )}
            </div>
            <button
              onClick={() => removeToast(t.id)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#676b78',
                cursor: 'pointer',
                padding: '2px',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
