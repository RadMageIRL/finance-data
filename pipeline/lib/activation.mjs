// The activation guard (DATA_CONVENTIONS sections 17.9 and 20). Two purposes with their own
// requirements: a nonpublishing live collection (Stage B) and publication (Stage C or D). A run
// with mode "live" is refused unless every collection requirement is given as true; nothing in the
// pipeline publishes.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { holidayTableProblems } from './calendar.mjs';

/**
 * facts: { pipelineDir, liveTransportExists, liveCollectionAuthorized, stateStoreExists,
 * dataRepositoryExists, publicationAuthorized, labsRouteAuthorized }. purpose: 'collect' (the
 * default) or 'publish'. Returns the list of blockers; an empty list means the purpose may proceed.
 */
export function activationProblems(facts, purpose = 'collect') {
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
  if (facts.liveTransportExists !== true) problems.push('the live transport is not given as present');
  if (facts.liveCollectionAuthorized !== true) problems.push('live collection is not authorized (the LIVE_COLLECTION_AUTHORIZED variable and the manual confirmation)');
  if (facts.stateStoreExists !== true) problems.push('there is no verified durable private state store');
  if (purpose === 'publish') {
    if (facts.dataRepositoryExists !== true) problems.push('the data repository is not given as existing');
    if (facts.publicationAuthorized !== true) problems.push('publication of economic data is not authorized');
    if (facts.labsRouteAuthorized !== true) problems.push('the Labs route for the data namespace is not authorized');
  }
  return problems;
}
