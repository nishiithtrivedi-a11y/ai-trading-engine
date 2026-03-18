import { useEffect, useState } from 'react';
import axios from 'axios';
import { Layers, Check, X, Shield, Activity, TrendingUp, Settings2 } from 'lucide-react';

export function ProfilesPage() {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/profiles/')
      .then(res => setProfiles(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  const familyIcons: any = {
      technical: <TrendingUp className="w-4 h-4 text-blue-500" />,
      quant: <Activity className="w-4 h-4 text-purple-500" />,
      fundamental: <Shield className="w-4 h-4 text-green-500" />,
      macro: <Layers className="w-4 h-4 text-orange-500" />,
      sentiment: <Layers className="w-4 h-4 text-pink-500" />,
      intermarket: <Layers className="w-4 h-4 text-teal-500" />,
      futures: <Layers className="w-4 h-4 text-indigo-500" />,
      options: <Layers className="w-4 h-4 text-sky-500" />,
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Profiles & Analysis Modules</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Engine configurations and active strategy module mappings.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">Loading profiles schema...</div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {profiles.map((p, i) => (
                <div key={i} className="bg-card border border-border rounded-xl flex flex-col overflow-hidden hover:border-primary/50 transition-colors">
                    <div className="p-5 border-b border-border bg-muted/10 h-32 flex flex-col justify-between">
                        <div>
                            <div className="flex items-center gap-2 mb-2">
                                <Settings2 className="w-5 h-5 text-primary" />
                                <h3 className="font-bold text-lg leading-tight w-full truncate">{p.id}</h3>
                            </div>
                            <p className="text-xs text-muted-foreground line-clamp-2">{p.description}</p>
                        </div>
                    </div>
                    
                    <div className="p-5 flex-1 space-y-4">
                        <div>
                            <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-3">Enabled Families</div>
                            <div className="flex flex-wrap gap-2">
                                {p.enabled_families.map((f: string) => (
                                    <span key={f} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20 capitalize">
                                        {familyIcons[f] || <Layers className="w-3 h-3" />}
                                        {f}
                                    </span>
                                ))}
                                {p.enabled_families.length === 0 && <span className="text-xs text-muted-foreground italic">None active</span>}
                            </div>
                        </div>

                        <div>
                            <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-3">Coverage Matrix</div>
                            <div className="grid grid-cols-2 gap-y-2 text-xs">
                                {Object.entries(p.coverage).slice(0, 8).map(([family, isActive]) => (
                                    <div key={family} className="flex items-center gap-2 capitalize">
                                        {isActive ? (
                                            <Check className="w-3.5 h-3.5 text-green-500" />
                                        ) : (
                                            <X className="w-3.5 h-3.5 text-muted-foreground/30" />
                                        )}
                                        <span className={isActive ? "text-foreground font-medium" : "text-muted-foreground/50"}>{family}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                    
                    <div className="px-5 py-3 bg-muted/20 border-t border-border flex justify-between items-center text-xs text-muted-foreground">
                        <span className="truncate w-1/2">Req: {p.dependencies.join(', ')}</span>
                        <span className="font-bold truncate text-right w-1/2">{p.asset_classes.join(', ')}</span>
                    </div>
                </div>
            ))}
        </div>
      )}
    </div>
  );
}
