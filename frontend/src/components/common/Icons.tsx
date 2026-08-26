import React from 'react';

// GoldGuard Shield Logo with stylized gold wings
export const GoldGuardLogo: React.FC<{ size?: number; className?: string }> = ({ size = 28, className = '' }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M16 2L4 7V15.5C4 22.8 9.1 29.5 16 31C22.9 29.5 28 22.8 28 15.5V7L16 2Z"
      fill="#F0B90B"
      fillOpacity="0.15"
      stroke="#F0B90B"
      strokeWidth="2"
      strokeLinejoin="round"
    />
    <path
      d="M16 7L8 11V16C8 20.8 11.4 25.2 16 26.5C20.6 25.2 24 20.8 24 16V11L16 7Z"
      fill="#F0B90B"
    />
    <path
      d="M16 11L11 14.5V17C11 20 13.1 22.8 16 23.6C18.9 22.8 21 20 21 17V14.5L16 11Z"
      fill="#13171F"
    />
  </svg>
);

// Binance Exchange Logo Icon
export const BinanceIcon: React.FC<{ size?: number; className?: string }> = ({ size = 18, className = '' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <rect width="24" height="24" rx="12" fill="#F0B90B" fillOpacity="0.2" />
    <path
      d="M12 6L14.4 8.4L9.6 13.2L7.2 10.8L12 6ZM16.8 10.8L19.2 13.2L16.8 15.6L14.4 13.2L16.8 10.8ZM12 15.6L14.4 18L9.6 22.8L7.2 20.4L12 15.6ZM12 10.8L14.4 13.2L12 15.6L9.6 13.2L12 10.8Z"
      fill="#F0B90B"
    />
  </svg>
);

// Wing/Feather icon for Hermes
export const HermesIcon: React.FC<{ size?: number; className?: string }> = ({ size = 18, className = '' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z" />
    <line x1="16" y1="8" x2="2" y2="22" />
    <line x1="17.5" y1="15" x2="9" y2="15" />
  </svg>
);
