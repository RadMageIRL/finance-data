// The activation guard (DATA_CONVENTIONS section 17.9). Live collection is not authorized: this
// lists what blocks it, and a run with mode "live" is refused whatever the list says. Fixture runs use mode "fixture"
// and never open a network connection.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { holidayTableProblems } from './calendar.mjs';

/**
 * facts: { pipelineDir, liveTransportExists, liveCollectionAuthorized, stateStoreExists,
 * dataRepositoryExists, publicationAuthorized, labsRouteAuthorized }. Returns the list of blockers; an empty list would mean live
 * collection may be activated.
 */
export function activationProblems(facts) {
  const problems = [];
  const path = join(facts.pipelineDir, 'registry', 'fed-holidays.json');
  if (!existsSync(path)) problems.push('no Federal Reserve holiday table at pipeline/registry/fed-holidays.json');
  else {
    let table = null;
    try {
      table = JSON.parse(readFileSync(path, 'utf8'));
    } catch {
      problems.push('the holiday table is not JSON');
    }
    if (table) {
      problems.push(...holidayTableProblems(table));
      if (table.status !== 'verified') problems.push('the holiday table is not verified against the Federal Reserve\'s published schedule');
    }
  }
  if (facts.liveTransportExists !== true) problems.push('there is no live transport: live network collection is not written and not authorized');
  if (facts.liveCollectionAuthorized !== true) problems.push('live collection is not authorized (stage B)');
  if (facts.stateStoreExists !== true) problems.push('there is no durable private state store (finance-data-state is not created)');
  if (facts.dataRepositoryExists !== true) problems.push('the data repository is not given as existing');
  if (facts.publicationAuthorized !== true) problems.push('publication of economic data is not authorized');
  if (facts.labsRouteAuthorized !== true) problems.push('the Labs route for the data namespace is not authorized');
  return problems;
}
