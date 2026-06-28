# Systembolaget distance map

An interactive map of every Systembolaget store in Sweden, with a
**"distance to nearest Systembolaget"** overlay: each point on the map is
coloured by how far it is from the closest store (green = near, red = far).

It's a self-contained static site — no build step, no backend — designed to
deploy to GitHub Pages.

## What's here

| File | Purpose |
|------|---------|
| `index.html` | Page shell + control panel |
| `app.js` | Leaflet map, the canvas distance-field overlay, store markers, click-to-measure |
| `style.css` | Styling for the panel and legend |
| `data/stores.json` | The store network (id, name, address, lat/lon) — committed so the site works with no API call |
| `fetch_stores.py` | Regenerates `data/stores.json` from the Systembolaget API |

## How the overlay works

For a grid of screen cells, `app.js` samples the lat/lon at each cell centre
and computes the great-circle (haversine) distance to the nearest of the ~450
stores, then paints the cell on a green→red colormap. It recomputes whenever
the map settles, so the field stays accurate at every zoom level. Click
anywhere to get the exact distance and the name of the nearest store.

## Data source

Store coordinates come from Systembolaget's public site-search endpoint
(`GET /v1/sitesearch/site?q=`), documented in
[`../wine-guide/api-docs/systembolaget/api.md`](../wine-guide/api-docs/systembolaget/api.md)
(claim C074 — an empty query returns the whole network). Only Systembolaget's
own stores are kept; third-party agents (`isAgent=true`) are dropped.

To refresh the data:

```bash
cd systembolaget-map
python3 fetch_stores.py   # needs `requests`; rewrites data/stores.json
```

## Local preview

`app.js` loads `data/stores.json` via `fetch()`, so open it through a local
web server rather than `file://`:

```bash
cd systembolaget-map
python3 -m http.server 8000
# then open http://localhost:8000/
```

## Deployment

`.github/workflows/deploy-pages.yml` publishes this directory to GitHub Pages
on every push to `main` that touches `systembolaget-map/`. Enable it once under
**Settings → Pages → Build and deployment → Source: GitHub Actions**.
