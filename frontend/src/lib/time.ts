export const toMillis = (iso: string): number => new Date(iso).getTime();

export const fmtHM = (iso: string): string => {
  const d = new Date(iso);
  const h = String(d.getUTCHours()).padStart(2, "0");
  const m = String(d.getUTCMinutes()).padStart(2, "0");
  return `${h}:${m}`;
};

export const fmtHMS = (iso: string): string => {
  const d = new Date(iso);
  const h = String(d.getUTCHours()).padStart(2, "0");
  const m = String(d.getUTCMinutes()).padStart(2, "0");
  const s = String(d.getUTCSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
};

export const fmtDateTime = (iso: string): string => {
  const d = new Date(iso);
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${fmtHMS(iso)} UTC`;
};

export const minutesSince = (iso: string, baseIso: string): number => {
  return (toMillis(iso) - toMillis(baseIso)) / 60000;
};
