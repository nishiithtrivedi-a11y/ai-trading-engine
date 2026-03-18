import { useEffect, useState } from 'react';
import axios from 'axios';
import { Bell, Activity, Play, ShieldAlert, AlertTriangle, Crosshair } from 'lucide-react';

export function TopNav() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/overview')
      .then(res => setData(res.data))
      .catch(err => console.error(err));
  }, []);

  const drawdownMode = data?.drawdown_mode || 'Normal';
  const isReducedRisk = drawdownMode.toLowerCase() !== 'normal';

  return (
    <div className="h-14 border-b border-border flex items-center justify-between px-6 bg-background relative z-20">
      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2 text-sm text-muted-foreground">
          <Activity className="w-4 h-4 text-green-500" />
          <span className="font-medium">System Normal</span>
        </div>
        
        {/* Global Risk visibility */}
        <div className="h-6 w-px bg-border"></div>
        <div className={`flex items-center space-x-2 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full border ${isReducedRisk ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' : 'bg-primary/10 text-primary border-primary/20'}`}>
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Risk Mode: {drawdownMode}</span>
        </div>
        <div className="flex items-center space-x-2 text-xs font-bold text-muted-foreground uppercase tracking-widest hidden md:flex">
            <Crosshair className="w-3.5 h-3.5" />
            <span>Exposure: {data?.active_positions || 0} Open</span>
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
                <span className={`${isReducedRisk ? 'text-orange-400' : 'text-green-500'}`}>12% / 25% UTIL</span>
            </div>
            <div className="flex flex-col items-end">
                <span className="uppercase text-[9px] font-sans font-bold tracking-widest opacity-70">Capital @ Risk</span>
                <span className="text-foreground">$ 2,450.00</span>
            </div>
        </div>

        <button className="flex items-center space-x-2 px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground text-sm rounded-md border border-border transition-colors">
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
