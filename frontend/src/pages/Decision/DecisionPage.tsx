import { useEffect, useState } from 'react';
import axios from 'axios';
import { Briefcase, CheckCircle2, XCircle } from 'lucide-react';
import { AnalysisBadge } from '../../components/shared/AnalysisBadge';

export function DecisionPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/decision/latest')
      .then(res => setData(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Decision Engine & Portfolio Plan</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Aggregated signals mapped to planned sizing allocations.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">Fetching decision data...</div>
      ) : (
        <div className="grid gap-6">
          <div className="grid gap-4 md:grid-cols-3">
              <div className="bg-card border border-border p-6 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 font-medium text-muted-foreground">
                      <Briefcase className="w-5 h-5 text-blue-500" /> Planned Allocation
                  </div>
                  <div className="text-3xl font-bold">
                    ₹{data?.portfolio_plan?.total_allocated_capital?.toLocaleString() || '0'}
                  </div>
                  <div className="text-sm text-muted-foreground">of active capital pool</div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 font-medium text-muted-foreground">
                      <CheckCircle2 className="w-5 h-5 text-green-500" /> Selected Trades
                  </div>
                  <div className="text-3xl font-bold">
                    {data?.selected?.decisions?.length || 0}
                  </div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 font-medium text-muted-foreground">
                      <XCircle className="w-5 h-5 text-red-500" /> Rejected Trades
                  </div>
                  <div className="text-3xl font-bold">
                    {data?.rejected?.decisions?.length || 0}
                  </div>
              </div>
          </div>
          
          <div className="bg-card border border-border rounded-xl flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-border bg-muted/20">
                <h3 className="font-semibold text-lg">Portfolio Execution Plan</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs uppercase bg-muted/50 border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-6 py-4 font-medium">Symbol</th>
                    <th className="px-6 py-4 font-medium">Action</th>
                    <th className="px-6 py-4 font-medium">Shares/Qty</th>
                    <th className="px-6 py-4 font-medium whitespace-nowrap">Est. Capital</th>
                    <th className="px-6 py-4 font-medium">Risk Pct</th>
                    <th className="px-6 py-4 font-medium">Signal Composition</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data?.portfolio_plan?.allocations?.length > 0 ? (
                    data.portfolio_plan.allocations.map((alloc: any, i: number) => (
                      <tr key={i} className="hover:bg-muted/50 transition-colors">
                        <td className="px-6 py-4 font-bold">{alloc.symbol}</td>
                        <td className="px-6 py-4 capitalize font-semibold text-green-500">{alloc.action || 'Buy'}</td>
                        <td className="px-6 py-4 font-mono">{alloc.shares || alloc.quantity || '-'}</td>
                        <td className="px-6 py-4 font-mono text-primary">₹{alloc.allocated_capital?.toLocaleString() || '-'}</td>
                        <td className="px-6 py-4 font-mono">{alloc.risk_percent ? `${(alloc.risk_percent * 100).toFixed(2)}%` : '-'}</td>
                        <td className="px-6 py-4">
                            {alloc.analysis_families ? (
                              <div className="flex gap-2 flex-wrap">
                                {Object.entries(alloc.analysis_families).map(([family, info]: [string, any]) => (
                                  <AnalysisBadge
                                    key={family}
                                    family={family}
                                    score={info.score ?? 0}
                                    provider={info.provider ?? ''}
                                    freshness={info.freshness ?? ''}
                                    contribution={info.contribution ?? ''}
                                  />
                                ))}
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground">—</span>
                            )}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">No allocations generated.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
