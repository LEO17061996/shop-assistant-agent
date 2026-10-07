// Copy eval results from the backend into the frontend so the /eval page is static
// and keeps working even when the API is asleep.
import { copyFileSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const src = join(import.meta.dirname, "..", "..", "backend", "eval", "results");
const publicDir = join(import.meta.dirname, "..", "public", "eval");
const dataDir = join(import.meta.dirname, "..", "data");

rmSync(publicDir, { recursive: true, force: true });
mkdirSync(publicDir, { recursive: true });
mkdirSync(dataDir, { recursive: true });

let runs = 0;
for (const file of readdirSync(src)) {
  if (!file.endsWith(".json")) continue;
  if (file === "summary.json") copyFileSync(join(src, file), join(dataDir, "eval-summary.json"));
  else if (file === "retrieval.json") copyFileSync(join(src, file), join(dataDir, "retrieval-eval.json"));
  else {
    copyFileSync(join(src, file), join(publicDir, file));
    runs++;
  }
}
console.log(`synced summary + ${runs} run files`);
