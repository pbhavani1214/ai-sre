import { AppShell } from '@mantine/core';
import AppHeader from './components/AppHeader';
import InvestigationPage from './pages/InvestigationPage';

export default function App() {
  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <AppHeader />
      </AppShell.Header>
      <AppShell.Main>
        <InvestigationPage />
      </AppShell.Main>
    </AppShell>
  );
}
