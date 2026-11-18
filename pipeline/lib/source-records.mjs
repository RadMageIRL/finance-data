// Date-bounded source record schemas (DATA_CONVENTIONS section 5): a record is accepted only
// by the schema in force for its date, field for field. A response with any record that fails
// is invalid as a whole (section 11.4); the caller decides that, this module only reports.

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DECIMAL_TEXT = /^-?\d+(\.\d+)?$/;
const DIGITS = /^\d+$/;

function typeProblem(spec, value) {
  switch (spec.type) {
    case 'date':
      return typeof value === 'string' && DATE.test(value) ? null : 'not a YYYY-MM-DD string';
    case 'number':
      return typeof value === 'number' && Number.isFinite(value) ? null : 'not a JSON number';
    case 'decimal-text':
      return typeof value === 'string' && DECIMAL_TEXT.test(value) ? null : 'not a decimal string';
    case 'decimal-text-or-null':
      return typeof value === 'string' && (value === 'null' || DECIMAL_TEXT.test(value)) ? null : 'not a decimal string or "null"';
    case 'digits':
      return typeof value === 'string' && DIGITS.test(value) ? null : 'not a string of digits';
    case 'flag':
      return spec.values.includes(value) ? null : `not one of ${JSON.stringify(spec.values)}`;
    default:
      return `unknown field type ${spec.type}`;
  }
}

/** The schema ids of one source, in date order, whose `date_field` is the same. */
export function schemasFor(table, source) {
  return Object.entries(table.records)
    .filter(([, s]) => s.source === source)
    .sort(([, a], [, b]) => (a.from < b.from ? -1 : 1));
}

/**
 * Checks one record. Returns { schema, problems }: the schema id in force for the record's
 * date (or null) and every problem found.
 */
export function checkRecord(table, source, record) {
  const candidates = schemasFor(table, source);
  if (candidates.length === 0) return { schema: null, problems: [`no schemas for source ${source}`] };
  const dateField = candidates[0][1].date_field;
  const date = record?.[dateField];
  if (typeof date !== 'string' || !DATE.test(date)) return { schema: null, problems: [`${dateField} missing or not a date`] };
  const match = candidates.find(([, s]) => s.from <= date && (s.to === null || date <= s.to));
  if (!match) return { schema: null, problems: [`no schema in force on ${date}`] };
  const [id, schema] = match;
  const problems = [];
  for (const [field, spec] of Object.entries(schema.fields)) {
    if (!(field in record)) problems.push(`${date}: missing ${field} (${id})`);
    else {
      const p = typeProblem(spec, record[field]);
      if (p) problems.push(`${date}: ${field} ${p} (${id})`);
    }
  }
  for (const [field, value] of Object.entries(record)) {
    if (field in schema.fields) continue;
    if (field in schema.optional) {
      const p = typeProblem(schema.optional[field], value);
      if (p) problems.push(`${date}: ${field} ${p} (${id})`);
    } else problems.push(`${date}: unknown field ${field} (${id})`);
  }
  return { schema: id, problems };
}

/**
 * Reads a JSON number's decimal text from a value already parsed by JSON.parse and stores it
 * with exactly `decimals` places, refusing more precision than declared (section 5). JSON.parse
 * gives the shortest round-trip text, which equals the published text for values with at most
 * 15 significant digits; longer values are refused rather than guessed.
 */
export function decimalFromNumber(value, decimals) {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new TypeError('not a finite number');
  const text = String(value);
  if (/e/i.test(text)) throw new RangeError(`${text}: exponent form refused`);
  const digits = text.replace(/^-/, '').replace('.', '').replace(/^0+/, '');
  if (digits.length > 15) throw new RangeError(`${text}: more than 15 significant digits`);
  const [int, frac = ''] = text.split('.');
  if (frac.length > decimals) throw new RangeError(`${text}: more than ${decimals} decimals`);
  return decimals === 0 ? int : `${int}.${frac.padEnd(decimals, '0')}`;
}
