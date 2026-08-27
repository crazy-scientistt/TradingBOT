import { 
  LayoutDashboard, 
  TrendingUp, 
  Layers, 
  CheckCircle2, 
  Briefcase, 
  BarChart2, 
  Settings, 
  ChevronDown,
  Sparkles,
  Cpu,
  ShieldAlert,
  Activity
} from 'lucide-react';
import { GoldGuardLogo, HermesIcon } from '../common/Icons';

interface SidebarProps {
  activeTab?: string;
  onSelectTab?: (tab: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab = 'Overview', onSelectTab }) => {
  const selected = activeTab;

  const navItems = [
    { name: 'Overview', icon: LayoutDashboard },
    { name: 'Agent', icon: Activity },
    { name: 'Studio', icon: Sparkles },
    { name: 'Hermes', icon: HermesIcon, isCustom: true },
    { name: 'Providers', icon: Cpu },
    { name: 'Cockpit', icon: ShieldAlert },
    { name: 'Market', icon: TrendingUp },
    { name: 'Context', icon: Layers },
    { name: 'Decisions', icon: CheckCircle2 },
    { name: 'Trades', icon: Briefcase },
  ];

  const handleSelect = (name: string) => {
    if (onSelectTab) onSelectTab(name);
  };

  return (
    <aside style={{
      width: '210px',
      minWidth: '210px',
      backgroundColor: '#090a0c',
      borderRight: '1px solid #181a1f',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      height: '100vh',
      position: 'sticky',
      top: 0,
      padding: '16px 12px 14px 12px',
      userSelect: 'none',
      zIndex: 20
    }}>
      {/* Top Logo & Navigation */}
      <div>
        {/* Brand Logo Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '4px 8px 24px 8px',
          cursor: 'pointer'
        }}>
          <GoldGuardLogo size={26} />
          <span style={{
            fontSize: '17px',
            fontWeight: 700,
            letterSpacing: '-0.01em',
            color: '#f0b90b',
            fontFamily: 'var(--font-sans)'
          }}>
            GoldGuard
          </span>
        </div>

        {/* Main Menu Links */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {navItems.map((item) => {
            const isActive = selected === item.name;
            const Icon = item.icon;
            return (
              <button
                key={item.name}
                onClick={() => handleSelect(item.name)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  border: isActive ? '1px solid rgba(240, 185, 11, 0.4)' : '1px solid transparent',
                  backgroundColor: isActive ? 'rgba(240, 185, 11, 0.08)' : 'transparent',
                  color: isActive ? '#f0b90b' : '#9498a4',
                  fontSize: '13.5px',
                  fontWeight: isActive ? 600 : 400,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s ease'
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.04)';
                    e.currentTarget.style.color = '#e2e4e8';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = 'transparent';
                    e.currentTarget.style.color = '#9498a4';
                  }
                }}
              >
                <Icon size={17} color={isActive ? '#f0b90b' : '#9498a4'} />
                <span>{item.name}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Settings & User Profile */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Settings button */}
        <button
          onClick={() => handleSelect('Settings')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            width: '100%',
            padding: '8px 12px',
            borderRadius: '6px',
            border: selected === 'Settings' ? '1px solid rgba(240, 185, 11, 0.4)' : '1px solid transparent',
            backgroundColor: selected === 'Settings' ? 'rgba(240, 185, 11, 0.08)' : 'transparent',
            color: selected === 'Settings' ? '#f0b90b' : '#9498a4',
            fontSize: '13.5px',
            cursor: 'pointer',
            textAlign: 'left',
            transition: 'all 0.15s ease'
          }}
          onMouseEnter={(e) => {
            if (selected !== 'Settings') {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.04)';
              e.currentTarget.style.color = '#e2e4e8';
            }
          }}
          onMouseLeave={(e) => {
            if (selected !== 'Settings') {
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = '#9498a4';
            }
          }}
        >
          <Settings size={17} />
          <span>Settings</span>
        </button>

        {/* User Profile Pill */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 6px',
          borderRadius: '8px',
          cursor: 'pointer',
          transition: 'background-color 0.15s ease'
        }}
        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.04)'}
        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* AD Avatar */}
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              backgroundColor: '#141518',
              border: '1.5px solid #d4a017',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#f0b90b',
              fontSize: '12px',
              fontWeight: 700
            }}>
              AD
            </div>

            {/* Name and plan */}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: '12.5px', fontWeight: 600, color: '#f8fafc', lineHeight: 1.2 }}>
                Alex Devon
              </span>
              <span style={{ fontSize: '11px', color: '#676b78' }}>
                Pro Plan
              </span>
            </div>
          </div>

          <ChevronDown size={14} color="#676b78" />
        </div>
      </div>
    </aside>
  );
};
