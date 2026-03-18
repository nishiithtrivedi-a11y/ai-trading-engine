import { useEffect, useState } from 'react';
import axios from 'axios';
import { Activity, Database, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

export function DiagnosticsPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/providers/health')
      .then(res => setData(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Provider Diagnostics & Data Health</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             API connection matrix, active modules, and feed latencies. Providers not actively configured in backend YAML are naturally filtered out here.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">Loading diagnostics...</div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-3">
              <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4">
                  <div className="p-3 bg-primary/10 rounded-full text-primary">
                      <Database className="w-6 h-6" />
                  </div>
                  <div>
                      <div className="text-sm font-medium text-muted-foreground">Primary Provider</div>
                      <div className="text-xl font-bold uppercase">{data?.default_provider || 'Not Set'}</div>
                  </div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4">
                  <div className="p-3 bg-green-500/10 rounded-full text-green-500">
                      <Activity className="w-6 h-6" />
                  </div>
                  <div>
                      <div className="text-sm font-medium text-muted-foreground">Active Feeds</div>
                      <div className="text-xl font-bold">{data?.diagnostics?.filter((d: any) => d.enabled).length || 0}</div>
                  </div>
              </div>
          </div>

          <div className="bg-card border border-border rounded-xl flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-border bg-muted/20">
                <h3 className="font-semibold text-lg">Diagnostics Matrix</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs uppercase bg-muted/50 border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-6 py-4 font-medium">Provider</th>
                    <th className="px-6 py-4 font-medium">Type</th>
                    <th className="px-6 py-4 font-medium">Status</th>
                    <th className="px-6 py-4 font-medium">Latency</th>
                    <th className="px-6 py-4 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data?.diagnostics?.length > 0 ? (
                    data.diagnostics.map((prov: any, i: number) => (
                        <tr key={i} className={`hover:bg-muted/50 transition-colors ${!prov.enabled && 'opacity-60 grayscale'}`}>
                            <td className="px-6 py-4 font-bold capitalize">{prov.name}</td>
                            <td className="px-6 py-4 text-muted-foreground">{prov.type?.replace('_', ' ')}</td>
                            <td className="px-6 py-4">
                                {prov.status === 'active_primary' ? (
                                    <span className="flex items-center gap-1.5 text-primary text-xs font-semibold uppercase tracking-wider"><CheckCircle2 className="w-4 h-4"/> Primary</span>
                                ) : prov.status === 'healthy' ? (
                                    <span className="flex items-center gap-1.5 text-green-500 text-xs font-semibold uppercase tracking-wider"><CheckCircle2 className="w-4 h-4"/> Healthy</span>
                                ) : prov.status === 'offline' ? (
                                    <span className="flex items-center gap-1.5 text-muted-foreground text-xs font-semibold uppercase tracking-wider"><XCircle className="w-4 h-4"/> Offline</span>
                                ) : (
                                    <span className="flex items-center gap-1.5 text-orange-400 text-xs font-semibold uppercase tracking-wider"><AlertCircle className="w-4 h-4"/> Degraded</span>
                                )}
                            </td>
                            <td className="px-6 py-4 font-mono">{prov.latency}</td>
                            <td className="px-6 py-4 text-muted-foreground text-xs">{prov.details}</td>
                        </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">No diagnostics data available.</td>
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
