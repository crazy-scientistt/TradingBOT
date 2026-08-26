import React, { useState } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { TopHeader } from './components/layout/TopHeader';
import { KpiCardsRow } from './components/metrics/KpiCardsRow';
import { CandlestickChart } from './components/chart/CandlestickChart';
import { OpenPositionCard } from './components/position/OpenPositionCard';
import { EquityCurveCard } from './components/bottom/EquityCurveCard';
import { LiveContextCard } from './components/bottom/LiveContextCard';
import { RiskHealthCard } from './components/bottom/RiskHealthCard';

import {
  mockKpiData,
  mockCandles,
  mockPosition,
  mockPipelineSteps,
  mockEquityHistory,
  mockLiveContext,
  mockRiskHealth
} from './data/mockData';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('Overview');
  const [selectedPair, setSelectedPair] = useState('PAXG / USDT');
  const [isPaperMode, setIsPaperMode] = useState(true);

  return (
    <div style={{
      display: 'flex',
      width: '100vw',
      minHeight: '100vh',
      backgroundColor: 'var(--bg-app)',
      color: 'var(--text-main)',
      overflowX: 'hidden'
    }}>
      {/* Left Sidebar */}
      <Sidebar activeTab={activeTab} onSelectTab={setActiveTab} />

      {/* Main Content Area */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        backgroundColor: '#0c0e12',
        minHeight: '100vh'
      }}>
        {/* Top Header */}
        <TopHeader
          currentPair={selectedPair}
          onSelectPair={setSelectedPair}
          isPaperMode={isPaperMode}
          onToggleMode={() => setIsPaperMode(!isPaperMode)}
        />

        {/* Dashboard Body Grid */}
        <main style={{
          flex: 1,
          padding: '10px 14px 14px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          overflowY: 'auto'
        }}>
          {/* Row 1: 5 KPI Cards */}
          <KpiCardsRow data={mockKpiData} />

          {/* Row 2: Middle Section - Chart (Left) + Open Position & Pipeline (Right) */}
          <div style={{
            display: 'flex',
            gap: '10px',
            alignItems: 'stretch',
            width: '100%'
          }}>
            <CandlestickChart candles={mockCandles} />
            <OpenPositionCard
              position={mockPosition}
              pipelineSteps={mockPipelineSteps}
            />
          </div>

          {/* Row 3: Bottom Section - Equity Curve (Left) + Live Context (Middle) + Risk & Health (Right) */}
          <div style={{
            display: 'flex',
            gap: '10px',
            alignItems: 'stretch',
            width: '100%'
          }}>
            <EquityCurveCard data={mockEquityHistory} />
            <LiveContextCard items={mockLiveContext} />
            <RiskHealthCard items={mockRiskHealth} />
          </div>
        </main>
      </div>
    </div>
  );
};

export default App;
