import { Shield, Server, Plug, Settings2, Cpu, Lock } from 'lucide-react';

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">System Control Room</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Configuration matrices, provider connections, and system limits (Read-Only).
          </p>
          <div className="mt-2 text-xs font-semibold text-orange-500 bg-orange-500/10 inline-block px-2 py-1 rounded">
             <Shield className="w-3 h-3 inline mr-1" />
             Read-Only View: Engine parameters and provider configs are file-driven in Phase 20.
          </div>
        </div>
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
                <button disabled className="w-full py-2 bg-muted text-muted-foreground/50 rounded text-xs uppercase tracking-widest font-bold cursor-not-allowed">Edit Core Config (Disabled)</button>
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
            <div className="mt-4 pt-4 border-t border-border">
                <button disabled className="w-full py-2 bg-muted text-muted-foreground/50 rounded text-xs uppercase tracking-widest font-bold cursor-not-allowed">Manage Providers (Disabled)</button>
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

        {/* New Phase 21+ Provider Connections Placeholder */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-4 md:col-span-2 lg:col-span-3 opacity-60">
            <div className="flex items-center gap-2 font-bold mb-4 border-b border-border pb-2">
                <Plug className="w-5 h-5 text-indigo-500" /> Provider Authentication & Sessions (Phase 21+)
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Broker Connections */}
                <div className="space-y-4">
                    <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Broker Connectors</h4>
                    <div className="space-y-3">
                        <div className="flex items-center justify-between p-3 border border-border bg-muted/20 rounded-md">
                            <span className="text-sm font-semibold">Zerodha Kite</span>
                            <span className="text-xs px-2 py-0.5 bg-muted text-muted-foreground rounded uppercase tracking-wider font-bold">Unlinked</span>
                        </div>
                        <div className="flex items-center justify-between p-3 border border-border bg-muted/20 rounded-md">
                            <span className="text-sm font-semibold">DhanHQ</span>
                            <span className="text-xs px-2 py-0.5 bg-muted text-muted-foreground rounded uppercase tracking-wider font-bold">Unlinked</span>
                        </div>
                        <div className="flex items-center justify-between p-3 border border-border bg-muted/20 rounded-md">
                            <span className="text-sm font-semibold">Upstox</span>
                            <span className="text-xs px-2 py-0.5 bg-muted text-muted-foreground rounded uppercase tracking-wider font-bold">Unlinked</span>
                        </div>
                    </div>
                </div>

                {/* API Keys */}
                <div className="space-y-4">
                    <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Data APIs</h4>
                    <div className="space-y-3">
                        <div className="flex items-center justify-between p-3 border border-border bg-muted/20 rounded-md">
                            <span className="text-sm font-semibold">Financial Modeling Prep</span>
                            <span className="text-xs px-2 py-0.5 bg-muted text-muted-foreground rounded uppercase tracking-wider font-bold">Missing Key</span>
                        </div>
                        <div className="flex items-center justify-between p-3 border border-border bg-muted/20 rounded-md">
                            <span className="text-sm font-semibold">Alpha Vantage</span>
                            <span className="text-xs px-2 py-0.5 bg-muted text-muted-foreground rounded uppercase tracking-wider font-bold">Missing Key</span>
                        </div>
                        <div className="flex items-center justify-between p-3 border border-border bg-muted/20 rounded-md">
                            <span className="text-sm font-semibold">Finnhub / EODHD</span>
                            <span className="text-xs px-2 py-0.5 bg-muted text-muted-foreground rounded uppercase tracking-wider font-bold">Missing Key</span>
                        </div>
                    </div>
                </div>

                {/* Local & Derived */}
                <div className="space-y-4">
                    <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Local & Static</h4>
                    <div className="space-y-3">
                        <div className="flex items-center justify-between p-3 border border-border bg-green-500/10 border-green-500/20 rounded-md">
                            <span className="text-sm font-semibold text-green-500">CSV Local Directory</span>
                            <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-600 rounded uppercase tracking-wider font-bold cursor-help" title="No Auth Required">Active</span>
                        </div>
                        <div className="flex items-center justify-between p-3 border border-border bg-green-500/10 border-green-500/20 rounded-md">
                            <span className="text-sm font-semibold text-green-500">Indian Option CSV</span>
                            <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-600 rounded uppercase tracking-wider font-bold cursor-help" title="No Auth Required">Active</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div className="mt-4 pt-4 border-t border-border">
                <button disabled className="w-full py-2 bg-muted text-muted-foreground/50 rounded text-xs uppercase tracking-widest font-bold cursor-not-allowed">Add Connection (Disabled)</button>
            </div>
        </div>

        {/* Execution & Broker (DISABLED VISUAL) */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-4 relative overflow-hidden md:col-span-2 lg:col-span-3">
            <div className="absolute inset-0 bg-background/50 backdrop-blur-[1px] z-10 flex flex-col items-center justify-center">
                <Lock className="w-8 h-8 text-muted-foreground mb-2" />
                <h3 className="font-bold text-lg text-foreground">Execution Controls Locked</h3>
                <p className="text-sm text-muted-foreground max-w-md text-center">Broker routing, live-safe modes, and automatic strategy deployment are structurally disabled in the Phase 20 dashboard.</p>
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

      </div>
    </div>
  );
}
