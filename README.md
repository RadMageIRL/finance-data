# finance-data

The economic data pipeline of RadMage Finance (https://radmagelabs.com/finance/): collector adapters, normalization, revision classification, review and rollback, a publish gate, and an independent checker.

## Status

Stage C: scheduled **private** collection (data conventions v0.7, section 21). **Private.** Nothing is published:

- the `collect` workflow runs every four hours at :17 UTC; a scheduled run collects only while the repository variables `LIVE_COLLECTION_AUTHORIZED` and `COLLECTION_SCHEDULE_ENABLED` are both `true` (delete either to pause); a manual live run also needs the typed confirmation LIVE; requests identify themselves as `RadMage Finance (+https://radmagelabs.com/finance/)`;
- every run is validated by the independent checker before the private state repository `RadMageIRL/finance-data-state` is written, through a GitHub App limited to that repository (contents write, metadata read) whose key is kept in GitHub's secret storage; the push is never forced, and one concurrency group keeps writers apart;
- unexpected changes are held for a person, who decides with the `operate` workflow (review, rollback, restore); alerts are kept as one issue per key, edited and closed, never duplicated;
- nothing is published: GitHub Pages is not enabled, the publication workflow is disabled, and no public dataset exists.

Publication needs its own authorization.

## Layout

| Path | What |
|---|---|
| `pipeline/registry/` | The source registry (data conventions v0.7) and the Federal Reserve holiday table |
| `pipeline/schemas/` | JSON Schemas of every file the pipeline writes |
| `pipeline/lib/` | The pipeline: pure functions, a file store and the state store, no dependencies, no network code |
| `pipeline/collectors/` | Provider adapters, which reach a provider only through a transport function, and the live transport |
| `pipeline/bin/` | `collect.mjs` (fixture and Stage C collection), `state-op.mjs` (promote, review, rollback, restore), `issues.mjs` (alert issues), `fixture-scenario.mjs` and `state-scenario.mjs` (the deterministic scenarios), `rehearse.mjs` |
| `pipeline/fixtures/` | Saved provider responses and test data (see NOTICE.md) |
| `tests/unit/pipeline/` | Unit and end-to-end fixture tests (Vitest) |
| `tests/datacheck/` | The independent checker, written from the specification text alone (Python standard library): plain, root, live root, state store and scenario modes, and the comparison with the saved histories |
| `tools/datacheck.mjs` | Writes both scenarios twice (the bytes must match, and the appendix B tree hash must equal the committed one on every platform) and runs the checker on them |
| `.github/workflows/` | `ci` (every push), `collect` (scheduled and manual), `operate` (manual), `rehearse` (manual, fixtures), `publish` (disabled) |

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
