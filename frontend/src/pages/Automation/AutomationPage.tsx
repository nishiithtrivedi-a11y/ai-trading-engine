import { CalendarClock, Clock, BellRing } from 'lucide-react';

export function AutomationPage() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">System Automation & Schedulers</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Recurring pipelines, event-driven workflows, and notification routing.
          </p>
        </div>
      </div>

      <div className="bg-primary/5 border border-primary/20 rounded-xl p-6 flex flex-col items-center justify-center text-center space-y-4">
          <CalendarClock className="w-12 h-12 text-primary" />
          <div>
              <h3 className="text-lg font-bold text-primary">Scheduled for Phase 21</h3>
              <p className="text-muted-foreground text-sm max-w-lg mt-1 mx-auto">
                  The automation engine is planned for Phase 21. Currently, all analysis pipelines must be executed manually via the command line or the "Run Pipeline" placeholder.
              </p>
          </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 opacity-50 select-none grayscale cursor-not-allowed">
          
          <div className="bg-card border border-border rounded-xl overflow-hidden flex flex-col">
              <div className="p-4 border-b border-border bg-muted/20 flex gap-2 items-center">
                  <Clock className="w-5 h-5" />
                  <h3 className="font-bold">Cron Workflows</h3>
              </div>
              <div className="p-6 space-y-4 text-sm flex-1">
                  <div className="flex items-center justify-between p-3 border border-border rounded bg-background">
                      <div className="font-medium">Market Open Scan</div>
                      <div className="font-mono text-muted-foreground">09:15 AM EST</div>
                  </div>
                  <div className="flex items-center justify-between p-3 border border-border rounded bg-background">
                      <div className="font-medium">End of Day Aggregation</div>
                      <div className="font-mono text-muted-foreground">16:05 PM EST</div>
                  </div>
                  <div className="flex items-center justify-between p-3 border border-border rounded bg-background">
                      <div className="font-medium">Weekly Profile Rebalance</div>
                      <div className="font-mono text-muted-foreground">FRI 17:00 PM EST</div>
                  </div>
              </div>
              <div className="bg-background border-t border-border p-4 flex justify-end">
                   <div className="px-4 py-1.5 bg-muted rounded text-xs font-bold uppercase tracking-widest text-muted-foreground cursor-not-allowed opacity-50">Add Cron</div>
              </div>
          </div>

          <div className="bg-card border border-border rounded-xl overflow-hidden flex flex-col">
              <div className="p-4 border-b border-border bg-muted/20 flex gap-2 items-center">
                  <BellRing className="w-5 h-5" />
                  <h3 className="font-bold">Notification Routing</h3>
              </div>
              <div className="p-6 space-y-4 text-sm flex-1">
                  <div className="flex items-center justify-between p-3 border border-border rounded bg-background">
                      <div className="font-medium">Drawdown Exceeded Alert</div>
                      <div className="font-mono text-muted-foreground">Slack / SMS</div>
                  </div>
                  <div className="flex items-center justify-between p-3 border border-border rounded bg-background">
                      <div className="font-medium">Provider Disconnect</div>
                      <div className="font-mono text-muted-foreground">Email</div>
                  </div>
              </div>
              <div className="bg-background border-t border-border p-4 flex justify-end">
                   <div className="px-4 py-1.5 bg-muted rounded text-xs font-bold uppercase tracking-widest text-muted-foreground cursor-not-allowed opacity-50">Add Rule</div>
              </div>
          </div>
      </div>
      
    </div>
  );
}
