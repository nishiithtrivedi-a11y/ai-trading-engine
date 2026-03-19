import { useEffect, useState } from 'react';
import axios from 'axios';
import { Bell, Activity, Play, ShieldAlert, AlertTriangle, Crosshair, Clock, Radio, Database, Wifi, WifiOff } from 'lucide-react';

const API = 'http://localhost:8000/api/v1';

interface PlatformStatus {
  runtime_data_source: string;
  connected_sessions: number;
  total_sessions: number;
  market_session: {
    phase: string;
    label: string;
    current_time_ist: string;
    is_tradeable: boolean;
    next_transition: string;
  };
  feature_availability: string;
  feature_availability_label: string;
  execution_enabled: boolean;
}

const MARKET_PHASE_STYLES: Record<string, { color: string; bg: string; dot: string }> = {
  open: { color: 'text-green-500', bg: 'bg-green-500/10 border-green-500/20', dot: 'bg-green-500' },
  pre_open: { color: 'text-blue-400', bg: 'bg-blue-400/10 border-blue-400/20', dot: 'bg-blue-400' },
  post_close: { color: 'text-amber-500', bg: 'bg-amber-500/10 border-amber-500/20', dot: 'bg-amber-500' },
  closed: { color: 'text-muted-foreground', bg: 'bg-muted border-border', dot: 'bg-muted-foreground' },
  weekend: { color: 'text-muted-foreground', bg: 'bg-muted border-border', dot: 'bg-muted-foreground' },
  unknown: { color: 'text-muted-foreground', bg: 'bg-muted border-border', dot: 'bg-muted-foreground' },
};

export function TopNav() {
  const [data, setData] = useState<any>(null);
  const [platform, setPlatform] = useState<PlatformStatus | null>(null);

  useEffect(() => {
    axios.get(`${API}/overview`)
      .then(res => setData(res.data))
      .catch(err => console.error(err));

    axios.get(`${API}/platform/status`)
      .then(res => setPlatform(res.data))
      .catch(err => console.error(err));
  }, []);

  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Refresh platform status every 60s
  useEffect(() => {
    const timer = setInterval(() => {
      axios.get(`${API}/platform/status`)
        .then(res => setPlatform(res.data))
        .catch(() => {});
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  const drawdownMode = data?.drawdown_mode ?? '—';
  const isReducedRisk = drawdownMode !== '—' && drawdownMode !== 'N/A' && drawdownMode.toLowerCase() !== 'normal';

  const marketPhase = platform?.market_session?.phase ?? 'unknown';
  const marketStyles = MARKET_PHASE_STYLES[marketPhase] || MARKET_PHASE_STYLES.unknown;
  const runtimeSource = platform?.runtime_data_source ?? '—';
  const connectedSessions = platform?.connected_sessions ?? 0;

  return (
    <div className="h-14 border-b border-border flex items-center justify-between px-6 bg-background relative z-20">
      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2 text-sm text-foreground">
          <Activity className="w-4 h-4 text-primary" />
          <span className="font-medium">Command Center</span>
        </div>

        {/* Market Session Indicator */}
        <div className="h-4 w-px bg-border"></div>
        <div className={`flex items-center space-x-2 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full border ${marketStyles.bg} ${marketStyles.color}`}
          title={platform?.market_session?.next_transition ?? ''}>
          <span className={`w-2 h-2 rounded-full ${marketStyles.dot} ${marketPhase === 'open' ? 'animate-pulse' : ''}`}></span>
          <span>{platform?.market_session?.label ?? 'Loading…'}</span>
        </div>

        {/* Runtime Data Source */}
        <div className={`flex items-center space-x-1.5 text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${
          runtimeSource === 'csv' || runtimeSource === 'indian_csv'
            ? 'bg-muted border-border text-muted-foreground'
            : 'bg-primary/10 border-primary/20 text-primary'
        }`}
          title={`Active data source: ${runtimeSource} | Connected providers: ${connectedSessions}/${platform?.total_sessions ?? 0}`}>
          <Database className="w-3 h-3" />
          <span>{runtimeSource.toUpperCase()}</span>
        </div>

        {/* Provider Sessions */}
        {connectedSessions > 0 && (
          <div className="flex items-center space-x-1.5 text-xs text-green-500" title={`${connectedSessions} provider session(s) active`}>
            <Wifi className="w-3.5 h-3.5" />
            <span className="font-bold">{connectedSessions}/{platform?.total_sessions ?? 0}</span>
          </div>
        )}

        {/* Global Date/Time */}
        <div className="h-4 w-px bg-border hidden lg:block"></div>
        <div className="hidden lg:flex items-center space-x-2 text-xs font-mono text-muted-foreground" title="Current system time">
          <Clock className="w-3.5 h-3.5" />
          <span>{currentTime.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })} • {currentTime.toLocaleTimeString('en-IN', { hour12: false, timeZoneName: 'short' })}</span>
        </div>
        
        {/* Global Risk visibility */}
        <div className="h-6 w-px bg-border hidden md:block"></div>
        <div className={`hidden md:flex items-center space-x-2 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full border ${isReducedRisk ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' : 'bg-primary/10 text-primary border-primary/20'}`}>
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Risk Mode: {drawdownMode}</span>
        </div>
        {isReducedRisk && (
            <div className="flex items-center space-x-1.5 text-xs font-bold text-orange-400 uppercase tracking-widest animate-pulse">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Capital Preservation Active</span>
            </div>
        )}
      </div>

      <div className="flex items-center space-x-4">
        {/* Risk Metrics Quick View */}
        <div className="hidden xl:flex items-center space-x-4 mr-4 text-xs font-mono text-muted-foreground border-r border-border pr-4">
            <div className="flex flex-col items-end">
                <span className="uppercase text-[9px] font-sans font-bold tracking-widest opacity-70">Exposure</span>
                <span className="text-foreground">{data?.active_positions ?? '—'} Open</span>
            </div>
        </div>

        <button
          onClick={() => {
            axios.post(`${API}/automation/trigger/manual_rescan`)
              .then(() => alert('Pipeline triggered successfully! Check Automation page for status.'))
              .catch(err => {
                const detail = err?.response?.data?.detail || err.message;
                alert(`Pipeline trigger: ${detail}`);
              });
          }}
          title="Trigger a manual rescan pipeline (Safe / Non-live)"
          className="flex items-center space-x-2 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary text-sm rounded-md border border-primary/20 transition-colors"
        >
          <Play className="w-4 h-4" />
          <span className="font-semibold">Run Pipeline</span>
        </button>
        <button className="text-muted-foreground hover:text-foreground relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full border border-background"></span>
        </button>
      </div>
    </div>
  );
}
