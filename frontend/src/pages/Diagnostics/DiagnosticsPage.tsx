import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Database, CheckCircle2, XCircle, AlertCircle, Loader2,
  Plug, RefreshCcw, Shield, Radio, Zap
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

interface PlatformStatus {
  runtime_data_source: string;
  connected_sessions: number;
  total_sessions: number;
  market_session: {
    phase: string;
    label: string;
    current_time_ist: string;
    is_tradeable: boolean;
    next_transition: string;
  };
  feature_availability: string;
  feature_availability_label: string;
}

const STATUS_MAP: Record<string, { color: string; icon: typeof CheckCircle2; label: string }> = {
  active: { color: 'text-green-500', icon: CheckCircle2, label: 'Active' },
  expired: { color: 'text-orange-500', icon: AlertCircle, label: 'Expired' },
  invalid: { color: 'text-red-500', icon: XCircle, label: 'Invalid' },
  error: { color: 'text-red-500', icon: XCircle, label: 'Error' },
  credentials_missing: { color: 'text-yellow-500', icon: AlertCircle, label: 'Creds Missing' },
  not_configured: { color: 'text-muted-foreground', icon: AlertCircle, label: 'Not Configured' },
};

const DIAGNOSTICS_STATUS_MAP: Record<string, { color: string; label: string }> = {
  active_primary: { color: 'text-primary', label: 'PRIMARY' },
  session_active: { color: 'text-green-500', label: 'SESSION ACTIVE' },
  healthy: { color: 'text-green-500', label: 'HEALTHY' },
  configured: { color: 'text-muted-foreground', label: 'CONFIGURED' },
  offline: { color: 'text-muted-foreground', label: 'OFFLINE' },
};

const MARKET_PHASE_STYLES: Record<string, { color: string; bg: string }> = {
  open: { color: 'text-green-500', bg: 'bg-green-500/10' },
  pre_open: { color: 'text-blue-400', bg: 'bg-blue-400/10' },
  post_close: { color: 'text-amber-500', bg: 'bg-amber-500/10' },
  closed: { color: 'text-muted-foreground', bg: 'bg-muted' },
  weekend: { color: 'text-muted-foreground', bg: 'bg-muted' },
  unknown: { color: 'text-muted-foreground', bg: 'bg-muted' },
};

const FEATURE_STYLES: Record<string, { color: string; bg: string }> = {
  realtime_analysis: { color: 'text-green-500', bg: 'bg-green-500/10' },
  post_market: { color: 'text-amber-500', bg: 'bg-amber-500/10' },
  offline_analysis: { color: 'text-muted-foreground', bg: 'bg-muted' },
  fallback_active: { color: 'text-blue-400', bg: 'bg-blue-400/10' },
};

