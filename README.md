# Kenya Policy Pressure Index (KPPI) — v2

A composite political-economic stress indicator for Kenya.  
Runs weekly, stores results in SQLite, and emails a rich HTML summary.

---

## What it measures

KPPI blends five normalised pressure signals into a single score **0–100**:

| Component | Weight | Source |
|-----------|--------|--------|
| Inflation (CPI % YoY) | 25% | World Bank Open Data |
| FX Rate (KES/USD depreciation) | 20% | Open ExchangeRate API |
| Bond / T-bill yield (91-day) | 20% | Central Bank of Kenya (CBK) |
| Market stress (NASI index) | 15% | NSE Insider |
| Political event pressure | 20% | Google News RSS + GDELT (blended) |

### Score tiers

| Score | Tier | Meaning |
|-------|------|---------|
| 0–30 | 🟢 Low | Stable |
| 30–50 | 🟡 Moderate | Watch |
| 50–70 | 🟠 High | Elevated |
| 70–85 | 🔴 Severe | Compounding stress |
| 85–100 | 🚨 Crisis | Acute instability |

Each run also reports a **data confidence score** (0–100%) indicating how many
indicators came from live vs. fallback vs. mock sources, and whether the
political signal had a single or blended source.

---

## Features

- **Zero required API keys** — all primary sources are free and open
- **Graceful degradation** — every indicator has a fallback chain; the index
  still computes if one source is down
- **4-week political moving average** — smooths weekly news spikes
- **Data confidence scoring** — flags mock/fallback sources so you know how
  reliable each run is
- **Weekly email summary** — rich HTML report with progress bars, confidence
  indicator, and smoothed political trend
- **SQLite persistence** — full history stored locally; exportable to CSV
- **Streamlit dashboard** — local web UI for visualising history
- **macOS launchd scheduler** — runs automatically every Sunday at 08:00

---

## Project structure

```
kppi_project/
├── src/kppi/
│   ├── config.py               # Pydantic-settings config (env-driven)
│   ├── data/
│   │   ├── fetchers/
│   │   │   ├── base.py         # Abstract BaseFetcher + IndicatorReading
│   │   │   ├── worldbank.py    # Inflation (World Bank) + CBK T-bill scraper
│   │   │   ├── exchangerate.py # KES/USD rate (Open ExchangeRate API)
│   │   │   ├── gdelt.py        # Political pressure - dual-query GDELT Doc API
│   │   │   ├── kenya_news.py   # Political pressure - Google News RSS (Kenya)
│   │   │   ├── nasi.py         # NASI index from NSE Insider
│   │   │   └── mock.py         # Synthetic demo data
│   │   └── pipeline.py         # Orchestrates all fetchers with fallbacks
│   ├── index/
│   │   ├── normalizer.py       # Per-indicator 0-100 piecewise normalisation
│   │   └── calculator.py       # Weighted composite + tier + confidence scoring
│   ├── storage/
│   │   └── database.py         # SQLite persistence with schema migrations
│   ├── scheduler/
│   │   └── jobs.py             # Run-once + APScheduler periodic refresh
│   ├── notifications/
│   │   └── email.py            # HTML weekly summary via Gmail SMTP
│   └── dashboard/
│       └── app.py              # Streamlit dashboard
├── tests/
│   ├── test_fetchers.py
│   ├── test_index.py
│   └── test_storage.py
├── data/                       # SQLite DB lives here (git-ignored)
├── logs/                       # Rotating log files (git-ignored)
├── .env.example                # Template - copy to .env and fill in
└── run.py                      # CLI entrypoint
```

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/kenya-policy-pressure-index.git
cd kenya-policy-pressure-index
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env - minimum required: nothing! All defaults work out of the box.
# Optional: add EMAIL_ENABLED=true + Gmail App Password for weekly emails.
```

### 3. Run

```bash
# One-shot live fetch + compute + save
python run.py once

# Demo with mock data (no network required)
USE_MOCK_DATA=true python run.py once

# Launch Streamlit dashboard
python run.py dashboard

# Install weekly macOS launchd job (Sundays 08:00)
python run.py setup-weekly

# Export history to CSV
python run.py export
```

---

## Email notifications

Set these in `.env` to receive a weekly HTML summary:

```env
EMAIL_ENABLED=true
EMAIL_TO=you@gmail.com
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-gmail-app-password   # NOT your login password
```

Create a Gmail App Password at https://myaccount.google.com/apppasswords
(2-Step Verification must be enabled first).

---

## Political pressure methodology

The political component blends two no-key sources:

| Source | Weight | What it captures |
|--------|--------|-----------------|
| Google News RSS (Kenya) | 60% | Kenya-specific article volume, recency, and severity keywords |
| GDELT Doc API v2 | 40% | Global news tone + conflict event volume |

**Google News score** = 40% volume (saturating curve) + 40% keyword severity + 20% recency  
**GDELT score** = 40% article volume + 40% negative tone + 20% Kenya-actor specificity

A 4-week moving average is stored alongside the raw political score to reduce
the effect of single-week news spikes.

If only one source is available, confidence is penalised by 8%.

---

## Configuration reference

All settings can be overridden via environment variables or `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MOCK_DATA` | `false` | Use synthetic data instead of live APIs |
| `DB_PATH` | `data/kppi.db` | SQLite database path |
| `UPDATE_INTERVAL_HOURS` | `168` | Scheduler interval (168 = weekly) |
| `EXCHANGERATE_API_KEY` | *(empty)* | Optional - free tier works without it |
| `EMAIL_ENABLED` | `false` | Enable weekly email summaries |
| `EMAIL_TO` | *(empty)* | Recipient address |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port (STARTTLS) |
| `SMTP_USER` | *(empty)* | Sender Gmail address |
| `SMTP_PASSWORD` | *(empty)* | Gmail App Password |
| `WEIGHT_INFLATION` | `0.25` | Index weight for inflation |
| `WEIGHT_FX` | `0.20` | Index weight for FX rate |
| `WEIGHT_BOND` | `0.20` | Index weight for bond yield |
| `WEIGHT_MARKET_STRESS` | `0.15` | Index weight for market stress |
| `WEIGHT_POLITICAL` | `0.20` | Index weight for political pressure |

---

## Running tests

```bash
pytest tests/ -q
```

---

## Data sources

All sources are free and require no API key:

| Indicator | Source |
|-----------|--------|
| CPI Inflation | World Bank Open Data |
| KES/USD FX rate | Open ExchangeRate API |
| 91-day T-bill rate | Central Bank of Kenya |
| NASI index | NSE Insider |
| Political news | Google News RSS |
| Political sentiment | GDELT Project |

---

## License

MIT
