import React, { useEffect, useState } from 'react';
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
import { AgentActivity } from './components/agent/AgentActivity';

import { MarketView } from './components/views/MarketView';
import { ContextView } from './components/views/ContextView';
import { DecisionsView } from './components/views/DecisionsView';
import { TradesView } from './components/views/TradesView';
import { SettingsModal } from './components/views/SettingsModal';
import { ToastContainer } from './components/common/ToastContainer';
import { ErrorBoundary } from './components/common/ErrorBoundary';

const DataNotice: React.FC<{ title: string; detail?: string }> = ({ title, detail }) => (
  <div
    role="status"
    style={{
      flex: 1,
      minHeight: '140px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '8px',
      border: '1px solid #22242a',
      borderRadius: '8px',
      backgroundColor: '#0d0e12',
      color: '#cbd5e1',
      textAlign: 'center',
      padding: '20px',
    }}
  >
    <strong>{title}</strong>
    {detail && <span style={{ color: '#9498a4', fontSize: '12px' }}>{detail}</span>}
  </div>
);

const ConnectionBanner: React.FC = () => {
  const { loading, error, degraded, dataStatus } = useBot();
  if (!loading && !error && !degraded) return null;
  const message = error
    ? `Disconnected from live data: ${error}`
    : loading
      ? 'Connecting to the paper-trading service…'
      : 'Live data is degraded. Values below are limited to observations returned by the service.';
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        margin: '8px 14px 0',
        padding: '8px 12px',
        borderRadius: '6px',
        border: `1px solid ${error ? 'rgba(239, 68, 68, 0.45)' : 'rgba(240, 185, 11, 0.35)'}`,
        backgroundColor: error ? 'rgba(239, 68, 68, 0.08)' : 'rgba(240, 185, 11, 0.08)',
        color: error ? '#fca5a5' : '#f0b90b',
        fontSize: '12px',
      }}
    >
      {message}
      {dataStatus.lastUpdatedAt && !loading && (
        <span style={{ color: '#9498a4', marginLeft: '8px' }}>
          Last snapshot: {new Date(dataStatus.lastUpdatedAt).toLocaleTimeString()}
        </span>
      )}
    </div>
  );
};

const QualificationStrip: React.FC = () => {
  const { runtimeStatus } = useBot();
  if (!runtimeStatus) return null;
  const owner = runtimeStatus.executionOwner || 'legacy';
  const dataset = runtimeStatus.datasetStatus || 'UNKNOWN';
  const hermes = runtimeStatus.hermesStatus || 'unknown';
  const lessons = runtimeStatus.reflectionCount ?? 0;
  return (
    <div
      style={{
        margin: '8px 14px 0',
        padding: '8px 12px',
        borderRadius: '6px',
        border: '1px solid #1c2330',
        backgroundColor: '#0b1018',
        color: '#94a3b8',
        fontSize: '11px',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '14px',
        letterSpacing: '0.04em',
      }}
    >
      <span>OWNER {owner.toUpperCase()}</span>
      <span>DATASET {dataset}</span>
      <span>HERMES {hermes.toUpperCase()}</span>
      <span>LESSONS {lessons}</span>
      <span>LIVE {runtimeStatus.halted ? 'LOCKED' : 'OFF'}</span>
    </div>
  );
};

const MainDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState('Home');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const {
    kpi,
    candles,
    position,
    pipelineSteps,
    equityHistory,
    liveContext,
    riskHealth,
    quote,
    genomes,
    botState,
  } = useBot();
  const [spreadHistory, setSpreadHistory] = useState<number[]>([]);
  useEffect(() => {
    if (quote && Number.isFinite(quote.spread)) {
      setSpreadHistory((previous) => [...previous.slice(-39), quote.spread]);
    }
  }, [quote]);

  const handleSelectTab = (tab: string) => {
    if (tab === 'Settings') {
      setIsSettingsOpen(true);
    } else {
      setActiveTab(tab);
    }
  };

  return (
    <div className="gg-shell" style={{ backgroundColor: 'var(--bg-app)', color: 'var(--text-main)', overflowX: 'hidden' }}>
      {/* Left Sidebar */}
      <Sidebar activeTab={activeTab} onSelectTab={handleSelectTab} />

      {/* Main Content Area */}
      <div className="gg-main" style={{ backgroundColor: 'var(--bg-app)', minHeight: '100vh' }}>
        {/* Top Header */}
        <TopHeader onOpenSettings={() => setIsSettingsOpen(true)} />
        <ConnectionBanner />
        <QualificationStrip />

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
          {(activeTab === 'Home' || activeTab === 'Overview') && (
            <>
              {/* Row 1: 5 KPI Cards */}
              {kpi ? (
                <KpiCardsRow data={kpi} spreadHistory={spreadHistory} />
              ) : (
                <DataNotice title="Waiting for a real paper-account snapshot" detail="No equity, PnL, drawdown, or spread value has been observed yet." />
              )}

              {/* Row 2: Middle Section - Chart (Left) + Open Position & Pipeline (Right) */}
              <div className="gg-row">
                <CandlestickChart candles={candles} quote={quote} position={position} />
                {position ? (
                  <OpenPositionCard position={position} pipelineSteps={pipelineSteps} />
                ) : (
                  <DataNotice title="No open paper position" detail="The paper account is flat or has not produced a position snapshot." />
                )}
              </div>

              {/* Row 3: Bottom Section - Equity Curve (Left) + Live Context (Middle) + Risk & Health (Right) */}
              <div className="gg-row">
                <EquityCurveCard data={equityHistory} />
                <LiveContextCard items={liveContext} />
                <RiskHealthCard items={riskHealth} />
              </div>
            </>
          )}

          {activeTab === 'Agent' && <AgentActivity />}
          {activeTab === 'Studio' && (genomes.length > 0 ? <StrategyStudio /> : <DataNotice title="No strategy genomes observed" detail="The Strategy Studio remains read-only until the registry returns a real genome." />)}
          {(activeTab === 'Learning' || activeTab === 'Hermes') && <ResearchLab />}
          {activeTab === 'Providers' && <RouteMatrix />}
          {activeTab === 'Cockpit' && (botState ? <EmergencyCockpit /> : <DataNotice title="Runtime status unavailable" detail="Emergency controls are unavailable until the server reports runtime state." />)}
          {activeTab === 'Market' && (quote && candles.length > 0 ? <MarketView /> : <DataNotice title="Market data unavailable" detail="This view does not fabricate quotes or candles while the feed is disconnected." />)}
          {(activeTab === 'News' || activeTab === 'Context') && <ContextView />}
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
    <ErrorBoundary>
      <BotProvider>
        <MainDashboard />
      </BotProvider>
    </ErrorBoundary>
  );
};

export default App;
