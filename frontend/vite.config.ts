import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite React config targeting Python FastAPI backend on port 8000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  }
});
