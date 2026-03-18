import { useEffect, useState } from 'react';
import axios from 'axios';
import { Search, Filter, ArrowUpRight, ArrowDownRight } from 'lucide-react';

export function ScannerPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/scanner/latest')
      .then(res => setData(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Scanner Results</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            {data?.metadata?.timestamp ? `Last Scan: ${data.metadata.timestamp}` : 'Loading scan metrics...'}
          </p>
        </div>
        <div className="flex space-x-3">
          <button className="flex items-center space-x-2 px-3 py-2 bg-card border border-border rounded-md text-sm hover:bg-muted">
            <Filter className="w-4 h-4" />
            <span>Filter</span>
          </button>
          <button 
            title="Trigger a manual rescan pipeline (Safe / Non-live)"
            onClick={() => {
              axios.post('http://localhost:8000/api/v1/automation/trigger/manual_rescan')
                .then(() => alert('Rescan triggered successfully! Check Automation page for progress.'))
                .catch(err => alert('Failed to trigger rescan: ' + err.message));
            }}
            className="flex items-center space-x-2 px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm hover:bg-primary/90 transition-colors"
          >
            <Search className="w-4 h-4" />
            <span>Rescan Now</span>
          </button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl flex flex-col overflow-hidden">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-muted-foreground">Fetching scanner candidates...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs uppercase bg-muted/50 border-b border-border text-muted-foreground">
                <tr>
                  <th className="px-6 py-4 font-medium">Symbol</th>
                  <th className="px-6 py-4 font-medium">Signal</th>
                  <th className="px-6 py-4 font-medium">Score</th>
                  <th className="px-6 py-4 font-medium">Entry Price</th>
                  <th className="px-6 py-4 font-medium">Liq. Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data?.opportunities?.length > 0 ? (
                  data.opportunities.map((opp: any, i: number) => (
                    <tr key={i} className="hover:bg-muted/50 transition-colors">
                      <td className="px-6 py-4 font-bold">{opp.symbol || 'UNKNOWN'}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded inline-flex items-center space-x-1 text-xs font-semibold ${
                          opp.signal === 'buy' ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'
                        }`}>
                          {opp.signal === 'buy' ? <ArrowUpRight className="w-3 h-3"/> : <ArrowDownRight className="w-3 h-3"/>}
                          <span className="uppercase">{opp.signal}</span>
                        </span>
                      </td>
                      <td className="px-6 py-4 font-mono">{opp.score?.toFixed(2) || opp.combined_score?.toFixed(2) || '-'}</td>
                      <td className="px-6 py-4 font-mono">{opp.entry_price != null ? `₹${opp.entry_price.toFixed(2)}` : '-'}</td>
                      <td className="px-6 py-4 font-mono">{opp.score_liquidity != null ? opp.score_liquidity.toFixed(3) : '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">No opportunities found in the recent scan.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