export function DiagnosticsPage() {
  const [data, setData] = useState<any>(null);
  const [sessions, setSessions] = useState<ProviderSession[]>([]);
  const [platform, setPlatform] = useState<PlatformStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/providers/health`).catch(() => ({ data: null })),
      axios.get(`${API}/providers/sessions`).catch(() => ({ data: { providers: [] } })),
      axios.get(`${API}/platform/status`).catch(() => ({ data: null })),
    ]).then(([healthRes, sessionRes, platformRes]) => {
      setData(healthRes.data);
      setSessions(sessionRes.data.providers || []);
      setPlatform(platformRes.data);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const marketPhase = platform?.market_session?.phase ?? 'unknown';
  const marketStyles = MARKET_PHASE_STYLES[marketPhase] || MARKET_PHASE_STYLES.unknown;
  const featureKey = platform?.feature_availability ?? 'offline_analysis';
  const featureStyles = FEATURE_STYLES[featureKey] || FEATURE_STYLES.offline_analysis;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Provider Diagnostics & Data Health</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Session health, runtime source, market state, and feature availability.
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

          {/* ─── 4 Summary Cards ─── */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4">
                  <div className="p-3 bg-primary/10 rounded-full text-primary">
                      <Database className="w-6 h-6" />
                  </div>
                  <div>
                      <div className="text-sm font-medium text-muted-foreground">Runtime Data Source</div>
                      <div className="text-xl font-bold uppercase">{platform?.runtime_data_source || data?.default_provider || 'Not Set'}</div>
                      {platform && platform.runtime_data_source !== platform.market_session?.phase && platform.connected_sessions > 0 && (platform.runtime_data_source === 'csv' || platform.runtime_data_source === 'indian_csv') && (
                        <div className="text-[10px] text-amber-500 mt-0.5">
                          ⚠ Provider connected — runtime still on CSV
                        </div>
                      )}
                  </div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4">
                  <div className="p-3 bg-indigo-500/10 rounded-full text-indigo-500">
                      <Plug className="w-6 h-6" />
                  </div>
                  <div>
                      <div className="text-sm font-medium text-muted-foreground">Provider Sessions</div>
                      <div className="text-xl font-bold">{platform?.connected_sessions ?? sessions.filter(s => s.session_status === 'active').length} / {platform?.total_sessions ?? sessions.length}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {(platform?.connected_sessions ?? 0) > 0 ? 'Active connections' : 'No active sessions'}
                      </div>
                  </div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4">
                  <div className={`p-3 rounded-full ${marketStyles.bg}`}>
                      <Radio className={`w-6 h-6 ${marketStyles.color}`} />
                  </div>
                  <div>
                      <div className="text-sm font-medium text-muted-foreground">Market Session</div>
                      <div className={`text-xl font-bold ${marketStyles.color}`}>
                        {platform?.market_session?.label ?? 'Unknown'}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {platform?.market_session?.next_transition ?? ''}
                      </div>
                  </div>
              </div>
              <div className="bg-card border border-border p-6 rounded-xl flex items-center gap-4">
                  <div className={`p-3 rounded-full ${featureStyles.bg}`}>
                      <Zap className={`w-6 h-6 ${featureStyles.color}`} />
                  </div>
                  <div>
                      <div className="text-sm font-medium text-muted-foreground">Feature Availability</div>
                      <div className={`text-sm font-bold ${featureStyles.color}`}>
                        {platform?.feature_availability_label ?? 'Loading...'}
                      </div>
                  </div>
              </div>
          </div>

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
                  const isActive = s.session_status === 'active';
                  const isPrimary = s.provider_type === (platform?.runtime_data_source ?? data?.default_provider);
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
                          <span className="text-green-600">
                            Session active. {s.last_validated ? `Validated: ${new Date(s.last_validated).toLocaleString()}` : ''}
                          </span>
                        )}
                        {s.session_status === 'expired' && (
                          <span className="text-orange-600">Session expired. Reconnect required.</span>
                        )}
                        {(s.session_status === 'invalid' || s.session_status === 'error') && (
                          <span className="text-red-500">{s.error_message || 'Auth validation failed.'}</span>
                        )}
                      </div>
                      {/* Runtime role indicator */}
                      {isActive && !isPrimary && (
                        <div className="text-[10px] bg-blue-500/10 text-blue-400 px-2 py-1 rounded">
                          Connected — not currently primary data source (primary: {platform?.runtime_data_source ?? 'CSV'})
                        </div>
                      )}
                      {isActive && isPrimary && (
                        <div className="text-[10px] bg-green-500/10 text-green-600 px-2 py-1 rounded">
                          Active primary runtime data source
                        </div>
                      )}
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
                    <th className="px-6 py-4 font-medium">Runtime Status</th>
                    <th className="px-6 py-4 font-medium">Session</th>
                    <th className="px-6 py-4 font-medium">Latency</th>
                    <th className="px-6 py-4 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data?.diagnostics?.length > 0 ? (
                    data.diagnostics.map((prov: any, i: number) => {
                      const diagStatus = DIAGNOSTICS_STATUS_MAP[prov.status] || { color: 'text-muted-foreground', label: prov.status?.toUpperCase() ?? '—' };
                      const sessionStatus = prov.session_status ? (STATUS_MAP[prov.session_status] || STATUS_MAP.not_configured) : null;
                      return (
                        <tr key={i} className={`hover:bg-muted/50 transition-colors ${!prov.enabled && 'opacity-60'}`}>
                            <td className="px-6 py-4 font-bold capitalize">{prov.name}</td>
                            <td className="px-6 py-4 text-muted-foreground">{prov.type?.replace('_', ' ')}</td>
                            <td className="px-6 py-4">
                                <span className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider ${diagStatus.color}`}>
                                  {prov.status === 'active_primary' && <CheckCircle2 className="w-4 h-4"/>}
                                  {prov.status === 'session_active' && <CheckCircle2 className="w-4 h-4"/>}
                                  {prov.status === 'healthy' && <CheckCircle2 className="w-4 h-4"/>}
                                  {prov.status === 'configured' && <AlertCircle className="w-4 h-4"/>}
                                  {prov.status === 'offline' && <XCircle className="w-4 h-4"/>}
                                  {diagStatus.label}
                                </span>
                            </td>
                            <td className="px-6 py-4">
                              {sessionStatus ? (
                                <span className={`flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider ${sessionStatus.color}`}>
                                  <sessionStatus.icon className="w-3 h-3" /> {sessionStatus.label}
                                </span>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </td>
                            <td className="px-6 py-4 font-mono">{prov.latency}</td>
                            <td className="px-6 py-4 text-muted-foreground text-xs">{prov.details}</td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">No diagnostics data available.</td>
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
