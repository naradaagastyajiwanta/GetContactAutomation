# WhatsApp Service Tests

This directory contains comprehensive tests for the WhatsApp service using Jest.

## Test Structure

```
tests/
├── setup.ts              # Test setup and global mocks
├── utils/
│   └── mocks.ts          # Mock utilities and test helpers
├── messageQueue.test.ts  # Message queue, debouncing, and persistence tests
├── rateLimiter.test.ts   # Token bucket rate limiting tests
├── errorHandling.test.ts # Retry logic, exponential backoff, circuit breaker tests
├── typeSafety.test.ts    # LID resolution, type validation, phone normalization tests
└── memoryCleanup.test.ts # Memory cleanup, TTL, and resource disposal tests
```

## Running Tests

### Install Dependencies
```bash
cd whatsapp-service
npm install
```

### Run All Tests
```bash
npm test
```

### Run Tests in Watch Mode
```bash
npm run test:watch
```

### Run Tests with Coverage
```bash
npm run test:coverage
```

### Run Specific Test File
```bash
npm test messageQueue
npm test rateLimiter
npm test errorHandling
npm test typeSafety
npm test memoryCleanup
```

## Test Coverage

- **Message Queue Tests**: Queue operations, message deduplication, debouncing behavior, LID resolution
- **Rate Limiter Tests**: Token consumption/refill, rate limits, token reset, concurrent requests
- **Error Handling Tests**: Exponential backoff, retry logic, circuit breaker pattern
- **Type Safety Tests**: Phone normalization, LID resolution fallback, message key validation
- **Memory Cleanup Tests**: PendingMessages TTL, timer cleanup, resource disposal

## Test Utilities

The `utils/mocks.ts` file provides helper functions for testing:

- `createMockMessage(options)` - Create fake Baileys messages
- `createLIDMessage(lid, text)` - Create LID messages for resolution testing
- `createVCardArrayMessage(contacts)` - Create vCard contact messages
- `MockBaileysSocket` - Mocked Baileys socket for testing
- `createMockRequest(body, params)` - Mock Express requests
- `createMockResponse()` - Mock Express responses
- `flushPromises()` - Wait for pending promises to resolve

## CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: |
    cd whatsapp-service
    npm install
    npm test
```

## Coverage Goals

- Lines: >80%
- Functions: >80%
- Branches: >75%
- Statements: >80%
