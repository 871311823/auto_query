import json, re, math
from collections import defaultdict

def postprocess_results(llm_raw, items_json, auto_out_json, fetch_items=None):
    CAT_BASE = {"A":7,"B":6,"C":6,"E":6,"I":5,"G":5,"H":6,"K":5,"D":4,"F":3,"J":3,"L":0}
    SUBJECTS = {"\u672a\u6210\u5e74\u4eba","\u6559\u5e08","\u533b\u751f","\u5b66\u751f","\u519c\u6c11","\u519c\u6c11\u5de5","\u516c\u52a1\u5458","\u592e\u4f01","\u56fd\u4f01","\u5730\u65b9\u653f\u5e9c","\u8001\u4eba"}

    def load_list(value):
        if isinstance(value, list): return value
        if isinstance(value, dict): return [value]
        if not value: return []
        try: return json.loads(value) if isinstance(json.loads(value), list) else []
        except: return []

    def split_categories(cat):
        text = (cat or "").upper()
        return [p for p in re.split(r"[,,\uff0c+/\u3001\s]+", text) if p]

    def get_base(cat):
        cats = split_categories(cat)
        if not cats or "L" in cats: return 0
        return max([CAT_BASE.get(c, 0) for c in cats])

    def calc_subj(subject):
        if not subject: return 0
        parts = re.split(r"[,,\uff0c+/\u3001\s]+", subject)
        return 1 if any(p.strip() in SUBJECTS for p in parts) else 0

    def to_int(value, default=0):
        try: return int(str(value).strip())
        except: return default

    def calc_score(cat, conflict, polarity, subject):
        base = get_base(cat)
        if base == 0: return 1
        score = base + (conflict - 5) * 0.4 + polarity * (-0.2) + calc_subj(subject)
        return max(1, min(10, round(score * 10) / 10))

    def verdict(score, source):
        threshold = 6.5 if ("\u77e5\u4e4e" in source or "\u8d34\u5427" in source) else 7.0
        if score >= threshold: return "\u5165\u9009"
        if score >= 5: return "\u5f85\u89c2\u5bdf"
        return "\u6dd8\u6c70"

    def parse_llm_lines(content):
        parsed = []
        for raw_line in str(content or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("---"): continue
            if "|" not in line: continue
            if line.startswith("\u5e8f\u53f7|") or line.startswith("idx|"): continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 7: continue
            idx_text = re.sub(r"^[#\u7b2c\s]*", "", parts[0]).rstrip(".,\u3001)")
            if not idx_text.isdigit(): continue
            idx = int(idx_text)
            cat = parts[1].upper()
            conflict = to_int(parts[2], -1)
            polarity = to_int(parts[3], 0)
            if conflict < 0 or conflict > 10: continue
            if polarity < -5 or polarity > 5: polarity = max(-5, min(5, polarity))
            subject = parts[4] if len(parts) > 4 else ""
            reason = parts[5] if len(parts) > 5 else ""
            suggest = parts[6] if len(parts) > 6 else ""
            summary_col = parts[7] if len(parts) > 7 else "-"
            dedup = parts[8] if len(parts) > 8 else "\u65b0\u4e8b\u4ef6"
            parsed.append({"idx": idx, "\u5206\u7c7b": cat, "\u51b2\u7a81\u5f3a\u5ea6": conflict, "\u6781\u6027": polarity, "\u4e3b\u4f53": subject, "\u5165\u9009\u7406\u7531": reason, "\u6a21\u578b\u5efa\u8bae": suggest, "\u8206\u60c5\u6458\u8981": summary_col or "-", "\u53bb\u91cd\u5224\u5b9a": dedup if dedup in {"\u65b0\u4e8b\u4ef6","\u540c\u4e8b\u4ef6\u66f4\u65b0","\u91cd\u590d"} else "\u65b0\u4e8b\u4ef6"})
        return parsed

    items = load_list(items_json)
    auto_out = load_list(auto_out_json)
    item_by_idx = {to_int(item.get("idx")): item for item in items if to_int(item.get("idx")) > 0}
    to_llm_idx = {idx for idx, item in item_by_idx.items() if item.get("idx") and not any(to_int(a.get("idx")) == idx for a in auto_out)}

    parsed_rows = parse_llm_lines(llm_raw)
    parsed_by_idx = {}
    for row in parsed_rows:
        if row["idx"] in item_by_idx: parsed_by_idx[row["idx"]] = row

    llm_results = []
    for idx, row in parsed_by_idx.items():
        item = item_by_idx[idx]
        source = item.get("\u6765\u6e90","")
        cat = row["\u5206\u7c7b"]
        conflict = row["\u51b2\u7a81\u5f3a\u5ea6"]
        polarity = row["\u6781\u6027"]
        subject = row["\u4e3b\u4f53"]
        score = calc_score(cat, conflict, polarity, subject)
        final_v = verdict(score, source)
        llm_results.append({"idx": idx, "\u6765\u6e90": source, "\u5a92\u4f53": item.get("\u5a92\u4f53",""), "\u6807\u9898": item.get("\u6807\u9898",""), "url": item.get("url",""), "\u70ed\u5ea6": item.get("\u70ed\u5ea6",""), "\u6307\u6807\u7c7b\u578b": item.get("\u6307\u6807\u7c7b\u578b",""), "\u5206\u7c7b": cat, "\u57fa\u7840\u5206": get_base(cat), "\u51b2\u7a81\u5f3a\u5ea6": conflict, "\u6781\u6027": polarity, "\u4e3b\u4f53": subject, "\u4e3b\u4f53\u4fee\u6b63": calc_subj(subject), "\u7efc\u5408\u8bc4\u5206": score, "\u6700\u7ec8\u5224\u5b9a": final_v, "\u6a21\u578b\u5efa\u8bae": row.get("\u6a21\u578b\u5efa\u8bae",""), "\u5165\u9009\u7406\u7531": row.get("\u5165\u9009\u7406\u7531","")[:80], "\u8206\u60c5\u6458\u8981": "-", "\u53bb\u91cd\u5224\u5b9a": row.get("\u53bb\u91cd\u5224\u5b9a","\u65b0\u4e8b\u4ef6")})

    parsed_idx = set(parsed_by_idx.keys())
    fallback_results = []
    for idx in sorted(to_llm_idx - parsed_idx):
        item = item_by_idx[idx]
        fallback_results.append({"idx": idx, "\u6765\u6e90": item.get("\u6765\u6e90",""), "\u5a92\u4f53": item.get("\u5a92\u4f53",""), "\u6807\u9898": item.get("\u6807\u9898",""), "url": item.get("url",""), "\u70ed\u5ea6": item.get("\u70ed\u5ea6",""), "\u6307\u6807\u7c7b\u578b": item.get("\u6307\u6807\u7c7b\u578b",""), "\u5206\u7c7b": "L", "\u57fa\u7840\u5206": 0, "\u51b2\u7a81\u5f3a\u5ea6": 0, "\u6781\u6027": 0, "\u4e3b\u4f53": "", "\u4e3b\u4f53\u4fee\u6b63": 0, "\u7efc\u5408\u8bc4\u5206": 1, "\u6700\u7ec8\u5224\u5b9a": "\u6dd8\u6c70", "\u6a21\u578b\u5efa\u8bae": "\u6dd8\u6c70", "\u5165\u9009\u7406\u7531": "LLM\u672a\u8fd4\u56de\u6216\u683c\u5f0f\u9519\u8bef", "\u8206\u60c5\u6458\u8981": "-", "\u53bb\u91cd\u5224\u5b9a": "\u65b0\u4e8b\u4ef6"})

    all_results = llm_results + fallback_results + auto_out
    all_results.sort(key=lambda x: to_int(x.get("idx")))

    # ==== fetch_quality ====
    quality_map = {}
    if fetch_items:
        for fi in (fetch_items if isinstance(fetch_items, list) else fetch_items.get("items", [])):
            idx_q = to_int(fi.get("idx"))
            if idx_q > 0:
                quality_map[idx_q] = fi.get("fetch_quality", "")

    for r in all_results:
        r["fetch_quality"] = quality_map.get(to_int(r.get("idx")), "")

    # ==== dedup ====
    def _dedup(items):
        if len(items) <= 1: return items
        def qr(q):
            return {"real_article":3,"partial":2,"search_only":1}.get(q or "",0)
        # 解析"与N"从入选理由中找引用的 anchor idx
        anchors = {}  # anchor_idx -> [items]
        lone = []
        for item in items:
            reason = item.get("入选理由","") or ""
            m = re.search(r"与(\d+)", reason)
            if m:
                anchor = int(m.group(1))
                anchors.setdefault(anchor, []).append(item)
            else:
                lone.append(item)
        # 将 anchor 本身从 lone 中移到对应组
        for anchor in list(anchors.keys()):
            for item in lone[:]:
                if to_int(item.get("idx")) == anchor:
                    anchors[anchor].append(item)
                    lone.remove(item)
                    break
        # 合并结果
        kept = []
        for group in anchors.values():
            group.sort(key=lambda x: (-qr(x.get("fetch_quality","")), -float(x.get("综合评分",0)), to_int(x.get("idx"))))
            kept.append(group[0])
            for d in group[1:]:
                d["最终判定"] = "淘汰"
                d["去重判定"] = "重复"
        # 剩余的 lone 使用标题相似度作为补充
        if lone:
            def tok(t):
                t = re.sub(r"[^一-鿿\w]","",str(t or ""))
                if not t: return set()
                stop = {"的","了","在","是","我","你","他","她","这","那","和","与","就","也","都","而","但","或","被","把","对","从","到","以","为","上","下","中","大","小","不","没","有","将","会","已","能","可","要","让","向","往","来","去","说","看","做","用","打","出","入","还","又","再","才","只","更","最","很","太","非","反","正","第","之","所","其","该","各","每","比","如","等","及","于","过","后","前","内","外","多","少","几","两","个","些","某","哪","谁","何","什","么","怎","样","啊","吧","吗","呢","哈","呀","哦","嗯","哇","哎","喂","一","二","三","四","五","六","七","八","九","十","百","千","万","亿"}
                c = [x for x in t if x not in stop]
                return set(c[i]+c[i+1] for i in range(len(c)-1))
            def sim(t1,t2):
                s1,s2 = tok(t1),tok(t2)
                if not s1 or not s2: return 0.0
                return len(s1&s2)/len(s1|s2) if (s1|s2) else 0.0
            si = sorted(lone, key=lambda x: to_int(x.get("idx")))
            n = len(si); asg = [False]*n
            for i in range(n):
                if asg[i]: continue
                g = [si[i]]; asg[i]=True
                ti = si[i].get("标题","")
                for j in range(i+1,n):
                    if asg[j]: continue
                    if sim(ti, si[j].get("标题","")) > 0.35:
                        g.append(si[j]); asg[j]=True
                g.sort(key=lambda x: (-qr(x.get("fetch_quality","")), -float(x.get("综合评分",0)), to_int(x.get("idx"))))
                kept.append(g[0])
                for d in g[1:]:
                    d["最终判定"] = "淘汰"
                    d["去重判定"] = "重复"
        return kept

    # 合并入选+待观察一起去重
    act = [r for r in all_results if r.get("最终判定") == "入选"]
    wat = [r for r in all_results if r.get("最终判定") == "待观察"]
    rej = [r for r in all_results if r.get("最终判定") == "淘汰"]
    # 去重只对入选操作，待观察保持原样不被吞
    act = _dedup(act)
    act.sort(key=lambda x: -float(x.get("综合评分",0)))
    sel = [r for r in act if r.get("最终判定") == "入选"]
    # wat 保持原始待观察列表，不被去重吞掉
    all_results = sel + wat + rej
    all_results.sort(key=lambda x: to_int(x.get("idx")))
    selected = [r for r in all_results if r.get("最终判定") == "入选"]
    watching = [r for r in all_results if r.get("最终判定") == "待观察"]
    rejected = [r for r in all_results if r.get("最终判定") == "淘汰"]
    selected.sort(key=lambda x: -float(x.get("综合评分",0)))
    watching.sort(key=lambda x: -float(x.get("综合评分",0)))
    dedup_count = len([r for r in all_results if r.get("去重判定") == "重复"])

    lines = ["===== \u8206\u60c5\u6e05\u6d17\u62a5\u544a v4.0 ====="]
    lines.append(("\u603b\u6761\u76ee: " + str(len(items)) + "\u6761 | LLM\u89e3\u6790\u6210\u529f: " + str(len(llm_results)) + "\u6761 | \u89e3\u6790\u5157\u5e95: " + str(len(fallback_results)) + "\u6761 | \u81ea\u52a8\u5904\u7406: " + str(len(auto_out)) + "\u6761"))
    lines.append("\u5165\u9009: " + str(len(selected)) + "\u6761 | \u5f85\u89c2\u5bdf: " + str(len(watching)) + "\u6761 | \u6dd8\u6c70: " + str(len(rejected)) + "\u6761")
    lines.append("")

    if selected:
        lines.append("--- \u5165\u9009\u9879 ---")
        for r in selected:
            media = " / " + r["\u5a92\u4f53"] if r.get("\u5a92\u4f53") else ""
            lines.append("#" + f"{to_int(r['idx']):03d}" + " " + str(r["\u7efc\u5408\u8bc4\u5206"]) + "\u5206 [" + r["\u6765\u6e90"] + media + "] " + r["\u6807\u9898"][:50])
            lines.append("   \u5206\u7c7b:" + r["\u5206\u7c7b"] + " \u51b2\u7a81:" + str(r["\u51b2\u7a81\u5f3a\u5ea6"]) + " \u6781\u6027:" + str(r["\u6781\u6027"]) + " \u4e3b\u4f53:" + r["\u4e3b\u4f53"])
            lines.append("   \u7406\u7531:" + r["\u5165\u9009\u7406\u7531"][:80])
            if r.get("url"): lines.append("   URL:" + r["url"])
            lines.append("")

    if watching:
        lines.append("--- \u5f85\u89c2\u5bdf ---")
        for r in watching[:15]:
            media = " / " + r["\u5a92\u4f53"] if r.get("\u5a92\u4f53") else ""
            lines.append("#" + f"{to_int(r['idx']):03d}" + " " + str(r["\u7efc\u5408\u8bc4\u5206"]) + "\u5206 [" + r["\u6765\u6e90"] + media + "] " + r["\u6807\u9898"][:50])
        lines.append("")

    if fallback_results:
        lines.append("\u672a\u89e3\u6790\u5157\u5e95\u6761\u76ee: " + str(len(fallback_results)) + "\u6761")

    return {"result": "\n".join(lines), "result_json": json.dumps(all_results, ensure_ascii=False)}
