import { useEffect, useState } from 'react';
import { Activity, Database, CheckCircle, BarChart2, Layers } from 'lucide-react';
import axios from 'axios';

export function OverviewPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/overview')
      .then(res => setData(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-bold tracking-tight">Platform Overview</h2>
        <div className="flex items-center space-x-2 text-sm text-green-500 bg-green-500/10 px-3 py-1 rounded-full">
          <CheckCircle className="w-4 h-4" />
          <span>System Healthy</span>
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
              {data?.availability?.scanner ? 'Active' : 'No Data'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
