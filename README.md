# Smart Fridge Companion App

A cost-effective, browser-based alternative to expensive smart refrigerators. Smart Fridge Companion App (built as **Pantry Ledger**) helps you track what's in your kitchen, avoid food waste, and get recipe ideas from what you already have — no hardware, no subscription, no backend required.

## Why this exists

Commercial smart fridges solve food-waste tracking with built-in cameras and sensors, but they cost thousands of dollars and require buying an entirely new appliance. This project delivers the same core value — inventory tracking, expiry alerts, and recipe suggestions — as a free, single-file web app that runs in any modern browser and works on the fridge you already own.

## Features

- **Inventory management (CRUD)** — add, edit, delete, search, and filter pantry items
- **Expiry tracking** — color-coded status (fresh / expiring soon / expired) with an at-a-glance dashboard
- **Multiple input methods**
  - 📷 **QR code scanning** — live camera decoding via `jsQR`
  - 🏷️ **Label scanning (OCR)** — capture or upload a photo of a package label; text is extracted via `Tesseract.js`
  - 🎙️ **Voice input** — describe an item out loud (e.g. *"Add three apples, expires in six days"*) using the Web Speech API
  - ⌨️ Manual entry
- **Recipe recommendations** — matches your current (non-expired) inventory against a built-in recipe database, ranks by ingredient coverage, and highlights recipes that use ingredients about to expire
- **Dashboard** — category breakdown chart, expiry stats, and a "needs attention" list
- **Local persistence** — your data is saved automatically between visits, no account or server needed
- **Toast notifications** — get alerted on load if anything is expired or expiring soon

## Tech stack

Pure client-side, single HTML file:

- Vanilla HTML / CSS / JavaScript (no framework, no build step)
- [jsQR](https://github.com/cozmo/jsQR) — QR code decoding
- [Tesseract.js](https://github.com/naptha/tesseract.js) — OCR for label scanning
- [Chart.js](https://www.chartjs.org/) — dashboard visualizations
- Web Speech API — voice input (browser-native)

## Getting started

### Run it locally

No installation required. Just open the file in a modern browser:

```bash
git clone https://github.com/<your-username>/smart-fridge-companion-app.git
cd smart-fridge-companion-app
open index.html   # or double-click the file
```

> Camera and microphone access require a secure context. Opening the file directly (`file://`) works in most browsers for local testing, but for full camera/mic support (especially on mobile) serve it over `https://` or `localhost`.

### Serve locally (recommended for camera/mic testing)

```bash
# Python
python3 -m http.server 8000

# Node
npx serve .
```

Then visit `http://localhost:8000`.

### Deploy for free with GitHub Pages

1. Push this repo to GitHub.
2. Go to **Settings → Pages**.
3. Under "Build and deployment", set **Source** to `Deploy from a branch`, branch `main`, folder `/ (root)`.
4. Your app will be live at `https://<your-username>.github.io/smart-fridge-companion-app/`.

## Browser support

| Feature | Requirement |
|---|---|
| QR scanning | Camera access (Chrome, Edge, Safari on HTTPS) |
| Label OCR | Camera or file upload — works everywhere |
| Voice input | `SpeechRecognition` support (best in Chrome; limited/no support in Firefox) |
| Everything else | Any modern browser |

## Project structure

```
smart-fridge-companion-app/
├── index.html      # the entire application
├── README.md
├── LICENSE
└── .gitignore
```

## Roadmap ideas

- Push/browser notifications instead of in-tab toasts
- Barcode (UPC) lookup against an open food database, in addition to QR
- Expandable recipe database or an API-backed recipe search
- Export/import inventory as CSV
- Multi-user / cloud sync backend

## License

MIT — see [LICENSE](LICENSE).
