import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // VITE_API_BASE_URL (see .env.example) points the dev proxy at the Django
  // backend. It must be an absolute origin — no trailing slash, no /api.
  const env = loadEnv(mode, __dirname, '');
  const apiTarget = (env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: true,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
