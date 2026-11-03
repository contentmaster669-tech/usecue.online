# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A static marketing + ordering site for **Cue Honesty Check**: a downloadable Claude Skill, sold once for $24.99, checked out and delivered by Lemon Squeezy. Domain: `usecue.online`.

This repo used to be an MCP server (the original Cue). All of that was removed; the history is in git before the "static ordering site" change. Do not reintroduce a backend: the Skill runs inside the buyer's Claude account, and Lemon Squeezy handles payment and delivery, so there is nothing for a server to do.

## Layout

```
site/index.html     landing + checkout page
site/products.js    product data — the ONLY place names, prices and checkout links live
site/styles.css     every style; palette variables at the top
site/privacy.html   placeholder legal page
site/terms.html     placeholder legal page
vercel.json         static hosting from site/, cleanUrls on
```

No build step, no package manager, no framework. Keep it that way unless there is a concrete reason.

## Rules that are easy to break

- **Product data comes from `products.js`.** `index.html` has empty `data-field="name|price|tagline"` elements and `data-buy` links that a small inline script fills from the featured product. Never type a price or checkout URL into the HTML — it will drift from the config. The `<title>` and meta description deliberately contain no price for the same reason.
- **Buy links must keep the `lemonsqueezy-button` class.** `lemon.js` (loaded `defer` from `app.lemonsqueezy.com`) turns those links into an in-page checkout overlay. The inline filler script runs before `lemon.js`, so links are populated by the time it scans the page. If you ever add buy links after page load, call `window.createLemonSqueezy()` afterwards.
- **Checkout URLs are `/checkout/buy/...` links from the product's Share panel.** Never use a `/checkout/?cart=...` URL — that is one buyer's cart.
- **Colours live only in `:root` in `styles.css`.** White/cream base, orange (`--color-primary`) for every action, teal (`--color-accent`) sparingly for badges, icons and dividers. Bright fill shades fail contrast as text, so text uses the separate `--color-primary-text` / `--color-accent-text` shades and buttons use dark `--color-on-primary` text. Keep every text pairing at WCAG AA.
- **Mobile:** tap targets are at least 44px (`--tap` is 48px for buttons). No horizontal scroll at 320px and up. Phones (`max-width: 40rem`) stack everything and make buttons full width.
- **Claude.ai only.** The product does not work in ChatGPT or other apps, and the copy says so plainly. Keep the "not affiliated with Anthropic" footer line.
- **No refund wording anywhere.** The owner chose not to state a refund policy on the site; do not add one without being asked.
- **Legal pages are drafts.** Highlighted `.todo` spans mark fields the owner must fill in.

## Brand

Typeface is JetBrains Mono (400/700, Google Fonts). The mark is a proofreader's caret with an orange dot — the dot is Cue's intervention. Copy is short, plain and honest about limits (e.g. "Will it catch every mistake?" → no).

## Adding a product

Append to `PRODUCTS` in `site/products.js`. The main page shows only `FEATURED_PRODUCT_ID`; the `MORE PRODUCTS` comment in `index.html` marks where a card list for the others belongs. It is not built yet.

## Commands

```bash
cd site && python -m http.server 8765   # local preview at http://127.0.0.1:8765
vercel --prod                           # deploy
```
