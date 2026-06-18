"""
_scripts/score_management_commentary.py
========================================
Scrapes REAL concall transcripts from Screener.in (paid account)
using authenticated session. Scores with sector-aware local NLP.
NO API KEY needed. Works for all stocks on Screener.

Usage:
  python _scripts/score_management_commentary.py              # score all recommended stocks
  python _scripts/score_management_commentary.py --symbols ARVIND INFY
  python _scripts/score_management_commentary.py --force      # re-score existing

Requires:
  pip install requests beautifulsoup4 pdfplumber psycopg2-binary
  .env.local: SCREENER_USERNAME, SCREENER_PASSWORD, DATABASE_URL
"""

import os, sys, re, json, time, logging, argparse, datetime, io, socket
import requests, psycopg2, psycopg2.extras
from bs4 import BeautifulSoup
import pdfplumber

# Force IPv4 — prevents DNS resolution failures on some Windows setups
import requests.packages.urllib3.util.connection as _urllib3_cn
def _ipv4_only(): return socket.AF_INET
_urllib3_cn.allowed_gai_family = _ipv4_only

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL       = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
SCREENER_USERNAME  = os.environ.get("SCREENER_USERNAME")
SCREENER_PASSWORD  = os.environ.get("SCREENER_PASSWORD")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.screener.in/",
}

# ── Screener company ID cache (avoids extra lookups) ─────────────────────────
# Format: NSE_SYMBOL → (screener_company_id, screener_slug)
# We discover these dynamically — cache persists for session
_screener_id_cache: dict[str, tuple[str, str]] = {}

# ── SECTOR-AWARE NLP SCORING ─────────────────────────────────────────────────
BULLISH = [
    (r"guidance (raised|upgraded|increased|improved|revised upward)", 15),
    (r"record (revenue|profit|order|quarter|performance)", 12),
    (r"(beat|exceeded|surpassed).{0,25}(estimate|expectation|consensus)", 10),
    (r"(order book|order inflow|pipeline|backlog).{0,30}(strong|robust|grew|healthy|record)", 10),
    (r"margin (expansion|improvement|uptick|widening)", 10),
    (r"strong (revenue|growth|demand|order|volume|performance)", 8),
    (r"(new client|deal win|market share gain|won.{0,10}(deal|contract|order))", 8),
    (r"(confident|optimistic|positive).{0,30}(outlook|growth|demand|trajectory)", 8),
    (r"double.?digit (growth|revenue|profit|volume)", 8),
    (r"(capacity (expansion|ramp|addition)|new plant|greenfield|brownfield)", 7),
    (r"(volume growth|volume (increase|recovery|uptick))", 7),
    (r"(dividend (increase|raised|special)|buyback|shareholder return)", 6),
    (r"(debt (reduction|repayment|free)|deleveraging)", 7),
    (r"(working capital (improvement|reduction)|cash flow (strong|positive|improve))", 6),
]
BEARISH = [
    (r"guidance (lowered|cut|reduced|withdrawn|revised downward)", -15),
    (r"(write.?off|impairment|goodwill write|provision for (bad|doubtful|npa))", -12),
    (r"client.{0,15}(ramp.down|exit|loss|churn|program end)", -10),
    (r"(missed|below|fell short|disappointed).{0,25}(estimate|expectation|guidance)", -10),
    (r"margin (pressure|compression|headwind|squeeze|decline)", -10),
    (r"(revenue|sales|topline).{0,20}(declined|fell|dropped|down).{0,15}\d+%", -10),
    (r"(slowdown|challenging|difficult|tough).{0,25}(demand|growth|environment|market)", -8),
    (r"(pricing pressure|price erosion|competitive intensity|price war)", -8),
    (r"(delay|defer|postpone|push.?out).{0,25}(project|order|capex|decision|ramp)", -7),
    (r"(cautious|uncertain|watchful).{0,25}(outlook|demand|macro)", -7),
    (r"(macro|geopolit|currency|forex).{0,25}(headwind|uncertainty|impact|volatility)", -6),
    (r"(attrition|talent|retention).{0,20}(challenge|concern|high|pressure)", -5),
    (r"(inventory (buildup|high|concern)|channel inventory)", -6),
]

