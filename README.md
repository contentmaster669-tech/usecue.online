# Cue — ordering site

The marketing and checkout site for **Cue Honesty Check**, a one-time-purchase
Claude Skill that makes Claude audit its own draft for sycophancy and
hallucination. Live at `https://usecue.online`.

It is a static site: plain HTML, one stylesheet, no build step. Checkout and
file delivery are handled entirely by Lemon Squeezy.

## Files

| File | What it is |
|---|---|
| `site/index.html` | The landing + ordering page |
| `site/products.js` | **Product data** — name, price, tagline, checkout link |
| `site/styles.css` | All styles; the colour palette is at the top |
| `site/privacy.html` | Privacy Policy (draft placeholder) |
| `site/terms.html` | Terms of Service (draft placeholder) |
| `vercel.json` | Serves `site/` as static files, with clean URLs (`/privacy`) |

## Common edits

- **Price, name or checkout link** → `site/products.js`. Nothing else in the
  site hardcodes them.
- **Colours** → the `:root` block at the top of `site/styles.css`.
- **Demo video** → `site/index.html`, search for `DEMO VIDEO GOES HERE`.
- **Add a second product** → append an entry to `PRODUCTS` in
  `site/products.js`, then build the card list where `index.html` says
  `MORE PRODUCTS`.

## Run locally

```bash
cd site
python -m http.server 8765
# open http://127.0.0.1:8765
```

Any static file server works. Note that `/privacy` (without `.html`) only
resolves on Vercel, where `cleanUrls` is on; the site itself links to
`privacy.html`, which works everywhere.

## Deploy

```bash
vercel --prod
```
