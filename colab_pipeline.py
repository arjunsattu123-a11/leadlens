# ============================================================
# LeadLens — AI Company Enrichment Pipeline
# Google Colab Notebook  (Run each cell top to bottom)
# ============================================================

# ── CELL 1: Install dependencies ────────────────────────────
# !pip install -q anthropic requests beautifulsoup4 lxml

# ── CELL 2: Imports & Config ────────────────────────────────
import json, re, time, os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from difflib import SequenceMatcher


# 🔑 Set your Anthropic API key here OR use an environment variable
# AI integration can be added here in future (e.g., LLM-based enrichment)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TARGET_KEYWORDS = [
    "about", "contact", "services", "service", "solutions",
    "team", "company", "who-we-are", "what-we-do"
]


# ── CELL 3: Scraping Utilities ──────────────────────────────

def fuzzy_score(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def is_relevant_link(href):
    if not href:
        return False
    path = urlparse(href).path.lower().strip("/")
    for seg in path.split("/"):
        for kw in TARGET_KEYWORDS:
            if fuzzy_score(seg, kw) > 0.75 or kw in seg:
                return True
    return False

def clean_html(html_content):
    """Strip HTML noise and return clean readable text."""
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer",
                      "nav", "aside", "form", "iframe", "svg", "img",
                      "meta", "link", "button", "input"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 30]
    return "\n".join(lines[:150])  # Token optimized

def get_sitemap_urls(base_url):
    """Approach 1: Extract URLs from sitemap."""
    for path in ["/sitemap.xml", "/sitemap_index.xml"]:
        try:
            r = requests.get(base_url.rstrip("/") + path, headers=HEADERS, timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, "xml")
                return [t.text for t in soup.find_all("loc")]
        except Exception:
            pass
    return []

def discover_relevant_urls(base_url):
    """Find up to 6 relevant pages using multiple strategies."""
    relevant = [base_url]

    # Approach 1: Sitemap
    sitemap_urls = get_sitemap_urls(base_url)
    if sitemap_urls:
        relevant += [u for u in sitemap_urls if is_relevant_link(u)][:5]
        return relevant[:6]

    # Approach 2: Crawl homepage links with fuzzy matching
    try:
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

    # Approach 3: Guess common path names
    for kw in ["about", "contact", "services"]:
        guess = base_url.rstrip("/") + "/" + kw
        if guess not in relevant:
            relevant.append(guess)

    return relevant[:6]

def scrape_url(url, retries=2):
    """Scrape a single URL with retry logic."""
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
    """Full scrape pipeline: discover → scrape → combine text."""
    urls = discover_relevant_urls(base_url)
    combined = ""
    for url in urls:
        chunk = scrape_url(url)
        if chunk:
            combined += f"\n\n[PAGE: {url}]\n{chunk}"
        if len(combined) > 12000:
            break
    return combined[:12000]


# ── CELL 4: AI Enrichment ───────────────────────────────────

SYSTEM_PROMPT = """You are a B2B research analyst. Extract structured company data from scraped website text.

CRITICAL RULES:
- NEVER fabricate or hallucinate contact details (emails, phone numbers, addresses).
- Only return data explicitly found in the provided text.
- If a field is not found, return "" (empty string) or [] for arrays.
- Return ONLY valid JSON — no markdown, no explanation, no preamble.
- For outreach_opener: write a personalized 1-2 sentence cold outreach using real info.
- For probable_pain_point: infer from their services/industry context."""

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
    """Send scraped text to Claude and get structured JSON."""
    if not scraped_text.strip():
        scraped_text = f"Could not scrape content from {url}"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = USER_PROMPT_TEMPLATE.format(
        content=scraped_text[:10000],
        url=url
    )

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"```$", "", raw).strip()
    result = json.loads(raw)
    result["source_url"] = url
    return result


# ── CELL 5: Main Pipeline Function ─────────────────────────

def process_company_urls(urls: list) -> list:
    """
    Main pipeline: takes a list of URLs, returns enriched JSON array.
    DO NOT modify this function signature.
    """
    results = []
    for url in urls:
        print(f"\n⟳  Processing: {url}")
        try:
            if not url.startswith("http"):
                url = "https://" + url
            scraped = scrape_company(url)
            print(f"   Scraped {len(scraped)} chars from {url}")
            enriched = enrich_with_ai(url, scraped)
            results.append(enriched)
            print(f"   ✓ Enriched: {enriched.get('company_name', 'Unknown')}")
        except Exception as e:
            print(f"   ✕ Error for {url}: {e}")
            results.append({
                "website_name": "", "company_name": "",
                "address": "", "mobile_number": "", "mail": [],
                "core_service": "", "target_customer": "",
                "probable_pain_point": "", "outreach_opener": "",
                "source_url": url, "error": str(e)
            })
    return results


# ── CELL 6: Run — Accepts URL input from user ───────────────

def main():
    print("=" * 60)
    print("  LeadLens — AI Company Enrichment Pipeline")
    print("=" * 60)
    print("\nPaste a JSON array of URLs (e.g. [\"https://example.com\"])")
    print("Then press Enter twice.\n")

    raw_input = input("Enter URL array: ").strip()

    # Parse input — handle both JSON array and plain comma-separated URLs
    try:
        urls = json.loads(raw_input)
        if isinstance(urls, str):
            urls = [urls]
    except json.JSONDecodeError:
        # Fallback: treat as comma-separated list
        urls = [u.strip().strip('"').strip("'") for u in raw_input.split(",") if u.strip()]

    if not urls:
        print("No URLs provided. Exiting.")
        return

    print(f"\n→ Processing {len(urls)} URL(s)...\n")
    results = process_company_urls(urls)

    print("\n" + "=" * 60)
    print("  RESULTS (JSON)")
    print("=" * 60)
    output = json.dumps(results, indent=2, ensure_ascii=False)
    print(output)

    # Save to results.json
    with open("results.json", "w") as f:
        f.write(output)
    print("\n✓ Saved to results.json")

    return results


if __name__ == "__main__":
    main()
