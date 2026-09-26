import { ActionIcon, Box, CopyButton, ScrollArea, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';

export default function CodeBlock({ code, maxHeight = 420 }) {
  return (
    <Box pos="relative">
      <ScrollArea.Autosize mah={maxHeight} type="auto">
        <pre className="code-block">{code}</pre>
      </ScrollArea.Autosize>
      <CopyButton value={code} timeout={1500}>
        {({ copied, copy }) => (
          <Tooltip label={copied ? 'Copied' : 'Copy code'} withArrow>
            <ActionIcon
              pos="absolute"
              top={8}
              right={8}
              variant="default"
              color={copied ? 'teal' : 'gray'}
              onClick={copy}
              aria-label="Copy code"
            >
              {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
            </ActionIcon>
          </Tooltip>
        )}
      </CopyButton>
    </Box>
  );
}
