import { useEffect, useState } from 'react';
import axios from 'axios';
import { Activity, AlertTriangle, TrendingUp, TrendingDown, Clock } from 'lucide-react';

export function MonitoringPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/monitoring/latest')
      .then(res => setData(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Active Monitoring</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Live tracked assets and active market alerts.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">Fetching monitoring data...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 space-y-6">
            <div className="bg-card border border-border rounded-xl flex flex-col overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-muted/20 flex justify-between items-center">
                  <h3 className="font-semibold flex items-center gap-2"><Activity className="w-4 h-4"/> Watchlist / Top Picks</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs uppercase bg-muted/50 border-b border-border text-muted-foreground">
                    <tr>
                      <th className="px-6 py-3 font-medium">Symbol</th>
                      <th className="px-6 py-3 font-medium">Rank</th>
                      <th className="px-6 py-3 font-medium">Score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {data?.top_picks?.length > 0 ? (
                      data.top_picks.slice(0, 10).map((pick: any, i: number) => (
                        <tr key={i} className="hover:bg-muted/50">
                          <td className="px-6 py-3 font-bold">{pick.symbol}</td>
                          <td className="px-6 py-3">#{pick.rank || pick.index || i + 1}</td>
                          <td className="px-6 py-3 font-mono text-primary">{pick.score?.toFixed(2) || pick.combined_score?.toFixed(2) || '-'}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={3} className="px-6 py-8 text-center text-muted-foreground">No top picks in active monitoring.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            
            <div className="bg-card border border-border rounded-xl flex flex-col overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-muted/20 flex justify-between items-center">
                  <h3 className="font-semibold flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-orange-400"/> Recent Alerts</h3>
              </div>
              <div className="p-0">
                  {data?.alerts?.length > 0 ? (
                      <div className="divide-y divide-border">
                          {data.alerts.map((alert: any, i: number) => (
                              <div key={i} className="p-4 flex gap-4 items-start">
                                  <div className="mt-1">
                                      {alert.type === 'bullish' ? <TrendingUp className="w-5 h-5 text-green-500" /> : <TrendingDown className="w-5 h-5 text-red-500" />}
                                  </div>
                                  <div>
                                      <p className="font-medium">{alert.message || `${alert.symbol} alert triggered`}</p>
                                      <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1"><Clock className="w-3 h-3"/> {alert.timestamp || 'Recent'}</p>
                                  </div>
                              </div>
                          ))}
                      </div>
                  ) : (
                      <div className="p-8 text-center text-muted-foreground">No active alerts.</div>
                  )}
              </div>
            </div>
          </div>
          
          <div className="space-y-6">
            <div className="bg-card border border-border rounded-xl p-6">
              <h3 className="font-semibold mb-4 text-lg">Market Snapshot</h3>
              <div className="space-y-4">
                  <div>
                      <div className="text-sm text-muted-foreground">Regime Bias</div>
                      <div className="text-xl font-bold capitalize">{data?.snapshot?.market_regime || data?.regime?.current_regime || 'Unknown'}</div>
                  </div>
                  <div>
                      <div className="text-sm text-muted-foreground">Volatility State</div>
                      <div className="text-lg capitalize">{data?.regime?.volatility_state || 'Normal'}</div>
                  </div>
                  <div>
                      <div className="text-sm text-muted-foreground">Breadth</div>
                      <div className="text-lg">{data?.snapshot?.breadth?.advancing_ratio ? `${(data.snapshot.breadth.advancing_ratio * 100).toFixed(1)}% Advancing` : 'N/A'}</div>
                  </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
