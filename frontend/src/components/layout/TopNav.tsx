import { useEffect, useState } from 'react';
import axios from 'axios';
import { Bell, Activity, Play, ShieldAlert, AlertTriangle, Crosshair, Clock } from 'lucide-react';

export function TopNav() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/overview')
      .then(res => setData(res.data))
      .catch(err => console.error(err));
  }, []);

  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const drawdownMode = data?.drawdown_mode ?? '—';
  const isReducedRisk = drawdownMode !== '—' && drawdownMode !== 'N/A' && drawdownMode.toLowerCase() !== 'normal';

  return (
    <div className="h-14 border-b border-border flex items-center justify-between px-6 bg-background relative z-20">
      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2 text-sm text-foreground">
          <Activity className="w-4 h-4 text-primary" />
          <span className="font-medium">Command Center</span>
        </div>

        {/* Global Date/Time */}
        <div className="h-4 w-px bg-border"></div>
        <div className="flex items-center space-x-2 text-xs font-mono text-muted-foreground" title="Current system time">
          <Clock className="w-3.5 h-3.5" />
          <span>Local System Time: {currentTime.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })} • {currentTime.toLocaleTimeString('en-IN', { hour12: false, timeZoneName: 'short' })}</span>
        </div>
        
        {/* Global Risk visibility */}
        <div className="h-6 w-px bg-border"></div>
        <div className={`flex items-center space-x-2 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full border ${isReducedRisk ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' : 'bg-primary/10 text-primary border-primary/20'}`}>
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Risk Mode: {drawdownMode}</span>
        </div>
        <div className="flex items-center space-x-2 text-xs font-bold text-muted-foreground uppercase tracking-widest hidden md:flex">
            <Crosshair className="w-3.5 h-3.5" />
            <span>Exposure: {data?.active_positions ?? '—'} Open</span>
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
        <div className="hidden lg:flex items-center space-x-4 mr-4 text-xs font-mono text-muted-foreground border-r border-border pr-4">
            <div className="flex flex-col items-end">
                <span className="uppercase text-[9px] font-sans font-bold tracking-widest opacity-70">Daily Risk Meter</span>
                <span className="text-muted-foreground">N/A</span>
            </div>
            <div className="flex flex-col items-end">
                <span className="uppercase text-[9px] font-sans font-bold tracking-widest opacity-70">Capital @ Risk</span>
                <span className="text-foreground">N/A</span>
            </div>
        </div>

        <button
          onClick={() => {
            axios.post('http://localhost:8000/api/v1/automation/trigger/manual_rescan')
              .then(() => alert('Pipeline triggered successfully! Check Automation page for status.'))
              .catch(err => alert('Failed to trigger pipeline: ' + err.message));
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
