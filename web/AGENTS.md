<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Frontend handoff

Read `../docs/web.md` before changing the landing page or `/vi-sao`. It documents routes, typography, benchmark provenance, sample media setup, verification, and build cache pitfalls. Keep benchmark values source-driven and preserve the current unproven conclusion. `ReviewPerspective` contains evaluation criteria, not customer testimonials. Generated media under `public/mock-media/` stays ignored. The landing showcase uses curated, tracked assets under `public/demo/showcase/`; keep its manifest and attribution and verify every referenced asset exists in a clean checkout.
