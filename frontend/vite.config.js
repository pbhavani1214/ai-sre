import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    // Tests talk to a fake backend URL; fetch is mocked per test.
    env: { VITE_API_BASE_URL: 'http://api.test' },
    css: false,
  },
});
