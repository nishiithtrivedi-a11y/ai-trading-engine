import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  Shield,
  Server,
  Plug,
  Settings2,
  Cpu,
  Lock,
  RefreshCcw,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  BellRing,
  ExternalLink,
  Radio,
} from 'lucide-react';

const API = 'http://localhost:8000/api/v1';

interface ProviderSession {
  provider_type: string;
  display_name: string;
  session_status: string;
  credentials_present: boolean;
  last_validated: string | null;
  expiry_time: string | null;
  error_message: string | null;
  diagnostics_summary: string;
  masked_indicators: Record<string, string>;
}

const SESSION_STATUS_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  active: { color: 'text-green-500', bg: 'bg-green-500/20', label: 'Active' },
  expired: { color: 'text-orange-500', bg: 'bg-orange-500/20', label: 'Expired' },
  invalid: { color: 'text-red-500', bg: 'bg-red-500/20', label: 'Invalid' },
  error: { color: 'text-red-500', bg: 'bg-red-500/20', label: 'Error' },
  credentials_missing: { color: 'text-yellow-500', bg: 'bg-yellow-500/20', label: 'Credentials Missing' },
  not_configured: { color: 'text-muted-foreground', bg: 'bg-muted', label: 'Not Configured' },
};

function SessionBadge({ status }: { status: string }) {
  const style = SESSION_STATUS_STYLES[status] || SESSION_STATUS_STYLES.not_configured;
  const Icon = status === 'active' ? CheckCircle2 : status === 'error' || status === 'invalid' ? XCircle : AlertCircle;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${style.color} ${style.bg}`}>
      <Icon className="w-3 h-3" /> {style.label}
    </span>
  );
}

export function SettingsPage() {
  const [providers, setProviders] = useState<ProviderSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [validating, setValidating] = useState<string | null>(null);
  const [runtimeSource, setRuntimeSource] = useState('csv');
  const [marketLabel, setMarketLabel] = useState('Unknown');
  const [marketPhase, setMarketPhase] = useState('unknown');

  const [dhanConfigOpen, setDhanConfigOpen] = useState(false);
  const [dhanClientId, setDhanClientId] = useState('');
  const [dhanAccessToken, setDhanAccessToken] = useState('');
  const [savingDhan, setSavingDhan] = useState(false);

  const oauthPollRef = useRef<number | null>(null);
  const oauthTimeoutRef = useRef<number | null>(null);

  const clearOAuthPolling = useCallback(() => {
    if (oauthPollRef.current != null) {
      window.clearInterval(oauthPollRef.current);
      oauthPollRef.current = null;
    }
    if (oauthTimeoutRef.current != null) {
      window.clearTimeout(oauthTimeoutRef.current);
      oauthTimeoutRef.current = null;
    }
  }, []);

  const loadProviders = useCallback(() => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/providers/sessions`).catch(() => ({ data: { providers: [] } })),
      axios.get(`${API}/platform/status`).catch(() => ({ data: null })),
    ])
      .then(([sessRes, platRes]) => {
        setProviders(sessRes.data.providers || []);
        if (platRes.data) {
          setRuntimeSource(platRes.data.runtime_data_source ?? 'csv');
          setMarketLabel(platRes.data.market_session?.label ?? 'Unknown');
          setMarketPhase(platRes.data.market_session?.phase ?? 'unknown');
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadProviders();
  }, [loadProviders]);

  useEffect(() => {
    return () => clearOAuthPolling();
  }, [clearOAuthPolling]);

  const activeSessions = useMemo(
    () => providers.filter((p) => p.session_status === 'active').length,
    [providers],
  );

  const validateProvider = async (providerType: string) => {
    setValidating(providerType);
    try {
      const res = await axios.post(`${API}/providers/sessions/${providerType}/validate`);
      setProviders((prev) => prev.map((p) => (p.provider_type === providerType ? res.data.provider : p)));
    } catch {
      // noop
    } finally {
      setValidating(null);
    }
  };

  const handleOAuthConnect = async (providerType: string) => {
    try {
      clearOAuthPolling();
      const res = await axios.get(`${API}/providers/sessions/${providerType}/login`);
      const authWindow = window.open(res.data.login_url, `${providerType}_login`, 'width=500,height=700');

      if (!authWindow) {
        alert(`Popup blocked. Please allow popups to continue ${providerType} login.`);
        return;
      }

      oauthPollRef.current = window.setInterval(() => {
        if (authWindow.closed) {
          clearOAuthPolling();
          loadProviders();
        }
      }, 1000);

      oauthTimeoutRef.current = window.setTimeout(() => {
        if (!authWindow.closed) {
          authWindow.close();
          alert(`${providerType} login timed out after 2 minutes. Please try again.`);
        }
        clearOAuthPolling();
      }, 120000);
    } catch (err: any) {
      alert(`Failed to start ${providerType} connection: ${err.response?.data?.detail || err.message}`);
    }
  };

  const handleDhanSave = async () => {
    if (!dhanClientId || !dhanAccessToken) {
      alert('Both Client ID and Access Token are required.');
      return;
    }
    setSavingDhan(true);
    try {
      await axios.post(`${API}/providers/sessions/dhan/credentials`, {
        credentials: {
          CLIENT_ID: dhanClientId,
          ACCESS_TOKEN: dhanAccessToken,
        },
      });
      setDhanConfigOpen(false);
      setDhanClientId('');
      setDhanAccessToken('');
      loadProviders();
    } catch (err: any) {
      alert(`Failed to save Dhan credentials: ${err.message}`);
    } finally {
      setSavingDhan(false);
    }
  };

  const handleSetPrimary = async (providerType: string) => {
    try {
      await axios.post(`${API}/platform/runtime-source`, { provider_type: providerType });
      loadProviders();
    } catch (err: any) {
      alert(`Failed to set ${providerType} as primary: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">System Control Room</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Configuration matrices, provider connections, session management, and system limits.
          </p>
        </div>
        <button onClick={loadProviders} className="p-2 rounded-lg hover:bg-muted transition-colors" title="Refresh">
          <RefreshCcw className="w-5 h-5" />
        </button>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
            <Settings2 className="w-5 h-5 text-primary" /> Profile & Risk Defaults
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Default Drawdown Mode</span>
              <span className="font-mono">Operator-managed</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Max Capital @ Risk</span>
              <span className="font-mono">Operator-managed (INR)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Artifact Retention</span>
              <span className="font-mono">Operator-managed</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Log Verbosity</span>
              <span className="font-mono">Operator-managed</span>
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
            <Plug className="w-5 h-5 text-blue-500" /> Data Providers
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Primary Runtime Source</span>
              <span className="font-mono uppercase">{runtimeSource || 'csv'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Connected Sessions</span>
              <span className="font-mono">{activeSessions}/{providers.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Analysis Providers</span>
              <span className="font-mono">Operator-managed</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Market Session</span>
              <span className="font-mono">{marketLabel}</span>
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
            <Cpu className="w-5 h-5 text-purple-500" /> AI & Modules
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">AI Workspace Backend</span>
              <span className="font-mono">Advisory API</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Token Limit</span>
              <span className="font-mono">Operator-managed</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Analysis Families</span>
              <span className="font-mono">Profile-dependent</span>
            </div>
          </div>
          <div className="mt-4 pt-4 border-t border-border flex items-center gap-2">
            <Server className="w-4 h-4 text-green-500" />
            <span className="text-xs text-muted-foreground">Engine API config checks healthy</span>
          </div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-6 space-y-4">
        <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
          <Plug className="w-5 h-5 text-indigo-500" /> Provider Authentication & Sessions
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading provider sessions...
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {providers.map((p) => (
              <div key={p.provider_type} className="border border-border rounded-lg overflow-hidden">
                <div className="p-4 bg-muted/20 border-b border-border flex items-center justify-between">
                  <span className="font-semibold">{p.display_name || p.provider_type}</span>
                  <div className="flex gap-2 items-center">
                    {p.provider_type === runtimeSource && (
                      <span className="bg-primary/20 text-primary text-[10px] px-2 py-0.5 rounded font-bold uppercase">Primary</span>
                    )}
                    <SessionBadge status={p.session_status} />
                  </div>
                </div>

                <div className="p-4 space-y-3">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Credentials</span>
                    <span className={`font-mono ${p.credentials_present ? 'text-green-500' : 'text-orange-500'}`}>
                      {p.credentials_present ? 'Present' : 'Missing'}
                    </span>
                  </div>
                  {Object.entries(p.masked_indicators || {}).map(([key, val]) => (
                    <div key={key} className="flex justify-between text-xs">
                      <span className="text-muted-foreground">{key}</span>
                      <span className="font-mono text-[11px]">{val}</span>
                    </div>
                  ))}
                  {p.last_validated && (
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Last Validated</span>
                      <span className="font-mono">{new Date(p.last_validated).toLocaleString()}</span>
                    </div>
                  )}
                  {p.diagnostics_summary && (
                    <div className="text-[11px] text-muted-foreground bg-muted/30 p-2 rounded">{p.diagnostics_summary}</div>
                  )}
                  {p.error_message && (
                    <div className="text-[11px] text-red-500 bg-red-500/10 p-2 rounded">{p.error_message}</div>
                  )}
                </div>

                {p.session_status === 'active' && (
                  <div className="px-4 pb-2 space-y-1">
                    {p.provider_type !== runtimeSource && (
                      <div className="text-[10px] bg-blue-500/10 text-blue-400 px-2 py-1 rounded flex items-center gap-1">
                        <Radio className="w-3 h-3" /> Connected - not currently primary data source (primary: {runtimeSource.toUpperCase()})
                      </div>
                    )}
                    {['post_close', 'closed', 'weekend'].includes(marketPhase) && (
                      <div className="text-[10px] bg-amber-500/10 text-amber-500 px-2 py-1 rounded">Connected - {marketLabel}</div>
                    )}
                  </div>
                )}

                <div className="p-3 border-t border-border bg-muted/10 flex justify-end gap-2">
                  {p.provider_type === 'dhan' ? (
                    <button
                      onClick={() => setDhanConfigOpen(true)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-500/10 text-indigo-500 rounded text-xs font-bold uppercase tracking-wider hover:bg-indigo-500/20 transition-colors"
                    >
                      <Settings2 className="w-3 h-3" />
                      {p.session_status === 'active' || p.session_status === 'expired' ? 'Update Credentials' : 'Connect Dhan'}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleOAuthConnect(p.provider_type)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-500/10 text-indigo-500 rounded text-xs font-bold uppercase tracking-wider hover:bg-indigo-500/20 transition-colors"
                    >
                      {p.session_status === 'active' || p.session_status === 'expired' ? <RefreshCcw className="w-3 h-3" /> : <Plug className="w-3 h-3" />}
                      {p.session_status === 'active' || p.session_status === 'expired' ? 'Reconnect' : 'Connect'}
                    </button>
                  )}

                  {p.session_status === 'active' && p.provider_type !== runtimeSource && (
                    <button
                      onClick={() => handleSetPrimary(p.provider_type)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded text-xs font-bold uppercase tracking-wider hover:bg-primary/90 transition-colors"
                    >
                      Set as Primary
                    </button>
                  )}

                  <button
                    onClick={() => validateProvider(p.provider_type)}
                    disabled={validating === p.provider_type}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary rounded text-xs font-bold uppercase tracking-wider hover:bg-primary/20 transition-colors disabled:opacity-50"
                  >
                    {validating === p.provider_type ? <Loader2 className="w-3 h-3 animate-spin" /> : <Shield className="w-3 h-3" />}
                    {p.session_status === 'active' ? 'Refresh' : 'Validate'}
                  </button>
                </div>
              </div>
            ))}
            {providers.length === 0 && (
              <div className="col-span-3 text-center py-8 text-muted-foreground">
                No providers registered. Start the API backend to load provider sessions.
              </div>
            )}
          </div>
        )}

        <div className="pt-4 border-t border-border flex items-center gap-2">
          <BellRing className="w-4 h-4 text-amber-500" />
          <span className="text-xs text-muted-foreground">
            Notification targets and preferences are managed on the{' '}
            <a href="/automation" className="text-primary font-medium hover:underline inline-flex items-center gap-0.5">
              Automation page <ExternalLink className="w-3 h-3" />
            </a>
          </span>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-6 space-y-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-background/50 backdrop-blur-[1px] z-10 flex flex-col items-center justify-center">
          <Lock className="w-8 h-8 text-muted-foreground mb-2" />
          <h3 className="font-bold text-lg text-foreground">Execution Controls Locked</h3>
          <p className="text-sm text-muted-foreground max-w-md text-center">
            Broker routing and live deployment remain structurally disabled. Provider sessions do not enable trading.
          </p>
        </div>
        <div className="opacity-30 relative z-0">
          <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
            <Shield className="w-5 h-5 text-red-500" /> Live Execution & Brokers (Future Phase)
          </div>
        </div>
      </div>

      {dhanConfigOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="bg-card w-full max-w-md border border-border shadow-lg rounded-xl p-6 relative">
            <button onClick={() => setDhanConfigOpen(false)} className="absolute top-4 right-4 text-muted-foreground hover:text-foreground">
              <XCircle className="w-5 h-5" />
            </button>
            <h3 className="text-xl font-bold mb-4">Configure Dhan</h3>
            <p className="text-xs text-muted-foreground mb-6">
              Enter Client ID and Access Token. Credentials are stored in local environment settings.
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold mb-1">CLIENT ID</label>
                <input
                  value={dhanClientId}
                  onChange={(e) => setDhanClientId(e.target.value)}
                  type="text"
                  className="w-full bg-background border border-border rounded p-2 text-sm focus:outline-none focus:border-primary"
                  placeholder="100..."
                />
              </div>
              <div>
                <label className="block text-xs font-bold mb-1">ACCESS TOKEN</label>
                <input
                  value={dhanAccessToken}
                  onChange={(e) => setDhanAccessToken(e.target.value)}
                  type="password"
                  className="w-full bg-background border border-border rounded p-2 text-sm focus:outline-none focus:border-primary"
                  placeholder="eyJ..."
                />
              </div>
              <div className="pt-2">
                <button
                  onClick={handleDhanSave}
                  disabled={savingDhan}
                  className="w-full bg-primary text-primary-foreground py-2 rounded font-bold transition-colors hover:bg-primary/90 disabled:opacity-50 inline-flex items-center justify-center gap-2"
                >
                  {savingDhan && <Loader2 className="w-4 h-4 animate-spin" />}
                  {savingDhan ? 'Saving...' : 'Save & Reconnect'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
