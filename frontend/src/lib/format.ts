/** Convert snake_case to camelCase: "set_temperature" → "setTemperature". */
export const snakeToCamel = (s: string): string =>
  s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

/** Convert snake_case to Title Case: "set_temperature" → "Set Temperature". */
export const snakeToTitleCase = (s: string): string =>
  s
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
