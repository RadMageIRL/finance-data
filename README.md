# finance-data

The economic data pipeline of RadMage Finance (https://radmagelabs.com/finance/): collector adapters, normalization, revision classification, review and rollback, a publish gate, and an independent checker.

## Status

Stage C: scheduled **private** collection (data conventions v0.7, section 21), running the Stage D code of data conventions v0.8 (section 22) with publication **prepared and not enabled**. **Public code, private data:** this repository holds the code, and the accepted data lives in the separate **private** repository `RadMageIRL/finance-data-state`. Nothing is published here:

- the `collect` workflow runs every four hours at :17 UTC, dispatched in mode `timer` by a Cloudflare Worker cron (`17 */4 * * *`) that names the slot it fired for (GitHub's own cron is no longer a trigger); a scheduled run collects only while the repository variables `LIVE_COLLECTION_AUTHORIZED` and `COLLECTION_SCHEDULE_ENABLED` are both `true` (delete either to pause); a manual live run also needs the typed confirmation LIVE; requests identify themselves as `RadMage Finance (+https://radmagelabs.com/finance/)`;
- the `watch` workflow checks the collect runs from outside them (GitHub's own cron at 01:47, 07:47, 13:47 and 19:47 UTC, and a dispatch by the same Worker at 02:47, 06:47, 10:47, 14:47, 18:47 and 22:47 UTC) and opens or closes the alert issues for a run gap, a disabled collect workflow, a failure streak and repository inactivity, so a stopped timer is reported even when no collection starts; its job fails on a gap, a disabled workflow or a failure streak;
- every run is validated by the independent checker before the private state repository `RadMageIRL/finance-data-state` is written, through a GitHub App limited to that repository (contents write, metadata read) whose key is kept in GitHub's secret storage; the push is never forced, and one concurrency group keeps writers apart;
- unexpected changes are held for a person, who decides with the `operate` workflow (review, rollback, restore, and pin or unpin a snapshot); every reason given is checked before the operation runs; alerts are kept as one issue per key, edited and closed, never duplicated;
- each collect run also records the publication facts (the newest `data-*` release and its run) in the state store's private deployment log; with no release yet, there is nothing to record;
- nothing is published: GitHub Pages is not enabled, the `publish` workflow does nothing unless the repository variable `PUBLICATION_ENABLED` is `true` (it is not set), no release exists, and no public dataset exists.

Publication needs its own authorization.

Copies of this pipeline must change the request identification in `pipeline/registry/econ.json` (each source's `request.user_agent` and `request.contact`): it names RadMage Finance to the data providers.

## Layout

| Path | What |
|---|---|
| `pipeline/registry/` | The source registry (data conventions v0.8) and the Federal Reserve holiday table |
| `pipeline/schemas/` | JSON Schemas of every file the pipeline writes |
| `pipeline/lib/` | The pipeline: pure functions, a file store and the state store, no dependencies, no network code |
| `pipeline/collectors/` | Provider adapters, which reach a provider only through a transport function, and the live transport |
| `pipeline/bin/` | `collect.mjs` (fixture and Stage C collection), `state-op.mjs` (promote, review, rollback, restore, pin, unpin), `issues.mjs` (alert issues), `watch.mjs`, `publish.mjs` and `publication-facts.mjs` (publication, prepared), `site-data.mjs` (the site build's data steps, used by the Finance repository), `fixture-scenario.mjs`, `state-scenario.mjs` and `publish-scenario.mjs` (the deterministic scenarios), `rehearse.mjs` |
| `pipeline/fixtures/` | Saved provider responses and test data (see NOTICE.md) |
| `tests/unit/pipeline/` | Unit and end-to-end fixture tests (Vitest) |
| `tests/datacheck/` | The independent checker, written from the specification text alone (Python standard library): plain, root, live root, state store, scenario, publication and release modes, and the comparison with the saved histories |
| `tools/datacheck.mjs` | Writes the three scenarios twice (the bytes must match, and the appendix B tree hash must equal the committed one on every platform) and runs the checker on them |
| `pipeline/timer/worker.mjs` | The Cloudflare Worker `finance-collect-timer`: its cron `17 */4 * * *` dispatches `collect` in mode `timer` with the slot, its cron `47 2-22/4 * * *` dispatches `watch`, and its cron `41 */2 * * *` dispatches the `news` workflow of the Finance site repository (the two-hourly news refresh); minute 37 would dispatch `publish` in mode `timer`, but no such cron line exists; two secrets, each a fine-grained token with Actions read and write for one repository (`GITHUB_TOKEN` for this one, `NEWS_DISPATCH_TOKEN` for the Finance site); no route |
| `.github/workflows/` | `ci` (every push), `collect` (timer dispatch and manual), `watch` (GitHub cron and timer dispatch), `operate` (manual), `rehearse` (manual, fixtures), `publish` (prepared, not enabled) |

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
