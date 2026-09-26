/** "transform.join_region_lookup" -> "Join region lookup" */
export function humanize(name) {
  const last = name.split('.').pop().replace(/\[(.*)\]/, ' ($1)').replace(/_/g, ' ');
  return last.charAt(0).toUpperCase() + last.slice(1);
}

export function formatDateTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }) + ' UTC';
}

export function durationBetween(a, b) {
  const s = Math.round((new Date(b) - new Date(a)) / 1000);
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;
export const isValidEmail = (e) => typeof e === 'string' && EMAIL_RE.test(e);
export const isBlank = (v) => v === null || v === undefined || String(v).trim() === '';

/** "[validation.null_customer_id] 1 row has..." -> { id: 'validation.null_customer_id', text: '1 row has...' } */
export function parseCited(line) {
  const m = String(line).match(/^\s*\[([^\]]+)\]\s*(.*)$/s);
  return m ? { id: m[1], text: m[2] } : { id: null, text: String(line) };
}

export const isFailed = (check) => check.status !== 'PASSED';

/** validation_results as a name -> CheckResult map */
export const byName = (checks) => Object.fromEntries(checks.map((c) => [c.name, c]));
