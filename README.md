# finance-data

The economic data pipeline of RadMage Finance (https://radmagelabs.com/finance/): collector adapters, normalization, revision classification, review and rollback, a publish gate, and an independent checker.

## Status

Controlled integration, stage A. **Private.** Fixtures only:

- no request is sent to any data provider (there is no live transport; the pipeline refuses a live run);
- no workflow has a schedule;
- nothing is published (GitHub Pages is not enabled; the publication workflow is disabled).

Each later stage (live collection without publication, scheduled collection, publication) needs its own authorization.

## Layout

| Path | What |
|---|---|
| `pipeline/registry/` | The source registry (data conventions v0.5) and the Federal Reserve holiday table |
| `pipeline/schemas/` | JSON Schemas of every file the pipeline writes |
| `pipeline/lib/` | The pipeline: pure functions and a file store, no dependencies, no network code |
| `pipeline/collectors/` | Provider adapters; they reach a provider only through a transport function |
| `pipeline/bin/` | `fixture-scenario.mjs` (the 22-step scenario), `collect.mjs`, `rehearse.mjs` |
| `pipeline/fixtures/` | Saved provider responses and test data (see NOTICE.md) |
| `tests/unit/pipeline/` | Unit and end-to-end fixture tests (Vitest) |
| `tests/datacheck/` | The independent checker, written from the specification text alone (Python standard library) |
| `tools/datacheck.mjs` | Writes the scenario twice (the bytes must match) and runs the checker on it |
| `.github/workflows/` | `ci` (every push), `rehearse` and `collect` (manual, fixtures only), `publish` (disabled) |

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
