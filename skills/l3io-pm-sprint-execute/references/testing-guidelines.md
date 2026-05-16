# Unit Testing Guidelines

Communicate all responses in `{communication_language}`.

## Test Quality Review

Apply these checks when writing or reviewing unit tests — not only at story close but periodically as implementation evolves:

- **Beyond happy path:** Cover error paths, boundary conditions, and edge cases. A suite that only exercises the success scenario will miss regressions.
- **Continued relevance:** After significant refactors, verify existing tests still exercise meaningful behavior and are not vacuously passing (e.g., asserting on a mock that no longer reflects real behavior).
- **Parallelism:** Identify tests with no shared state or I/O and configure them to run in parallel to reduce suite duration. Tests that block parallelism due to shared resources should use test-scoped fixtures or isolation.

## Test Output Caching

When running tests — especially unit test suites — redirect output to a timestamped log file. This prevents the need to re-run the full suite just to inspect failure details or warnings:

```
<test-command> 2>&1 | tee /tmp/test-run-$(date +%Y%m%d-%H%M%S).log
```

After all failures and warnings have been analyzed and resolved, delete the cached log:

```
rm /tmp/test-run-*.log
```

Do not leave log files in the project directory or include them in commits.
