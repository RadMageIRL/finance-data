# finance-data

The economic data pipeline of RadMage Finance (https://radmagelabs.com/finance/): collector adapters, normalization, revision classification, review and rollback, a publish gate, and an independent checker.

## Status

Scheduled collection (data conventions v0.7, section 21) and automatic publication (data conventions v0.8, section 22). **Public code and releases, private state:** this repository holds the code and the published `data-*` releases; the accepted data and its history live in the separate **private** repository `RadMageIRL/finance-data-state`. The Finance site serves the published data at https://radmagelabs.com/finance/data/econ/ and the dashboards at https://radmagelabs.com/finance/data/.

- the `collect` workflow runs every four hours at :17 UTC, dispatched in mode `timer` by a Cloudflare Worker cron (`17 */4 * * *`) that names the slot it fired for (GitHub's own cron is no longer a trigger); a scheduled run collects only while the repository variables `LIVE_COLLECTION_AUTHORIZED` and `COLLECTION_SCHEDULE_ENABLED` are both `true` (delete either to pause); a manual live run also needs the typed confirmation LIVE; requests identify themselves as `RadMage Finance (+https://radmagelabs.com/finance/)`;
- the `watch` workflow checks the collect runs from outside them (GitHub's own cron at 01:47, 07:47, 13:47 and 19:47 UTC, and a dispatch by the same Worker at 02:47, 06:47, 10:47, 14:47, 18:47 and 22:47 UTC) and opens or closes the alert issues for a run gap, a disabled collect workflow, a failure streak and repository inactivity, so a stopped timer is reported even when no collection starts; from the public data it also checks the live manifest (`manifest-missing`, and `manifest-overdue` once the next update is late) and the release history (`publication-history-changed`); its job fails on a gap, a disabled workflow, a failure streak, a missing manifest, a manifest more than 24 hours overdue or a changed history;
- every run is validated by the independent checker before the private state repository `RadMageIRL/finance-data-state` is written, through a GitHub App limited to that repository (contents write, metadata read) whose key is kept in GitHub's secret storage; the push is never forced, and one concurrency group keeps writers apart;
- unexpected changes are held for a person, who decides with the `operate` workflow (review, rollback, restore, and pin or unpin a snapshot); every reason given is checked before the operation runs; alerts are kept as one issue per key, edited and closed, never duplicated;
- each collect run also records the publication facts (the newest `data-*` release and its run) in the state store's private deployment log, and raises `publication-behind` when an accepted dataset has waited more than 12 hours for its deployment while timer publication is on;
- the `publish` workflow runs in mode `timer` every four hours at :37 UTC, dispatched by the same Worker (cron `37 */4 * * *`), twenty minutes after each collection. It releases the accepted dataset only when that is newer than the deployed one, and otherwise ends as a no-op. The newest earlier release, whose deployment log the next one extends, is the one published last (ties broken by the higher release id, never by the tagged commit's date), and a dataset the site already serves is never released again. The independent checker validates the state and the publication tree first (V2); an immutable release `data-<snapshot>-<run id>-<attempt>` carries the four assets; the Finance site build in mode `data` checks the release again and deploys it only over the dataset it expected; the post-deploy verification (V3) reads every file back at both public addresses, retrying a network error, a timeout or a status 408, 429 or 5xx up to three times (after 2, 4 and 8 seconds), but never a file whose SHA-256 does not match. A failed V3 redeploys the newest verified dataset automatically and pauses timer publication until a publication started by a person passes. Publication runs only while the repository variables `PUBLICATION_ENABLED` and `PUBLICATION_SCHEDULE_ENABLED` are both `true`: delete `PUBLICATION_SCHEDULE_ENABLED` to stop timer publication, and `PUBLICATION_ENABLED` as well to stop all publication (collection is unaffected). The modes `manual` and `redeploy` remain for a person.

Copies of this pipeline must change the request identification in `pipeline/registry/econ.json` (each source's `request.user_agent` and `request.contact`): it names RadMage Finance to the data providers.

## Layout

| Path | What |
|---|---|
| `pipeline/registry/` | The source registry (data conventions v0.8) and the Federal Reserve holiday table |
| `pipeline/schemas/` | JSON Schemas of every file the pipeline writes |
| `pipeline/lib/` | The pipeline: pure functions, a file store and the state store, no dependencies, no network code |
| `pipeline/collectors/` | Provider adapters, which reach a provider only through a transport function, and the live transport |
| `pipeline/bin/` | `collect.mjs` (fixture and Stage C collection), `state-op.mjs` (promote, review, rollback, restore, pin, unpin), `issues.mjs` (alert issues), `watch.mjs`, `publish.mjs` and `publication-facts.mjs` (publication), `site-data.mjs` (the site build's data steps, used by the Finance repository), `fixture-scenario.mjs`, `state-scenario.mjs` and `publish-scenario.mjs` (the deterministic scenarios), `rehearse.mjs` |
| `pipeline/fixtures/` | Saved provider responses and test data (see NOTICE.md) |
| `tests/unit/pipeline/` | Unit and end-to-end fixture tests (Vitest) |
| `tests/datacheck/` | The independent checker, written from the specification text alone (Python standard library): plain, root, live root, state store, scenario, publication and release modes, and the comparison with the saved histories |
| `tools/datacheck.mjs` | Writes the three scenarios twice (the bytes must match, and the appendix B tree hash must equal the committed one on every platform) and runs the checker on them |
| `pipeline/timer/worker.mjs` | The Cloudflare Worker `finance-collect-timer`: its cron `17 */4 * * *` dispatches `collect` in mode `timer` with the slot, its cron `47 2-22/4 * * *` dispatches `watch`, and its cron `41 */2 * * *` dispatches the `news` workflow of the Finance site repository (the two-hourly news refresh), and its cron `37 */4 * * *` dispatches `publish` in mode `timer`; two secrets, each a fine-grained token with Actions read and write for one repository (`GITHUB_TOKEN` for this one, `NEWS_DISPATCH_TOKEN` for the Finance site); no route |
| `.github/workflows/` | `ci` (every push), `collect` (timer dispatch and manual), `watch` (GitHub cron and timer dispatch), `operate` (manual), `rehearse` (manual, fixtures), `publish` (timer dispatch every four hours, manual and redeploy) |

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
