import { defineConfig, devices } from '@playwright/test'

const projectPath = '/healthcare-claims-denial-copilot/'
const baseURL = 'http://127.0.0.1:4173' + projectPath

export default defineConfig({
  testDir: './e2e',
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort --base ' + projectPath,
    url: baseURL,
  },
  use: {
    baseURL,
    launchOptions: { executablePath: process.env.CLAIMS_CHROMIUM_PATH },
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
})
