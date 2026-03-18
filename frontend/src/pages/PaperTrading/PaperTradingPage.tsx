import { useEffect, useState } from 'react';
import axios from 'axios';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { DollarSign, Percent, History, Briefcase } from 'lucide-react';

export function PaperTradingPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/paper/state')
      .then(res => setData(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  // Check if real equity data exists
  const hasEquityData = data?.journal?.some((entry: any) => entry.equity || entry.balance);
  
  // Format chart data if journal exists and has equity values
  const chartData = hasEquityData ? data.journal.map((entry: any, i: number) => ({
    name: entry.timestamp || `Trade ${i}`,
    equity: parseFloat(entry.equity || entry.balance || '0')
  })) : [];

  // Compute session PnL from real journal data if possible
  const computedPnl: string | null = (() => {
    if (!hasEquityData || chartData.length < 2) return null;
    const first = chartData[0].equity;
    const last = chartData[chartData.length - 1].equity;
    if (!first || first === 0) return null;
    return `${((last - first) / first * 100).toFixed(2)}%`;
  })();

  // Filter positions to only actual open ones
  const activePositions = data?.positions?.filter((pos: any) => pos.status?.toLowerCase() !== 'closed') || [];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Paper Trading Session</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Simulated execution logs, PnL tracking, and active positions.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">Loading session state...</div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-4">
              <div className="bg-card border border-border p-6 rounded-xl">
                  <div className="flex items-center gap-2 font-medium text-muted-foreground mb-2">
                       <DollarSign className="w-5 h-5 text-primary" /> Current Equity
                  </div>
                  <div className="text-2xl font-bold">
                     {chartData.length > 0 && chartData[chartData.length-1].equity ? `₹${chartData[chartData.length-1].equity.toLocaleString()}` : 'N/A'}
                  </div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl">
                  <div className="flex items-center gap-2 font-medium text-muted-foreground mb-2">
                       <Percent className="w-5 h-5 text-green-500" /> Session PnL
                  </div>
                  <div className={`text-2xl font-bold ${computedPnl ? 'text-green-500' : 'text-muted-foreground'}`}>
                    {computedPnl ?? 'N/A'}
                  </div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl">
                  <div className="flex items-center gap-2 font-medium text-muted-foreground mb-2">
                       <Briefcase className="w-5 h-5 text-blue-500" /> Open Positions
                  </div>
                  <div className="text-2xl font-bold">{activePositions.length}</div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl">
                  <div className="flex items-center gap-2 font-medium text-muted-foreground mb-2">
                       <History className="w-5 h-5 text-purple-500" /> Journal Events Logged
                  </div>
                  <div className="text-2xl font-bold">{data?.journal?.length || 0}</div>
              </div>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
              <div className="md:col-span-2 bg-card border border-border rounded-xl p-6 h-96">
                  <h3 className="font-semibold mb-4">Equity Curve (Session)</h3>
                  {chartData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                          <XAxis dataKey="name" tick={{fill: 'var(--muted-foreground)'}} hide />
                          <YAxis domain={['auto', 'auto']} tick={{fill: 'var(--muted-foreground)'}} width={80} />
                          <Tooltip contentStyle={{backgroundColor: 'var(--card)', borderColor: 'var(--border)'}} />
                          <Area type="stepAfter" dataKey="equity" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.1} strokeWidth={2} />
                        </AreaChart>
                      </ResponsiveContainer>
                  ) : (
                      <div className="h-full flex items-center justify-center text-muted-foreground">Insufficient journal data to plot equity curve.</div>
                  )}
              </div>
              
              <div className="bg-card border border-border rounded-xl p-6 overflow-y-auto h-96">
                   <h3 className="font-semibold mb-4">Open Positions</h3>
                   {activePositions.length > 0 ? (
                       <div className="space-y-4">
                           {activePositions.map((pos: any, i: number) => (
                               <div key={i} className="flex justify-between items-center p-3 border border-border rounded-lg bg-muted/10">
                                   <div>
                                       <div className="font-bold">{pos.symbol}</div>
                                       <div className="text-xs text-muted-foreground capitalize">{pos.side || 'long'} • {pos.quantity || pos.shares || 0} shares</div>
                                   </div>
                                   <div className={`font-mono font-semibold ${pos.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                      ₹{pos.unrealized_pnl?.toFixed(2) || '0.00'}
                                   </div>
                               </div>
                           ))}
                       </div>
                   ) : (
                       <div className="text-center text-muted-foreground mt-12">No open positions.</div>
                   )}
              </div>
          </div>

        </div>
      )}
    </div>
  );
}
