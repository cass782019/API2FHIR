// @ts-check
import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config para FHIR-Forge frontend tests.
 * O frontend (nginx) deve estar rodando em http://localhost:3001 antes do teste.
 * A API FastAPI deve estar rodando em http://localhost:8000.
 */
export default defineConfig({
  testDir: './specs',
  timeout: 180_000,        // 3 min — cobre conversões LLM longas
  expect: { timeout: 15_000 },
  fullyParallel: false,    // Conversões consomem o LLM; serializar evita rate-limit
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:3001',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
