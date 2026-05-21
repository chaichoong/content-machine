# Dream 100 Accountants Tracker

A single-page web app for running an Operations Director Dream 100 outreach pipeline. UK SME-focused accountancy firms, tiered A/B/C, four-touch sequence, status tracking, funnel chart.

Built for [Operations Director](https://operationsdirector.co.uk) by Kevin Brittain.

## What it does

- Lists 100 firm slots, pre-seeded with 20 real UK SME-focused accountancy firms.
- Tier scoring (A, B, C, unscored).
- Status pipeline: To source, Researched, Touch 1 to 4 sent, Replied, Booked, Signed, Dead, Paused.
- Inline editing of status, owner, last-touch date, notes.
- Filters by tier, status, owner. Live text search.
- Funnel chart, tier doughnut, next-actions panel.
- Add new firms via the UI. Import or export CSV.
- All edits save in the browser (localStorage). No backend. No tracking.

## Data and privacy

This app has no server. Three storage facts:

1. The seed list of firms ships inside `seed.js` and is identical for every visitor.
2. Your status changes, notes, last-touch dates and any firms you add through the UI are saved in your own browser only.
3. Nothing is sent to a server, no cookies, no analytics.

The seed file contains only firm names and public website URLs. Add personal contact details (decision maker names, emails) via the app UI so they stay local to your browser.

## Local preview

No build step. Open `index.html` in a browser.

```
git clone https://github.com/YOUR-USERNAME/dream100-tracker.git
cd dream100-tracker
open index.html
```

Or serve it locally:

```
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Deploy to GitHub Pages

Follow these steps to publish at `https://YOUR-USERNAME.github.io/dream100-tracker/`.

1. Create a new public repository on GitHub called `dream100-tracker`.
2. Push the contents of this folder:

   ```
   git init
   git add .
   git commit -m "Initial commit: Dream 100 tracker v1.0"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/dream100-tracker.git
   git push -u origin main
   ```

3. In the GitHub repo, go to Settings, then Pages.
4. Under Source, pick "GitHub Actions".
5. The included workflow at `.github/workflows/pages.yml` will build and publish the site on every push to `main`.
6. After the first deploy, the URL appears in the Pages settings panel.

### Custom domain

To use `dream100.operationsdirector.co.uk`:

1. In the repo, add a `CNAME` file with the single line `dream100.operationsdirector.co.uk`.
2. In your DNS provider, add a CNAME record from `dream100` to `YOUR-USERNAME.github.io`.
3. Wait for DNS propagation, then enable HTTPS in Settings, Pages.

## How to add firms

Two routes.

**Route A. Via the app UI (browser-local).** Best for live tracking. Use the Add row at the bottom of the firms table. Status, notes and contact data stay in your browser.

**Route B. Via the seed file (shared).** Best for canonical seed data shared with the team. Edit `seed.js`, push to `main`, GitHub Pages redeploys automatically.

Seed file shape:

```js
window.DREAM100_SEED = [
  {
    tier: "A",                  // A, B, C, or ?
    firm: "Example Accountants",
    web: "https://example.co.uk",
    region: "South East",
    city: "London",
    staff: "10-20",
    niche: "SME, owner-managed",
    stack: "Xero, modern",
    title: "Managing Partner",
    owner: "Kevin",
    notes: "Strong advisory positioning",
  },
];
```

## File structure

```
dream100-tracker/
├── index.html              # The app (UI + logic)
├── seed.js                 # Canonical firm seed list (edit to update)
├── README.md               # This file
├── LICENSE                 # MIT
├── .gitignore
└── .github/
    └── workflows/
        └── pages.yml       # Auto-deploy to GitHub Pages on push to main
```

## Browser support

Tested on Chrome, Safari, Edge, Firefox. Uses standard ES2017+ features, fetch, localStorage, Chart.js 4 from CDN.

## Roadmap (not yet built)

- Optional Supabase backend for multi-user sync across devices.
- Optional Airtable sync for live integration with the Operations Director base.
- Per-firm message log (Touch 1 sent date, Touch 2 sent date, etc).

## Source material

- Sales page: <https://launch.operationsdirector.co.uk/launch>
- Main site: <https://operationsdirector.co.uk>
- Companion documents:
  - `Dream100_Accountants.xlsx` (full spreadsheet with tier criteria and sourcing methodology)
  - `Dream100_Sequence_Templates.docx` (four-touch templates)
  - `Accountant_Partner_Offer.docx` (affiliate partner offer doc)

## Licence

MIT. See `LICENSE`.
