import os
from flask import Flask, render_template
from flask_cors import CORS
from flask import Flask, render_template, request, jsonify
from urllib.parse import urljoin, urlparse
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
import requests, json, time, re
from flask import Flask, render_template, request, jsonify
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

print("TEMPLATE PATH:", TEMPLATE_DIR)  # debug

app = Flask(__name__, template_folder=TEMPLATE_DIR)
RESULTS_FILE = "results.json"

# @app.route("/")
# def index():
#     return render_template("index.html")
# ─────────────────────────────────────────────
# SCRAPING HELPERS
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TARGET_KEYWORDS = [
    "about", "contact", "services", "service", "solutions", "team"
]


def fuzzy_score(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def is_relevant_link(href):
    if not href:
        return False
    path = urlparse(href).path.lower().strip("/")
    segments = path.split("/")
    for seg in segments:
        for kw in TARGET_KEYWORDS:
            if fuzzy_score(seg, kw) > 0.75 or kw in seg:
                return True
    return False

def clean_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer",
                      "nav", "aside", "form", "iframe", "svg", "img",
                      "meta", "link", "button", "input"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 30]
    return "\n".join(lines[:150])  # token limit

def get_sitemap_urls(base_url):
    urls = []
    for path in ["/sitemap.xml", "/sitemap_index.xml"]:
        try:
            r = requests.get(base_url.rstrip("/") + path, headers=HEADERS, timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, "xml")
                locs = [t.text for t in soup.find_all("loc")]
                urls.extend(locs)
                break
        except Exception:
            pass
    return urls

def discover_relevant_urls(base_url):
    relevant = [base_url]
    try:
        # Approach 1: sitemap
        sitemap_urls = get_sitemap_urls(base_url)
        if sitemap_urls:
            relevant += [u for u in sitemap_urls if is_relevant_link(u)][:5]
            return relevant[:6]

        # Approach 2: crawl homepage links
        r = requests.get(base_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if urlparse(href).netloc == urlparse(base_url).netloc:
                if is_relevant_link(href) and href not in relevant:
                    relevant.append(href)
            if len(relevant) >= 6:
                break
    except Exception:
        pass

    # Approach 3: guess common paths
    for kw in ["about", "contact", "services"]:
        guess = base_url.rstrip("/") + "/" + kw
        if guess not in relevant:
            relevant.append(guess)

    return relevant[:6]

def scrape_url(url, retries=2):
    for attempt in range(retries):
        try:
            time.sleep(1 + attempt)
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return clean_html(r.text)
        except Exception:
            pass
    return ""

def scrape_company(base_url):
    urls = discover_relevant_urls(base_url)
    combined = ""
    for url in urls:
        chunk = scrape_url(url)
        if chunk:
            combined += f"\n\n[PAGE: {url}]\n{chunk}"
        if len(combined) > 12000:
            break
    return combined[:12000]

# ─────────────────────────────────────────────
# AI ENRICHMENT
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a B2B research analyst. Extract structured company data from scraped website text.

CRITICAL RULES:
- NEVER fabricate or hallucinate contact details (emails, phone numbers, addresses).
- Only return data explicitly found in the provided text.
- If a field is not found, return "" (empty string) or [] (empty array) for arrays.
- Return ONLY valid JSON — no markdown, no explanation, no preamble.
- For outreach_opener: write a personalized 1-2 sentence cold outreach message using real info.
- For probable_pain_point: infer from their services/industry, not from thin air.
"""

USER_PROMPT_TEMPLATE = """Based on the website content below, extract the following fields as a JSON object:

{{
  "website_name": "short brand/site name",
  "company_name": "full legal or trade name",
  "address": "physical address if found, else ''",
  "mobile_number": "phone number if found, else ''",
  "mail": ["array of email addresses found"],
  "core_service": "primary service or product offering",
  "target_customer": "who they sell to",
  "probable_pain_point": "likely challenge their customers face",
  "outreach_opener": "personalized cold outreach opener"
}}

WEBSITE CONTENT:
{content}

URL: {url}
"""

def enrich_with_ai(url, scraped_text):
    return {
        "website_name": urlparse(url).netloc,
        "company_name": urlparse(url).netloc,
        "address": "",
        "mobile_number": "",
        "mail": [],
        "core_service": scraped_text[:100] if scraped_text else "Website services",
        "target_customer": "Businesses",
        "probable_pain_point": "Need better online presence",
        "outreach_opener": "We can help improve your business visibility online.",
        "source_url": url
    }
# ─────────────────────────────────────────────
# STORAGE
# ─────────────────────────────────────────────

def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_result(data):
    results = load_results()
    # Update if URL already exists
    for i, r in enumerate(results):
        if r.get("source_url") == data.get("source_url"):
            results[i] = data
            break
    else:
        results.append(data)
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/enrich", methods=["POST"])
def enrich():
    body = request.get_json(force=True)
    url = body.get("url", "").strip()
    website_name = body.get("website_name", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    if not url.startswith("http"):
        url = "https://" + url

    try:
        scraped = scrape_company(url)
        result = enrich_with_ai(url, scraped)

        # Override website_name if user provided it
        if website_name:
            result["website_name"] = website_name

        save_result(result)
        return jsonify(result), 200

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI returned invalid JSON: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/results", methods=["GET"])
def results():
    return jsonify(load_results()), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
