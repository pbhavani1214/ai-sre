import { ActionIcon, Badge, Container, Group, Text, ThemeIcon, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { IconActivityHeartbeat, IconMoon, IconSun } from '@tabler/icons-react';
import { useHealth } from '../hooks/useHealth';

const HEALTH_BADGE = {
  mock: { color: 'gray', label: 'Demo data', tip: 'No backend configured (VITE_API_BASE_URL). Showing bundled sample data.' },
  ready: { color: 'green', label: 'Backend connected', tip: 'Backend reachable and the AI provider is configured.' },
  'no-llm': { color: 'yellow', label: 'AI not configured', tip: 'Backend reachable, but it has no LLM API key. Set LLM_API_KEY in the backend .env.' },
  offline: { color: 'red', label: 'Backend offline', tip: 'Could not reach the backend.' },
};

export default function AppHeader() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light');
  const dark = scheme === 'dark';
  const badge = HEALTH_BADGE[useHealth().status];

  return (
    <Container size="lg" h="100%">
      <Group h="100%" justify="space-between" wrap="nowrap">
        <Group gap="sm" wrap="nowrap">
          <ThemeIcon size="lg" radius="md" variant="gradient" gradient={{ from: 'indigo', to: 'cyan' }}>
            <IconActivityHeartbeat size={20} />
          </ThemeIcon>
          <div>
            <Text fw={700} lh={1.1}>AI Reliability Engineer</Text>
            <Text size="xs" c="dimmed" lh={1.1} visibleFrom="xs">Evidence-based pipeline investigation</Text>
          </div>
        </Group>
        <Group gap="xs" wrap="nowrap">
          {badge && (
            <Tooltip label={badge.tip} multiline w={260}>
              <Badge variant="light" color={badge.color} visibleFrom="xs">{badge.label}</Badge>
            </Tooltip>
          )}
          <Tooltip label={dark ? 'Light mode' : 'Dark mode'}>
            <ActionIcon
              variant="default"
              size="lg"
              aria-label="Toggle color scheme"
              onClick={() => setColorScheme(dark ? 'light' : 'dark')}
            >
              {dark ? <IconSun size={18} /> : <IconMoon size={18} />}
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>
    </Container>
  );
}
