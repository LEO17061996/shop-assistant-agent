# Kestrel Home — web

Next.js 16 frontend for the shopping assistant: chat with the agent ledger (`/`), eval report (`/eval`), architecture notes (`/how-it-works`).

```bash
npm install
npm run dev -- --port 3210        # API expected at NEXT_PUBLIC_API_URL (default http://localhost:8077)
npm run sync-eval                 # copy backend/eval/results into data/ and public/eval/
```