SECTOR_SIGNALS = {
    "textile": [
        (r"(pli|production.linked incentive|government scheme).{0,40}(textile|apparel|fabric|garment)", 15),
        (r"(china.plus.one|china\+1|bangladesh.shift|supply chain (diversif|shift|realign))", 12),
        (r"(technical textile|defence (fabric|textile)|smart textile|high.value fabric)", 12),
        (r"(export (order|growth|demand|momentum)|new export (market|client|geography))", 10),
        (r"(brand|retail|d2c|direct.to.consumer).{0,25}(revenue|growth|channel|contribution)", 8),
        (r"(cotton|yarn|fibre|polyester).{0,20}(price|cost).{0,20}(stable|decline|moderate|favorable)", 8),
        (r"(capacity utilis|utilization).{0,20}(high|increas|above \d+%|full)", 8),
        (r"(value.added|premium (product|mix|segment)|mix improvement)", 8),
        (r"(government (capex|spending|initiative|outlay|budget)).{0,30}(textile|apparel|weaving)", 10),
    ],
    "it": [
        (r"(ai|artificial intelligence|generative ai|gen.?ai).{0,30}(deal|win|revenue|client|project|mandate)", 12),
        (r"(large deal|mega deal|deal win|deal total value).{0,20}(million|billion|\$\d+|\d+m)", 15),
        (r"(cloud|digital transformation|modernization).{0,20}(deal|revenue|growth|ramp)", 8),
        (r"(headcount addition|net addition|hiring|campus hire)", 6),
        (r"(attrition).{0,15}(decline|fall|reduce|stable|low)", 8),
        (r"(vertical|segment).{0,15}(growth|recovery|momentum)", 6),
    ],
    "banking": [
        (r"(gross npa|gnpa|net npa|nnpa).{0,20}(decline|fall|improve|reduce|stable)", 12),
        (r"(credit growth|loan growth|advances growth).{0,20}(\d+%)", 10),
        (r"(casa|low.cost deposit|current account|savings).{0,20}(improve|grow|stable|high)", 8),
        (r"(provision coverage|pcr).{0,20}(improve|high|strong|above \d+%)", 8),
        (r"(slippage|stress|delinquency|npa formation).{0,20}(low|reduce|stable|decline)", 8),
        (r"(net interest margin|nim).{0,20}(stable|improve|expand|protect)", 8),
        (r"(roe|return on equity|roa).{0,20}(\d+%|improve|expand)", 7),
    ],
    "pharma": [
        (r"(anda|fda approval|usfda|plant inspection|483|eir|vai)", 12),
        (r"(us market|regulated market|us generics).{0,20}(approval|launch|filing|ramp)", 12),
        (r"(biosimilar|specialty|complex generic|injectables).{0,20}(launch|filing|growth|ramp)", 10),
        (r"(r&d|research spending|pipeline).{0,20}(milestone|filing|approval|progress)", 8),
        (r"(api|active pharma|domestic formulation).{0,20}(growth|recovery|strong)", 7),
    ],
    "infra": [
        (r"(order inflow|order win|l1 position|l1 bidder).{0,30}(crore|billion|₹\d+|\d+ cr)", 15),
        (r"(order book|executable order|order backlog).{0,30}(crore|strong|robust|\d+x|record)", 12),
        (r"(government (order|project|contract|capex|spend))", 10),
        (r"(execution (pick up|accelerat|improve|ramp|strong|ahead))", 8),
        (r"(railway|road|metro|defence|smart city|water|power transmission).{0,20}(order|project|bid|win)", 10),
        (r"(ebitda margin|operating margin).{0,20}(expand|improve|increase|higher)", 8),
    ],
}

SECTOR_KEYWORDS = {
    "textile": ["textile","apparel","fabric","cotton","yarn","garment","denim","fashion","weaving","spinning","knitting"],
    "it":      ["software","technology","it services","consulting","digital","cloud","saas","platform"],
    "banking": ["bank","nbfc","loan","credit","deposit","npa","casa","microfinance","insurance","finance"],
    "pharma":  ["pharma","drug","api","formulation","generics","biologics","healthcare","hospital"],
    "infra":   ["infrastructure","construction","engineering","epc","capital goods","power","roads","defence","water"],
}

GUIDANCE_PATTERNS = {
    "RAISED":         [r"(raise|upgrade|revise.{0,5}up|increase).{0,20}guidance", r"guidance.{0,20}(raised|upgraded|better|higher)"],
    "LOWERED":        [r"(lower|cut|reduce|revise.{0,5}down).{0,20}guidance", r"guidance.{0,20}(lower|cut|reduce|below|miss)"],
    "MAINTAINED":     [r"(maintain|reiterate|reaffirm|confirm|reiterat).{0,20}guidance", r"guidance.{0,20}(maintained|unchanged|intact|on track)"],
    "FIRST_GUIDANCE": [r"(provid|issu|announc|first.time).{0,20}guidance", r"(fy\d\d|next year).{0,15}guidance"],
    "WITHDRAWN":      [r"(withdraw|pull|retract).{0,20}guidance", r"guidance.{0,20}(withdrawn|retracted|removed)"],
}


