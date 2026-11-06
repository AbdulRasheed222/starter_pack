// Fails when a language file is missing a key from en.json, has one en.json doesn't, or drops
// a {placeholder}. Run in CI so a new string can't ship untranslated.
import { readFileSync, readdirSync } from "node:fs";

const dir = new URL("../messages/", import.meta.url);
const load = (name) => JSON.parse(readFileSync(new URL(name, dir), "utf8"));
const placeholders = (text) => [...text.matchAll(/{(\w+)}/g)].map((m) => m[1]).sort().join(",");

const en = load("en.json");
const problems = [];
for (const file of readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "en.json")) {
  const other = load(file);
  for (const key of Object.keys(en)) {
    if (!(key in other)) problems.push(`${file}: missing "${key}"`);
    else if (placeholders(en[key]) !== placeholders(other[key]))
      problems.push(`${file}: "${key}" should use {${placeholders(en[key])}}`);
  }
  for (const key of Object.keys(other)) {
    if (!(key in en)) problems.push(`${file}: "${key}" is not in en.json`);
  }
}
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
console.log("Messages match en.json.");
