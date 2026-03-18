export function StatusStrip() {
  return (
    <div className="h-8 border-t border-border bg-card flex items-center justify-between px-4 text-xs font-mono text-muted-foreground z-20 relative shadow-[0_-2px_10px_rgba(0,0,0,0.1)]">
      <div className="flex items-center space-x-4">
        <span className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-yellow-500 shadow-[0_0_5px_rgba(234,179,8,0.5)]"></span>
          <span className="font-bold text-yellow-500/90 tracking-widest uppercase text-[10px]">Paper Active</span>
        </span>
        <span className="opacity-30">|</span>
        <span className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.5)]"></span>
          <span className="font-bold text-red-500/90 tracking-widest uppercase text-[10px]">Execute Locked</span>
        </span>
        <span className="opacity-30 hidden md:inline">|</span>
        <span className="hidden md:flex items-center space-x-2 text-[10px] uppercase font-sans font-bold tracking-widest text-primary/70">
            <span>Concentration: &lt;15% per sector</span>
        </span>
      </div>
      <div className="flex items-center space-x-4">
        <span className="hidden lg:inline text-[10px] uppercase tracking-widest opacity-50">Local Engine • Port: 8000</span>
        <span className="font-bold tracking-wider text-primary/50">Vite SPA • Phase 20B</span>
      </div>
    </div>
  );
}
