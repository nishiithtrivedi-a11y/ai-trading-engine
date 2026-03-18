import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Activity, Database, CheckCircle2, XCircle, AlertCircle, Loader2,
  Plug, RefreshCcw, Shield
} from 'lucide-react';

const API = 'http://localhost:8000/api/v1';

interface ProviderSession {
  provider_type: string;
  display_name: string;
  session_status: string;
  credentials_present: boolean;
  last_validated: string | null;
  diagnostics_summary: string;
  error_message: string | null;
}

const STATUS_MAP: Record<string, { color: string; icon: typeof CheckCircle2; label: string }> = {
  active: { color: 'text-green-500', icon: CheckCircle2, label: 'Active' },
  expired: { color: 'text-orange-500', icon: AlertCircle, label: 'Expired' },
  invalid: { color: 'text-red-500', icon: XCircle, label: 'Invalid' },
  error: { color: 'text-red-500', icon: XCircle, label: 'Error' },
  credentials_missing: { color: 'text-yellow-500', icon: AlertCircle, label: 'Creds Missing' },
  not_configured: { color: 'text-muted-foreground', icon: AlertCircle, label: 'Not Configured' },
};

export function DiagnosticsPage() {
  const [data, setData] = useState<any>(null);
  const [sessions, setSessions] = useState<ProviderSession[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/providers/health`).catch(() => ({ data: null })),
      axios.get(`${API}/providers/sessions`).catch(() => ({ data: { providers: [] } })),
    ]).then(([healthRes, sessionRes]) => {
      setData(healthRes.data);
      setSessions(sessionRes.data.providers || []);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Provider Diagnostics & Data Health</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Session health, API connections, active modules, and feed latencies.
          </p>
        </div>
        <button onClick={loadData} className="p-2 rounded-lg hover:bg-muted transition-colors" title="Refresh">
          <RefreshCcw className="w-5 h-5" />
        </button>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading diagnostics...
        </div>
      ) : (
        <div className="space-y-6">

          {/* ─── Session Health ─── */}
          {sessions.length > 0 && (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-muted/20 flex items-center gap-2">
                <Plug className="w-5 h-5 text-indigo-500" />
                <h3 className="font-semibold text-lg">Session Health</h3>
              </div>
              <div className="grid gap-4 md:grid-cols-3 p-6">
                {sessions.map(s => {
                  const statusInfo = STATUS_MAP[s.session_status] || STATUS_MAP.not_configured;
                  const StatusIcon = statusInfo.icon;
                  return (
                    <div key={s.provider_type} className="border border-border rounded-lg p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold">{s.display_name || s.provider_type}</span>
                        <span className={`flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider ${statusInfo.color}`}>
                          <StatusIcon className="w-3.5 h-3.5" /> {statusInfo.label}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {s.session_status === 'not_configured' && 'Provider not configured — no credentials present.'}
                        {s.session_status === 'credentials_missing' && (
                          <span className="text-yellow-600">{s.diagnostics_summary || 'Some credentials are missing.'}</span>
                        )}
                        {s.session_status === 'active' && (
                          <span className="text-green-600">Session active. {s.last_validated ? `Validated: ${new Date(s.last_validated).toLocaleString()}` : ''}</span>
                        )}
                        {s.session_status === 'expired' && (
                          <span className="text-orange-600">Session expired. Reconnect required.</span>
                        )}
                        {(s.session_status === 'invalid' || s.session_status === 'error') && (
                          <span className="text-red-500">{s.error_message || 'Auth validation failed.'}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="px-6 pb-4 flex items-center gap-2">
                <Shield className="w-4 h-4 text-green-600" />
                <span className="text-[11px] text-muted-foreground">
                  Connecting a provider does <strong>not</strong> enable live trading. Execution remains structurally disabled.
                </span>
              </div>
            </div>
          )}

          {/* ─── Summary Cards ─── */}
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
              <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4">
                  <div className="p-3 bg-indigo-500/10 rounded-full text-indigo-500">
                      <Plug className="w-6 h-6" />
                  </div>
                  <div>
                      <div className="text-sm font-medium text-muted-foreground">Provider Sessions</div>
                      <div className="text-xl font-bold">{sessions.filter(s => s.session_status === 'active').length} / {sessions.length}</div>
                  </div>
              </div>
          </div>

          {/* ─── Diagnostics Matrix ─── */}
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
