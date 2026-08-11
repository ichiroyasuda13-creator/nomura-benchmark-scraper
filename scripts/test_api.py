"""Test Nomura fund search API."""
import json
import re
from pathlib import Path

import requests

API_URL = "https://fund.nomura-am.co.jp/nomura/cgi/wrap/qjsonp.aspx"
OUT = Path(__file__).resolve().parent / "api_sample.json"
headers = {"User-Agent": "NomuraBenchmarkScraper/1.0 (research)"}

with requests.Session() as session:
    session.headers.update(headers)
    r = session.get(
        API_URL,
        params={"F": "ctl/fund_search", "KEY1": "", "KEY2": ""},
        timeout=60,
    )
    m = re.match(r"^[^(]+\((.*)\)\s*$", r.text, re.S)
    data = json.loads(m.group(1))
    sec = data["section1"]
    funds = sec["data"]
    OUT.write_text(json.dumps({"hitcount": sec["hitcount"], "sample": funds[:3], "keys": sorted(funds[0].keys())}, ensure_ascii=False, indent=2), encoding="utf-8")

    aum_key = "TotalAssetValue"
    top = sorted(funds, key=lambda x: x.get(aum_key) or 0, reverse=True)[:10]
    summary = []
    for f in top:
        summary.append(
            {
                "FundName": f.get("FundName"),
                "FundCode": f.get("FundCode"),
                "TotalAssetValue": f.get("TotalAssetValue"),
                "DetailUrl": f.get("DetailUrl"),
                "IsETF": f.get("IsETF"),
            }
        )
    (Path(__file__).resolve().parent / "api_top10.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"hitcount={sec['hitcount']} funds={len(funds)} written")
