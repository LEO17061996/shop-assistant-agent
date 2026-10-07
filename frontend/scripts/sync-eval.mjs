// Copy eval results from the backend into the frontend so the /eval page is static
// and keeps working even when the API is asleep.
import { copyFileSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const src = join(import.meta.dirname, "..", "..", "backend", "eval", "results");
const publicDir = join(import.meta.dirname, "..", "public", "eval");
const dataDir = join(import.meta.dirname, "..", "data");

// Files read by pages at build time; everything else is an agent run loaded on demand
const DATA_FILES = {
  "summary.json": "eval-summary.json",
  "retrieval.json": "retrieval-eval.json",
  "studio.json": "studio-eval.json",
  "image_baseline.json": "image-baseline.json",
};

rmSync(publicDir, { recursive: true, force: true });
mkdirSync(publicDir, { recursive: true });
mkdirSync(dataDir, { recursive: true });

let runs = 0;
for (const file of readdirSync(src)) {
  if (!file.endsWith(".json")) continue;
  if (DATA_FILES[file]) copyFileSync(join(src, file), join(dataDir, DATA_FILES[file]));
  else {
    copyFileSync(join(src, file), join(publicDir, file));
    runs++;
  }
}
console.log(`synced ${Object.keys(DATA_FILES).length} data files + ${runs} run files`);