def detect_sector(text: str, company: str, industry: str = "") -> str:
    # Check industry field FIRST — most reliable signal
    industry_lower = industry.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in industry_lower for kw in keywords):
            return sector  # Industry match is definitive
    # Fall back to text scoring
    combined = (text[:5000] + " " + company).lower()  # limit text to avoid noise
    best, best_count = "generic", 0
    for sector, keywords in SECTOR_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in combined)
        if count > best_count:
            best_count = count
            best = sector
    return best


def score_text(text: str, company: str = "", industry: str = "") -> dict:
    t = text.lower()
    score = 0
    bulls, bears = [], []

    for p, w in BULLISH:
        if re.search(p, t): score += w; bulls.append(p[:45])
    for p, w in BEARISH:
        if re.search(p, t): score += w; bears.append(p[:45])

    sector = detect_sector(text, company, industry)
    if sector in SECTOR_SIGNALS:
        for p, w in SECTOR_SIGNALS[sector]:
            if re.search(p, t):
                score += w
                bulls.append(f"[{sector.upper()}] {p[:35]}")

    score = max(-100, min(100, score))
    tone = ("BULLISH" if score >= 40 else "CAUTIOUSLY_OPTIMISTIC" if score >= 15 else
            "NEUTRAL" if score >= -15 else "CAUTIOUS" if score >= -35 else "BEARISH")

    guidance = "NOT_PROVIDED"
    for direction, patterns in GUIDANCE_PATTERNS.items():
        if any(re.search(p, t) for p in patterns):
            guidance = direction; break

    rev = re.search(r"(\d+[-–]\d+%|\d+%)\s*(revenue|sales|growth|topline)", t)
    mar = re.search(r"(\d+[-–]\d+%|\d+%)\s*(ebitda|margin|pat|profit)", t)
    ob  = re.search(r"order.{0,10}book.{0,30}([\d,]+)\s*(cr|crore)", t)
    ob_val = None
    if ob:
        try: ob_val = float(re.sub(r"[,\s]", "", ob.group(1)))
        except: pass

    quality = min(100, max(20,
        40 + len(bulls)*4 + len(bears)*3 +
        (10 if rev else 0) + (10 if mar else 0) + (10 if ob_val else 0)
    ))
    conf = "HIGH" if len(text) > 5000 else "MEDIUM" if len(text) > 1000 else "LOW"

    return {
        "management_tone":    tone,
        "guidance_direction": guidance,
        "sentiment_score":    round(score, 1),
        "mgmt_quality_score": round(quality, 1),
        "revenue_guidance":   rev.group(0) if rev else None,
        "margin_guidance":    mar.group(0) if mar else None,
        "order_book_cr":      ob_val,
        "confidence":         conf,
        "key_growth_drivers": bulls[:5],
        "key_risks":          bears[:4],
        "positive_surprises": bulls[:3],
        "negative_surprises": bears[:2],
        "detected_sector":    sector,
    }


# ── SCREENER AUTHENTICATED SESSION ───────────────────────────────────────────
def make_screener_session() -> requests.Session:
    """Login to Screener.in and return authenticated session."""
    if not SCREENER_USERNAME or not SCREENER_PASSWORD:
        raise RuntimeError("SCREENER_USERNAME / SCREENER_PASSWORD not set in .env.local")

    s = requests.Session()
    s.headers.update(HEADERS)

    # Get CSRF token
    r = s.get("https://www.screener.in/login/", timeout=10)
    csrf = BeautifulSoup(r.text, "html.parser").find("input", {"name": "csrfmiddlewaretoken"})
    if not csrf:
        raise RuntimeError("Could not find CSRF token on Screener login page")

    # Login
    login = s.post("https://www.screener.in/login/", data={
        "csrfmiddlewaretoken": csrf["value"],
        "username":            SCREENER_USERNAME,
        "password":            SCREENER_PASSWORD,
    }, timeout=10)

    if "logout" not in login.text.lower():
        raise RuntimeError("Screener login failed — check SCREENER_USERNAME / SCREENER_PASSWORD")

    log.info("  Screener.in login successful ✓")
    return s


