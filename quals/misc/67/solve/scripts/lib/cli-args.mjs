/** @param {string[]} argv */

export function hasFlag(argv, name) {
  return argv.includes(name);
}

export function flagValue(argv, name, fallback = null) {
  const index = argv.indexOf(name);
  if (index < 0) {
    return fallback;
  }
  const next = argv[index + 1];
  if (next === undefined || next.startsWith("--")) {
    return fallback;
  }
  return next;
}

/** Value only when the next token is a non-flag argument. */
export function optionalFlagValue(argv, name) {
  const index = argv.indexOf(name);
  if (index < 0) {
    return undefined;
  }
  const next = argv[index + 1];
  if (next === undefined || next.startsWith("--")) {
    return "";
  }
  return next;
}

export function firstFlagValue(argv, names, fallback = null) {
  for (const name of names) {
    const value = flagValue(argv, name);
    if (value !== null) {
      return value;
    }
  }
  return fallback;
}
