import { Routes, Route } from 'react-router-dom';
import { Shell } from './components/layout/Shell';
import { OverviewPage } from './pages/Overview/OverviewPage';

import { ScannerPage } from './pages/Scanner/ScannerPage';

import { MonitoringPage } from './pages/Monitoring/MonitoringPage';
import { DecisionPage } from './pages/Decision/DecisionPage';
import { PaperTradingPage } from './pages/PaperTrading/PaperTradingPage';
import { DiagnosticsPage } from './pages/Diagnostics/DiagnosticsPage';
import { ArtifactsPage } from './pages/Artifacts/ArtifactsPage';
import { LogsPage } from './pages/Logs/LogsPage';
import { ProfilesPage } from './pages/Profiles/ProfilesPage';
import { DerivativesPage } from './pages/Derivatives/DerivativesPage';
import { AIWorkspacePage } from './pages/AI/AIWorkspacePage';
import { SettingsPage } from './pages/Settings/SettingsPage';
import { AutomationPage } from './pages/Automation/AutomationPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Shell />}>
        <Route index element={<OverviewPage />} />
        <Route path="scanner" element={<ScannerPage />} />
        <Route path="monitoring" element={<MonitoringPage />} />
        <Route path="decision" element={<DecisionPage />} />
        <Route path="derivatives" element={<DerivativesPage />} />
        <Route path="paper" element={<PaperTradingPage />} />
        <Route path="diagnostics" element={<DiagnosticsPage />} />
        <Route path="profiles" element={<ProfilesPage />} />
        <Route path="artifacts" element={<ArtifactsPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="ai" element={<AIWorkspacePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="automation" element={<AutomationPage />} />
      </Route>
    </Routes>
  );
}

export default App;
