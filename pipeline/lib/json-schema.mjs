// A small JSON Schema (2020-12) validator for the subset the pipeline schemas use, with no
// dependencies (the project adds none). Supported: type (one or a list, "integer" included),
// const, enum, pattern, minLength, maxLength, minimum, maximum, required, properties,
// patternProperties, additionalProperties (false or a schema), minProperties, items, minItems,
// maxItems, anyOf, oneOf, and $ref to "#/$defs/<name>" within the same document. Any other
// keyword in a schema is an error, so a schema can never silently ask for a check that does
// not happen. Keywords for one type (pattern, minimum, ...) apply only to values of that type,
// as JSON Schema defines.

const KNOWN = new Set([
  '$schema', '$id', '$defs', 'title', 'description',
  'type', 'const', 'enum', 'pattern', 'minLength', 'maxLength', 'minimum', 'maximum',
  'required', 'properties', 'patternProperties', 'additionalProperties', 'minProperties',
  'items', 'minItems', 'maxItems', 'anyOf', 'oneOf', '$ref',
]);

function typeOf(value) {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number';
  return typeof value;
}

function typeMatches(value, type) {
  const t = typeOf(value);
  return t === type || (type === 'number' && t === 'integer');
}

function equal(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** All problems found, as "path: message" strings; an empty list means the value is valid. */
export function validate(schema, value) {
  const errors = [];
  check(schema, value, '$', schema, errors);
  return errors;
}

function resolve(ref, root) {
  const m = /^#\/\$defs\/([A-Za-z0-9_]+)$/.exec(ref);
  if (!m || !root.$defs || !(m[1] in root.$defs)) throw new Error(`unsupported or unknown $ref ${ref}`);
  return root.$defs[m[1]];
}

function check(schema, value, path, root, errors) {
  if (schema === true) return;
  if (schema === false) {
    errors.push(`${path}: not allowed`);
    return;
  }
  for (const key of Object.keys(schema)) if (!KNOWN.has(key)) throw new Error(`unsupported schema keyword ${key} at ${path}`);
  if (schema.$ref) check(resolve(schema.$ref, root), value, path, root, errors);
  if (schema.type !== undefined) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!types.some((t) => typeMatches(value, t))) {
      errors.push(`${path}: expected ${types.join(' or ')}, got ${typeOf(value)}`);
      return;
    }
  }
  if ('const' in schema && !equal(schema.const, value)) errors.push(`${path}: must be ${JSON.stringify(schema.const)}`);
  if (schema.enum && !schema.enum.some((e) => equal(e, value))) errors.push(`${path}: must be one of ${JSON.stringify(schema.enum)}`);
  if (typeof value === 'string') {
    if (schema.pattern !== undefined && !new RegExp(schema.pattern, 'u').test(value)) errors.push(`${path}: does not match ${schema.pattern}`);
    const length = [...value].length;
    if (schema.minLength !== undefined && length < schema.minLength) errors.push(`${path}: shorter than ${schema.minLength}`);
    if (schema.maxLength !== undefined && length > schema.maxLength) errors.push(`${path}: longer than ${schema.maxLength}`);
  }
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push(`${path}: less than ${schema.minimum}`);
    if (schema.maximum !== undefined && value > schema.maximum) errors.push(`${path}: more than ${schema.maximum}`);
  }
  if (typeOf(value) === 'object') {
    const keys = Object.keys(value);
    for (const r of schema.required ?? []) if (!(r in value)) errors.push(`${path}: missing ${r}`);
    if (schema.minProperties !== undefined && keys.length < schema.minProperties) errors.push(`${path}: fewer than ${schema.minProperties} properties`);
    for (const k of keys) {
      let matched = false;
      if (schema.properties && k in schema.properties) {
        matched = true;
        check(schema.properties[k], value[k], `${path}.${k}`, root, errors);
      }
      for (const [p, s] of Object.entries(schema.patternProperties ?? {})) {
        if (new RegExp(p, 'u').test(k)) {
          matched = true;
          check(s, value[k], `${path}.${k}`, root, errors);
        }
      }
      if (!matched && schema.additionalProperties !== undefined) {
        if (schema.additionalProperties === false) errors.push(`${path}: unknown property ${k}`);
        else check(schema.additionalProperties, value[k], `${path}.${k}`, root, errors);
      }
    }
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(`${path}: fewer than ${schema.minItems} items`);
    if (schema.maxItems !== undefined && value.length > schema.maxItems) errors.push(`${path}: more than ${schema.maxItems} items`);
    if (schema.items) value.forEach((v, i) => check(schema.items, v, `${path}[${i}]`, root, errors));
  }
  if (schema.anyOf) {
    const ok = schema.anyOf.some((s) => {
      const e = [];
      check(s, value, path, root, e);
      return e.length === 0;
    });
    if (!ok) errors.push(`${path}: matches none of anyOf`);
  }
  if (schema.oneOf) {
    const passing = schema.oneOf.filter((s) => {
      const e = [];
      check(s, value, path, root, e);
      return e.length === 0;
    }).length;
    if (passing !== 1) errors.push(`${path}: matches ${passing} of oneOf (exactly 1 required)`);
  }
}
