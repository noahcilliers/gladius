# Gladius landing page

Static HTML, no build step. The whole site is one self-contained `index.html`: big ASCII sword hero, a short pitch, the LoRA specialists, clone command, link.

## Preview locally

```bash
python3 -m http.server 4173 --directory site
```

## Deploy to Vercel

Dashboard: import the repo, set **Root Directory** to `site`, set **Framework Preset** to *Other*, and leave the build command empty.

CLI:

```bash
npx vercel site --prod
```

The page copy (numbers, clone URL, requirements) is hardcoded in `index.html`. If the benchmarks or install steps change, update them there.