def get_screener_company_id(session: requests.Session, symbol: str) -> tuple[str, str] | None:
    """Find Screener company ID and slug for an NSE symbol."""
    if symbol in _screener_id_cache:
        return _screener_id_cache[symbol]

    try:
        # Search API
        r = session.get(f"https://www.screener.in/api/company/search/?q={symbol}&v=3", timeout=8)
        if r.status_code == 200:
            results = r.json()
            for item in results:
                if item.get("symbol", "").upper() == symbol or item.get("url","").upper().endswith(f"/{symbol}/"):
                    # Extract company ID from URL e.g. /company/ARVIND/ → need to get numeric ID
                    slug = item.get("url","").strip("/").split("/")[-1]
                    # Visit company page to get numeric ID from source links
                    r2 = session.get(f"https://www.screener.in{item['url']}", timeout=10)
                    # Find source quarter links like /company/source/quarter/262/
                    match = re.search(r"/company/source/quarter/(\d+)/", r2.text)
                    if match:
                        company_id = match.group(1)
                        _screener_id_cache[symbol] = (company_id, slug)
                        return company_id, slug

        # Fallback: direct URL
        r3 = session.get(f"https://www.screener.in/company/{symbol}/", timeout=10)
        if r3.status_code == 200:
            match = re.search(r"/company/source/quarter/(\d+)/", r3.text)
            if match:
                company_id = match.group(1)
                _screener_id_cache[symbol] = (company_id, symbol)
                return company_id, symbol

    except Exception as e:
        log.debug(f"Screener ID lookup {symbol}: {e}")
    return None


def get_transcript_links(session: requests.Session, symbol: str) -> list[str]:
    """Scrape actual concall transcript PDF links from Screener company page."""
    try:
        r = session.get(f"https://www.screener.in/company/{symbol}/", timeout=10)
        if r.status_code != 200:
            r = session.get(f"https://www.screener.in/company/{symbol}/consolidated/", timeout=10)
        if r.status_code != 200:
            return []
        soup  = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            # Match transcript/concall PDF links
            if any(x in href.lower() for x in ["concall", "transcript", "earnings", "analyst_call", "conf_call"]):
                if href.endswith(".pdf") or ".pdf" in href:
                    links.append(href)
        # Deduplicate preserving order
        seen = set()
        unique = []
        for l in links:
            if l not in seen:
                seen.add(l); unique.append(l)
        return unique
    except Exception as e:
        log.debug(f"Transcript link scrape failed for {symbol}: {e}")
        return []


def get_screener_concall_text(session: requests.Session, symbol: str) -> str | None:
    """Download actual concall transcript PDFs from company IR website."""
    # Step 1: Get transcript links from Screener page
    links = get_transcript_links(session, symbol)
    if not links:
        log.debug(f"  No transcript links found for {symbol}")
        return None

    log.info(f"    Found {len(links)} transcript links")
    all_texts = []

    # Download up to 4 most recent transcripts
    for url in links[:4]:
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200 or len(r.content) < 1000:
                log.debug(f"    Skip {url[-50:]}: {r.status_code}")
                continue
            if b"%PDF" not in r.content[:10] and r.content[:4] != b"%PDF":
                log.debug(f"    Skip {url[-50:]}: not a PDF")
                continue
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                text = "\n".join(pg.extract_text() or "" for pg in pdf.pages[:30])
            if len(text) > 200:
                quarter_hint = ""
                for q in ["Q1","Q2","Q3","Q4"]:
                    if q.lower() in url.lower():
                        quarter_hint = q; break
                log.info(f"    [{quarter_hint or 'Q?'}] {url[-45:]}: {len(text)} chars ({len(pdf.pages)}p)")
                all_texts.append(text)
        except Exception as e:
            log.debug(f"    PDF error {url[-40:]}: {e}")
        time.sleep(0.5)

    if all_texts:
        combined = "\n\n".join(all_texts)
        log.info(f"    Total: {len(all_texts)} transcripts, {len(combined)} chars")
        return combined
    return None


