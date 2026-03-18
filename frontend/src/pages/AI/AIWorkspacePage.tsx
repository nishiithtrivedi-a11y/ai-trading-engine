import { useState, useEffect } from 'react';
import axios from 'axios';
import { Send, Bot, AlertTriangle, ShieldCheck, FileText, BarChart3, Settings2, FileJson, RefreshCw } from 'lucide-react';

export function AIWorkspacePage() {
  const [prompt, setPrompt] = useState('');
  const [chatHistory, setChatHistory] = useState<{role: 'user'|'assistant', content: string}[]>([]);
  const [selectedContext, setSelectedContext] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Ping to wake up or check status implicitly
    axios.get('http://localhost:8000/api/v1/ai/status')
      .catch(console.error);
  }, []);

  const handleSend = async () => {
    if (!prompt.trim()) return;
    
    const userMsg = prompt;
    setPrompt('');
    setChatHistory(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const res = await axios.post('http://localhost:8000/api/v1/ai/prompt', {
        prompt: userMsg,
        context_sources: selectedContext
      });
      setChatHistory(prev => [...prev, { role: 'assistant', content: res.data.response }]);
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'assistant', content: 'Error reaching AI backend.' }]);
    } finally {
      setLoading(false);
    }
  };

  const toggleContext = (ctx: string) => {
    setSelectedContext(prev => prev.includes(ctx) ? prev.filter(c => c !== ctx) : [...prev, ctx]);
  };

  const CONTEXT_SOURCES = [
    { id: 'scanner', label: 'Scanner Results', icon: <BarChart3 className="w-4 h-4" /> },
    { id: 'decision', label: 'Decision Logic', icon: <Settings2 className="w-4 h-4" /> },
    { id: 'portfolio', label: 'Portfolio Plan', icon: <FileText className="w-4 h-4" /> },
    { id: 'paper', label: 'Paper Account', icon: <ShieldCheck className="w-4 h-4" /> },
    { id: 'logs', label: 'Engine Logs', icon: <FileJson className="w-4 h-4" /> }
  ];

  return (
    <div className="h-[calc(100vh-8rem)] flex gap-4">
      {/* LEFT: Prompt / Chat Panel */}
      <div className="w-1/3 bg-card border border-border rounded-xl flex flex-col overflow-hidden">
        <div className="p-4 border-b border-border bg-muted/20 flex justify-between items-center">
            <h3 className="font-bold flex items-center gap-2"><Bot className="w-5 h-5 text-primary" /> Assistant Chat</h3>
            <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full bg-orange-500/10 text-orange-400 border border-orange-500/20 font-bold flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Offline Placeholder
            </span>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="bg-primary/5 border border-primary/20 text-primary p-3 rounded-lg text-sm">
                System: Local simulation active. AI recommendations are advisory and cannot execute trades.
            </div>
            {chatHistory.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] p-3 rounded-lg text-sm whitespace-pre-wrap ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground border border-border'}`}>
                        {msg.content}
                    </div>
                </div>
            ))}
            {loading && (
                <div className="flex justify-start">
                    <div className="bg-muted text-muted-foreground p-3 rounded-lg text-sm flex items-center gap-2 border border-border"><RefreshCw className="w-4 h-4 animate-spin" /> Thinking...</div>
                </div>
            )}
        </div>

        <div className="p-4 border-t border-border bg-background">
            <div className="flex gap-2">
                <textarea 
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Ask for analysis, explain a trade..."
                    className="flex-1 bg-muted border border-border rounded-md p-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary min-h-[40px] max-h-[120px] resize-none"
                    onKeyDown={(e) => { if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                />
                <button 
                  onClick={handleSend}
                  disabled={loading || !prompt.trim()}
                  className="bg-primary hover:bg-primary/90 text-primary-foreground p-2 rounded-md flex items-center justify-center disabled:opacity-50 transition-colors"
                >
                    <Send className="w-5 h-5" />
                </button>
            </div>
        </div>
      </div>

      {/* CENTER: Output Workspace */}
      <div className="w-1/3 bg-card border border-border rounded-xl flex flex-col overflow-hidden relative">
          <div className="absolute inset-0 pointer-events-none border-[3px] border-dashed border-red-500/20 rounded-xl z-0"></div>
          <div className="p-4 border-b border-border bg-muted/20 z-10">
              <h3 className="font-bold flex items-center gap-2">Analysis Workspace</h3>
          </div>
          <div className="flex-1 p-6 relative z-10 flex flex-col items-center justify-center text-center space-y-4">
             <ShieldCheck className="w-12 h-12 text-muted-foreground/30" />
             <div>
                <h4 className="text-lg font-bold text-muted-foreground">Execution Separation Boundary</h4>
                <p className="text-sm text-muted-foreground mt-2 max-w-[250px] mx-auto">
                    The AI acts strictly as an analysis and reporting layer. It has zero authority to deploy strategies or execute live broker orders.
                </p>
             </div>
             
             <div className="w-full mt-8 text-left space-y-2">
                 <div className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">Presets</div>
                 <button className="w-full p-2 bg-muted/30 hover:bg-muted text-sm border border-border rounded text-left transition-colors">Generate EOD Summary Report</button>
                 <button className="w-full p-2 bg-muted/30 hover:bg-muted text-sm border border-border rounded text-left transition-colors">Explain Top Rejected Candidates</button>
                 <button className="w-full p-2 bg-muted/30 hover:bg-muted text-sm border border-border rounded text-left transition-colors">Audit Risk Exposure Constraints</button>
             </div>
          </div>
      </div>

      {/* RIGHT: Context Selection */}
      <div className="w-1/3 bg-card border border-border rounded-xl flex flex-col overflow-hidden">
        <div className="p-4 border-b border-border bg-muted/20">
            <h3 className="font-bold">Context Payload</h3>
            <p className="text-xs text-muted-foreground mt-1">Select state trees to inject into prompt.</p>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {CONTEXT_SOURCES.map(ctx => (
                <div key={ctx.id} 
                     onClick={() => toggleContext(ctx.id)}
                     className={`p-3 rounded-lg border cursor-pointer flex items-center justify-between transition-colors ${selectedContext.includes(ctx.id) ? 'bg-primary/10 border-primary/30 text-primary' : 'bg-background hover:bg-muted border-border text-foreground'}`}>
                    <div className="flex items-center gap-3">
                        <div className="p-1.5 rounded-md bg-muted/50">{ctx.icon}</div>
                        <span className="text-sm font-semibold">{ctx.label}</span>
                    </div>
                    <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${selectedContext.includes(ctx.id) ? 'bg-primary border-primary' : 'border-border'}`}>
                        {selectedContext.includes(ctx.id) && <div className="w-2 h-2 bg-primary-foreground rounded-full"></div>}
                    </div>
                </div>
            ))}
        </div>
      </div>
    </div>
  );
}
