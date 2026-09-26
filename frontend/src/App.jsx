import { useState } from 'react';
import { Alert, AppShell, Container } from '@mantine/core';
import AppHeader from './components/AppHeader';
import TargetSelectionPage from './pages/TargetSelectionPage';
import UploadPage from './pages/UploadPage';
import RunResultPage from './pages/RunResultPage';
import { getRun } from './services/api';

/**
 * Live flow: target selection -> CSV upload -> run result (validation, AI investigation, corrected retry, load).
 * `runs` and `investigations` are keyed by run_id so a retry (child run) and its original (parent) each keep their
 * own state; showing one never changes the other.
 */
export default function App() {
  const [view, setView] = useState({ name: 'targets', database: null, target: null, runId: null });
  const [runs, setRuns] = useState({});
  const [investigations, setInvestigations] = useState({});
  const [openError, setOpenError] = useState(null);
  const go = (name, patch = {}) => {
    setOpenError(null);
    setView((v) => ({ ...v, ...patch, name }));
  };

  const showRun = (run) => {
    setRuns((r) => ({ ...r, [run.run_id]: run }));
    go('run', { runId: run.run_id });
    window.scrollTo?.({ top: 0 });
  };
  const openRun = async (runId) => {
    if (runs[runId]) return go('run', { runId });
    try {
      showRun(await getRun(runId));
    } catch (e) {
      setOpenError(e.message);
    }
  };

  const run = view.runId ? runs[view.runId] : null;

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <AppHeader onHome={() => go('targets')} />
      </AppShell.Header>
      <AppShell.Main>
        {view.name === 'targets' && (
          <TargetSelectionPage
            initialDatabaseId={view.database?.database_id ?? null}
            initialTargetId={view.target?.target_id ?? null}
            onContinue={({ database, target }) => go('upload', { database, target, runId: null })}
          />
        )}
        {view.name === 'upload' && (
          <UploadPage database={view.database} target={view.target} onBack={() => go('targets')} onCreated={showRun} />
        )}
        {view.name === 'run' && run && (
          <>
            {openError && (
              <Container size="md" pt="md">
                <Alert color="red" variant="light" title="Could not open that run" role="alert">{openError}</Alert>
              </Container>
            )}
            <RunResultPage
              key={run.run_id}
              run={run}
              target={view.target}
              database={view.database}
              investigation={investigations[run.run_id] ?? null}
              onInvestigation={(result) => setInvestigations((m) => ({ ...m, [run.run_id]: result }))}
              onRetried={showRun}
              onOpenRun={openRun}
              onUploadAnother={() => go('upload', { runId: null })}
              onChooseTarget={() => go('targets', { runId: null })}
            />
          </>
        )}
      </AppShell.Main>
    </AppShell>
  );
}
