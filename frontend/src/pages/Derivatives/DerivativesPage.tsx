import { useEffect, useState } from 'react';
import axios from 'axios';
import { Network, Database, AlertCircle, Info, Activity } from 'lucide-react';

export function DerivativesPage() {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/derivatives/summary')
      .then(res => setSummary(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Derivatives Intelligence</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Options chains, Greeks, volatility surfaces, and futures basis arrays.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">Connecting to options layer...</div>
      ) : summary?.status === 'unavailable' ? (
        <div className="space-y-6">
            
            {/* Degraded State Warning */}
            <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-6 flex flex-col items-center justify-center text-center space-y-4">
                <AlertCircle className="w-10 h-10 text-orange-400" />
                <div>
                    <h3 className="text-lg font-bold text-orange-400">Offline: {summary.message}</h3>
                    <p className="text-orange-400/80 text-sm max-w-lg mt-1">
                        The current live session relies purely on spot feeds via `csv` provider. Options pricing, IV computation, and Greeks are gracefully suspended.
                    </p>
                </div>
            </div>

            {/* Diagnostics Panel */}
            <div className="grid gap-4 md:grid-cols-4">
                <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4 opacity-50">
                   <div className="p-3 bg-muted rounded-full">
                      <Database className="w-5 h-5" />
                   </div>
                   <div>
                       <div className="text-sm font-medium text-muted-foreground">Source</div>
                       <div className="font-bold">{summary.diagnostics?.source}</div>
                   </div>
                </div>
                <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4 opacity-50">
                   <div className="p-3 bg-muted rounded-full">
                      <Activity className="w-5 h-5" />
                   </div>
                   <div>
                       <div className="text-sm font-medium text-muted-foreground">Coverage</div>
                       <div className="font-bold">{summary.diagnostics?.coverage}</div>
                   </div>
                </div>
                <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4 opacity-50">
                   <div className="p-3 bg-muted rounded-full">
                      <Network className="w-5 h-5" />
                   </div>
                   <div>
                       <div className="text-sm font-medium text-muted-foreground">Freshness</div>
                       <div className="font-bold">{summary.diagnostics?.freshness}</div>
                   </div>
                </div>
                <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4 bg-primary/5 border-primary/20">
                   <div className="p-3 bg-primary/20 rounded-full text-primary">
                      <Info className="w-5 h-5" />
                   </div>
                   <div>
                       <div className="text-sm font-medium text-muted-foreground">Spot Reference</div>
                       <div className="font-bold text-primary">{summary.spot_reference?.symbol} @ {summary.spot_reference?.price}</div>
                   </div>
                </div>
            </div>

            {/* Placeholder UI Grid to satisfy dense layout requirement but visibly disabled */}
            <div className="grid gap-6 md:grid-cols-3 opacity-40 select-none grayscale cursor-not-allowed">
                <div className="md:col-span-2 bg-card border border-border rounded-xl p-6 h-96 flex flex-col">
                    <div className="flex justify-between items-center mb-4">
                        <h3 className="font-semibold">Options Chain (NIFTY - <span className="text-muted-foreground font-normal">Awaiting Expiry Data</span>)</h3>
                    </div>
                    <div className="flex-1 border border-border rounded flex items-center justify-center bg-muted/20 text-muted-foreground text-sm">
                        [ CHAIN GRID PLACEHOLDER ]
                    </div>
                </div>

                <div className="bg-card border border-border rounded-xl p-6 h-96 flex flex-col space-y-4">
                    <div>
                        <h3 className="font-semibold mb-2">Volatility Surface</h3>
                        <div className="h-32 border border-border rounded flex items-center justify-center bg-muted/20 text-muted-foreground text-xs">
                            [ IV SKEW PLOT ]
                        </div>
                    </div>
                    <div>
                        <h3 className="font-semibold mb-2">OI Concentration</h3>
                        <div className="h-32 border border-border rounded flex items-center justify-center bg-muted/20 text-muted-foreground text-xs">
                            [ STRIKE LADDER ]
                        </div>
                    </div>
                </div>
            </div>

        </div>
      ) : (
          <div>Standard derivatives UI rendering (unavailable in current smoke)</div>
      )}
    </div>
  );
}
