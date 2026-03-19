import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Search, ArrowUpRight, ArrowDownRight } from 'lucide-react';

const API = 'http://localhost:8000/api/v1';

export function ScannerPage() {
  const [data, setData] = useState<any>(null);
  const [platform, setPlatform] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadAll = () => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/scanner/latest`).catch(() => ({ data: null })),
      axios.get(`${API}/platform/status`).catch(() => ({ data: null })),
    ])
      .then(([scanRes, platRes]) => {
        setData(scanRes.data);
        setPlatform(platRes.data);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadAll();
  }, []);

  const subtitle = useMemo(() => {
    if (loading) {
      return 'Loading scan metrics...';
    }

    if (data?.metadata?.timestamp) {
      return `Last Scan: ${data.metadata.timestamp}`;
    }

    if ((data?.opportunities?.length ?? 0) > 0) {
      return 'Using latest scanner artifact (timestamp metadata unavailable).';
    }

    const phase = platform?.market_session?.phase;
    if (phase && ['closed', 'post_close', 'weekend'].includes(phase)) {
      return `No fresh scan metadata. Market state: ${platform?.market_session?.label || phase}.`;
    }

    return 'No scan metadata available yet. Trigger a rescan to generate fresh artifacts.';
  }, [loading, data, platform]);

  const handleRescan = () => {
    const phase = platform?.market_session?.phase;
    if (phase === 'closed' || phase === 'weekend' || phase === 'post_close') {
      const proceed = window.confirm(
        'Market is currently not open. A rescan may use cached or end-of-day data. Proceed?',
      );
      if (!proceed) {
        return;
      }
    }

    axios
      .post(`${API}/automation/trigger/manual_rescan`)
      .then(() => alert('Manual rescan pipeline triggered successfully. Check Automation page for progress.'))
      .catch((err) => {
        const msg = err.response?.data?.detail || err.message;
        alert(`Failed to trigger rescan: ${msg}`);
      });
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Scanner Results</h2>
          <p className="text-muted-foreground mt-1 text-sm">{subtitle}</p>
        </div>
        <div className="flex space-x-3">
          {platform && (
            <div className="hidden md:flex items-center gap-4 px-4 border-r border-border mr-2">
              <div className="flex flex-col items-end">
                <span className="text-[10px] uppercase text-muted-foreground font-bold leading-none">Market Session</span>
                <span className={`text-xs font-bold ${platform.market_session?.phase === 'open' ? 'text-green-500' : 'text-amber-500'}`}>
                  {platform.market_session?.label || 'Unknown'}
                </span>
              </div>
              <div className="flex flex-col items-end border-l border-border pl-4">
                <span className="text-[10px] uppercase text-muted-foreground font-bold leading-none">Data Source</span>
                <span className="text-xs font-bold text-primary flex items-center gap-1 uppercase">
                  {platform.runtime_data_source || 'csv'}
                </span>
              </div>
            </div>
          )}
          <button
            title="Trigger a manual rescan pipeline (safe, non-live)"
            onClick={handleRescan}
            className="flex items-center space-x-2 px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm font-bold hover:bg-primary/90 transition-colors shadow-sm"
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
                        <span
                          className={`px-2 py-1 rounded inline-flex items-center space-x-1 text-xs font-semibold ${
                            opp.signal === 'buy' ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'
                          }`}
                        >
                          {opp.signal === 'buy' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                          <span className="uppercase">{opp.signal}</span>
                        </span>
                      </td>
                      <td className="px-6 py-4 font-mono">{opp.score?.toFixed(2) || opp.combined_score?.toFixed(2) || '-'}</td>
                      <td className="px-6 py-4 font-mono">{opp.entry_price != null ? `INR ${opp.entry_price.toFixed(2)}` : '-'}</td>
                      <td className="px-6 py-4 font-mono">{opp.score_liquidity != null ? opp.score_liquidity.toFixed(3) : '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                      No opportunities found in the latest scanner artifact.
                    </td>
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
