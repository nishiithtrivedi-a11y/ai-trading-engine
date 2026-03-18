import { Shield, Activity, TrendingUp, Layers, HelpCircle } from 'lucide-react';

interface AnalysisBadgeProps {
  family: string;
  score?: number;
  provider?: string;
  freshness?: string;
  contribution?: string;
}

export function AnalysisBadge({ family, score, provider, freshness, contribution }: AnalysisBadgeProps) {
  const getFamilyStyles = () => {
    switch (family) {
      case 'technical': return { icon: <TrendingUp className="w-3.5 h-3.5" />, color: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20' };
      case 'quant': return { icon: <Activity className="w-3.5 h-3.5" />, color: 'text-purple-500', bg: 'bg-purple-500/10', border: 'border-purple-500/20' };
      case 'fundamental': return { icon: <Shield className="w-3.5 h-3.5" />, color: 'text-green-500', bg: 'bg-green-500/10', border: 'border-green-500/20' };
      case 'macro': return { icon: <Layers className="w-3.5 h-3.5" />, color: 'text-orange-500', bg: 'bg-orange-500/10', border: 'border-orange-500/20' };
      case 'sentiment': return { icon: <Layers className="w-3.5 h-3.5" />, color: 'text-pink-500', bg: 'bg-pink-500/10', border: 'border-pink-500/20' };
      case 'intermarket': return { icon: <Layers className="w-3.5 h-3.5" />, color: 'text-teal-500', bg: 'bg-teal-500/10', border: 'border-teal-500/20' };
      case 'futures': return { icon: <Layers className="w-3.5 h-3.5" />, color: 'text-indigo-500', bg: 'bg-indigo-500/10', border: 'border-indigo-500/20' };
      case 'options': return { icon: <Layers className="w-3.5 h-3.5" />, color: 'text-sky-500', bg: 'bg-sky-500/10', border: 'border-sky-500/20' };
      default: return { icon: <HelpCircle className="w-3.5 h-3.5" />, color: 'text-muted-foreground', bg: 'bg-muted', border: 'border-border' };
    }
  };

  const style = getFamilyStyles();

  return (
    <div className={`group relative inline-flex items-center gap-1.5 px-2.5 py-1 rounded border ${style.bg} ${style.border} ${style.color} text-[10px] font-bold uppercase tracking-wider cursor-help`}>
      {style.icon}
      <span>{family}</span>
      {score !== undefined && (
        <span className={`ml-1 pl-1.5 border-l ${style.border} opacity-80`}>
          {score.toFixed(2)}
        </span>
      )}

      {/* Tooltip on Hover */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-3 bg-card border border-border shadow-lg rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 text-foreground font-sans normal-case tracking-normal">
          <div className="font-bold border-b border-border pb-1 mb-2 capitalize">{family} Family</div>
          <div className="space-y-1 text-xs text-muted-foreground">
              {score !== undefined && <div className="flex justify-between"><span>Score:</span> <span className="font-mono text-foreground">{score.toFixed(2)}</span></div>}
              {provider && <div className="flex justify-between"><span>Source:</span> <span className="font-mono text-foreground truncate ml-2">{provider}</span></div>}
              {freshness && <div className="flex justify-between"><span>Freshness:</span> <span className="font-mono text-foreground">{freshness}</span></div>}
              {contribution && <div className="flex justify-between"><span>Weight:</span> <span className="font-mono text-foreground text-primary">{contribution}</span></div>}
          </div>
      </div>
    </div>
  );
}
