import React, { useState } from 'react';
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

import {
  mockKpiData,
  mockCandles,
  mockPosition,
  mockPipelineSteps,
  mockEquityHistory,
  mockLiveContext,
  mockRiskHealth,
  mockGenomes,
  mockProviders,
  mockRoutes,
  mockQuota,
  mockReflections,
  mockBotState,
} from './data/mockData';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('Overview');
  const [selectedPair, setSelectedPair] = useState('PAXG / USDT');
  const [isPaperMode, setIsPaperMode] = useState(true);

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
      <Sidebar activeTab={activeTab} onSelectTab={setActiveTab} />

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
        <TopHeader
          currentPair={selectedPair}
          onSelectPair={setSelectedPair}
          isPaperMode={isPaperMode}
          onToggleMode={() => setIsPaperMode(!isPaperMode)}
        />

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
              <KpiCardsRow data={mockKpiData} />

              {/* Row 2: Middle Section - Chart (Left) + Open Position & Pipeline (Right) */}
              <div
                style={{
                  display: 'flex',
                  gap: '10px',
                  alignItems: 'stretch',
                  width: '100%',
                }}
              >
                <CandlestickChart candles={mockCandles} />
                <OpenPositionCard
                  position={mockPosition}
                  pipelineSteps={mockPipelineSteps}
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
                <EquityCurveCard data={mockEquityHistory} />
                <LiveContextCard items={mockLiveContext} />
                <RiskHealthCard items={mockRiskHealth} />
              </div>
            </>
          )}

          {activeTab === 'Studio' && (
            <StrategyStudio
              initialGenomes={mockGenomes}
              activeGenomeId="trend-pullback-v1"
            />
          )}

          {activeTab === 'Hermes' && (
            <ResearchLab
              quota={mockQuota}
              reflections={mockReflections}
            />
          )}

          {activeTab === 'Providers' && (
            <RouteMatrix
              providers={mockProviders}
              initialRoutes={mockRoutes}
            />
          )}

          {activeTab === 'Cockpit' && (
            <EmergencyCockpit status={mockBotState} />
          )}

          {/* Fallback for other sidebar items */}
          {['Market', 'Context', 'Decisions', 'Trades'].includes(activeTab) && (
            <div
              style={{
                backgroundColor: '#0d0e12',
                border: '1px solid #1e222b',
                borderRadius: '8px',
                padding: '24px',
                textAlign: 'center',
                color: '#9498a4',
              }}
            >
              <h3 style={{ color: '#f8fafc', margin: '0 0 8px 0' }}>{activeTab} Feed</h3>
              <p style={{ fontSize: '13px', margin: 0 }}>
                Live streaming feed integrated with Binance Spot PAXG/USDT market stream and decision ledger.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
