import { useState } from 'react';
import { AppShell } from '@mantine/core';
import AppHeader from './components/AppHeader';
import TargetSelectionPage from './pages/TargetSelectionPage';
import UploadPage from './pages/UploadPage';
import RunResultPage from './pages/RunResultPage';
import InvestigationPage from './pages/InvestigationPage';

/**
 * Live flow: target selection -> CSV upload -> run created. The bundled demo stays one link away.
 * `target` is the TargetSummary chosen on the first screen; `run` is the RunSummary from POST /api/runs.
 */
export default function App() {
  const [view, setView] = useState({ name: 'targets', target: null, run: null });
  const go = (name, patch = {}) => setView((v) => ({ ...v, ...patch, name }));

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <AppHeader onHome={() => go('targets')} />
      </AppShell.Header>
      <AppShell.Main>
        {view.name === 'targets' && (
          <TargetSelectionPage
            initialTargetId={view.target?.target_id ?? null}
            onContinue={(target) => go('upload', { target, run: null })}
            onOpenDemo={() => go('demo')}
          />
        )}
        {view.name === 'upload' && (
          <UploadPage target={view.target} onBack={() => go('targets')} onCreated={(run) => go('run', { run })} />
        )}
        {view.name === 'run' && (
          <RunResultPage
            run={view.run}
            target={view.target}
            onUploadAnother={() => go('upload', { run: null })}
            onChooseTarget={() => go('targets', { run: null })}
          />
        )}
        {view.name === 'demo' && <InvestigationPage />}
      </AppShell.Main>
    </AppShell>
  );
}
