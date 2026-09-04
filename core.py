import json
import re
import ssl
import time
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError
from lxml import html
from difflib import SequenceMatcher
from html import unescape
import threading
import datetime

TIMEOUT = 10
MAX_WORKERS = 5
MAX_RETRY = 2
RETRY_DELAY = 1
MAX_FULL_TEXT = 8000

TRUSTED_DOMAINS = [
    "thepaper.cn", "news.sina.com.cn", "xinwen.sina.com.cn",
    "news.qq.com", "new.qq.com", "news.163.com", "sohu.com",
    "cctv.com", "news.cctv.com", "china.com.cn", "chinanews.com",
    "xinhuanet.com", "people.com.cn", "gmw.cn", "youth.cn",
    "ce.cn", "cnr.cn", "huanqiu.com", "bjnews.com.cn",
    "weibo.com", "mp.weixin.qq.com", "thecover.cn",
    "jfdaily.com", "shobserver.com", "whb.cn", "dfdaily.com",
    "stdaily.com", "zgkjb.com", "cyol.com", "huanqiu.com",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _build_headers(referer=None):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    return headers


def _fetch(url, timeout=TIMEOUT, retry=MAX_RETRY, data=None):
    ctx = ssl._create_unverified_context()
    for attempt in range(retry + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=_build_headers())
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                charset = "utf-8"
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].split(";")[0].strip()
                try:
                    body = raw.decode(charset)
                except Exception:
                    body = raw.decode("utf-8", errors="replace")
                return resp.status, body
        except HTTPError as e:
            if attempt < retry:
                time.sleep(RETRY_DELAY)
                continue
            return e.code, str(e)
        except (URLError, OSError) as e:
            if attempt < retry:
                time.sleep(RETRY_DELAY)
                continue
            return None, str(e)
    return None, "max retry"


def _extract_text(html_text):
    try:
        doc = html.fromstring(html_text)
        for el in doc.xpath("//script | //style | //noscript"):
            try:
                el.getparent().remove(el)
            except Exception:
                pass
        text = doc.text_content()
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        return html_text


FOOTER_HINTS = [
    "沪ICP备", "沪公网安备", "互联网新闻信息服务许可证", "增值电信业务经营许可证",
    "Android版", "iPhone版", "iPad版", "关于澎湃", "加入澎湃", "联系我们",
    "广告合作", "法律声明", "隐私政策", "澎湃矩阵", "Copyright", "©",
]


def _looks_like_footer(text):
    t = text or ""
    hits = sum(1 for kw in FOOTER_HINTS if kw in t)
    if len(t) <= 600 and hits >= 2:
        return True
    return "沪ICP备" in t or "沪公网安备" in t


