import re
import time
import requests
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

OUT = Path("data/amfi_target_portfolios")
OUT.mkdir(parents=True, exist_ok=True)

TARGET_FUNDS = [
    "SBI Small Cap Fund",
    "Nippon India Small Cap Fund",
    "HDFC Small Cap Fund",
    "Kotak Small Cap Fund",
    "Axis Small Cap Fund",
    "Quant Small Cap Fund",
    "DSP Small Cap Fund",
    "Tata Small Cap Fund",
    "Bandhan Small Cap Fund",
    "Invesco India Smallcap Fund",
    "HDFC Mid-Cap Opportunities Fund",
    "Kotak Midcap Fund",
    "Nippon India Growth Fund",
    "Motilal Oswal Midcap Fund",
    "SBI Magnum Midcap Fund",
    "Axis Midcap Fund",
    "Quant Mid Cap Fund",
    "Edelweiss Mid Cap Fund",
    "DSP Midcap Fund",
    "Invesco India Mid Cap Fund",
]

AMC_PAGES = {
    "sbi": "https://www.sbimf.com/portfolios",
    "hdfc": "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio",
    "nippon": "https://mf.nipponindiaim.com/FundsAndPerformance/Pages/Portfolio-Holdings.aspx",
    "kotak": "https://www.kotakmf.com/Information/forms-and-downloads",
    "axis": "https://www.axismf.com/statutory-disclosures",
    "quant": "https://quantmutual.com/statutory-disclosures",
    "dsp": "https://www.dspim.com/mandatory-disclosures",
    "tata": "https://www.tatamutualfund.com/downloads",
    "bandhan": "https://bandhanmutual.com/downloads/disclosures",
    "invesco": "https://www.invescomutualfund.com/literature-and-form",
    "motilal": "https://www.motilaloswalmf.com/downloads/mutual-fund",
    "edelweiss": "https://www.edelweissmf.com/statutory",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 AACapital Research Bot"
}

FILE_EXTS = [".xlsx", ".xls", ".csv", ".pdf"]

KEYWORDS = [
    "portfolio",
    "monthly",
    "disclosure",
    "scheme",
    "holding",
]


def is_file_link(url: str) -> bool:
    u = url.lower()
    return any(ext in u for ext in FILE_EXTS)


def looks_like_portfolio(url: str, text: str) -> bool:
    s = f"{url} {text}".lower()
    return is_file_link(s) and any(k in s for k in KEYWORDS)


def clean_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")


def fetch_links(amc: str, page_url: str):
    print(f"\nFetching {amc}: {page_url}")

    try:
        r = requests.get(page_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"FAILED {amc}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    links = []

    for a in soup.find_all("a"):
        href = a.get("href")
        text = a.get_text(" ", strip=True)

        if not href:
            continue

        full = urljoin(page_url, href)

        if looks_like_portfolio(full, text):
            links.append((full, text))

    raw_files = re.findall(r'https?://[^\s"\']+\.(?:xlsx|xls|csv|pdf)[^\s"\']*', r.text, flags=re.I)

    for u in raw_files:
        if looks_like_portfolio(u, ""):
            links.append((u, ""))

    return list(dict.fromkeys(links))


def download(amc: str, url: str):
    folder = OUT / amc
    folder.mkdir(parents=True, exist_ok=True)

    filename = clean_name(url.split("/")[-1].split("?")[0])

    if not filename:
        filename = clean_name(url[-100:])

    path = folder / filename

    if path.exists() and path.stat().st_size > 0:
        print(f"EXISTS {path}")
        return

    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024 * 128):
                    if chunk:
                        f.write(chunk)

        print(f"DOWNLOADED {path}")

    except Exception as e:
        print(f"FAILED DOWNLOAD {url}: {e}")


def main():
    total = 0

    for amc, page in AMC_PAGES.items():
        links = fetch_links(amc, page)

        print(f"Found {len(links)} candidate files for {amc}")

        for url, text in links[:24]:
            download(amc, url)
            total += 1
            time.sleep(0.5)

    print(f"\nDone. Candidate files processed: {total}")
    print(f"Saved under: {OUT}")


if __name__ == "__main__":
    main()