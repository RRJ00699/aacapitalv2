import re, time, requests
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from datetime import date
from tqdm import tqdm

OUT = Path("data/amfi_portfolios_5yr")
OUT.mkdir(parents=True, exist_ok=True)

AMC_PAGES = {
    "sbi": "https://www.sbimf.com/portfolios",
    "hdfc": "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio",
    "dsp": "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

GOOD = [
    "monthly portfolio",
    "monthly-portfolio",
    "portfolio details",
    "portfolio disclosure",
    "all schemes monthly portfolio",
    "portfolio as on",
]

BAD = [
    "commission", "risk", "valuation", "privacy", "policy", "factsheet",
    "kim", "sid", "addendum", "notice", "idcw", "rollover", "grievance",
    "dashboard", "reckoner", "financial", "annual", "half yearly"
]

EXTS = [".xlsx", ".xls", ".csv", ".pdf"]


def year_tokens(years=5):
    today = date.today()
    tokens = set()
    for i in range(years * 12 + 2):
        d = today - relativedelta(months=i)
        tokens |= {
            d.strftime("%Y").lower(),
            d.strftime("%b").lower(),
            d.strftime("%B").lower(),
            d.strftime("%b-%Y").lower(),
            d.strftime("%B-%Y").lower(),
            d.strftime("%m-%Y").lower(),
        }
    return tokens


TOKENS = year_tokens(5)


def is_candidate(url, text):
    s = f"{url} {text}".lower()

    if not any(ext in s for ext in EXTS):
        return False

    if any(b in s for b in BAD):
        return False

    if not any(g in s for g in GOOD):
        return False

    if not any(t in s for t in TOKENS):
        return False

    return True


def clean_name(s):
    s = s.split("?")[0].split("/")[-1]
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s)[:180]


def extract_links(page):
    r = requests.get(page, headers=HEADERS, timeout=40)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    links = []

    for a in soup.find_all("a"):
        href = a.get("href")
        txt = a.get_text(" ", strip=True)
        if href:
            links.append((urljoin(page, href), txt))

    raw = re.findall(r'https?://[^\s"\']+\.(?:xlsx|xls|csv|pdf)[^\s"\']*', r.text, re.I)
    links += [(u, "") for u in raw]

    return list(dict.fromkeys(links))


def download(amc, url, text):
    folder = OUT / amc
    folder.mkdir(parents=True, exist_ok=True)

    name = clean_name(url)
    if not name:
        name = re.sub(r"[^a-zA-Z0-9]+", "_", text)[:100]

    path = folder / name

    if path.exists() and path.stat().st_size > 0:
        return "EXISTS", path

    with requests.get(url, headers=HEADERS, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 128):
                if chunk:
                    f.write(chunk)

    return "DOWNLOADED", path


def main():
    all_links = []

    for amc, page in AMC_PAGES.items():
        print(f"\nFetching {amc}: {page}")

        try:
            links = extract_links(page)
        except Exception as e:
            print(f"FAILED {amc}: {e}")
            continue

        good = [(amc, u, t) for u, t in links if is_candidate(u, t)]
        print(f"Found {len(good)} real portfolio candidates for {amc}")
        all_links.extend(good)

    print(f"\nTotal portfolio files: {len(all_links)}")

    for amc, url, text in tqdm(all_links):
        try:
            status, path = download(amc, url, text)
            print(status, amc, path.name)
            time.sleep(0.4)
        except Exception as e:
            print("FAILED", amc, url, e)


if __name__ == "__main__":
    main()