def _get_screener_concall_text_fallback(session: requests.Session, symbol: str) -> str | None:
    """Fallback: use Screener quarter source files (board outcome letters)."""
    result = get_screener_company_id(session, symbol)
    if not result:
        log.debug(f"  No Screener ID found for {symbol}")
        return None
    company_id, slug = result
    log.debug(f"  Screener ID: {company_id} slug: {slug}")

    # Fetch last 4 quarters and combine for trend
    now      = datetime.date.today()
    all_texts = []
    seen      = set()

    for delta in range(18):  # scan up to 18 months back
        d       = now - datetime.timedelta(days=delta * 30)
        q_month = (d.month // 3) * 3 or 12
        key     = (d.year, q_month)
        if key in seen: continue
        seen.add(key)

        url = f"https://www.screener.in/company/source/quarter/{company_id}/{q_month}/{d.year}/"
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200 or len(r.content) < 1000:
                continue
            if r.content[:4] == b'%PDF' or b'%PDF' in r.content[:10]:
                with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                    text = "\n".join(pg.extract_text() or "" for pg in pdf.pages[:30])
                if len(text) > 200:
                    log.info(f"    [Q{q_month}/{d.year}] {len(text)} chars ({len(pdf.pages)}p)")
                    all_texts.append(f"=== Q{q_month}/{d.year} ===\n{text}")
            elif len(r.text) > 500:
                soup = BeautifulSoup(r.text, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    log.info(f"    [Q{q_month}/{d.year}] {len(text)} chars (HTML)")
                    all_texts.append(f"=== Q{q_month}/{d.year} ===\n{text}")
        except Exception as e:
            log.debug(f"  Q{q_month}/{d.year}: {e}")
        time.sleep(0.3)
        if len(all_texts) >= 4: break  # 4 quarters is enough

    if all_texts:
        return "\n\n".join(all_texts)
    return None


# ── DB HELPERS ────────────────────────────────────────────────────────────────
def get_db():
    if not DATABASE_URL: raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)


def get_current_quarter() -> str:
    """Return most recently completed Indian FY quarter."""
    now = datetime.date.today()
    m, y = now.month, now.year
    fy = y if m >= 4 else y - 1
    # Completed quarter
    if 4 <= m <= 6:   q, fy_q = "Q4", fy
    elif 7 <= m <= 9: q, fy_q = "Q1", fy + 1
    elif 10 <= m <= 12: q, fy_q = "Q2", fy + 1
    else:             q, fy_q = "Q3", fy + 1
    return f"{q}FY{str(fy_q)[-2:]}"


def get_recommended_symbols() -> list[dict]:
    """Get stocks in technical_signals that need commentary scored."""
    quarter = get_current_quarter()
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DISTINCT
            ts.symbol                                    AS nse_symbol,
            COALESCE(f.name, ts.symbol)                  AS company_name,
            COALESCE(f.industry, f.industry_group, '')   AS industry,
            ts.buy_zone_score
        FROM technical_signals ts
        LEFT JOIN stock_fundamentals f ON f.nse_symbol = ts.symbol
        WHERE ts.buy_zone_score IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM management_commentary mc
              WHERE mc.nse_symbol = ts.symbol AND mc.quarter = %s
          )
        ORDER BY ts.buy_zone_score DESC NULLS LAST
    """, (quarter,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    log.info(f"Found {len(rows)} recommended stocks missing commentary for {quarter}")
    return rows


def save_to_neon(symbol: str, company: str, quarter: str, result: dict):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO management_commentary
          (nse_symbol, company_name, quarter,
           revenue_guidance, margin_guidance, order_book_cr,
           management_tone, guidance_direction,
           key_growth_drivers, key_risks, positive_surprises, negative_surprises,
           mgmt_quality_score, sentiment_score,
           data_source, confidence, extraction_notes,
           created_at, updated_at)
        VALUES (%s,%s,%s, %s,%s,%s, %s,%s, %s,%s,%s,%s, %s,%s, %s,%s,%s, NOW(),NOW())
        ON CONFLICT (nse_symbol, quarter) DO UPDATE SET
          revenue_guidance   = EXCLUDED.revenue_guidance,
          margin_guidance    = EXCLUDED.margin_guidance,
          order_book_cr      = EXCLUDED.order_book_cr,
          management_tone    = EXCLUDED.management_tone,
          guidance_direction = EXCLUDED.guidance_direction,
          key_growth_drivers = EXCLUDED.key_growth_drivers,
          key_risks          = EXCLUDED.key_risks,
          positive_surprises = EXCLUDED.positive_surprises,
          negative_surprises = EXCLUDED.negative_surprises,
          mgmt_quality_score = EXCLUDED.mgmt_quality_score,
          sentiment_score    = EXCLUDED.sentiment_score,
          data_source        = EXCLUDED.data_source,
          confidence         = EXCLUDED.confidence,
          extraction_notes   = EXCLUDED.extraction_notes,
          updated_at         = NOW()
    """, (
        symbol, company, quarter,
        result.get("revenue_guidance"), result.get("margin_guidance"), result.get("order_book_cr"),
        result.get("management_tone","NEUTRAL"), result.get("guidance_direction","NOT_PROVIDED"),
        json.dumps(result.get("key_growth_drivers",[])), json.dumps(result.get("key_risks",[])),
        json.dumps(result.get("positive_surprises",[])), json.dumps(result.get("negative_surprises",[])),
        result.get("mgmt_quality_score"), result.get("sentiment_score"),
        result.get("data_source","SCREENER"), result.get("confidence","LOW"),
        result.get("extraction_notes"),
    ))
    conn.commit(); cur.close(); conn.close()


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────
def process_symbols(session: requests.Session, symbols_info: list[dict], force: bool):
    quarter = get_current_quarter()
    conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    for row in symbols_info:
        sym      = row["nse_symbol"].upper().strip()
        company  = row.get("company_name", sym)
        industry = row.get("industry", "")

        if not force:
            cur.execute("SELECT 1 FROM management_commentary WHERE nse_symbol=%s AND quarter=%s", (sym, quarter))
            if cur.fetchone():
                log.info(f"  {sym}: already scored for {quarter} (--force to re-score)")
                continue

        log.info(f"  Scoring {sym} ({company}) [{industry}] for {quarter}...")

        # Get concall text from Screener
        text = get_screener_concall_text(session, sym)

        if not text or len(text) < 100:
            log.warning(f"    No concall text found for {sym} — saving with LOW confidence")
            result = {
                "management_tone": "NEUTRAL", "guidance_direction": "NOT_PROVIDED",
                "sentiment_score": 0, "mgmt_quality_score": 10, "confidence": "LOW",
                "revenue_guidance": None, "margin_guidance": None, "order_book_cr": None,
                "key_growth_drivers": [], "key_risks": [], "positive_surprises": [], "negative_surprises": [],
                "data_source": "NO_DATA", "extraction_notes": "No concall found on Screener",
                "detected_sector": detect_sector("", company, industry),
            }
        else:
            result = score_text(text, company, industry)
            result["data_source"]      = "SCREENER_PDF"
            result["extraction_notes"] = f"Scored {len(text)} chars from Screener concall PDF"

        save_to_neon(sym, company, quarter, result)

        log.info(
            f"  ✓ {sym}: {result['management_tone']} "
            f"sentiment={result.get('sentiment_score',0):+.0f} "
            f"sector={result.get('detected_sector','?')} "
            f"conf={result['confidence']}"
        )
        time.sleep(1.5)

    cur.close(); conn.close()


