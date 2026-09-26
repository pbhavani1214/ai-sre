/** "evidence_collection" -> "Evidence collection" (last dotted segment only) */
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

/** "[validation.not_null.001] row 3 ..." -> { id: 'validation.not_null.001', text: 'row 3 ...' } */
export function parseCited(line) {
  const m = String(line).match(/^\s*\[([^\]]+)\]\s*(.*)$/s);
  return m ? { id: m[1], text: m[2] } : { id: null, text: String(line) };
}

export function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const DATABASE_LABEL = { sqlite: 'SQLite' };
/** "sqlite" -> "SQLite"; unknown types are shown as returned. */
export const databaseLabel = (type) => DATABASE_LABEL[type] ?? type;
