"""fetcher.py — 抓取宁波大学信息科学与工程学院"新闻中心"列表，生成 RSS 2.0"""
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from lxml import etree

# ===== 配置 =====
TARGET_URL = "https://eecs.nbu.edu.cn/index/xwzx.htm"
RSS_OUTPUT_FILE = "feed.xml"
MAX_ITEMS = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://eecs.nbu.edu.cn/",
}

CHANNEL = {
    "title": "宁波大学信息科学与工程学院 - 新闻中心",
    "link": TARGET_URL,
    "description": "宁波大学信息科学与工程学院（集成电路学院、人工智能学院）新闻中心最新动态，自动从官网列表页抓取。",
    "language": "zh-cn",
}

# 标题前缀日期的正则
DATE_PREFIX_RE = re.compile(r"^\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\s*(.*)$")


def fetch(url: str) -> str:
    """获取网页源码"""
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.encoding = "utf-8"
    r.raise_for_status()
    return r.text


def parse_date(text: str):
    """从标题前缀 'YYYY/MM/DD' 解析日期"""
    m = DATE_PREFIX_RE.match(text)
    if not m:
        return None
    y, mo, d, _ = m.groups()
    try:
        return datetime(int(y), int(mo), int(d))
    except ValueError:
        return None


def parse(html: str) -> list:
    """解析出 [{title, link, pubdate_dt}, ...]"""
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # 详情页 URL 格式: ../info/1230/<id>.htm
        if not re.search(r"/info/1230/\d+\.htm", href):
            continue

        # 拼成绝对 URL
        full_link = urljoin(TARGET_URL, href)
        if full_link in seen:
            continue
        seen.add(full_link)

        # 标题（去掉前后空白）
        title = a.get_text(strip=True)
        if not title:
            continue

        # 解析前缀日期
        pubdate_dt = parse_date(title)
        if not pubdate_dt:
            continue

        # 把日期从标题里移除，让标题更干净
        m = DATE_PREFIX_RE.match(title)
        clean_title = m.group(4).strip() if m else title

        items.append({
            "title": clean_title,
            "link": full_link,
            "pubdate_dt": pubdate_dt,
        })

    return items


def make_rss(items: list) -> None:
    """生成 RSS 2.0 XML（按时间倒序）"""
    fg = FeedGenerator()
    fg.id(CHANNEL["link"])
    fg.title(CHANNEL["title"])
    fg.link(href=CHANNEL["link"], rel="alternate")
    fg.description(CHANNEL["description"])
    fg.language(CHANNEL["language"])
    fg.lastBuildDate(datetime.now(timezone(timedelta(hours=8))))

    for it in items:
        fe = fg.add_entry()
        fe.id(it["link"])
        fe.title(it["title"])
        fe.link(href=it["link"], rel="alternate")
        fe.pubDate(it["pubdate_str"])
        fe.description(it["title"])

    # feedgen 会按 id 重排，用 lxml 按 pubDate 倒序覆盖
    root = etree.fromstring(fg.rss_str(pretty=True))
    channel = root.find("channel")
    xml_items = channel.findall("item")

    def _dt(it):
        pd = it.find("pubDate")
        if pd is not None and pd.text:
            try:
                return parsedate_to_datetime(pd.text)
            except Exception:
                return None
        return None

    xml_items.sort(key=lambda it: _dt(it) or datetime.min, reverse=True)
    for it in xml_items:
        channel.remove(it)
    for it in xml_items:
        channel.append(it)

    with open(RSS_OUTPUT_FILE, "wb") as f:
        f.write(etree.tostring(root, pretty_print=True,
                               xml_declaration=True, encoding="UTF-8"))


if __name__ == "__main__":
    html = fetch(TARGET_URL)
    items = parse(html)
    items.sort(key=lambda x: x["pubdate_dt"], reverse=True)

    for it in items:
        it["pubdate_str"] = it["pubdate_dt"].strftime("%a, %d %b %Y 00:00:00 +0800")

    n = min(len(items), MAX_ITEMS)
    make_rss(items[:n])
    print(f"生成 {n} 条 RSS（{CHANNEL['title']}）")
    print(f"输出文件: {RSS_OUTPUT_FILE}")
