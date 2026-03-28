#!/usr/bin/env python3
"""Stock Analyzer report generator"""

import datetime
import json
import os
import shutil
import textwrap
from urllib.parse import quote_plus

import pandas as pd
import yfinance as yf
import requests

US_CANDIDATES = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
JP_CANDIDATES = ["7203.T", "9984.T", "6758.T", "8306.T", "9432.T"]

REPORT_ROOT = "reports"
TODAY = datetime.date.today().isoformat()
OUT_DIR = os.path.join(REPORT_ROOT, TODAY)

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")


def mkdir_p(path):
    os.makedirs(path, exist_ok=True)


def safe_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def fetch_ticker_data(symbol):
    ticker = yf.Ticker(symbol)
    history = ticker.history(period="1mo", interval="1d")
    return ticker, history


def fetch_yfinance_news(ticker):
    try:
        return ticker.news or []
    except Exception:
        return []


def fetch_newsapi(symbol):
    if not NEWSAPI_KEY:
        return []

    query = quote_plus(symbol)
    endpoint = f"https://newsapi.org/v2/everything?q={query}&pageSize=5&sortBy=publishedAt&language=en"
    resp = requests.get(endpoint, headers={"Authorization": NEWSAPI_KEY}, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("articles", [])
    return []


def write_report(symbol, info, hist, yfn, npa):
    filename = os.path.join(OUT_DIR, f"{symbol.replace('.', '_')}.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {symbol} レポート\n\n")
        f.write("## 基本情報\n\n")
        for k in ["longName", "symbol", "sector", "industry", "country", "marketCap"]:
            f.write(f"- **{k}**: {info.get(k, 'N/A')}\n")
        f.write("\n")

        f.write("## 最新株価（1ヶ月データ）\n\n")
        f.write(hist.tail(5).to_markdown() + "\n\n")

        f.write("## yfinance ニュース\n\n")
        if yfn:
            for i, item in enumerate(yfn[:5], 1):
                title = item.get("title") or item.get("headline")
                link = item.get("link") or item.get("url")
                f.write(f"{i}. [{title}]({link})\n")
        else:
            f.write("- ニュースが取得できませんでした。\n")
        f.write("\n")

        f.write("## NewsAPI ニュース\n\n")
        if npa:
            for i, item in enumerate(npa[:5], 1):
                f.write(f"{i}. [{item.get('title')}]{'(' + item.get('url') + ')' if item.get('url') else ''}\n")
        else:
            f.write("- NewsAPI でニュースが取得されませんでした。\n")


def sync_reports_to_docs():
    docs_reports = os.path.join("docs", "reports")
    if os.path.isdir(docs_reports):
        shutil.rmtree(docs_reports)
    shutil.copytree(REPORT_ROOT, docs_reports)

    index_path = os.path.join(docs_reports, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("# レポート一覧\n\n")
        for day in sorted(os.listdir(docs_reports), reverse=True):
            day_path = os.path.join(docs_reports, day)
            if os.path.isdir(day_path):
                f.write(f"- [{day}]({day}/README.md)\n")


def generate_md_index(us, jp):
    filepath = os.path.join(OUT_DIR, "README.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {TODAY} の株式分析レポート\n\n")
        f.write("## US 銘柄\n\n")
        for s in us:
            f.write(f"- [{s}]({s.replace('.', '_')}.md)\n")
        f.write("\n## JP 銘柄\n\n")
        for s in jp:
            f.write(f"- [{s}]({s.replace('.', '_')}.md)\n")


def main():
    mkdir_p(OUT_DIR)

    us_list = US_CANDIDATES
    jp_list = JP_CANDIDATES

    reports = {"date": TODAY, "us": us_list, "jp": jp_list, "items": []}

    for symbol in us_list + jp_list:
        print(f"Collecting {symbol}...")
        ticker, hist = fetch_ticker_data(symbol)
        info = ticker.info if hasattr(ticker, "info") else {}
        yfn_news = fetch_yfinance_news(ticker)
        nws = fetch_newsapi(symbol)

        write_report(symbol, info, hist, yfn_news, nws)

        reports["items"].append({
            "symbol": symbol,
            "name": info.get("longName") or symbol,
            "lastClose": float(hist["Close"].dropna().iloc[-1]) if not hist.empty else None,
        })

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        f.write(safe_json(reports))

    generate_md_index(us_list, jp_list)

    # docs 生成
    mkdir_p("docs")
    with open("docs/index.md", "w", encoding="utf-8") as f:
        f.write("# Stock Analyzer\n\n")
        f.write(f"最終更新: {TODAY}\n\n")
        f.write("## レポート一覧\n\n")
        f.write(f"- [レポート {TODAY}](reports/{TODAY}/)\n")

    sync_reports_to_docs()

    print("レポート生成完了: " + OUT_DIR)


if __name__ == "__main__":
    main()