def _clean_paragraph(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\[!--begin:.*?--\].*?\[!--end:.*?--\]", "", text, flags=re.S)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) < 6:
        return ""
    if any(kw in text for kw in FOOTER_HINTS) and len(text) <= 80:
        return ""
    if text in ("登录", "查看更多", "开始答题", "扫码下载") or re.match(r"^[A-Za-z]+版$", text):
        return ""
    if re.search(r"(记者|编辑|通讯员|作者).*(记者|编辑|通讯员|素材来源)", text) and len(text) <= 120:
        return ""
    if re.match(r"^(来源|原标题|责任编辑|编辑|记者|作者|校对|监制|主编|总台)\s*[:：]", text):
        return ""
    if re.match(r"^[新闻频道\s>]*正在加载", text) or "正在加载" in text:
        return ""
    if re.match(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?(\s+\d{1,2}:\d{2})?\s*$", text):
        return ""
    if ">听全文" in text or "字号" in text or "听全文" in text[:20]:
        return ""
    if re.search(r"摄$", text) and len(text) <= 60:
        return ""
    return text


def _paragraph_texts(root):
    """按段落收集文本，避免把页头、作者栏等杂质混进正文"""
    paras = []
    ps = root.xpath(".//p")
    if ps:
        for p in ps:
            for rm in p.xpath(".//script | .//style | .//noscript"):
                try:
                    rm.getparent().remove(rm)
                except Exception:
                    pass
            t = _clean_paragraph(p.text_content())
            if t:
                paras.append(t)
        return paras
    for rm in root.xpath(".//script | .//style | .//noscript"):
        try:
            rm.getparent().remove(rm)
        except Exception:
            pass
    text = re.sub(r"\s+", " ", root.text_content()).strip()
    return [text] if len(text) > 100 and not _looks_like_footer(text) else []


def _extract_inline_article(html_text):
    """央视等站点把正文存在 script 的 contentdate 变量里，先尝试解析"""
    pattern = re.compile(r"var\s+(contentdate|contentDate|artibody|articlebody|articleContent|content)\s*=\s*(['\"])(.*?)\2\s*;", re.S)
    for m in pattern.finditer(html_text):
        val = m.group(3)
        if "<p" not in val:
            continue
        try:
            paras = _paragraph_texts(html.fromstring(unescape(val)))
        except Exception:
            continue
        if paras and len("\n".join(paras)) >= 100:
            return "\n".join(paras)
    return None


def _extract_article(html_text):
    inline = _extract_inline_article(html_text)
    if inline:
        return inline
    try:
        doc = html.fromstring(html_text)
        selectors = [
            "//div[contains(@class,'cententWrap')]",
            "//div[contains(@class,'content_area')]",
            "//article",
            "//div[@id='artibody']",
            "//div[contains(@class,'article')]",
            "//div[contains(@class,'content')]",
            "//div[contains(@class,'main-text')]",
            "//div[@id='article']",
            "//div[contains(@class,'post_content')]",
            "//div[contains(@class,'article-content')]",
            "//div[contains(@class,'news-content')]",
            "//div[contains(@class,'text')]",
            "//div[@class='text']",
        ]
        for sel in selectors:
            els = doc.xpath(sel)
            if not els:
                continue
            for el in els:
                paras = _paragraph_texts(el)
                if paras:
                    return "\n".join(paras)
        page_paras = _paragraph_texts(doc)
        if page_paras:
            return "\n".join(page_paras)
        return _extract_text(html_text)
    except Exception:
        return _extract_text(html_text)


def _title_similarity(t1, t2):
    if not t1 or not t2:
        return 0
    t1 = re.sub(r"\s+", "", t1.lower())
    t2 = re.sub(r"\s+", "", t2.lower())
    if len(t1) <= 10 or len(t2) <= 10:
        return 1.0 if (t1 in t2 or t2 in t1) else 0.0
    return SequenceMatcher(None, t1, t2).ratio()


def _is_trusted(url):
    for d in TRUSTED_DOMAINS:
        if d in url.lower():
            return True
    return False


def _search_duckduckgo(title, max_results=5):
    query = (title[:80] + " " + str(datetime.date.today().year)).strip()
    data = urllib.parse.urlencode({"q": query, "df": "w"}).encode()
    url = "https://html.duckduckgo.com/html/"
    status, body = _fetch(url, retry=1, data=data)
    if not body:
        return []
    results = []
    try:
        doc = html.fromstring(body)
        for result in doc.xpath("//div[contains(@class,'result')]"):
            try:
                a = result.xpath(".//a[contains(@class,'result__a')]")[0]
                href = a.get("href", "")
                snippet = a.text_content().strip()
                if href.startswith("http"):
                    results.append((href, snippet))
            except Exception:
                continue
    except Exception:
        pass
    return results[:max_results]


SKIP_SOURCES = {"知乎", "百度贴吧"}


def _search_bing(title, max_results=5):
    """用 Bing 搜索作为央底"""
    query = title[:100] + " " + str(datetime.date.today().year)
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&qft=+filterui:age-lt=30"
    status, body = _fetch(url, retry=1)
    if not body:
        return []
    results = []
    try:
        doc = html.fromstring(body)
        for li in doc.xpath("//li[contains(@class, \'b_algo\')]"):
            try:
                a = li.xpath(".//h2/a")[0]
                href = a.get("href", "")
                text = a.text_content().strip()
                if href.startswith("http"):
                    results.append((href, text))
            except:
                continue
    except:
        pass
    return results[:max_results]


def _search_fallback(title):
    """优先 DuckDuckGo，失败则用 Bing 央底"""
    results = _search_duckduckgo(title)
    if results:
        return results
    return _search_bing(title)
    return _search_duckduckgo(title)


def _is_search_page_url(url):
    u = (url or "").lower()
    for hint in ("so.toutiao.com/search", "baidu.com/s", "s.weibo.com", "user.guancha.cn", "search?keyword="):
        if hint in u:
            return True
    return False


def _looks_like_feed(text):
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return False
    head = t[:200]
    if "完整榜单" in head or "搜索智能聚合" in head or "想要发表评论" in head:
        return True
    if "置顶" in head and ("评论" in head or "阅读" in head):
        return True
    if "点击展开全文" in t or "展开全文" in t[:400]:
        return True
    if len(re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", t)) >= 3:
        return True
    return False


def _title_match(title, text):
    t1 = re.sub(r"\s+", "", title or "")
    t2 = re.sub(r"\s+", "", text or "")
    if len(t1) <= 8:
        return True
    kws = set(t1[:14])
    if not kws:
        return True
    hits = sum(1 for c in kws if c in t2)
    return hits / len(kws) >= 0.4


def _title_entity_match(title, text):
    m = re.match(r"^([\u4e00-\u9fff]{2,4})(?:等|被|遭|：|:|\s|，)", title or "")
    if m and m.group(1) not in (text or ""):
        return False
    return True


def _article_too_old(text):
    today = datetime.date.today()
    t = text or ""
    dates = []
    for m in re.finditer(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", t):
        try:
            dates.append(datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except Exception:
            continue
    if dates:
        latest = max(dates)
        return (today - latest).days > 60
    m = re.search(r"([1-9]|1[0-2])月([1-9]|[12]\d|3[01])日电", t)
    if m:
        try:
            d = datetime.date(today.year, int(m.group(1)), int(m.group(2)))
        except Exception:
            return False
        if d > today:
            d = datetime.date(today.year - 1, d.month, d.day)
        return (today - d).days > 60
    return False


def fetch_direct(url, timeout=TIMEOUT):
    status, body = _fetch(url, timeout=timeout)
    if not body:
        return False, f"抓取失败: {status}"
    if status != 200:
        return False, f"HTTP {status}"
    if "verify" in body[:500].lower() or "captcha" in body[:500].lower():
        return False, "需要验证"
    text = _extract_article(body)
    if len(text) < 50:
        return False, f"正文过短({len(text)}字)"
    if _looks_like_footer(text) and len(text) < 600:
        return False, "仅抓到页脚信息"
    return True, text[:MAX_FULL_TEXT]


def fetch_with_search(item, progress_callback=None):
    result = dict(item)
    idx = result.get("idx", "?")
    title = result.get("标题", "")
    url = result.get("url", "")
    source = result.get("来源", "")

    # 知乎/贴吧话题源不需要原文定位
    if source in SKIP_SOURCES:
        result["full_text"] = None
        result["fetch_status"] = "话题源，无需原文"
        result["fetch_quality"] = "topic_source"
        if progress_callback:
            progress_callback(f"#{idx} [{source}] 话题源，跳过")
        return result

    if url and _is_search_page_url(url):
        fail_reason = "搜索页URL，改用搜索定位原文"
    elif url and url.startswith("http"):
        ok, content = fetch_direct(url)
        if ok and not _looks_like_feed(content) and _title_match(title, content) and _title_entity_match(title, content) and not _article_too_old(content):
            result["full_text"] = content
            result["fetch_status"] = "直接抓取成功"
            result["fetch_quality"] = _assess_quality(result)
            if progress_callback:
                q = result["fetch_quality"]
                progress_callback(f"#{idx} [{source}] 直接抓取成功 (质量:{q})")
            return result
        fail_reason = "直接抓取内容异常（新闻流/与标题不匹配）" if ok else content
    else:
        fail_reason = "无有效URL"

    if progress_callback:
        progress_callback(f"#{idx} [{source}] 直抓失败({fail_reason})，搜索中...")

    search_results = _search_fallback(title)
    matched = []
    for search_url, snippet in search_results:
        if _is_search_page_url(search_url):
            continue
        sim = _title_similarity(title, snippet)
        trusted = _is_trusted(search_url)
        score = sim + (0.2 if trusted else 0)
        matched.append((score, search_url, snippet))

    matched.sort(key=lambda x: -x[0])
    if not matched:
        fail_reason = "搜索无结果"
    else:
        for best_score, best_url, best_snippet in matched:
            if best_score < 0.3:
                fail_reason = f"搜索无高匹配(最高{best_score:.2f})"
                break
            ok, content = fetch_direct(best_url)
            if ok and not _looks_like_feed(content) and _title_match(title, content) and _title_entity_match(title, content) and not _article_too_old(content):
                result["full_text"] = content
                result["fetch_status"] = f"搜索匹配(相似度{best_score:.2f})"
                result["matched_url"] = best_url
                result["fetch_quality"] = _assess_quality(result)
                if progress_callback:
                    q = result["fetch_quality"]
                    progress_callback(f"  ✓ 匹配: {best_url} (质量:{q})")
                return result
            fail_reason = f"搜索匹配但内容异常: {content[:80] if ok else content}"

    result["full_text"] = None
    result["fetch_status"] = fail_reason
    result["fetch_quality"] = "unavailable"
    if progress_callback:
        progress_callback(f"  ✗ {fail_reason}")
    return result

def _assess_quality(item):
    """判断抓取到的内容质量等级"""
    text = item.get("full_text") or ""
    status = item.get("fetch_status", "")
    source = item.get("来源", "")
    url = item.get("url", "")
    matched_url = item.get("matched_url", "")

    if not text:
        return "unavailable"

    # 质量好的信号：真实新闻正文特征
    news_signals = ["表示", "回应", "报道", "记者", "来源", "发表", "称", "指出", "强调"]
    signal_count = sum(1 for s in news_signals if s in text[:200])
    content_len = len(text)

    # 搜索页面特征
    is_search_page = (
        "搜索" in text[:300] or
        "相关" in text[:300] or
        "百度贴吧" in text[:200] or
        text[:50].strip().endswith("-百度贴吧") or
        text[:100].strip().endswith("-百度贴吧")
    )

    # 今日头条/百度等搜索链接 → 拿到的很可能是搜索页
    if "so.toutiao.com" in url or "baidu.com/s" in url:
        is_search_page = True

    # 微信原文通常需要验证，但若通过搜索匹配拿到了转载正文，则按正文质量评估
    if "mp.weixin.qq.com" in url and not matched_url:
        return "unavailable"

    if content_len > 500 and signal_count >= 2 and not is_search_page:
        return "real_article"
    elif content_len > 200 or (is_search_page and content_len > 100):
        return "partial"
    else:
        return "unavailable"


def process_all(items, progress_callback=None, max_workers=MAX_WORKERS):
    total = len(items)
    done = 0
    results = [None] * total
    errors = 0
    sem = threading.Semaphore(max_workers)

    def worker(i, item):
        nonlocal done, errors
        sem.acquire()
        try:
            r = fetch_with_search(item, progress_callback)
            results[i] = r
            if r.get("full_text") is None:
                errors += 1
        except Exception as e:
            results[i] = dict(item)
            results[i]["full_text"] = None
            results[i]["fetch_status"] = f"异常: {str(e)}"
            errors += 1
        finally:
            done += 1
            if progress_callback:
                progress_callback(f"进度: {done}/{total}")
            sem.release()

    threads = []
    for i, item in enumerate(items):
        t = threading.Thread(target=worker, args=(i, item))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    stats = {
        "total": total,
        "success": total - errors,
        "failed": errors,
        "success_rate": f"{(total - errors) / total * 100:.1f}%" if total else "0%",
    }
    return results, stats


def parse_input(raw):
    if isinstance(raw, dict):
        if "result_json" in raw:
            return json.loads(raw["result_json"])
        if "items" in raw and isinstance(raw["items"], list):
            return raw["items"]
        return [raw]
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                if "result_json" in parsed:
                    return json.loads(parsed["result_json"])
                return [parsed]
        except json.JSONDecodeError:
            pass
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return []


def fetch_tophub(tophub_key):
    """舆情抓取：调用 Tophub API 获取各平台热搜"""
    ctx = ssl._create_unverified_context()
    NODES = [
        {"name": "微博", "hashid": "KqndgxeLl9"},
        {"name": "知乎", "hashid": "mproPpoq6O"},
        {"name": "澎湃新闻", "hashid": "wWmoO5Rd4E"},
        {"name": "百度贴吧", "hashid": "Om4ejxvxEN"},
        {"name": "百度", "hashid": "Jb0vmloB1G"},
        {"name": "微信", "hashid": "WnBe01o371"},
        {"name": "IT之家", "hashid": "74Kvx59dkx"},
        {"name": "抖音", "hashid": "K7GdaMgdQy"},
        {"name": "今日头条", "hashid": "x9ozB4KoXb"},
        {"name": "新浪国内新闻", "hashid": "Jb0vmwGeB1"},
        {"name": "新京报", "hashid": "YqoXQ8XvOD"},
        {"name": "央视新闻", "hashid": "qndg1WxoLl"},
    ]
    TOPIC_SOURCES = {"知乎", "百度贴吧"}
    NEED_BACKGROUND = {"微博", "百度", "抖音", "今日头条", "微信", "IT之家", "澎湃新闻", "新京报", "央视新闻"}

    def clean(v):
        return "" if v is None else str(v).strip()

    def map_fields(source, item):
        desc = clean(item.get("description", ""))
        extra = clean(item.get("extra", ""))
        media = summary = heat = metric = ""
        if source == "知乎":
            summary = desc; heat = extra; metric = "热度"
        elif source == "新浪国内新闻":
            media = desc; heat = extra; metric = "热度"
        elif source == "央视新闻":
            media = extra; metric = "媒体"
        elif source == "IT之家":
            heat = extra; metric = "评论数"
        elif source == "百度贴吧":
            heat = extra; metric = "讨论量"
        else:
            summary = desc; heat = extra; metric = "热度" if extra else ""
        return media, summary, heat, metric

    all_items, errors = [], []
    batches = [NODES[:7], NODES[7:]]
    for batch in batches:
        for node in batch:
            source = node["name"]
            try:
                req = urllib.request.Request(
                    f"https://api.tophubdata.com/nodes/{node['hashid']}",
                    headers={"Authorization": tophub_key, "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("data", {}).get("items", [])
                for item in items:
                    title = clean(item.get("title", ""))
                    if not title:
                        continue
                    media, summary, heat, metric = map_fields(source, item)
                    all_items.append({
                        "来源": source, "标题": title, "摘要": summary,
                        "url": clean(item.get("url", "")), "热度": heat,
                        "媒体": media, "指标类型": metric, "排名": item.get("rank", ""),
                    })
            except Exception as e:
                errors.append(f"{source}: {str(e)}")
        time.sleep(1)

    seen = set()
    deduped = []
    for item in all_items:
        k = item["标题"][:30]
        if k not in seen:
            seen.add(k)
            deduped.append(item)

    out = [f"共采集 {len(all_items)} 条，去重后 {len(deduped)} 条"]
    if errors:
        out.append(f"失败节点: {'; '.join(errors)}")
    out.append("")
    for i, item in enumerate(deduped):
        has_desc = bool(item["摘要"] and item["摘要"].strip())
        if item["来源"] in TOPIC_SOURCES:
            label = "原生-话题" if has_desc else "话题源-无摘要"
        elif has_desc:
            label = "原生摘要"
        elif item["来源"] in NEED_BACKGROUND:
            label = "待补充背景"
        else:
            label = "无摘要"
        metric_text = ""
        if item.get("媒体"):
            metric_text += f" | 媒体: {item['媒体']}"
        if item.get("热度"):
            metric_text += f" | {item.get('指标类型') or '热度'}: {item['热度']}"
        desc_preview = item["摘要"][:50] if item["摘要"] else "(空)"
        out.append(f"{i+1}. [{item['来源']}] {item['标题']}")
        out.append(f"   排名: {item.get('排名', '')}{metric_text} | 来源标记: {label}")
        out.append(f"   摘要: {desc_preview}")
        out.append("")
    json_data = json.dumps(deduped, ensure_ascii=False)
    return {"fetch_results": "\n".join(out) + "\n\n===DATA===\n" + json_data}

def preprocess_items(fetch_results):
    return {'items_json': '[]', 'to_llm_text': '', 'auto_out_json': '[]', 'stats_json': '{}'}

def postprocess_results(llm_raw, items_json, auto_out_json):
    return {'result': '', 'result_json': '[]'}
