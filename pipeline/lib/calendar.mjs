// Time and business days (DATA_CONVENTIONS sections 3, 14.2 and 17.9). Stored times are UTC;
// dates derived from times are dates in America/New_York (ET dates). New York Fed business
// days are Monday to Friday except Federal Reserve holidays, and the holiday table is always an
// input: the registry has no verified table yet (independent review R11, open by the owner's
// decision), so nothing here guesses a holiday.

const ET = 'America/New_York';
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const DAY = 86_400_000;

const etFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: ET, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

function ms(iso) {
  if (typeof iso !== 'string' || !TIME.test(iso)) throw new TypeError(`not a UTC time to the second: ${iso}`);
  return Date.parse(iso);
}

/** A UTC time in milliseconds as the stored form, to the second. */
export function isoSeconds(t) {
  return `${new Date(t).toISOString().slice(0, 19)}Z`;
}

/** The wall clock in New York of a UTC instant, as UTC milliseconds of that wall clock. */
function etWall(t) {
  const p = Object.fromEntries(etFormat.formatToParts(new Date(t)).map((x) => [x.type, x.value]));
  return Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour), Number(p.minute), Number(p.second));
}

/** The ET date (YYYY-MM-DD) of a stored UTC time. */
export function etDate(iso) {
  return new Date(etWall(ms(iso))).toISOString().slice(0, 10);
}

/** The ET wall-clock time of day (HH:MM:SS) of a stored UTC time. */
export function etClock(iso) {
  return new Date(etWall(ms(iso))).toISOString().slice(11, 19);
}

/** The UTC time of a wall-clock time (HH:MM or HH:MM:SS) on a date in a zone (ET or UTC). */
export function zonedTime(date, clock, zone) {
  if (!DATE.test(date)) throw new TypeError(`not a date: ${date}`);
  const [h, m, s = '00'] = clock.split(':');
  const wall = Date.parse(`${date}T${h}:${m}:${s}Z`);
  if (zone === 'UTC') return isoSeconds(wall);
  if (zone !== ET) throw new RangeError(`unsupported zone ${zone}`);
  // The offset at the first guess, corrected once for a guess on the other side of a change.
  let t = wall - (etWall(wall) - wall);
  t = wall - (etWall(t) - t);
  return isoSeconds(t);
}

export function addDays(date, n) {
  if (!DATE.test(date)) throw new TypeError(`not a date: ${date}`);
  return new Date(Date.parse(`${date}T00:00:00Z`) + n * DAY).toISOString().slice(0, 10);
}

/** 0 Sunday to 6 Saturday. */
export function weekday(date) {
  if (!DATE.test(date)) throw new TypeError(`not a date: ${date}`);
  return new Date(`${date}T00:00:00Z`).getUTCDay();
}

export function daysBetween(a, b) {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY);
}

/** Problems of a holiday table (section 17.9); an empty list means it can be used. */
export function holidayTableProblems(table) {
  const problems = [];
  if (table?.schema !== 'rmf.econ.holidays/1') return ['holiday table: schema is not rmf.econ.holidays/1'];
  if (!['verified', 'fixture'].includes(table.status)) problems.push('holiday table: status must be verified or fixture');
  if (typeof table.source !== 'string' || table.source === '') problems.push('holiday table: source missing');
  if (!DATE.test(table.checked ?? '')) problems.push('holiday table: checked is not a date');
  const [first, last] = Array.isArray(table.years) ? table.years : [];
  if (!Number.isInteger(first) || !Number.isInteger(last) || first > last) problems.push('holiday table: years must be [first, last]');
  const days = Array.isArray(table.holidays) ? table.holidays : [];
  if (!Array.isArray(table.holidays)) problems.push('holiday table: holidays missing');
  days.forEach((d, i) => {
    if (!DATE.test(d)) problems.push(`holiday table: ${d} is not a date`);
    else {
      const y = Number(d.slice(0, 4));
      if (y < first || y > last) problems.push(`holiday table: ${d} is outside years ${first} to ${last}`);
      if ([0, 6].includes(weekday(d))) problems.push(`holiday table: ${d} is a weekend day`);
      if (i > 0 && days[i - 1] >= d) problems.push(`holiday table: ${d} is not after ${days[i - 1]}`);
    }
  });
  return problems;
}

/**
 * Business-day arithmetic over a holiday table. Every question about a date in a year the
 * table does not cover throws: an uncovered year is unknown, never "no holidays".
 */
export function makeCalendar(table) {
  const problems = holidayTableProblems(table);
  if (problems.length) throw new TypeError(problems.join('; '));
  const holidays = new Set(table.holidays);
  const [first, last] = table.years;
  const covered = (date) => {
    const y = Number(date.slice(0, 4));
    return y >= first && y <= last;
  };
  const isBusinessDay = (date) => {
    if (!DATE.test(date)) throw new TypeError(`not a date: ${date}`);
    if (!covered(date)) throw new RangeError(`holiday table does not cover ${date} (years ${first} to ${last})`);
    const w = weekday(date);
    return w !== 0 && w !== 6 && !holidays.has(date);
  };
  const nextBusinessDay = (date) => {
    let d = addDays(date, 1);
    while (!isBusinessDay(d)) d = addDays(d, 1);
    return d;
  };
  /** The date n business days after `date` (n at least 0; `date` itself need not be one). */
  const addBusinessDays = (date, n) => {
    let d = date;
    for (let i = 0; i < n; i += 1) d = nextBusinessDay(d);
    return d;
  };
  return { status: table.status, covered, isBusinessDay, nextBusinessDay, addBusinessDays, publicationDay: nextBusinessDay };
}

/** The fourth Tuesday of a month (year, month 1 to 12) as a date. */
export function fourthTuesday(year, month) {
  const firstDay = `${year}-${String(month).padStart(2, '0')}-01`;
  const offset = (2 - weekday(firstDay) + 7) % 7;
  return addDays(firstDay, offset + 21);
}

/** The first fourth Tuesday strictly after a date (the H.6 release rule, section 14.2). */
export function nextFourthTuesdayAfter(date) {
  let y = Number(date.slice(0, 4));
  let m = Number(date.slice(5, 7));
  for (;;) {
    const t = fourthTuesday(y, m);
    if (t > date) return t;
    m += 1;
    if (m === 13) {
      m = 1;
      y += 1;
    }
  }
}

/** The last day of the previous calendar quarter of a date, and that quarter's first day. */
export function previousQuarter(date) {
  const y = Number(date.slice(0, 4));
  const q = Math.floor((Number(date.slice(5, 7)) - 1) / 3);
  const startMonth = q * 3 + 1;
  const thisStart = `${y}-${String(startMonth).padStart(2, '0')}-01`;
  const end = addDays(thisStart, -1);
  const ps = q === 0 ? `${y - 1}-10-01` : `${y}-${String(startMonth - 3).padStart(2, '0')}-01`;
  return { start: ps, end };
}

export function addHours(iso, hours) {
  return isoSeconds(ms(iso) + hours * 3_600_000);
}

/** A snapshot id (YYYYMMDDTHHMMSSZ) from a stored time, and back. */
export function snapshotId(iso) {
  ms(iso);
  return iso.replace(/[-:]/g, '');
}
export function snapshotTime(id) {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(id);
  if (!m) throw new TypeError(`not a snapshot id: ${id}`);
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`;
}
