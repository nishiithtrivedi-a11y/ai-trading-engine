import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Shield, Server, Plug, Settings2, Cpu, Lock, RefreshCcw,
  CheckCircle2, XCircle, AlertCircle, Loader2, BellRing, ExternalLink
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

  // Dhan config modal states
  const [dhanConfigOpen, setDhanConfigOpen] = useState(false);
  const [dhanClientId, setDhanClientId] = useState('');
  const [dhanAccessToken, setDhanAccessToken] = useState('');
  const [savingDhan, setSavingDhan] = useState(false);

  const loadProviders = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/providers/sessions`)
      .then(res => setProviders(res.data.providers || []))
      .catch(() => setProviders([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadProviders(); }, [loadProviders]);

  const validateProvider = async (providerType: string) => {
    setValidating(providerType);
    try {
      const res = await axios.post(`${API}/providers/sessions/${providerType}/validate`);
      setProviders(prev => prev.map(p =>
        p.provider_type === providerType ? res.data.provider : p
      ));
    } catch { /* ignore */ }
    finally { setValidating(null); }
  };

  const handleOAuthConnect = async (providerType: string) => {
    try {
      const res = await axios.get(`${API}/providers/sessions/${providerType}/login`);
      const authWindow = window.open(res.data.login_url, `${providerType}_login`, 'width=500,height=700');
      
      const timer = setInterval(() => {
        if (authWindow?.closed) {
          clearInterval(timer);
          loadProviders();
        }
      }, 1000);
    } catch (err: any) {
      alert(`Failed to start ${providerType} connection: ${err.response?.data?.detail || err.message}`);
    }
  };

  const handleDhanSave = async () => {
    if (!dhanClientId || !dhanAccessToken) {
      alert("Both Client ID and Access Token are required."); return;
    }
    setSavingDhan(true);
    try {
      await axios.post(`${API}/providers/sessions/dhanhq/credentials`, {
        credentials: {
          CLIENT_ID: dhanClientId,
          ACCESS_TOKEN: dhanAccessToken
        }
      });
      setDhanConfigOpen(false);
      setDhanClientId('');
      setDhanAccessToken('');
      loadProviders();
    } catch (err: any) {
      alert(`Failed to save DhanHQ credentials: ${err.message}`);
    } finally {
      setSavingDhan(false);
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
        
        {/* Core Settings */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
            <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
                <Settings2 className="w-5 h-5 text-primary" /> Profile & Risk Defaults
            </div>
            <div className="space-y-3">
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Default Drawdown Mode</span>
                    <span className="font-mono">Normal (100%)</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Max Capital @ Risk</span>
                    <span className="font-mono">₹25,000.00</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Artifact Retention</span>
                    <span className="font-mono">30 Days</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Log Verbosity</span>
                    <span className="font-mono">INFO</span>
                </div>
            </div>
            <div className="mt-4 pt-4 border-t border-border">
                <button disabled title="Core Config is managed via backend yaml files in this release." className="w-full py-2 bg-muted text-muted-foreground/50 rounded text-xs uppercase tracking-widest font-bold cursor-not-allowed opacity-60">Edit Core Config (Disabled)</button>
            </div>
        </div>

        {/* Data Providers */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
            <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
                <Plug className="w-5 h-5 text-blue-500" /> Data Providers
            </div>
            <div className="space-y-3">
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Primary End-of-Day</span>
                    <span className="font-mono">CSV Local</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">News & Sentiment</span>
                    <span className="font-mono">MarketAux (Mock)</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Options / Greeks</span>
                    <span className="font-mono text-orange-500">Unconfigured</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Fundamentals</span>
                    <span className="font-mono">AlphaVantage (Mock)</span>
                </div>
            </div>
        </div>

        {/* AI & Diagnostics */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
            <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
                <Cpu className="w-5 h-5 text-purple-500" /> AI & Modules
            </div>
            <div className="space-y-3">
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">AI Workspace Backend</span>
                    <span className="font-mono">Local Placeholder</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Token Limit</span>
                    <span className="font-mono">8192 ctx</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Analysis Families</span>
                    <span className="font-mono">8 Configured</span>
                </div>
            </div>
            <div className="mt-4 pt-4 border-t border-border flex items-center gap-2">
                <Server className="w-4 h-4 text-green-500" /> <span className="text-xs text-muted-foreground">Engine API Config checks healthy</span>
            </div>
        </div>
      </div>

      {/* ─── Provider Authentication & Sessions (Phase 21.x — LIVE) ─── */}
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
              {providers.map(p => (
                <div key={p.provider_type} className="border border-border rounded-lg overflow-hidden">
                  <div className="p-4 bg-muted/20 border-b border-border flex items-center justify-between">
                    <span className="font-semibold">{p.display_name || p.provider_type}</span>
                    <SessionBadge status={p.session_status} />
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
                      <div className="text-[11px] text-muted-foreground bg-muted/30 p-2 rounded">
                        {p.diagnostics_summary}
                      </div>
                    )}
                    {p.error_message && (
                      <div className="text-[11px] text-red-500 bg-red-500/10 p-2 rounded">
                        {p.error_message}
                      </div>
                    )}
                  </div>
                  <div className="p-3 border-t border-border bg-muted/10 flex justify-end gap-2">
                    {p.provider_type === 'zerodha' || p.provider_type === 'upstox' ? (
                      <button
                        onClick={() => handleOAuthConnect(p.provider_type)}
                        title="Open interactive login to safely acquire and save the session token"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-500/10 text-indigo-500 rounded text-xs font-bold uppercase tracking-wider hover:bg-indigo-500/20 transition-colors"
                      >
                        <Plug className="w-3 h-3" /> Connect
                      </button>
                    ) : null}
                    
                    {p.provider_type === 'dhanhq' ? (
                      <button
                        onClick={() => setDhanConfigOpen(true)}
                        title="Update fixed API credentials"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-500/10 text-indigo-500 rounded text-xs font-bold uppercase tracking-wider hover:bg-indigo-500/20 transition-colors"
                      >
                        <Settings2 className="w-3 h-3" /> Config
                      </button>
                    ) : null}

                    <button
                      onClick={() => validateProvider(p.provider_type)}
                      disabled={validating === p.provider_type}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary rounded text-xs font-bold uppercase tracking-wider hover:bg-primary/20 transition-colors disabled:opacity-50"
                    >
                      {validating === p.provider_type ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <RefreshCcw className="w-3 h-3" />
                      )}
                      Validate
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

          {/* Notification quick-link */}
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

      {/* Execution & Broker (DISABLED VISUAL) */}
      <div className="bg-card border border-border rounded-xl p-6 space-y-4 relative overflow-hidden">
          <div className="absolute inset-0 bg-background/50 backdrop-blur-[1px] z-10 flex flex-col items-center justify-center">
              <Lock className="w-8 h-8 text-muted-foreground mb-2" />
              <h3 className="font-bold text-lg text-foreground">Execution Controls Locked</h3>
              <p className="text-sm text-muted-foreground max-w-md text-center">Broker routing, live-safe modes, and automatic strategy deployment are structurally disabled. Provider connections do NOT enable trading.</p>
          </div>
          <div className="opacity-30 relative z-0">
              <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
                  <Shield className="w-5 h-5 text-red-500" /> Live Execution & Brokers (Phase 22+)
              </div>
              <div className="grid grid-cols-3 gap-6">
                  <div className="space-y-3">
                      <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Primary Broker</span>
                          <span className="font-mono text-foreground">Interactive Brokers</span>
                      </div>
                      <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Paper Trading Target</span>
                          <span className="font-mono text-foreground">Local Simulation</span>
                      </div>
                  </div>
                  <div className="space-y-3">
                      <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Smart Order Routing</span>
                          <span className="font-mono text-foreground">VWAP Split</span>
                      </div>
                      <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Live-Safe Mode</span>
                          <span className="font-mono text-foreground uppercase">Enforce</span>
                      </div>
                  </div>
                   <div className="space-y-3">
                      <div className="w-full bg-red-500 text-white rounded p-3 text-center font-bold text-sm">
                          AUTHORIZE DEPLOYMENT
                      </div>
                  </div>
              </div>
          </div>
      </div>

      {/* Dhan Config Modal */}
      {dhanConfigOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="bg-card w-full max-w-md border border-border shadow-lg rounded-xl p-6 relative">
            <button onClick={() => setDhanConfigOpen(false)} className="absolute top-4 right-4 text-muted-foreground hover:text-foreground">
              <XCircle className="w-5 h-5" />
            </button>
            <h3 className="text-xl font-bold mb-4">Configure DhanHQ</h3>
            <p className="text-xs text-muted-foreground mb-6">Enter your static API credentials retrieved from web.dhan.co. These will be saved locally without requiring a restart.</p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold mb-1">CLIENT ID</label>
                <input value={dhanClientId} onChange={e => setDhanClientId(e.target.value)} type="text" className="w-full bg-background border border-border rounded p-2 text-sm focus:outline-none focus:border-primary" placeholder="100..." />
              </div>
              <div>
                <label className="block text-xs font-bold mb-1">ACCESS TOKEN</label>
                <input value={dhanAccessToken} onChange={e => setDhanAccessToken(e.target.value)} type="password" className="w-full bg-background border border-border rounded p-2 text-sm focus:outline-none focus:border-primary" placeholder="eyJ..." />
              </div>
              <div className="pt-2">
                <button onClick={handleDhanSave} disabled={savingDhan} className="w-full bg-primary text-primary-foreground py-2 rounded font-bold transition-colors hover:bg-primary/90 disabled:opacity-50 inline-flex items-center justify-center gap-2">
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
