# 🏙️ Muni Alerts

**Muni Alerts** is a FastAPI-based web app that aggregates and classifies municipal RFP/RFQ/bid opportunities across Central Ohio.  
It automates scraping from government procurement portals, stores structured results in SQLite, and delivers email digests.

---

## 🚀 Features

- Scrapes bid portals for:
  - City of Columbus
  - COTA
  - SWACO
  - CRAA
  - MORPC
  - Dublin Schools
  - Metro Parks
  - ...and more!
- Handles both HTML and PDF-based postings
- Uses Playwright + Requests + Selenium (depending on source)
- Stores all data in `muni_local.db`
- Generates production-style email digests via Mailtrap SMTP
- Async ingestion runner to update all municipalities
- Modular architecture (`app/ingest/municipalities/...`)

---

## 🧰 Tech Stack

| Layer | Tools |
|-------|-------|
| Backend | FastAPI, Uvicorn |
| Scraping | Requests, Selenium, Playwright |
| Database | SQLite (SQLAlchemy) |
| Mail | Mailtrap SMTP |
| Environment | Python 3.11+, Virtualenv, VS Code |

---

## 🧑‍💻 Local Setup

```bash
# clone the repo
git clone https://github.com/JMAlloway/muni.git
cd muni

# create a virtual environment
python -m venv .venv
.\.venv\Scripts\activate  # (Windows)

# install dependencies
pip install -r requirements.txt

# run the app
python -m app.main
