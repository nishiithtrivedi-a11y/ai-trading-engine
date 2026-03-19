import { useEffect, useMemo, useState } from 'react';
import { Activity, Database, BarChart2, Layers } from 'lucide-react';
import axios from 'axios';

const API = 'http://localhost:8000/api/v1';

interface PlatformStatus {
  feature_availability: string;
  feature_availability_label: string;
}

export function OverviewPage() {
  const [data, setData] = useState<any>(null);
  const [platform, setPlatform] = useState<PlatformStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/overview`).catch(() => ({ data: null })),
      axios.get(`${API}/platform/status`).catch(() => ({ data: null })),
    ])
      .then(([overviewRes, platformRes]) => {
        setData(overviewRes.data);
        setPlatform(platformRes.data);
      })
      .finally(() => setLoading(false));
  }, []);

  const statusColor = useMemo(() => {
    const feature = platform?.feature_availability;
    if (feature === 'realtime_analysis') {
      return 'text-green-500 bg-green-500/10';
    }
    if (feature === 'post_market' || feature === 'session_ready') {
      return 'text-amber-500 bg-amber-500/10';
    }
    return 'text-muted-foreground bg-muted';
  }, [platform]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-bold tracking-tight">Platform Overview</h2>
        <div className={`flex items-center space-x-2 text-sm px-3 py-1 rounded-full ${statusColor}`}>
          <Activity className="w-4 h-4" />
          <span>{platform?.feature_availability_label || 'Platform status unavailable'}</span>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">Loading dashboard data...</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="bg-card border border-border rounded-xl p-6 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-muted-foreground">Market Regime</h3>
              <Activity className="w-4 h-4 text-primary" />
            </div>
            <div className="text-2xl font-bold mt-2 capitalize">{data?.metrics?.market_regime || 'Unknown'}</div>
          </div>

          <div className="bg-card border border-border rounded-xl p-6 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-muted-foreground">Backtest Runs</h3>
              <Database className="w-4 h-4 text-primary" />
            </div>
            <div className="text-2xl font-bold mt-2">{data?.metrics?.backtest_runs ?? 0}</div>
          </div>

          <div className="bg-card border border-border rounded-xl p-6 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-muted-foreground">Phase Coverage</h3>
              <Layers className="w-4 h-4 text-primary" />
            </div>
            <div className="text-2xl font-bold mt-2">
              {data?.metrics?.total_phases_available ?? 0}
              <span className="text-sm font-normal text-muted-foreground"> / {data?.metrics?.total_phases ?? 0}</span>
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-6 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-muted-foreground">Scanner State</h3>
              <BarChart2 className="w-4 h-4 text-primary" />
            </div>
            <div className={`text-2xl font-bold mt-2 ${data?.availability?.scanner ? 'text-green-500' : 'text-muted-foreground'}`}>
              {data?.availability?.scanner ? 'Artifact Available' : 'No Data'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
