import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/unit/**/*.test.ts'],
    environment: 'node',
    // End-to-end pipeline tests run several seconds under a fully parallel load; 5 s (the default)
    // gave a spurious timeout once, and a timeout must never be what fails or passes a test.
    testTimeout: 30_000,
  },
});
