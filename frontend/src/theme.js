import { createTheme } from '@mantine/core';

export const theme = createTheme({
  primaryColor: 'indigo',
  defaultRadius: 'md',
  fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  fontFamilyMonospace: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
  headings: { fontWeight: '650' },
  components: {
    Card: { defaultProps: { withBorder: true, padding: 'lg', radius: 'lg' } },
  },
});
