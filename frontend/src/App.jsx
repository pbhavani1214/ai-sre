import { useState } from 'react';
import { AppShell } from '@mantine/core';
import AppHeader from './components/AppHeader';
import TargetSelectionPage from './pages/TargetSelectionPage';
import InvestigationPage from './pages/InvestigationPage';

/** Screens: the live flow starts at target selection; the bundled demo stays one link away. */
export default function App() {
  const [view, setView] = useState('targets');

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <AppHeader onHome={() => setView('targets')} />
      </AppShell.Header>
      <AppShell.Main>
        {view === 'targets' && <TargetSelectionPage onOpenDemo={() => setView('demo')} />}
        {view === 'demo' && <InvestigationPage />}
      </AppShell.Main>
    </AppShell>
  );
}
