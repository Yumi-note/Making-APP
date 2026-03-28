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
RUN_ID = f"{TODAY}-{NOW_STR}"
LAST_UPDATED = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")


def mkdir_p(path):
    os.makedirs(path, exist_ok=True)


def safe_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def classify_market(symbol):
    return "JP" if symbol.endswith(".T") else "US"


def to_float_or_none(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_scores(symbol, info, yfn, npa):
    market = classify_market(symbol)

    news_count = len(yfn) + len(npa)
    news_score = min(100, news_count * 10)

    pe = to_float_or_none(info.get("trailingPE"))
    div_yield = to_float_or_none(info.get("dividendYield"))
    div_pct = div_yield * 100 if div_yield is not None else None

    value_score = 50
    if pe is not None and pe > 0:
        if market == "US":
            if pe <= 15:
                value_score += 25
            elif pe <= 25:
                value_score += 15
            elif pe <= 35:
                value_score += 5
        else:
            if pe <= 12:
                value_score += 25
            elif pe <= 20:
                value_score += 15
            elif pe <= 30:
                value_score += 5

    if div_pct is not None:
        if div_pct >= 3.5:
            value_score += 25
        elif div_pct >= 2.0:
            value_score += 15
        elif div_pct >= 1.0:
            value_score += 5

    value_score = max(0, min(100, value_score))
    overall = int(round(news_score * 0.5 + value_score * 0.35 + 15))

    if overall >= 75:
        decision = "有望"
        tone = "positive"
    elif overall >= 60:
        decision = "監視"
        tone = "neutral"
    else:
        decision = "見送り"
        tone = "negative"

    return {
        "market": market,
        "newsScore": news_score,
        "valueScore": value_score,
        "overallScore": overall,
        "decision": decision,
        "tone": tone,
        "newsCount": news_count,
        "trailingPE": pe,
        "dividendYieldPct": div_pct,
    }


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
        f.write("> このページの目的: 単一銘柄のファンダメンタル・価格推移・ニュースを確認し、候補採用可否を判断する。\n\n")
        f.write(f"- 最終更新: {LAST_UPDATED}\n")
        f.write(f"- 実行ID: {RUN_ID}\n\n")
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
        f.write("> このページの目的: 実行履歴（日時ごと）から過去レポートを追跡する。\n\n")
        f.write(f"- 最終更新: {LAST_UPDATED}\n")
        f.write(f"- 実行ID: {RUN_ID}\n\n")
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
        idx.write("> このページの目的: 全実行分の銘柄ページへ、日付と時刻から素早くアクセスする。\n\n")
        idx.write(f"- 最終更新: {LAST_UPDATED}\n")
        idx.write(f"- 実行ID: {RUN_ID}\n\n")

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


def write_ui_stylesheet():
    mkdir_p(os.path.join("docs", "stylesheets"))
    css_path = os.path.join("docs", "stylesheets", "extra.css")
    with open(css_path, "w", encoding="utf-8") as f:
        f.write("""
:root {
  --positive: #1e8e3e;
  --negative: #c62828;
  --neutral: #5f6368;
  --value: #1565c0;
  --news: #ef6c00;
  --panel: #f5f7fb;
}

.purpose {
  background: var(--panel);
  border-left: 4px solid var(--value);
  padding: 0.8rem 1rem;
  margin: 1rem 0;
}

.meta-line {
  font-size: 0.95rem;
  color: #334155;
  margin-bottom: 0.6rem;
}

.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.15rem 0.6rem;
  font-size: 0.85rem;
  font-weight: 600;
}

.badge-positive { background: #e8f5e9; color: var(--positive); }
.badge-negative { background: #ffebee; color: var(--negative); }
.badge-neutral { background: #eceff1; color: var(--neutral); }
.badge-news { background: #fff3e0; color: var(--news); }
.badge-value { background: #e3f2fd; color: var(--value); }
""".strip())


def render_row(item):
    pe = "-" if item["trailingPE"] is None else f"{item['trailingPE']:.2f}"
    dy = "-" if item["dividendYieldPct"] is None else f"{item['dividendYieldPct']:.2f}%"
    report_link = f"reports/{TODAY}/{NOW_STR}/{item['symbol'].replace('.', '_')}.md"
    return (
        f"| {item['market']} | [{item['symbol']}]({report_link}) | {item['name']} | "
        f"{item['newsScore']} | {item['valueScore']} | {item['overallScore']} | "
        f"{pe} | {dy} | {item['decision']} |"
    )


def write_today_page(items):
    path = os.path.join("docs", "today.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 今日の候補10銘柄\n\n")
        f.write("<div class=\"purpose\">このページの目的: 毎日の最終候補10銘柄を、ニュース材料と割安性で素早く比較する。</div>\n\n")
        f.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
        f.write("- US 5銘柄 + JP 5銘柄（固定）\n")
        f.write("- 評価軸: ニュース（量+質）50%、割安（PER+配当）35%、安定性補正15%\n\n")
        f.write("| 市場 | 銘柄 | 企業名 | News | Value | 総合 | PER | 配当利回り | 判定 |\n")
        f.write("|---|---|---|---:|---:|---:|---:|---:|---|\n")
        for item in sorted(items, key=lambda x: x["overallScore"], reverse=True):
            f.write(render_row(item) + "\n")


def write_news_page(items):
    path = os.path.join("docs", "news.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# ニュース分析\n\n")
        f.write("<div class=\"purpose\">このページの目的: ニュース材料が強い銘柄を先に把握し、監視優先度を決める。</div>\n\n")
        f.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
        f.write("| 順位 | 銘柄 | 市場 | ニュース件数 | News Score | 判定 |\n")
        f.write("|---:|---|---|---:|---:|---|\n")
        ranked = sorted(items, key=lambda x: (x["newsScore"], x["overallScore"]), reverse=True)
        for i, item in enumerate(ranked, 1):
            f.write(f"| {i} | {item['symbol']} | {item['market']} | {item['newsCount']} | {item['newsScore']} | {item['decision']} |\\n")


def write_value_page(items):
    path = os.path.join("docs", "value.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 割安分析\n\n")
        f.write("<div class=\"purpose\">このページの目的: PERと配当利回りで割安候補を比較し、中長期候補の優先順位を決める。</div>\n\n")
        f.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
        f.write("## 国別ルール\n\n")
        f.write("- US: PER 15以下を高評価、配当利回り3.5%以上を高評価\n")
        f.write("- JP: PER 12以下を高評価、配当利回り3.5%以上を高評価\n\n")
        f.write("| 順位 | 銘柄 | 市場 | PER | 配当利回り | Value Score | 総合 |\n")
        f.write("|---:|---|---|---:|---:|---:|---:|\n")
        ranked = sorted(items, key=lambda x: (x["valueScore"], x["overallScore"]), reverse=True)
        for i, item in enumerate(ranked, 1):
            pe = "-" if item["trailingPE"] is None else f"{item['trailingPE']:.2f}"
            dy = "-" if item["dividendYieldPct"] is None else f"{item['dividendYieldPct']:.2f}%"
            f.write(f"| {i} | {item['symbol']} | {item['market']} | {pe} | {dy} | {item['valueScore']} | {item['overallScore']} |\\n")


def write_update_log_page(items):
    path = os.path.join("docs", "update_log.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 更新状況\n\n")
        f.write("<div class=\"purpose\">このページの目的: いつ何が更新されたかを確認し、データ鮮度を担保する。</div>\n\n")
        f.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
        f.write("## 今回の実行サマリー\n\n")
        f.write(f"- 実行ディレクトリ: `{OUT_DIR}`\n")
        f.write(f"- 対象銘柄数: {len(items)}\n")
        f.write(f"- US銘柄数: {len([i for i in items if i['market'] == 'US'])}\n")
        f.write(f"- JP銘柄数: {len([i for i in items if i['market'] == 'JP'])}\n\n")
        f.write("## 対象銘柄\n\n")
        for item in sorted(items, key=lambda x: (x["market"], x["symbol"])):
            f.write(f"- {item['market']} / {item['symbol']} / 判定: {item['decision']}\n")


def main():
    mkdir_p(OUT_DIR)

    us_list = US_CANDIDATES
    jp_list = JP_CANDIDATES

    reports = {
        "date": TODAY,
        "time": NOW_STR,
        "runId": RUN_ID,
        "lastUpdated": LAST_UPDATED,
        "us": us_list,
        "jp": jp_list,
        "items": [],
    }

    for symbol in us_list + jp_list:
        print(f"Collecting {symbol}...")
        ticker, hist = fetch_ticker_data(symbol)
        info = ticker.info if hasattr(ticker, "info") else {}
        yfn_news = fetch_yfinance_news(ticker)
        nws = fetch_newsapi(symbol)

        write_report(symbol, info, hist, yfn_news, nws)

        scores = compute_scores(symbol, info, yfn_news, nws)
        reports["items"].append({
            "symbol": symbol,
            "name": info.get("longName") or symbol,
            "lastClose": float(hist["Close"].dropna().iloc[-1]) if not hist.empty else None,
            **scores,
        })

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        f.write(safe_json(reports))

    generate_md_index(us_list, jp_list)

    # docs 生成
    mkdir_p("docs")
    write_ui_stylesheet()

    items = reports["items"]
    write_today_page(items)
    write_news_page(items)
    write_value_page(items)
    write_update_log_page(items)

    with open("docs/index.md", "w", encoding="utf-8") as f:
        f.write("# Stock Analyzer\n\n")
        f.write("<div class=\"purpose\">このページの目的: 画面の役割を把握し、今日の銘柄選定にすぐ移る。</div>\n\n")
        f.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
        f.write("## 画面ガイド\n\n")
        f.write("- [今日の候補10銘柄](today.md): 毎日の候補を最短で選ぶ\n")
        f.write("- [ニュース分析](news.md): 材料の強さで優先順位をつける\n")
        f.write("- [割安分析](value.md): PER+配当で中長期候補を絞る\n")
        f.write("- [更新状況](update_log.md): 更新時刻と実行状況を確認する\n")
        f.write("- [銘柄レポート一覧](stocks/index.md): 全実行分の銘柄詳細を見る\n")
        f.write("- [実行履歴](reports/index.md): 日時別の過去実行を追う\n")

    sync_reports_to_docs()
    sync_stocks_to_docs()

    print("レポート生成完了: " + OUT_DIR)


if __name__ == "__main__":
    main()
