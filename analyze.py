#!/usr/bin/env python3
"""Stock Analyzer report generator"""

import datetime
import json
import os
import random
import shutil
import textwrap
from urllib.parse import quote_plus

import pandas as pd
import yfinance as yf
import requests

# 候補リスト（毎回このプールからランダムに選択）
US_POOL = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "NVDA", "META", "NFLX", "AMD", "INTC",
    "CRM", "ORCL", "ADBE", "PYPL", "UBER",
    "SHOP", "SPOT", "SNAP", "TWLO", "ZM",
]
JP_POOL = [
    "7203.T", "9984.T", "6758.T", "8306.T", "9432.T",
    "6367.T", "7974.T", "4063.T", "8411.T", "9433.T",
    "6902.T", "7751.T", "4543.T", "8035.T", "6501.T",
    "9020.T", "7267.T", "4307.T", "6273.T", "6594.T",
]

# 毎回5銘柄ずつランダムに選択
random.seed(datetime.datetime.now().timestamp())
US_CANDIDATES = random.sample(US_POOL, 5)
JP_CANDIDATES = random.sample(JP_POOL, 5)

REPORT_ROOT = "reports"
TODAY = datetime.date.today().isoformat()
NOW_STR = datetime.datetime.now().strftime("%H%M%S")
OUT_DIR = os.path.join(REPORT_ROOT, TODAY, NOW_STR)

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
            if not os.path.isdir(day_path):
                continue
            f.write(f"## {day}\n\n")
            for time_dir in sorted(os.listdir(day_path), reverse=True):
                time_path = os.path.join(day_path, time_dir)
                if os.path.isdir(time_path):
                    f.write(f"- [{time_dir}]({day}/{time_dir}/README.md)\n")
            f.write("\n")


def sync_stocks_to_docs():
    """全レポートをdocs/stocksにコピーして一覧を作成"""
    docs_stocks = os.path.join("docs", "stocks")
    if os.path.isdir(docs_stocks):
        shutil.rmtree(docs_stocks)
    mkdir_p(docs_stocks)

    if not os.path.isdir(REPORT_ROOT):
        return

    index_path = os.path.join(docs_stocks, "index.md")
    with open(index_path, "w", encoding="utf-8") as idx:
        idx.write("# 銘柄レポート一覧\n\n")

        date_dirs = sorted(
            [d for d in os.listdir(REPORT_ROOT) if os.path.isdir(os.path.join(REPORT_ROOT, d))],
            reverse=True,
        )
        if not date_dirs:
            idx.write("- レポートがありません。\n")
            return

        for date_dir in date_dirs:
            date_path = os.path.join(REPORT_ROOT, date_dir)
            time_dirs = sorted(
                [t for t in os.listdir(date_path) if os.path.isdir(os.path.join(date_path, t))],
                reverse=True,
            )
            if not time_dirs:
                continue

            idx.write(f"## {date_dir}\n\n")
            for time_dir in time_dirs:
                src_dir = os.path.join(date_path, time_dir)
                dst_dir = os.path.join(docs_stocks, date_dir, time_dir)
                mkdir_p(dst_dir)

                stock_files = sorted(
                    [f for f in os.listdir(src_dir) if f.endswith(".md") and f != "README.md"]
                )
                if not stock_files:
                    continue

                idx.write(f"### {time_dir}\n\n")
                for filename in stock_files:
                    src = os.path.join(src_dir, filename)
                    dst = os.path.join(dst_dir, filename)
                    shutil.copy2(src, dst)
                    symbol = filename.replace(".md", "").replace("_", ".")
                    idx.write(f"- [{symbol}]({date_dir}/{time_dir}/{filename})\n")
                idx.write("\n")


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
        f.write(f"最終更新: {TODAY} {NOW_STR}\n\n")
        f.write("## レポート一覧\n\n")
        f.write(f"- [レポート {TODAY} {NOW_STR}](reports/{TODAY}/{NOW_STR}/)\n")

    sync_reports_to_docs()
    sync_stocks_to_docs()

    print("レポート生成完了: " + OUT_DIR)


if __name__ == "__main__":
    main()
