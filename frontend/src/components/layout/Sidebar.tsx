import type { ComponentType } from 'react';
import { 
  LayoutDashboard, 
  TrendingUp, 
  Newspaper, 
  CheckCircle2, 
  Briefcase, 
  Settings, 
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

export const Sidebar: React.FC<SidebarProps> = ({ activeTab = 'Home', onSelectTab }) => {
  const selected = activeTab === 'Overview' ? 'Home' : activeTab === 'Context' ? 'News' : activeTab === 'Hermes' ? 'Learning' : activeTab;

  const primary = [
    { name: 'Home', icon: LayoutDashboard },
    { name: 'Agent', icon: Activity },
    { name: 'News', icon: Newspaper },
    { name: 'Learning', icon: HermesIcon, isCustom: true },
    { name: 'Providers', icon: Cpu },
  ];

  const more = [
    { name: 'Studio', icon: Sparkles },
    { name: 'Market', icon: TrendingUp },
    { name: 'Decisions', icon: CheckCircle2 },
    { name: 'Trades', icon: Briefcase },
    { name: 'Cockpit', icon: ShieldAlert },
  ];

  const handleSelect = (name: string) => {
    if (onSelectTab) onSelectTab(name);
  };

  const renderItem = (item: { name: string; icon: ComponentType<{ size?: number; color?: string }> }) => {
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
  };

  return (
    <aside className="gg-sidebar" style={{
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
      <div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '4px 8px 24px 8px',
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

        <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {primary.map(renderItem)}
          <div style={{ height: '1px', backgroundColor: '#1c2028', margin: '10px 8px' }} />
          <span style={{ fontSize: '10px', color: '#525661', letterSpacing: '0.08em', padding: '0 12px 6px' }}>
            MORE
          </span>
          {more.map(renderItem)}
        </nav>
      </div>

      <div>
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
          }}
        >
          <Settings size={17} />
          <span>Settings</span>
        </button>
      </div>
    </aside>
  );
};
