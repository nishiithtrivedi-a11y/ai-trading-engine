import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  CalendarClock, Clock, BellRing, Play, RefreshCcw, CheckCircle2, XCircle,
  AlertCircle, Timer, Zap, Mail, MessageCircle, Send, ChevronDown,
  ChevronUp, ToggleLeft, ToggleRight, Loader2
} from 'lucide-react';

const API = 'http://localhost:8000/api/v1/automation';

interface ScheduleInfo {
  job_id: string;
  pipeline_type: string;
  name: string;
  description: string;
  enabled: boolean;
  schedule_mode: string;
  schedule_interval_minutes: number | null;
  schedule_daily_time: string | null;
  schedule_timezone: string;
  next_run: string | null;
  last_run: {
    run_id: string;
    status: string;
    started_at: string;
    completed_at: string | null;
    duration_seconds: number | null;
  } | null;
}

interface RunRecord {
  run_id: string;
  job_id: string;
  pipeline_type: string;
  trigger_source: string;
  status: string;
  execution_mode: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  linked_artifacts: string[];
  error_message: string | null;
  error_details: string | null;
}

interface ChannelPref {
  channel_type: string;
  enabled: boolean;
  digest_mode: boolean;
}

interface TypePref {
  notification_type: string;
  enabled: boolean;
  min_severity: string;
}

interface ContactTarget {
  channel_type: string;
  target_value: string;
  label: string;
  enabled: boolean;
}

interface NotifPrefs {
  channels: ChannelPref[];
  types: TypePref[];
  contacts: ContactTarget[];
}

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-green-500',
  running: 'text-blue-500',
  failed: 'text-red-500',
  queued: 'text-yellow-500',
  cancelled: 'text-muted-foreground',
};

