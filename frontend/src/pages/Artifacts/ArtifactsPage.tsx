import { useEffect, useState } from 'react';
import axios from 'axios';
import { Folder, FileJson, FileText, FileSpreadsheet, ChevronRight, Download } from 'lucide-react';

export function ArtifactsPage() {
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  
  const [treeData, setTreeData] = useState<any>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    axios.get('http://localhost:8000/api/v1/artifacts/runs')
      .then(res => setRuns(res.data))
      .catch(err => console.error(err));
  }, []);

  const handleSelectRun = (phase: string, runId: string | null) => {
    setSelectedPhase(phase);
    setSelectedRunId(runId);
    setSelectedFile(null);
    setPreviewData(null);
    axios.get(`http://localhost:8000/api/v1/artifacts/tree?phase=${phase}${runId ? `&run_id=${runId}` : ''}`)
      .then(res => setTreeData(res.data))
      .catch(err => console.error(err));
  };

  const handleSelectFile = (path: string) => {
    setSelectedFile(path);
    setPreviewLoading(true);
    axios.get(`http://localhost:8000/api/v1/artifacts/preview?phase=${selectedPhase}&path=${path}${selectedRunId ? `&run_id=${selectedRunId}` : ''}`)
      .then(res => setPreviewData(res.data))
      .catch(err => {
         console.error(err);
         setPreviewData({ type: 'text', content: 'Failed to load preview or file is too large.' });
      })
      .finally(() => setPreviewLoading(false));
  };

  const getFileIcon = (ext: string) => {
      switch(ext) {
          case '.json': return <FileJson className="w-4 h-4 text-yellow-500" />;
          case '.csv': return <FileSpreadsheet className="w-4 h-4 text-green-500" />;
          case '.md': return <FileText className="w-4 h-4 text-blue-500" />;
          default: return <FileText className="w-4 h-4 text-muted-foreground" />;
      }
  };

  return (
    <div className="space-y-6 h-full flex flex-col">
      <div className="flex justify-between items-center shrink-0">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Manifest & Artifact Explorer</h2>
          <p className="text-muted-foreground mt-1 text-sm">
             Browse output directories, validate schemas, and inspect raw pipeline artifacts.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 flex-1 min-h-[600px]">
          {/* Runs Sidebar */}
          <div className="bg-card border border-border rounded-xl flex flex-col overflow-hidden">
             <div className="p-4 border-b border-border bg-muted/20 font-semibold">Run History</div>
             <div className="overflow-y-auto flex-1 p-2 space-y-1">
                 {runs.map((run, i) => (
                     <div key={i} className="space-y-1">
                         <div 
                            className={`p-2 text-sm font-medium rounded-lg cursor-pointer flex items-center justify-between ${selectedPhase === run.phase && !selectedRunId ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
                            onClick={() => handleSelectRun(run.phase, null)}
                         >
                             <div className="flex items-center gap-2">
                                <Folder className="w-4 h-4" />
                                <span className="truncate w-32">{run.phase}</span>
                             </div>
                             {run.all_runs.length === 0 && <ChevronRight className="w-4 h-4 opacity-50"/>}
                         </div>
                         {run.all_runs.map((rid: string) => (
                             <div 
                                key={rid} 
                                className={`ml-6 p-2 text-xs rounded-lg cursor-pointer flex items-center gap-2 ${selectedPhase === run.phase && selectedRunId === rid ? 'bg-primary text-primary-foreground' : 'hover:bg-muted text-muted-foreground'}`}
                                onClick={() => handleSelectRun(run.phase, rid)}
                             >
                                 <Folder className="w-3 h-3" />
                                 <span className="truncate">{rid}</span>
                             </div>
                         ))}
                     </div>
                 ))}
                 {runs.length === 0 && <div className="p-4 text-center text-sm text-muted-foreground">No outputs found.</div>}
             </div>
          </div>

          {/* File Tree */}
          <div className="bg-card border border-border rounded-xl flex flex-col overflow-hidden">
             <div className="p-4 border-b border-border bg-muted/20 font-semibold">Artifact Tree</div>
             <div className="overflow-y-auto flex-1 p-2 space-y-1">
                 {!treeData ? (
                     <div className="p-4 text-center text-sm text-muted-foreground">Select a run directory.</div>
                 ) : treeData.files.length === 0 ? (
                     <div className="p-4 text-center text-sm text-muted-foreground">No files in directory.</div>
                 ) : (
                     treeData.files.map((f: any, i: number) => (
                         <div 
                            key={i}
                            className={`p-2 text-sm rounded-lg cursor-pointer flex items-center justify-between group ${selectedFile === f.path ? 'bg-muted border border-border' : 'hover:bg-muted/50 border border-transparent'}`}
                            onClick={() => handleSelectFile(f.path)}
                         >
                             <div className="flex items-center gap-2 truncate w-40">
                                {getFileIcon(f.extension)}
                                <span className="truncate">{f.name}</span>
                             </div>
                             <span className="text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">{(f.size_bytes / 1024).toFixed(1)}kb</span>
                         </div>
                     ))
                 )}
             </div>
          </div>

          {/* Preview Panel */}
          <div className="md:col-span-2 bg-card border border-border rounded-xl flex flex-col overflow-hidden">
             <div className="p-4 border-b border-border bg-muted/20 font-semibold flex justify-between items-center">
                 <span>Preview {selectedFile ? `- ${selectedFile}` : ''}</span>
                 {selectedFile && <button className="p-1 hover:bg-muted rounded"><Download className="w-4 h-4 text-muted-foreground"/></button>}
             </div>
             <div className="overflow-y-auto flex-1 p-4 bg-muted/5 font-mono text-sm relative">
                 {previewLoading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10">Loading...</div>}
                 
                 {!selectedFile && !treeData?.manifest_preview ? (
                     <div className="h-full flex items-center justify-center text-muted-foreground opacity-50">Select a file to preview.</div>
                 ) : !selectedFile && treeData?.manifest_preview ? (
                     <div>
                         <div className="text-xs text-muted-foreground mb-4 uppercase tracking-wider font-sans font-bold">Root Manifest Summary</div>
                         <pre className="whitespace-pre-wrap text-green-400 bg-background p-4 rounded-lg border border-border">
                             {JSON.stringify(treeData.manifest_preview, null, 2)}
                         </pre>
                     </div>
                 ) : previewData?.type === 'json' ? (
                     <pre className="whitespace-pre-wrap text-yellow-500/90">{JSON.stringify(previewData.content, null, 2)}</pre>
                 ) : previewData?.type === 'csv' ? (
                     <div className="overflow-x-auto text-xs font-sans">
                         <table className="w-full text-left">
                             <thead className="bg-muted/50 border-b border-border">
                                 <tr>
                                     {previewData.content[0] && Object.keys(previewData.content[0]).map(k => (
                                         <th key={k} className="px-3 py-2 font-medium">{k}</th>
                                     ))}
                                 </tr>
                             </thead>
                             <tbody className="divide-y divide-border">
                                 {previewData.content.slice(0, 100).map((row: any, i: number) => (
                                     <tr key={i} className="hover:bg-muted/20">
                                         {Object.values(row).map((val: any, j: number) => (
                                             <td key={j} className="px-3 py-2 truncate max-w-[150px]">{String(val)}</td>
                                         ))}
                                     </tr>
                                 ))}
                             </tbody>
                         </table>
                         {previewData.content.length > 100 && <div className="p-4 text-center text-muted-foreground italic">Showing first 100 rows preview.</div>}
                     </div>
                 ) : previewData?.type === 'markdown' ? (
                     <div className="prose prose-sm dark:prose-invert max-w-none font-sans">
                         <pre className="whitespace-pre-wrap text-muted-foreground font-mono">{previewData.content}</pre>
                     </div>
                 ) : (
                     <pre className="whitespace-pre-wrap text-muted-foreground">{previewData?.content}</pre>
                 )}
             </div>
          </div>
      </div>
    </div>
  );
}
