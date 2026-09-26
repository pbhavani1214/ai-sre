import { ActionIcon, Badge, Container, Group, Text, ThemeIcon, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { IconActivityHeartbeat, IconMoon, IconSun } from '@tabler/icons-react';
import { USE_MOCK } from '../services/api';

export default function AppHeader() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light');
  const dark = scheme === 'dark';

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
          {USE_MOCK && (
            <Tooltip label="No backend configured. Showing bundled sample data.">
              <Badge variant="light" color="gray" visibleFrom="xs">Demo data</Badge>
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
