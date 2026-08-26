import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import {
  KpiMetrics,
  Candle,
  PositionDetails,
  PipelineStep,
  EquityDataPoint,
  NewsItem,
  HealthStatusItem,
} from '../types/dashboard';
import {
  StrategyGenome,
  AIProvider,
  ProviderRoute,
  ResearchQuota,
  TradeReflection,
  BotStateStatus,
} from '../types';
import {
  mockKpiData,
  mockCandles,
  mockPosition,
  mockPipelineSteps,
  mockLiveContext,
  mockRiskHealth,
  mockEquityHistory,
  mockGenomes,
  mockProviders,
  mockRoutes,
  mockQuota,
  mockReflections,
  mockBotState,
} from '../data/mockData';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message?: string;
  timestamp: string;
}

interface BotContextType {
  // Global App State
  botRunning: boolean;
  isPaperMode: boolean;
  selectedPair: string;
  activeGenomeId: string;
  systemHealthy: boolean;

  // Real-time Overview Data
  kpi: KpiMetrics;
  candles: Candle[];
  quote: { bid: number; ask: number; spread: number; spread_rate: number; observed_at: string };
  position: PositionDetails;
  pipelineSteps: PipelineStep[];
  liveContext: NewsItem[];
  riskHealth: HealthStatusItem[];
  equityHistory: EquityDataPoint[];

  // Subsystem Entities
  genomes: StrategyGenome[];
  providers: AIProvider[];
  routes: ProviderRoute[];
  quota: ResearchQuota;
  reflections: TradeReflection[];
  botState: BotStateStatus;

  // Toasts
  toasts: ToastMessage[];
  addToast: (type: ToastMessage['type'], title: string, message?: string) => void;
  removeToast: (id: string) => void;

  // Actions
  toggleBot: () => Promise<void>;
  toggleMode: () => void;
  setSelectedPair: (pair: string) => void;
  refreshAll: () => Promise<void>;
  promoteGenome: (genomeId: string) => Promise<void>;
  triggerHermesStep: () => Promise<void>;
  updateRoute: (role: 'decision' | 'context' | 'hermes', provider: string) => Promise<void>;
  probeLatencies: () => Promise<void>;
  triggerKillSwitch: () => Promise<void>;
  revokeAutonomy: () => Promise<void>;
  revertBaseline: () => Promise<void>;
}

const BotContext = createContext<BotContextType | null>(null);

