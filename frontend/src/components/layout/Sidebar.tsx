
import { NavLink } from 'react-router-dom';
import { 
  BarChart2, 
  Activity, 
  Target, 
  Briefcase, 
  Settings, 
  Search,
  Database,
  Terminal,
  Cpu,
  TrendingUp,
  LineChart
} from 'lucide-react';
import { cn } from '@/lib/utils';

export function Sidebar() {
  const routes = [
    { name: 'Overview', path: '/', icon: BarChart2 },
    { name: 'Scanner', path: '/scanner', icon: Search },
    { name: 'Monitoring', path: '/monitoring', icon: Activity },
    { name: 'Decision & Portfolio', path: '/decision', icon: Target },
    { name: 'Derivatives', path: '/derivatives', icon: LineChart },
    { name: 'Paper Trading', path: '/paper', icon: Briefcase },
    { name: 'Diagnostics', path: '/diagnostics', icon: Database },
    { name: 'Profiles & Modules', path: '/profiles', icon: Cpu },
    { name: 'Logs & Validation', path: '/logs', icon: Terminal },
    { name: 'AI Workspace', path: '/ai', icon: TrendingUp },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  return (
    <div className="w-64 bg-card border-r border-border h-full flex flex-col">
      <div className="p-4 border-b border-border flex items-center space-x-2">
        <div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center text-primary font-bold">
          AI
        </div>
        <div>
          <h1 className="text-sm font-semibold">TCC Engine</h1>
          <p className="text-xs text-muted-foreground">Command Center</p>
        </div>
      </div>
      <div className="flex-1 py-4 flex flex-col gap-1 px-2 overflow-y-auto">
        {routes.map((route) => (
          <NavLink
            key={route.path}
            to={route.path}
            className={({ isActive }) =>
              cn(
                "flex items-center space-x-3 px-3 py-2 text-sm rounded-md transition-colors",
                isActive 
                  ? "bg-primary/10 text-primary font-medium" 
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )
            }
          >
            <route.icon className="w-4 h-4" />
            <span>{route.name}</span>
          </NavLink>
        ))}
      </div>
    </div>
  );
}
