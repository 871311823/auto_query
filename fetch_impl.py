import json, ssl, time, urllib.request

def fetch_tophub(tophub_key):
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
    NEED_BG = {"微博", "百度", "抖音", "今日头条", "微信", "IT之家", "澎湃新闻", "新京报", "央视新闻"}

    def clean(v): return "" if v is None else str(v).strip()

    def map_fields(src, item):
        desc = clean(item.get("description", ""))
        extra = clean(item.get("extra", ""))
        media = summary = heat = metric = ""
        if src == "知乎": summary = desc; heat = extra; metric = "热度"
        elif src == "新浪国内新闻": media = desc; heat = extra; metric = "热度"
        elif src == "央视新闻": media = extra; metric = "媒体"
        elif src == "IT之家": heat = extra; metric = "评论数"
        elif src == "百度贴吧": heat = extra; metric = "讨论量"
        else: summary = desc; heat = extra; metric = "热度" if extra else ""
        return media, summary, heat, metric

    all_items, errors = [], []
    for batch in [NODES[:7], NODES[7:]]:
        for node in batch:
            src = node["name"]
            try:
                req = urllib.request.Request(
                    "https://api.tophubdata.com/nodes/" + node["hashid"],
                    headers={"Authorization": tophub_key, "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data.get("data", {}).get("items", []):
                        title = clean(item.get("title", ""))
                        if not title: continue
                        media, summary, heat, metric = map_fields(src, item)
                        all_items.append({"来源": src, "标题": title, "摘要": summary, "url": clean(item.get("url","")), "热度": heat, "媒体": media, "指标类型": metric, "排名": item.get("rank","")})
            except Exception as e:
                errors.append(src + ": " + str(e))
        time.sleep(1)

    seen = set(); deduped = []
    for item in all_items:
        k = item["标题"][:30]
        if k not in seen: seen.add(k); deduped.append(item)

    out = ["共采集 " + str(len(all_items)) + " 条，去重后 " + str(len(deduped)) + " 条"]
    if errors: out.append("失败节点: " + "; ".join(errors))
    out.append("")
    for i, item in enumerate(deduped):
        has_desc = bool(item["摘要"] and item["摘要"].strip())
        label = "原生-话题" if (item["来源"] in TOPIC_SOURCES and has_desc) else "话题源-无摘要" if item["来源"] in TOPIC_SOURCES else "原生摘要" if has_desc else "待补充背景" if item["来源"] in NEED_BG else "无摘要"
        mt = ""
        if item.get("媒体"): mt += " | 媒体: " + item["媒体"]
        if item.get("热度"): mt += " | " + (item.get("指标类型") or "热度") + ": " + item["热度"]
        dp = item["摘要"][:50] if item["摘要"] else "(空)"
        out.append(str(i+1) + ". [" + item["来源"] + "] " + item["标题"])
        out.append("   排名: " + str(item.get("排名","")) + mt + " | 来源标记: " + label)
        out.append("   摘要: " + dp)
        out.append("")
    return {"fetch_results": "\n".join(out) + "\n\n===DATA===\n" + json.dumps(deduped, ensure_ascii=False)}
