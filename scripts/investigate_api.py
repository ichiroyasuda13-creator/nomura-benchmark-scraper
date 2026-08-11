"""Temporary script to investigate Nomura fund search API."""
import re
from urllib.parse import urljoin

import requests

headers = {"User-Agent": "NomuraBenchmarkScraper/1.0 (research)"}
base = "https://fund.nomura-am.co.jp"
page_url = f"{base}/nomura/contents/index.aspx?F=fund_search&tab=1&sort=-5"

with requests.Session() as session:
    session.headers.update(headers)
    r = session.get(page_url, timeout=30)
    print(f"Page status={r.status_code} len={len(r.text)}")

    scripts = re.findall(r'<script[^>]+src="([^"]+)"', r.text)
    for src in scripts:
        if not any(k in src.lower() for k in ("fund", "qik", "search")):
            continue
        url = urljoin(page_url, src)
        jr = session.get(url, timeout=30)
        print(f"\n=== {url} status={jr.status_code} len={len(jr.text)}")
        if jr.status_code != 200:
            continue
        patterns = re.findall(
            r"https?://[^\s\"'<>]+|/[^\s\"'<>]+\.(?:ashx|asmx|json)|"
            r"fundsearch[^\s\"'<>]*|qik_[^\s\"'<>]+|ajax[^\s\"'<>]+",
            jr.text,
            re.I,
        )
        seen = set()
        for m in patterns:
            if any(x in m.lower() for x in ("google", "youtube", "w3.org")):
                continue
            if m not in seen:
                seen.add(m)
                print(" ", m[:150])

        # Print lines containing url or ajax
        for line in jr.text.splitlines():
            low = line.lower()
            if any(k in low for k in ("url", "ajax", "api", "endpoint", "fetch", "post", "get")):
                if "google" not in low:
                    print(" line:", line.strip()[:200])
