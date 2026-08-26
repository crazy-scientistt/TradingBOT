import React, { useState } from 'react';
import { BotProvider, useBot } from './context/BotContext';
import { Sidebar } from './components/layout/Sidebar';
import { TopHeader } from './components/layout/TopHeader';
import { KpiCardsRow } from './components/metrics/KpiCardsRow';
import { CandlestickChart } from './components/chart/CandlestickChart';
import { OpenPositionCard } from './components/position/OpenPositionCard';
import { EquityCurveCard } from './components/bottom/EquityCurveCard';
import { LiveContextCard } from './components/bottom/LiveContextCard';
import { RiskHealthCard } from './components/bottom/RiskHealthCard';

import { StrategyStudio } from './components/strategy/StrategyStudio';
import { ResearchLab } from './components/research/ResearchLab';
import { RouteMatrix } from './components/providers/RouteMatrix';
import { EmergencyCockpit } from './components/risk/EmergencyCockpit';

import { MarketView } from './components/views/MarketView';
import { ContextView } from './components/views/ContextView';
import { DecisionsView } from './components/views/DecisionsView';
import { TradesView } from './components/views/TradesView';
import { SettingsModal } from './components/views/SettingsModal';
import { ToastContainer } from './components/common/ToastContainer';

const MainDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState('Overview');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const {
    kpi,
    candles,
    position,
    pipelineSteps,
    equityHistory,
    liveContext,
    riskHealth,
  } = useBot();

  const handleSelectTab = (tab: string) => {
    if (tab === 'Settings') {
      setIsSettingsOpen(true);
    } else {
      setActiveTab(tab);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        width: '100vw',
        minHeight: '100vh',
        backgroundColor: 'var(--bg-app)',
        color: 'var(--text-main)',
        overflowX: 'hidden',
      }}
    >
      {/* Left Sidebar */}
      <Sidebar activeTab={activeTab} onSelectTab={handleSelectTab} />

      {/* Main Content Area */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
          backgroundColor: 'var(--bg-app)',
          minHeight: '100vh',
        }}
      >
        {/* Top Header */}
        <TopHeader onOpenSettings={() => setIsSettingsOpen(true)} />

        {/* Dashboard Body / Active Tab View */}
        <main
          style={{
            flex: 1,
            padding: '10px 14px 14px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            overflowY: 'auto',
          }}
        >
          {activeTab === 'Overview' && (
            <>
              {/* Row 1: 5 KPI Cards */}
              <KpiCardsRow data={kpi} />

              {/* Row 2: Middle Section - Chart (Left) + Open Position & Pipeline (Right) */}
              <div
                style={{
                  display: 'flex',
                  gap: '10px',
                  alignItems: 'stretch',
                  width: '100%',
                }}
              >
                <CandlestickChart candles={candles} />
                <OpenPositionCard
                  position={position}
                  pipelineSteps={pipelineSteps}
                />
              </div>

              {/* Row 3: Bottom Section - Equity Curve (Left) + Live Context (Middle) + Risk & Health (Right) */}
              <div
                style={{
                  display: 'flex',
                  gap: '10px',
                  alignItems: 'stretch',
                  width: '100%',
                }}
              >
                <EquityCurveCard data={equityHistory} />
                <LiveContextCard items={liveContext} />
                <RiskHealthCard items={riskHealth} />
              </div>
            </>
          )}

          {activeTab === 'Studio' && <StrategyStudio />}
          {activeTab === 'Hermes' && <ResearchLab />}
          {activeTab === 'Providers' && <RouteMatrix />}
          {activeTab === 'Cockpit' && <EmergencyCockpit />}
          {activeTab === 'Market' && <MarketView />}
          {activeTab === 'Context' && <ContextView />}
          {activeTab === 'Decisions' && <DecisionsView />}
          {activeTab === 'Trades' && <TradesView />}
        </main>
      </div>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />

      {/* Toast Notification Container */}
      <ToastContainer />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BotProvider>
      <MainDashboard />
    </BotProvider>
  );
};

export default App;
