# NEXUS marketing site

A standalone landing site for NEXUS: home page, pricing, docs and a live status page.
It is separate from the NEXUS app in `../frontend` and has no backend of its own.

Stack: React 19 + TypeScript + Vite + Tailwind CSS 4 + React Router.

```bash
cd site
npm install
npm run dev        # http://127.0.0.1:5180
npm run build      # type-check + production build into dist/
npm run preview    # serve dist/ on http://127.0.0.1:4180
```

## Pages

| Route | What it is |
|---|---|
| `/` | Hero with a live product mockup, integrations, features, privacy model, setup steps, example commands, pricing, FAQ |
| `/pricing` | Plan cards, comparison table, billing FAQ |
| `/docs` | Getting-started guide condensed from the project docs |
| `/status` | Checks a running NEXUS backend (`/api/health`, `/api/system/status`) straight from the browser |

## Editing content

All copy, links, plans and prices are in [`src/content.ts`](src/content.ts).

- **Prices and checkout links are placeholders.** Set `pricing.currency`, each plan's `price`, and
  `checkoutUrl` (a Stripe, Lemon Squeezy or Gumroad payment link). While `checkoutUrl` is empty the button
  sends visitors to the install guide.
- `site.appUrl` is where "Open app" goes (a hosted NEXUS frontend, or the local dev server).
- `site.communityUrl` / `site.contactEmail` show extra footer links when set.

Design tokens (colours, fonts, glows, animations) are in [`src/index.css`](src/index.css).

## Status page and CORS

The status page calls your backend from the visitor's browser, so the backend must allow the site's origin.
Add it to `CORS_ORIGINS` in the backend `.env`, e.g. `CORS_ORIGINS=http://127.0.0.1:5180`. In local mode the
backend only listens on `127.0.0.1`, so the check only works from the same machine.

## Deploying

`npm run build` outputs a static site in `dist/`. It uses client-side routing, so the host must serve
`index.html` for unknown paths: `public/_redirects` covers Netlify and Cloudflare Pages, and `vercel.json`
covers Vercel.