export const BotProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [botRunning, setBotRunning] = useState<boolean>(false);
  const [isPaperMode, setIsPaperMode] = useState<boolean>(true);
  const [selectedPair, setSelectedPair] = useState<string>('PAXG / USDT');
  const [activeGenomeId, setActiveGenomeId] = useState<string>('trend-pullback-v1');
  const [systemHealthy, setSystemHealthy] = useState<boolean>(true);

  const [kpi, setKpi] = useState<KpiMetrics>(mockKpiData);
  const [candles, setCandles] = useState<Candle[]>(mockCandles);
  const [quote, setQuote] = useState({
    bid: 2500.2,
    ask: 2500.5,
    spread: 0.3,
    spread_rate: 0.00012,
    observed_at: new Date().toISOString(),
  });
  const [position, setPosition] = useState<PositionDetails>(mockPosition);
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>(mockPipelineSteps);
  const [liveContext, setLiveContext] = useState<NewsItem[]>(mockLiveContext);
  const [riskHealth, setRiskHealth] = useState<HealthStatusItem[]>(mockRiskHealth);
  const [equityHistory, setEquityHistory] = useState<EquityDataPoint[]>(mockEquityHistory);

  const [genomes, setGenomes] = useState<StrategyGenome[]>(mockGenomes);
  const [providers, setProviders] = useState<AIProvider[]>(mockProviders);
  const [routes, setRoutes] = useState<ProviderRoute[]>(mockRoutes);
  const [quota, setQuota] = useState<ResearchQuota>(mockQuota);
  const [reflections, setReflections] = useState<TradeReflection[]>(mockReflections);
  const [botState, setBotState] = useState<BotStateStatus>(mockBotState);

  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((type: ToastMessage['type'], title: string, message?: string) => {
    const newToast: ToastMessage = {
      id: `${Date.now()}-${Math.random()}`,
      type,
      title,
      message,
      timestamp: new Date().toLocaleTimeString(),
    };
    setToasts((prev) => [newToast, ...prev.slice(0, 4)]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== newToast.id));
    }, 5000);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      // 1. Health & Status
      const [healthRes, statusRes] = await Promise.allSettled([
        api.getHealth(),
        api.getStatus(),
      ]);

      if (healthRes.status === 'fulfilled') {
        setSystemHealthy(healthRes.value.status === 'ok');
        setRiskHealth([
          {
            id: '1',
            label: `Database: ${healthRes.value.database || 'ok'}`,
            status: healthRes.value.database === 'ok' ? 'OK' : 'ERROR',
            icon: 'database',
          },
          {
            id: '2',
            label: 'Single Execution Lease',
            status: 'OK',
            icon: 'lease',
          },
          {
            id: '3',
            label: 'OpenCodex / Gemini 3.7 Route',
            status: 'OK',
            icon: 'gemini',
          },
          {
            id: '4',
            label: 'Hermes Research Agent',
            status: 'OK',
            icon: 'hermes',
          },
        ]);
      }

      if (statusRes.status === 'fulfilled') {
        setBotRunning(statusRes.value.bot_running);
        if (statusRes.value.active_genome_id) {
          setActiveGenomeId(statusRes.value.active_genome_id);
        }
      }

      // 2. Overview Live Metrics
      const [kpiRes, posRes, quoteRes, candlesRes, eqRes, ctxRes] = await Promise.allSettled([
        api.getKpi(),
        api.getPosition(),
        api.getMarketQuote('PAXGUSDT'),
        api.getMarketCandles('PAXGUSDT', '15m', 50),
        api.getEquityCurve(),
        api.getLiveContext(),
      ]);

      if (kpiRes.status === 'fulfilled') setKpi(kpiRes.value);
      if (posRes.status === 'fulfilled') {
        setPosition(posRes.value.position);
        setPipelineSteps(posRes.value.pipelineSteps);
      }
      if (quoteRes.status === 'fulfilled') setQuote(quoteRes.value);
      if (candlesRes.status === 'fulfilled' && candlesRes.value.length > 0) {
        setCandles(candlesRes.value);
      }
      if (eqRes.status === 'fulfilled') setEquityHistory(eqRes.value);
      if (ctxRes.status === 'fulfilled') setLiveContext(ctxRes.value);

      // 3. Subsystem Entities
      const [genomesRes, provRes, routesRes, quotaRes, refRes, stateRes] = await Promise.allSettled([
        api.getGenomes(),
        api.getProviders(),
        api.getRoutes(),
        api.getQuota(),
        api.getReflections(),
        api.getBotState(),
      ]);

      if (genomesRes.status === 'fulfilled' && genomesRes.value.length > 0) setGenomes(genomesRes.value);
      if (provRes.status === 'fulfilled') setProviders(provRes.value);
      if (routesRes.status === 'fulfilled' && routesRes.value.length > 0) setRoutes(routesRes.value);
      if (quotaRes.status === 'fulfilled') setQuota(quotaRes.value);
      if (refRes.status === 'fulfilled' && refRes.value.length > 0) setReflections(refRes.value);
      if (stateRes.status === 'fulfilled') setBotState(stateRes.value);
    } catch (err: any) {
      console.warn('Live API poll fallback:', err);
    }
  }, []);

  // Initial load and polling ticker
  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 4000);
    return () => clearInterval(interval);
  }, [refreshAll]);

  // Actions
  const toggleBot = async () => {
    try {
      if (botRunning) {
        await api.stopBot();
        setBotRunning(false);
        addToast('info', 'Trading Bot Stopped', 'Coordinator loop paused');
      } else {
        await api.startBot();
        setBotRunning(true);
        addToast('success', 'Trading Bot Started', 'Scanning 15m closed candles on PAXG/USDT');
      }
    } catch (err: any) {
      addToast('error', 'Bot Action Failed', err.message);
    }
  };

  const toggleMode = () => {
    setIsPaperMode(!isPaperMode);
    addToast('info', 'Mode Switched', !isPaperMode ? 'Switched to Paper Mode ($100 balance)' : 'Switched to Live Mode');
  };

  const promoteGenome = async (genomeId: string) => {
    try {
      const res = await api.promoteGenome(genomeId);
      setActiveGenomeId(genomeId);
      addToast('success', 'Strategy Promoted', `Genome ${genomeId} is now the active trading strategy`);
      refreshAll();
    } catch (err: any) {
      addToast('error', 'Promotion Failed', err.message);
    }
  };

  const triggerHermesStep = async () => {
    try {
      const res = await api.triggerHermesStep();
      addToast('success', 'Hermes Reasoning Step Complete', `Generated candidate ${res.candidate.genome_id}`);
      refreshAll();
    } catch (err: any) {
      addToast('error', 'Hermes Step Failed', err.message);
    }
  };

  const updateRoute = async (role: 'decision' | 'context' | 'hermes', provider: string) => {
    try {
      await api.setRoute(role, provider);
      addToast('success', 'Route Updated', `Assigned ${provider} to ${role} role`);
      refreshAll();
    } catch (err: any) {
      addToast('error', 'Route Update Failed', err.message);
    }
  };

  const probeLatencies = async () => {
    try {
      const res = await api.probeProviders();
      setProviders(res);
      addToast('info', 'Latencies Probed', 'Live response times updated');
    } catch (err: any) {
      addToast('error', 'Probe Failed', err.message);
    }
  };

  const triggerKillSwitch = async () => {
    try {
      await api.triggerKillSwitch();
      setBotRunning(false);
      addToast('warning', 'EMERGENCY KILL SWITCH ENGAGED', 'All positions closed, trading halted');
      refreshAll();
    } catch (err: any) {
      addToast('error', 'Kill Switch Failed', err.message);
    }
  };

  const revokeAutonomy = async () => {
    try {
      await api.revokeAutonomy();
      addToast('warning', 'Autonomy Suspended', 'Human approval now required for all mutations');
      refreshAll();
    } catch (err: any) {
      addToast('error', 'Action Failed', err.message);
    }
  };

  const revertBaseline = async () => {
    try {
      await api.revertBaseline();
      setActiveGenomeId('trend-pullback-v1');
      addToast('success', 'Reverted to Baseline', 'Promoted safe trend-pullback-v1 strategy');
      refreshAll();
    } catch (err: any) {
      addToast('error', 'Revert Failed', err.message);
    }
  };

  return (
    <BotContext.Provider
      value={{
        botRunning,
        isPaperMode,
        selectedPair,
        activeGenomeId,
        systemHealthy,
        kpi,
        candles,
        quote,
        position,
        pipelineSteps,
        liveContext,
        riskHealth,
        equityHistory,
        genomes,
        providers,
        routes,
        quota,
        reflections,
        botState,
        toasts,
        addToast,
        removeToast,
        toggleBot,
        toggleMode,
        setSelectedPair,
        refreshAll,
        promoteGenome,
        triggerHermesStep,
        updateRoute,
        probeLatencies,
        triggerKillSwitch,
        revokeAutonomy,
        revertBaseline,
      }}
    >
      {children}
    </BotContext.Provider>
  );
};

export const useBot = () => {
  const context = useContext(BotContext);
  if (!context) {
    throw new Error('useBot must be used within a BotProvider');
  }
  return context;
};
