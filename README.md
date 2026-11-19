# finance-data

The economic data pipeline of RadMage Finance (https://radmagelabs.com/finance/): collector adapters, normalization, revision classification, review and rollback, a publish gate, and an independent checker.

## Status

Controlled integration, stage B. **Private.** Live collection is manual and nonpublishing:

- a live collection runs only when started by hand with the confirmation LIVE while the repository variable `LIVE_COLLECTION_AUTHORIZED` is `true`; it identifies itself as `RadMage Finance (+https://radmagelabs.com/finance/)`;
- its results go only to the private state repository `RadMageIRL/finance-data-state`, written by a GitHub App limited to that repository (contents write, metadata read) whose key is kept in GitHub's secret storage;
- no workflow has a schedule;
- nothing is published (GitHub Pages is not enabled; the publication workflow is disabled), and no result is accepted automatically.

Each later stage (scheduled collection, publication) needs its own authorization.

## Layout

| Path | What |
|---|---|
| `pipeline/registry/` | The source registry (data conventions v0.6) and the Federal Reserve holiday table |
| `pipeline/schemas/` | JSON Schemas of every file the pipeline writes |
| `pipeline/lib/` | The pipeline: pure functions, a file store and the state store, no dependencies, no network code |
| `pipeline/collectors/` | Provider adapters, which reach a provider only through a transport function, and the live transport |
| `pipeline/bin/` | `fixture-scenario.mjs` (the 22-step scenario), `collect.mjs`, `rehearse.mjs` |
| `pipeline/fixtures/` | Saved provider responses and test data (see NOTICE.md) |
| `tests/unit/pipeline/` | Unit and end-to-end fixture tests (Vitest) |
| `tests/datacheck/` | The independent checker, written from the specification text alone, with its comparison of a collection against the saved histories (Python standard library) |
| `tools/datacheck.mjs` | Writes the scenario twice (the bytes must match), runs the checker on it, and runs the comparison self-test |
| `.github/workflows/` | `ci` (every push), `rehearse` (manual, fixtures), `collect` (manual: fixtures, or one authorized live collection), `publish` (disabled) |

## Running the checks

```
npm ci
npx vitest run
python3 -I tests/datacheck/check_p22.py
node tools/datacheck.mjs
```

## Provenance

The code is developed and fully verified (including a mutation pass) in the RadMage Finance repository, and each verified checkpoint is imported here as one commit that names its source commit.

## License

The code is under the MIT License (LICENSE). The provider data saved in `pipeline/fixtures/` is not covered by that license; see NOTICE.md.