const STATUS_BG: Record<string, string> = {
  completed: 'bg-green-500/10 border-green-500/30',
  running: 'bg-blue-500/10 border-blue-500/30',
  failed: 'bg-red-500/10 border-red-500/30',
  queued: 'bg-yellow-500/10 border-yellow-500/30',
  cancelled: 'bg-muted/50 border-border',
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || 'text-muted-foreground';
  const bg = STATUS_BG[status] || 'bg-muted/50 border-border';
  const Icon = status === 'completed' ? CheckCircle2 : status === 'failed' ? XCircle : status === 'running' ? Loader2 : AlertCircle;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-bold uppercase tracking-wider ${color} ${bg}`}>
      <Icon className={`w-3 h-3 ${status === 'running' ? 'animate-spin' : ''}`} />
      {status}
    </span>
  );
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function fmtDuration(sec: number | null | undefined): string {
  if (sec == null) return '—';
  if (sec < 60) return `${sec.toFixed(1)}s`;
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
}

const CHANNEL_LABELS: Record<string, { label: string; icon: typeof Mail }> = {
  email: { label: 'Email', icon: Mail },
  telegram: { label: 'Telegram', icon: Send },
  whatsapp: { label: 'WhatsApp', icon: MessageCircle },
  slack: { label: 'Slack', icon: MessageCircle },
  discord: { label: 'Discord', icon: MessageCircle },
  webhook: { label: 'Webhook', icon: Zap },
};

export function AutomationPage() {
  const [schedules, setSchedules] = useState<ScheduleInfo[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [prefs, setPrefs] = useState<NotifPrefs | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [triggerMessage, setTriggerMessage] = useState<{ type: 'success' | 'error' | 'cooldown'; text: string } | null>(null);
  const [showNotifPanel, setShowNotifPanel] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/schedules`).catch(() => ({ data: { schedules: [] } })),
      axios.get(`${API}/runs?limit=30`).catch(() => ({ data: { runs: [] } })),
      axios.get(`${API}/notification/preferences`).catch(() => ({ data: { preferences: null } })),
    ]).then(([sRes, rRes, pRes]) => {
      setSchedules(sRes.data.schedules || []);
      setRuns(rRes.data.runs || []);
      setPrefs(pRes.data.preferences || null);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const triggerPipeline = async (pipelineType: string) => {
    setTriggering(pipelineType);
    setTriggerMessage(null);
    try {
      await axios.post(`${API}/trigger/${pipelineType}`, { trigger_source: 'manual_ui' });
      setTriggerMessage({ type: 'success', text: `${pipelineType.replace(/_/g, ' ')} triggered successfully.` });
      setTimeout(loadData, 500);
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || 'Trigger failed';
      if (status === 429) {
        setTriggerMessage({ type: 'cooldown', text: `Cooldown active — ${detail}` });
      } else {
        setTriggerMessage({ type: 'error', text: detail });
      }
    } finally {
      setTriggering(null);
      setTimeout(() => setTriggerMessage(null), 8000);
    }
  };

  const savePrefs = async () => {
    if (!prefs) return;
    setSavingPrefs(true);
    try {
      await axios.put(`${API}/notification/preferences`, prefs);
    } catch { /* ignore */ }
    finally { setSavingPrefs(false); }
  };

  const testChannel = async (channelType: string) => {
    setTestResult(null);
    try {
      const res = await axios.post(`${API}/notification/test/${channelType}`);
      setTestResult(res.data.result?.success ? `✅ ${channelType} test sent` : `❌ ${res.data.result?.error_message || 'Failed'}`);
    } catch { setTestResult('❌ Test request failed'); }
    setTimeout(() => setTestResult(null), 5000);
  };

  const toggleChannel = (channelType: string) => {
    if (!prefs) return;
    setPrefs({
      ...prefs,
      channels: prefs.channels.map(c =>
        c.channel_type === channelType ? { ...c, enabled: !c.enabled } : c
      ),
    });
  };

  const toggleType = (notifType: string) => {
    if (!prefs) return;
    setPrefs({
      ...prefs,
      types: prefs.types.map(t =>
        t.notification_type === notifType ? { ...t, enabled: !t.enabled } : t
      ),
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">System Automation & Schedulers</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Recurring pipelines, manual triggers, run history, and notification routing.
          </p>
        </div>
        <button onClick={loadData} className="p-2 rounded-lg hover:bg-muted transition-colors" title="Refresh">
          <RefreshCcw className="w-5 h-5" />
        </button>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading automation data...
        </div>
      ) : (
        <>
          {/* ─── Schedule Dashboard ─── */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-border bg-muted/20 flex items-center gap-2">
              <CalendarClock className="w-5 h-5 text-primary" />
              <h3 className="font-bold text-lg">Pipeline Schedules</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs uppercase bg-muted/50 border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-6 py-3 font-medium">Pipeline</th>
                    <th className="px-6 py-3 font-medium">Schedule</th>
                    <th className="px-6 py-3 font-medium">Last Run</th>
                    <th className="px-6 py-3 font-medium">Next Run</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {schedules.map(s => (
                    <tr key={s.job_id} className="hover:bg-muted/30 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-semibold">{s.name}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">{s.description}</div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="font-mono text-xs">
                          {s.schedule_mode === 'daily' && `Daily ${s.schedule_daily_time} ${s.schedule_timezone}`}
                          {s.schedule_mode === 'interval' && `Every ${s.schedule_interval_minutes}m`}
                          {s.schedule_mode === 'manual' && 'Manual only'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs">
                        {s.last_run ? (
                          <div>
                            <div>{fmtTime(s.last_run.started_at)}</div>
                            <div className="text-muted-foreground">{fmtDuration(s.last_run.duration_seconds)}</div>
                          </div>
                        ) : <span className="text-muted-foreground">Never</span>}
                      </td>
                      <td className="px-6 py-4 text-xs font-mono">
                        {s.next_run ? fmtTime(s.next_run) : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-6 py-4">
                        {s.last_run ? <StatusBadge status={s.last_run.status} /> : (
                          <span className="text-xs text-muted-foreground uppercase tracking-wider">Idle</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => triggerPipeline(s.pipeline_type)}
                          disabled={triggering === s.pipeline_type}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-md text-xs font-bold uppercase tracking-wider hover:bg-primary/90 transition-colors disabled:opacity-50"
                        >
                          {triggering === s.pipeline_type ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <Play className="w-3 h-3" />
                          )}
                          {s.pipeline_type === 'manual_rescan' ? 'Rescan Now' : 'Run'}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {schedules.length === 0 && (
                    <tr><td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">No schedules configured.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ─── Quick Trigger Bar ─── */}
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {[
              { type: 'morning_scan', label: 'Morning Scan', icon: Clock },
              { type: 'intraday_refresh', label: 'Intraday Refresh', icon: RefreshCcw },
              { type: 'manual_rescan', label: 'Rescan Now', icon: Zap },
              { type: 'eod_processing', label: 'EOD Processing', icon: Timer },
            ].map(({ type, label, icon: Icon }) => (
              <button
                key={type}
                onClick={() => triggerPipeline(type)}
                disabled={triggering === type}
                className="flex items-center gap-3 p-4 bg-card border border-border rounded-xl hover:border-primary/50 hover:bg-primary/5 transition-all disabled:opacity-50 group"
              >
                <div className="p-2 bg-primary/10 rounded-lg group-hover:bg-primary/20 transition-colors">
                  <Icon className="w-5 h-5 text-primary" />
                </div>
                <div className="text-left">
                  <div className="font-semibold text-sm">{label}</div>
                  <div className="text-xs text-muted-foreground">Tap to trigger</div>
                </div>
                {triggering === type && <Loader2 className="w-4 h-4 animate-spin ml-auto text-primary" />}
              </button>
            ))}
          </div>

          {/* Trigger feedback banner */}
          {triggerMessage && (
            <div className={`px-4 py-3 rounded-lg border text-sm font-medium flex items-center gap-2 ${
              triggerMessage.type === 'success' ? 'bg-green-500/10 border-green-500/30 text-green-600' :
              triggerMessage.type === 'cooldown' ? 'bg-amber-500/10 border-amber-500/30 text-amber-600' :
              'bg-red-500/10 border-red-500/30 text-red-500'
            }`}>
              {triggerMessage.type === 'success' && <CheckCircle2 className="w-4 h-4" />}
              {triggerMessage.type === 'cooldown' && <Clock className="w-4 h-4" />}
              {triggerMessage.type === 'error' && <XCircle className="w-4 h-4" />}
              {triggerMessage.text}
            </div>
          )}

          {/* ─── Run History ─── */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-border bg-muted/20 flex items-center gap-2">
              <Timer className="w-5 h-5 text-blue-500" />
              <h3 className="font-bold text-lg">Run History</h3>
              <span className="text-xs text-muted-foreground ml-auto">{runs.length} recent runs</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs uppercase bg-muted/50 border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-6 py-3 font-medium">Run ID</th>
                    <th className="px-6 py-3 font-medium">Pipeline</th>
                    <th className="px-6 py-3 font-medium">Trigger</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Started</th>
                    <th className="px-6 py-3 font-medium">Duration</th>
                    <th className="px-6 py-3 font-medium">Mode</th>
                    <th className="px-6 py-3 font-medium">Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {runs.map(r => (
                    <tr key={r.run_id} className="hover:bg-muted/30 transition-colors">
                      <td className="px-6 py-3 font-mono text-xs">{r.run_id}</td>
                      <td className="px-6 py-3 font-semibold text-xs capitalize">{r.pipeline_type.replace(/_/g, ' ')}</td>
                      <td className="px-6 py-3 text-xs text-muted-foreground capitalize">{r.trigger_source.replace(/_/g, ' ')}</td>
                      <td className="px-6 py-3"><StatusBadge status={r.status} /></td>
                      <td className="px-6 py-3 text-xs">{fmtTime(r.started_at)}</td>
                      <td className="px-6 py-3 text-xs font-mono">{fmtDuration(r.duration_seconds)}</td>
                      <td className="px-6 py-3">
                        <span className="text-[10px] px-2 py-0.5 bg-muted rounded uppercase tracking-wider font-bold">
                          {r.execution_mode}
                        </span>
                      </td>
                      <td className="px-6 py-3">
                        {r.status === 'failed' && r.error_message ? (
                          <span className="text-xs text-red-500" title={r.error_details ?? r.error_message}>
                            {r.error_message.length > 60 ? r.error_message.slice(0, 60) + '…' : r.error_message}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {runs.length === 0 && (
                    <tr><td colSpan={8} className="px-6 py-8 text-center text-muted-foreground">No runs recorded yet. Trigger a pipeline above.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ─── Notification Preferences ─── */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setShowNotifPanel(!showNotifPanel)}
              className="w-full px-6 py-4 border-b border-border bg-muted/20 flex items-center gap-2 hover:bg-muted/30 transition-colors"
            >
              <BellRing className="w-5 h-5 text-amber-500" />
              <h3 className="font-bold text-lg">Notification Preferences</h3>
              <span className="ml-auto">
                {showNotifPanel ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </span>
            </button>

            {showNotifPanel && prefs && (
              <div className="p-6 space-y-6">
                {/* Channel Toggles */}
                <div>
                  <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-3">Channels</h4>
                  <div className="grid gap-3 md:grid-cols-3">
                    {prefs.channels.map(ch => {
                      const info = CHANNEL_LABELS[ch.channel_type] || { label: ch.channel_type, icon: BellRing };
                      const ChIcon = info.icon;
                      const isPlaceholder = ['whatsapp', 'slack', 'discord', 'webhook'].includes(ch.channel_type);
                      return (
                        <div key={ch.channel_type} className={`flex items-center justify-between p-3 border rounded-lg transition-colors ${ch.enabled ? 'border-primary/30 bg-primary/5' : 'border-border bg-muted/10'} ${isPlaceholder ? 'opacity-50' : ''}`}>
                          <div className="flex items-center gap-2">
                            <ChIcon className="w-4 h-4" />
                            <span className="text-sm font-medium">{info.label}</span>
                            {isPlaceholder && <span className="text-[9px] px-1.5 py-0.5 bg-muted rounded uppercase tracking-wider font-bold">Soon</span>}
                          </div>
                          <button onClick={() => toggleChannel(ch.channel_type)} disabled={isPlaceholder}>
                            {ch.enabled ? <ToggleRight className="w-6 h-6 text-primary" /> : <ToggleLeft className="w-6 h-6 text-muted-foreground" />}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Notification Type Toggles */}
                <div>
                  <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-3">Alert Types</h4>
                  <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                    {prefs.types.map(tp => (
                      <div key={tp.notification_type} className="flex items-center justify-between p-2.5 border border-border rounded-lg">
                        <span className="text-xs font-medium capitalize">{tp.notification_type.replace(/_/g, ' ')}</span>
                        <button onClick={() => toggleType(tp.notification_type)}>
                          {tp.enabled ? <ToggleRight className="w-5 h-5 text-primary" /> : <ToggleLeft className="w-5 h-5 text-muted-foreground" />}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Contact Targets */}
                <div>
                  <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-3">Contact Targets</h4>
                  {prefs.contacts.length > 0 ? (
                    <div className="space-y-2">
                      {prefs.contacts.map((ct, i) => (
                        <div key={i} className="flex items-center justify-between p-3 border border-border rounded-lg bg-muted/10">
                          <div>
                            <div className="text-sm font-medium capitalize">{ct.channel_type}: {ct.label || ct.target_value}</div>
                            <div className="text-xs text-muted-foreground font-mono">{ct.target_value}</div>
                          </div>
                          <span className={`text-[10px] px-2 py-0.5 rounded uppercase tracking-wider font-bold ${ct.enabled ? 'bg-green-500/20 text-green-600' : 'bg-muted text-muted-foreground'}`}>
                            {ct.enabled ? 'Active' : 'Disabled'}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground p-4 border border-dashed border-border rounded-lg text-center">
                      No contact targets configured. Add targets via the Settings page or API.
                    </div>
                  )}
                </div>

                {/* Action bar */}
                <div className="flex items-center gap-3 pt-4 border-t border-border">
                  <button
                    onClick={savePrefs}
                    disabled={savingPrefs}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-xs font-bold uppercase tracking-wider hover:bg-primary/90 transition-colors disabled:opacity-50"
                  >
                    {savingPrefs ? 'Saving…' : 'Save Preferences'}
                  </button>
                  <button
                    onClick={() => testChannel('email')}
                    className="px-4 py-2 bg-muted rounded-md text-xs font-bold uppercase tracking-wider hover:bg-muted/80 transition-colors"
                  >
                    Test Email
                  </button>
                  <button
                    onClick={() => testChannel('telegram')}
                    className="px-4 py-2 bg-muted rounded-md text-xs font-bold uppercase tracking-wider hover:bg-muted/80 transition-colors"
                  >
                    Test Telegram
                  </button>
                  {testResult && (
                    <span className="text-xs ml-2">{testResult}</span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ─── Safety Notice ─── */}
          <div className="bg-green-500/5 border border-green-500/20 rounded-xl p-4 flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-green-500 mt-0.5 shrink-0" />
            <div>
              <div className="text-sm font-semibold text-green-600">Execution Disabled — Safe Automation Only</div>
              <div className="text-xs text-muted-foreground mt-1">
                All pipelines run in research/paper/live-safe mode. No broker orders are placed.
                Notifications are outbound-only — no trade approval or execution via messaging channels.
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
