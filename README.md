# LeadLens — Company Enrichment System

## Overview
LeadLens is a Flask-based web application that takes a company website URL, scrapes relevant content, and generates structured business insights such as core services, target customers, and outreach suggestions.

---

## Features

- Web scraping using BeautifulSoup
- Smart URL discovery (about/contact/services pages)
- Data extraction and cleaning
- Structured JSON output
- Simple web UI for interaction
- Local storage using results.json

---

## Project Structure

leadlens_submission/
│
├── app.py                # Flask backend
├── colab_pipeline.py     # CLI pipeline for testing
├── results.json          # Stores results (auto-created)
├── templates/
│   └── index.html        # Frontend UI
└── README.md

---

## How to Run

### 1. Install dependencies

pip install flask flask-cors requests beautifulsoup4

---

### 2. Run the application

python app.py

---

### 3. Open in browser

http://127.0.0.1:5001

---

## How It Works

1. User enters a company URL
2. System scrapes relevant pages
3. Extracts meaningful text content
4. Processes and structures the data
5. Displays insights in the UI

---

## Key Design Decisions

- Uses sitemap + link crawling + path guessing
- Cleans HTML by removing scripts, nav, footer
- Uses fuzzy matching to find relevant pages
- Limits text size for performance
- Ensures consistent JSON output format

---

## Future Improvements

- AI-based enrichment (LLM integration)
- Database integration
- Better contact information extraction
- Deployment to cloud
