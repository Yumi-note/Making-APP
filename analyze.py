#!/usr/bin/env python3
"""Stock Analyzer report generator"""

import datetime
import json
import os
import random
import shutil
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


def to_int_or_none(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def format_market_cap(cap):
    if cap is None:
        return "N/A"
    units = [(1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M")]
    for base, suffix in units:
        if cap >= base:
            return f"{cap / base:.2f}{suffix}"
    return str(int(cap))


def get_business_profile(sector, industry):
    sector_lower = (sector or "").lower()
    industry_lower = (industry or "").lower()

    defaults = {
        "segments": [
            "主力プロダクト/サービス領域",
            "成長投資領域",
            "収益安定領域",
        ],
        "daily_impact": "日常生活・産業インフラのどこかで利用される基盤を提供し、社会活動の効率性に影響を与える。",
        "job_roles": [
            "事業開発/戦略",
            "プロダクト開発/運用",
            "営業/カスタマーサクセス",
        ],
    }

    profiles = {
        "technology": {
            "segments": ["ソフトウェア/クラウド", "半導体・ハードウェア", "広告/プラットフォーム"],
            "daily_impact": "仕事の生産性、コミュニケーション、エンタメなど日常のデジタル体験に直結。",
            "job_roles": ["プロダクト開発", "インフラ運用", "エンタープライズ営業"],
        },
        "financial": {
            "segments": ["法人金融", "個人金融", "資産運用/決済"],
            "daily_impact": "住宅ローン、決済、貯蓄・投資など個人と企業の資金循環を支える。",
            "job_roles": ["法人営業", "審査/リスク管理", "資産運用"],
        },
        "healthcare": {
            "segments": ["医薬品", "医療機器", "ヘルスケアサービス"],
            "daily_impact": "治療・予防・健康維持の質とアクセスに影響し、生活の安心に寄与。",
            "job_roles": ["研究開発", "薬事/品質保証", "医療機関向け営業"],
        },
        "consumer": {
            "segments": ["ブランド製品", "小売/EC", "サプライチェーン"],
            "daily_impact": "食品、衣料、日用品、EC体験など生活に最も近い消費活動へ影響。",
            "job_roles": ["商品企画", "店舗/EC運営", "マーケティング"],
        },
        "industrial": {
            "segments": ["製造装置", "インフラ/建設", "輸送/物流"],
            "daily_impact": "モノづくりや社会インフラの生産性・安全性を左右し、供給網全体に波及。",
            "job_roles": ["生産技術", "調達/SCM", "法人営業"],
        },
        "communication": {
            "segments": ["通信インフラ", "モバイルサービス", "法人向けソリューション"],
            "daily_impact": "ネット接続・通話・データ通信など生活とビジネスの基盤に直接影響。",
            "job_roles": ["ネットワーク運用", "サービス企画", "法人営業"],
        },
    }

    if "software" in industry_lower or "semiconductor" in industry_lower or "internet" in industry_lower:
        return profiles["technology"]
    if "bank" in industry_lower or "financial" in industry_lower or "insurance" in industry_lower:
        return profiles["financial"]
    if "pharma" in industry_lower or "biotech" in industry_lower or "health" in industry_lower:
        return profiles["healthcare"]
    if "retail" in industry_lower or "consumer" in industry_lower or "apparel" in industry_lower:
        return profiles["consumer"]
    if "telecom" in industry_lower or "communication" in industry_lower:
        return profiles["communication"]
    if "industrial" in sector_lower or "manufactur" in industry_lower or "auto" in industry_lower:
        return profiles["industrial"]
    if "technology" in sector_lower:
        return profiles["technology"]
    if "financial" in sector_lower:
        return profiles["financial"]
    if "health" in sector_lower:
        return profiles["healthcare"]
    if "consumer" in sector_lower:
        return profiles["consumer"]
    if "communication" in sector_lower:
        return profiles["communication"]
    return defaults


def build_japanese_company_overview(item, profile):
    name = item.get("name") or item.get("symbol")
    symbol = item.get("symbol") or "N/A"
    market = item.get("market") or "N/A"
    country = item.get("country") or "N/A"
    sector = item.get("sector") or "N/A"
    industry = item.get("industry") or "N/A"
    market_cap = format_market_cap(item.get("marketCap"))
    employees = item.get("fullTimeEmployees")
    employees_text = f"約{employees:,}名" if employees else "非開示"

    segment_text = "、".join(profile["segments"])
    roles_text = "、".join(profile["job_roles"])

    paragraphs = [
        (
            f"{name}（{symbol}）は{country}を主な事業基盤とする{sector}セクターの企業で、"
            f"市場区分は{market}です。業種は{industry}に属し、時価総額は{market_cap}、"
            f"従業員規模は{employees_text}です。"
        ),
        (
            f"事業の柱は{segment_text}で、単一事業に依存するのではなく複数領域を組み合わせて"
            f"収益基盤を形成している点が特徴です。中長期で見る際は、既存事業の安定性と成長投資領域の"
            f"拡大余地を併せて確認すると、事業の持続性を判断しやすくなります。"
        ),
        (
            f"日常生活への影響としては、{profile['daily_impact']}"
            f"そのため、この企業の業績や投資方針の変化は、消費者体験・企業活動・社会インフラの"
            f"いずれかに波及する可能性があります。"
        ),
        (
            f"仕事内容の観点では、{roles_text}といった職務領域が主軸です。"
            f"企業研究では、どの事業部が成長ドライバーか、どの領域が利益を下支えしているかを"
            f"分けて把握することで、銘柄選定時の納得感を高められます。"
        ),
    ]
    return "\n\n".join(paragraphs)


def assign_position_tier(item, market_items):
    sorted_caps = sorted(
        [i for i in market_items if i["marketCap"] is not None],
        key=lambda x: x["marketCap"],
        reverse=True,
    )
    if not sorted_caps or item["marketCap"] is None:
        return "情報不足", "同市場内の時価総額情報が不足しており、ポジション判定は暫定。"

    idx = [x["symbol"] for x in sorted_caps].index(item["symbol"]) + 1
    total = len(sorted_caps)

    if idx <= max(1, total // 3):
        return "上位", f"同市場の対象銘柄群で時価総額順位が上位（{idx}/{total}）に位置。"
    if idx <= max(2, (total * 2) // 3):
        return "中位", f"同市場の対象銘柄群で時価総額順位が中位（{idx}/{total}）に位置。"
    return "下位", f"同市場の対象銘柄群で時価総額順位が下位（{idx}/{total}）に位置。"


def build_sector_position_map(item, market_items):
    sector = item.get("sector") or ""
    peers = [x for x in market_items if (x.get("sector") or "") == sector and x.get("marketCap") is not None]
    if len(peers) < 2 or item.get("marketCap") is None:
        return "同セクター比較データが不足しているため、ポジション図は暫定。"

    ranked = sorted(peers, key=lambda x: x["marketCap"], reverse=True)
    idx = [x["symbol"] for x in ranked].index(item["symbol"]) + 1
    total = len(ranked)
    ratio = idx / total
    if ratio <= 0.33:
        zone = "上位ゾーン"
        bar = "[■■■■■]"
    elif ratio <= 0.67:
        zone = "中位ゾーン"
        bar = "[■■■□□]"
    else:
        zone = "下位ゾーン"
        bar = "[■□□□□]"
    return f"同セクター内順位: {idx}/{total} {zone} {bar}"


def build_valuation_comment(item):
    market = item.get("market")
    pe = item.get("trailingPE")
    dy = item.get("dividendYieldPct")
    if pe is None and dy is None:
        return "評価に十分なPER/配当データが不足。"

    if market == "US":
        pe_note = "PER基準(US): 15以下が割安目安"
    else:
        pe_note = "PER基準(JP): 12以下が割安目安"

    pe_eval = "PERデータなし"
    if pe is not None:
        if (market == "US" and pe <= 15) or (market == "JP" and pe <= 12):
            pe_eval = f"PER {pe:.2f} は割安寄り"
        elif (market == "US" and pe <= 25) or (market == "JP" and pe <= 20):
            pe_eval = f"PER {pe:.2f} は中立"
        else:
            pe_eval = f"PER {pe:.2f} は割高寄り"

    dy_eval = "配当データなし"
    if dy is not None:
        if dy >= 3.5:
            dy_eval = f"配当利回り {dy:.2f}% は高水準"
        elif dy >= 2.0:
            dy_eval = f"配当利回り {dy:.2f}% は中水準"
        else:
            dy_eval = f"配当利回り {dy:.2f}% は低め"

    return f"{pe_note}。{pe_eval}。{dy_eval}。"


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
    research_link = f"research/{item['symbol'].replace('.', '_')}.md"
    return (
        f"| {item['market']} | [{item['symbol']}]({report_link}) / [企業研究]({research_link}) | {item['name']} | "
        f"{item['newsScore']} | {item['valueScore']} | {item['overallScore']} | "
        f"{pe} | {dy} | {item['decision']} |"
    )


def write_research_pages(items):
    docs_research = os.path.join("docs", "research")
    if os.path.isdir(docs_research):
        shutil.rmtree(docs_research)
    mkdir_p(docs_research)

    market_groups = {
        "US": [i for i in items if i["market"] == "US"],
        "JP": [i for i in items if i["market"] == "JP"],
    }

    index_path = os.path.join(docs_research, "index.md")
    with open(index_path, "w", encoding="utf-8") as idx:
        idx.write("# 企業研究\n\n")
        idx.write("<div class=\"purpose\">このページの目的: 銘柄選定だけでなく、企業そのものの理解を深める。</div>\n\n")
        idx.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
        idx.write("| 銘柄 | 市場 | 企業名 | 業界立ち位置 | 研究ページ |\n")
        idx.write("|---|---|---|---|---|\n")

        for item in sorted(items, key=lambda x: x["overallScore"], reverse=True):
            tier, _ = assign_position_tier(item, market_groups[item["market"]])
            symbol_file = item["symbol"].replace(".", "_")
            page_path = os.path.join(docs_research, f"{symbol_file}.md")
            profile = get_business_profile(item.get("sector"), item.get("industry"))
            jp_overview = build_japanese_company_overview(item, profile)
            tier_label, tier_desc = assign_position_tier(item, market_groups[item["market"]])

            with open(page_path, "w", encoding="utf-8") as f:
                f.write(f"# {item['symbol']} 企業研究\n\n")
                f.write("<div class=\"purpose\">このページの目的: 企業の事業実態と業界立ち位置を把握し、中長期視点で判断する。</div>\n\n")
                f.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
                f.write("## 企業の基本像\n\n")
                f.write(f"- 企業名: {item['name']}\n")
                f.write(f"- 市場: {item['market']}\n")
                f.write(f"- 国: {item.get('country') or 'N/A'}\n")
                f.write(f"- セクター: {item.get('sector') or 'N/A'}\n")
                f.write(f"- 業種: {item.get('industry') or 'N/A'}\n")
                f.write(f"- 時価総額: {format_market_cap(item.get('marketCap'))}\n")
                if item.get("website"):
                    f.write(f"- 公式サイト: {item['website']}\n")
                f.write("\n")

                f.write("## この企業は何をしているか\n\n")
                f.write(jp_overview + "\n\n")

                f.write("## 事業部レベルの構成（推定）\n\n")
                for seg in profile["segments"]:
                    f.write(f"- {seg}\n")
                f.write("\n")

                f.write("## 業界での立ち位置\n\n")
                f.write(f"- 判定: **{tier_label}**\n")
                f.write(f"- 根拠: {tier_desc}\n\n")
                f.write("### 業界ポジション図（簡易）\n\n")
                f.write("```text\n")
                f.write("上位プレイヤー  : [■■■■■]\n")
                f.write("中位プレイヤー  : [■■■□□]\n")
                f.write("下位/新興       : [■□□□□]\n")
                f.write(f"この銘柄の位置  : [{tier_label}]\n")
                f.write(build_sector_position_map(item, market_groups[item["market"]]) + "\n")
                f.write("```\n\n")

                f.write("## 割安性コメント（国別基準）\n\n")
                f.write("- " + build_valuation_comment(item) + "\n\n")

                f.write("## 日常生活への影響\n\n")
                f.write(profile["daily_impact"] + "\n\n")

                f.write("## どんな仕事内容があるか（事業部レベル）\n\n")
                for role in profile["job_roles"]:
                    f.write(f"- {role}\n")
                f.write("\n")

                f.write("## 銘柄選定への接続\n\n")
                f.write(f"- [当日の銘柄レポート](../reports/{TODAY}/{NOW_STR}/{item['symbol'].replace('.', '_')}.md)\n")
                f.write(f"- News Score: {item['newsScore']} / Value Score: {item['valueScore']} / 総合: {item['overallScore']}\n")

            idx.write(
                f"| {item['symbol']} | {item['market']} | {item['name']} | {tier} | "
                f"[詳細](./{symbol_file}.md) |\n"
            )


def write_slack_payload(items):
    payload_path = os.path.join("docs", "slack_payload.json")
    top_items = sorted(items, key=lambda x: x["overallScore"], reverse=True)[:10]
    lines = [
        f"更新: {LAST_UPDATED}",
        f"実行ID: {RUN_ID}",
        "今日の候補10銘柄",
    ]
    for i, item in enumerate(top_items, 1):
        lines.append(
            f"{i}. {item['symbol']} ({item['market']}) Score:{item['overallScore']} News:{item['newsScore']} Value:{item['valueScore']} 判定:{item['decision']}"
        )

    payload = {
        "runId": RUN_ID,
        "updatedAt": LAST_UPDATED,
        "channel": "#stock-alerts",
        "text": "\n".join(lines),
        "top10": top_items,
    }
    with open(payload_path, "w", encoding="utf-8") as f:
        f.write(safe_json(payload))


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
            f.write(f"| {i} | {item['symbol']} | {item['market']} | {item['newsCount']} | {item['newsScore']} | {item['decision']} |\n")


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
            f.write(f"| {i} | {item['symbol']} | {item['market']} | {pe} | {dy} | {item['valueScore']} | {item['overallScore']} |\n")


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
        f.write("\n## Slack通知準備データ\n\n")
        f.write("- [Slack payload](slack_payload.json): 定時通知・条件通知に利用するJSON\n")


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
            "marketCap": to_float_or_none(info.get("marketCap")),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "website": info.get("website"),
            "fullTimeEmployees": to_int_or_none(info.get("fullTimeEmployees")),
            "businessSummary": info.get("longBusinessSummary"),
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
    write_research_pages(items)
    write_update_log_page(items)
    write_slack_payload(items)

    with open("docs/index.md", "w", encoding="utf-8") as f:
        f.write("# Stock Analyzer\n\n")
        f.write("<div class=\"purpose\">このページの目的: 画面の役割を把握し、今日の銘柄選定にすぐ移る。</div>\n\n")
        f.write(f"<div class=\"meta-line\">最終更新: {LAST_UPDATED} / 実行ID: {RUN_ID}</div>\n\n")
        f.write("## 画面ガイド\n\n")
        f.write("- [今日の候補10銘柄](today.md): 毎日の候補を最短で選ぶ\n")
        f.write("- [ニュース分析](news.md): 材料の強さで優先順位をつける\n")
        f.write("- [割安分析](value.md): PER+配当で中長期候補を絞る\n")
        f.write("- [企業研究](research/index.md): 企業の立ち位置・事業・社会的影響を把握する\n")
        f.write("- [更新状況](update_log.md): 更新時刻と実行状況を確認する\n")
        f.write("- [Slack payload](slack_payload.json): 通知連携用データ\n")
        f.write("- [銘柄レポート一覧](stocks/index.md): 全実行分の銘柄詳細を見る\n")
        f.write("- [実行履歴](reports/index.md): 日時別の過去実行を追う\n")

    sync_reports_to_docs()
    sync_stocks_to_docs()

    print("レポート生成完了: " + OUT_DIR)


if __name__ == "__main__":
    main()
