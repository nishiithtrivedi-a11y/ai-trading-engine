import { useEffect, useState } from 'react';
import axios from 'axios';
import { Database, Wifi } from 'lucide-react';

const API = 'http://localhost:8000/api/v1';

export function StatusStrip() {
  const [source, setSource] = useState('—');
  const [connected, setConnected] = useState(0);
  const [total, setTotal] = useState(0);
  const [feature, setFeature] = useState('');
  const [featureLabel, setFeatureLabel] = useState('');

  useEffect(() => {
    axios.get(`${API}/platform/status`)
      .then(res => {
        const d = res.data;
        setSource(d.runtime_data_source ?? '—');
        setConnected(d.connected_sessions ?? 0);
        setTotal(d.total_sessions ?? 0);
        setFeature(d.feature_availability ?? '');
        setFeatureLabel(d.feature_availability_label ?? '');
      })
      .catch(() => {});
  }, []);

  const featureColor =
    feature === 'realtime_analysis' ? 'text-green-500' :
    feature === 'post_market' ? 'text-amber-500' :
    feature === 'fallback_active' ? 'text-blue-400' :
    'text-muted-foreground';

  return (
    <div className="h-8 border-t border-border bg-card flex items-center justify-between px-4 text-xs font-mono text-muted-foreground z-20 relative shadow-[0_-2px_10px_rgba(0,0,0,0.1)]">
      <div className="flex items-center space-x-4">
        <span className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-yellow-500 shadow-[0_0_5px_rgba(234,179,8,0.5)]"></span>
          <span className="font-bold text-yellow-500/90 tracking-widest uppercase text-[10px]">Paper Active</span>
        </span>
        <span className="opacity-30">|</span>
        <span className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.5)]"></span>
          <span className="font-bold text-red-500/90 tracking-widest uppercase text-[10px]">Execute Locked</span>
        </span>
        <span className="opacity-30 hidden md:inline">|</span>
        {/* Runtime Data Source */}
        <span className="hidden md:flex items-center space-x-1.5 text-[10px] uppercase font-sans font-bold tracking-widest">
          <Database className="w-3 h-3" />
          <span>Source: {source.toUpperCase()}</span>
        </span>
        <span className="opacity-30 hidden md:inline">|</span>
        {/* Connected Providers */}
        <span className="hidden md:flex items-center space-x-1.5 text-[10px] uppercase font-sans font-bold tracking-widest">
          <Wifi className="w-3 h-3" />
          <span>Providers: {connected}/{total}</span>
        </span>
        <span className="opacity-30 hidden lg:inline">|</span>
        {/* Feature Availability */}
        <span className={`hidden lg:flex items-center space-x-1.5 text-[10px] uppercase font-sans font-bold tracking-widest ${featureColor}`}>
          <span>{featureLabel || 'Loading…'}</span>
        </span>
      </div>
      <div className="flex items-center space-x-4">
        <span className="hidden lg:inline text-[10px] uppercase tracking-widest opacity-50">Local Engine • Port: 8000</span>
        <span className="font-bold tracking-wider text-primary/50">Vite SPA • Phase 22.x</span>
      </div>
    </div>
  );
}
