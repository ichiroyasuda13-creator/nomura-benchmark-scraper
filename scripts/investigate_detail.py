"""Investigate fund detail page for prospectus PDF links."""
import re
from pathlib import Path

import requests

headers = {"User-Agent": "NomuraBenchmarkScraper/1.0 (research)"}
urls = [
    "https://www.nomura-am.co.jp/fund/funddetail.php?fundcd=140380",
    "https://www.nomura-am.co.jp/fund/funddetail.php?fundcd=180371",
]

out = Path(__file__).resolve().parent / "detail_samples.html"
parts = []
with requests.Session() as session:
    session.headers.update(headers)
    for url in urls:
        r = session.get(url, timeout=30)
        parts.append(f"<!-- {url} status={r.status_code} -->\n")
        # extract pdf links with context
        for m in re.finditer(r".{0,80}交付目論見書.{0,200}", r.text):
            parts.append(m.group(0) + "\n")
        for m in re.finditer(r'href="([^"]+\.pdf[^"]*)"[^>]*>([^<]{0,40})', r.text):
            href, label = m.group(1), m.group(2)
            if any(k in (label + href) for k in ("目論見", "pros", "交付", "説明")):
                parts.append(f"PDF: {label.strip()} -> {href}\n")

out.write_text("\n".join(parts), encoding="utf-8")
print(f"written {out}")
