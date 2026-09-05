# Deploy

The marketing site for [HerAndHim](https://github.com/ericwang915/HerAndHim) —
a static Astro build hosted on **Cloudflare Pages**, project `clawsoul`
(the project predates the rename and keeps its old name — `herandhim.ai` is attached to it).

- Production: https://herandhim.ai (also https://clawsoul.pages.dev)
- Cloudflare account: run `npm run cf:whoami` to see which account you're authed against

## Local

```bash
cd frontend
npm install
npm run dev        # http://localhost:4321
npm run build      # static output in dist/
```

## One-shot deploy (from your machine)

```bash
npm run deploy     # astro build + wrangler pages deploy dist --project-name=clawsoul
```

Wrangler needs to be authed on this machine. If it isn't:

```bash
npm run cf:login   # opens the browser
npm run cf:whoami  # confirm the account
```

Deploys land on the existing `clawsoul` project, which already serves herandhim.ai —
so don't create a second project unless you also move the custom domains.

## Auto-deploy on git push (recommended)

The site now lives in the repo at `frontend/`, so Cloudflare can build it directly:

1. CF dashboard → **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**
2. Pick `ericwang915/HerAndHim`, then set:
   - Production branch: `main`
   - Build command: `npm run build`
   - Output directory: `dist`
   - Root directory: `frontend`
3. Every push to `main` rebuilds; PRs get their own preview URL.

Once Git deploys are live, drop the manually-uploaded project (or keep one and
rename the other) so two projects aren't serving the same source.

## Custom domain

1. Put the domain on Cloudflare (nameservers → Cloudflare).
2. Dashboard → **Workers & Pages** → `clawsoul` → **Custom domains** → **Set up a custom domain**
3. Enter `herandhim.ai`. Cloudflare creates the CNAME on the same account — done.

`astro.config.mjs` already sets `site: 'https://herandhim.ai'`, which is what
canonical URLs and the OG image URL are built from. Change it there if the
domain changes.

## What ships

- `dist/` — static HTML/CSS/JS from Astro; no server, no API, no data collection
- `public/_headers` — security + cache headers (HSTS, X-Frame-Options, …)
- `public/selfies/`, `public/demo/` — sample images copied from the repo's `assets/`

## Rollback

```bash
npx wrangler pages deployment list --project-name=clawsoul
```

Or dashboard → Pages → `clawsoul` → **Deployments** → **Rollback** on any older build.