def main():
    p = argparse.ArgumentParser(description="Score management commentary from Screener.in concall PDFs")
    p.add_argument("--symbols",     nargs="+", help="NSE symbols e.g. ARVIND INFY TCS")
    p.add_argument("--force",       action="store_true", help="Re-score even if already done this quarter")
    p.add_argument("--recommended", action="store_true", help="Score all stocks in technical_signals (default)")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set. Load .env.local first."); sys.exit(1)
    if not SCREENER_USERNAME or not SCREENER_PASSWORD:
        log.error("SCREENER_USERNAME / SCREENER_PASSWORD not set in .env.local"); sys.exit(1)

    quarter = get_current_quarter()
    log.info(f"Management Commentary Scorer — {quarter}")
    log.info(f"Source: Screener.in authenticated session (paid account)")
    log.info(f"Scoring: Local sector-aware NLP — no API credits needed")
    log.info("=" * 60)

    # Login once — reuse session for all stocks
    session = make_screener_session()

    if args.symbols:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        rows = []
        for sym in args.symbols:
            cur.execute("""
                SELECT nse_symbol,
                       COALESCE(name, nse_symbol)            AS company_name,
                       COALESCE(industry, industry_group, '') AS industry
                FROM stock_fundamentals WHERE nse_symbol = %s LIMIT 1
            """, (sym.upper(),))
            row = cur.fetchone()
            rows.append(dict(row) if row else {"nse_symbol": sym.upper(), "company_name": sym, "industry": ""})
        cur.close(); conn.close()
        process_symbols(session, rows, args.force)
    else:
        rows = get_recommended_symbols()
        if not rows:
            log.info("All recommended stocks already scored. Use --force to re-score.")
            return
        process_symbols(session, rows, args.force)

    log.info("=" * 60)
    log.info("Done.")


if __name__ == "__main__":
    main()
