import json, re

def preprocess_items(fetch_results):
    MAX_LLM_ITEMS = 500
    MAX_DESC_CHARS = 140

    def parse_items(value):
        raw = value
        if isinstance(raw, dict):
            if isinstance(raw.get("items"), list): return raw["items"]
            if "items_json" in raw:
                try: return json.loads(raw["items_json"])
                except: pass
            if "fetch_results" in raw: raw = raw["fetch_results"]
        if not isinstance(raw, str): raw = str(raw)
        raw = raw.strip()
        if not raw: return []
        if "===DATA===" in raw:
            try: return json.loads(raw.split("===DATA===", 1)[-1].strip())
            except: return []
        start, end = raw.find("["), raw.rfind("]")
        if start >= 0 and end > start:
            try: return json.loads(raw[start:end+1])
            except: pass
        try: return json.loads(raw)
        except: return []

    def clean_text(value, limit=0):
        text = "" if value is None else str(value)
        text = re.sub(r"\s+", " ", text).strip()
        if limit and len(text) > limit: return text[:limit] + "..."
        return text

    def contains_any(text, words):
        low = text.lower()
        return any(w.lower() in low for w in words)

    STRONG_DROP_KW = ["\u6e38\u620f","\u7535\u7ade","lol","\u738b\u8005\u8363\u8000","\u5403\u9e21","\u539f\u795e","\u5d29\u574f","dota","cs","\u9b54\u517d","\u7089\u77f3","\u5b88\u671b\u5148\u950b","\u6c38\u52ab","\u65e0\u754f\u5951\u7ea6","steam","epic","xbox","playstation","switch","\u62bd\u5361","\u6c2a\u91d1","\u76ae\u80a4","\u8d5b\u5b63","\u6bb5\u4f4d","\u6392\u4f4d","\u5f00\u9ed1","\u653b\u7565","\u901a\u5173","boss","\u526f\u672c","\u4e16\u754c\u676f","\u82f1\u8d85","\u897f\u7532","nba","cba","\u4e2d\u8d85","\u6b27\u51a0","\u8054\u8d5b","\u8fdb\u7403","\u6bd4\u5206","\u593a\u51a0","\u51a0\u519b","\u4e9a\u519b","\u91d1\u724c","\u94f6\u724c","\u94dc\u724c","\u8db3\u7403","\u7bee\u7403","\u7f51\u7403","\u7fbd\u6bdb\u7403","\u4e52\u4e53\u7403","\u6e38\u6cf3","\u7530\u5f84","\u4f53\u64cd","\u8df3\u6c34","\u4e3e\u91cd","\u8fd0\u52a8\u5458","\u6559\u7ec3","\u88c1\u5224","\u8f6c\u4f1a","\u7b7e\u7ea6","\u9000\u5f79","\u590d\u51fa","\u5168\u7ea2\u5a5f","\u9648\u828b\u6e58","\u90d1\u94a6\u6587","\u5b59\u9896\u838e","\u738b\u695a\u94a6","\u6a0a\u632f\u4e1c","\u9a6c\u9f99","\u7a7f\u642d","\u9020\u578b","\u7ea2\u6bef","\u5199\u771f","\u8def\u900f","\u751f\u56fe","\u989c\u503c","\u8eab\u6750","\u604b\u60c5","\u5206\u624b","\u7ed3\u5a5a","\u79bb\u5a5a","\u51fa\u8f68","\u5c0f\u4e09","\u7efc\u827a","\u771f\u4eba\u79c0","\u9009\u79c0","\u51fa\u9053","\u5076\u50cf","\u7537\u56e2","\u5973\u56e2","\u65b0\u5267","\u65b0\u6b4c","\u6f14\u5531\u4f1a","\u7968\u623f","\u6536\u89c6\u7387","\u7f51\u5267","\u53e4\u5076","\u7c89\u4e1d","\u5e94\u63f4","\u7ad9\u59d0","\u79c1\u751f","\u996d\u5708","\u8d85\u8bdd","\u52a8\u6f2b","\u756a\u5267","\u6f2b\u753b","\u4e8c\u6b21\u5143","cos","\u6f2b\u5c55","\u517b\u751f","\u51cf\u80a5","\u7626\u8eab","\u5065\u8eab","\u763c\u4f0d","\u8dd1\u6b65","\u661f\u5ea7","\u7b97\u547d","\u98ce\u6c34","\u5854\u7f57","\u9e21\u6c64","\u52b1\u5fd7","\u6b63\u80fd\u91cf","\u4eba\u751f\u611f\u609f","\u60c5\u611f"]
    WEAK_DROP_KW = ["\u624b\u673a","\u82af\u7247","\u5904\u7406\u5668","\u663e\u5361","\u7b14\u8bb0\u672c","\u5e73\u677f","\u8033\u673a","\u667a\u80fd\u624b\u8868","ios","android","windows","mac","linux","\u9e3f\u8499","\u66f4\u65b0","\u7248\u672c","\u4e0b\u8f7d","\u5b89\u88c5","\u6559\u7a0b","\u6280\u5de7","\u6d4b\u8bc4","\u5f00\u7bb1","\u8bc4\u6d4b","\u53d1\u5e03","\u4e0a\u5e02\u65f6\u95f4"]
    KEEP_KW = ["\u4e2d\u56fd","\u4e2d\u65b9","\u6d89\u534e","\u53f0\u6e7e","\u53f0\u6d77","\u5357\u6d77","\u5916\u4ea4","\u5236\u88c1","\u5c01\u9501","\u7981\u4ee4","\u5b9e\u4f53\u6e05\u5355","\u51fa\u53e3\u7ba1\u5236","\u5173\u7a0e","\u7f8e\u56fd\u5546\u52a1\u90e8","\u79d1\u6280\u81ea\u7acb","\u4e00\u53f7\u9886\u5bfc\u4eba","\u4e3b\u5e2d\u4ee4","\u653f\u6cbb\u5c40","\u4e2d\u592e\u7ecf\u6d4e\u5de5\u4f5c\u4f1a\u8bae","\u4e2d\u592e\u519c\u6751\u5de5\u4f5c\u4f1a\u8bae","\u5168\u4f1a","\u7701\u59d4","\u5e02\u59d4","\u4e2d\u5171\u4e2d\u592e","\u8150\u8d25","\u843d\u9a6c","\u8c03\u67e5","\u901a\u62a5","\u4e3e\u62a5","\u6267\u6cd5","\u53f8\u6cd5","\u51a4\u6848","\u7ef4\u6743","\u8ba8\u85aa","\u7f62\u5de5","\u5f81\u5730","\u62c6\u8fc1","\u5730\u65b9\u503a","\u7fa4\u4f53","\u4e8b\u6545","\u7206\u70b8","\u706b\u707e","\u4f24\u4ea1","\u6b7b\u4ea1","\u5931\u8054","\u81ea\u6740","\u6821\u56ed\u9738\u51cc","\u672a\u6210\u5e74\u4eba","\u5b66\u751f","\u6559\u5e08","\u533b\u751f","\u533b\u9662","\u533b\u60a3","\u98df\u54c1\u5b89\u5168","\u6cc4\u9732","\u5077\u62cd","\u7a83\u542c","\u6362\u8138","\u7b97\u6cd5","\u5ba1\u6838","\u6b67\u89c6","\u9020\u5047","\u8bc8\u9a97","\u8dd1\u8def","\u6027\u4fb5","\u6027\u9a9a\u6270","\u5bb6\u66b4","\u8c23\u8a00","\u9634\u8c0b\u8bba","ai","\u4eba\u5de5\u667a\u80fd","deepseek","claude","tiktok","\u88c1\u5458","\u4fe1\u4efb\u4e0e\u5b89\u5168","\u5e73\u53f0\u5b89\u5168","\u534e\u4e3a","\u534a\u5bfc\u4f53","\u56fd\u53f0\u529e","\u4e03\u4e03\u4e8b\u53d8","\u4e03\u4e03","\u6838\u6c61\u67d3","\u6838\u6c61\u6c34","\u8d2a\u8150","\u53d7\u8d3f","\u53cc\u5f00","\u7559\u7f6e","\u5173\u505c","\u67e5\u5c01","\u7ed1\u67b6","\u9047\u96be","\u9047\u5bb3","\u793a\u5a01","\u6297\u8bae","\u6e38\u884c","\u5ba1\u67e5","\u7ea6\u8c08","\u5904\u7f5a","\u6574\u6539","\u75ab\u82d7","\u75ab\u60c5","\u5c01\u63a7","\u6781\u7aef","\u6050\u6016","\u7f51\u66b4","\u4eba\u8089","\u8206\u60c5","\u7279\u9996","\u6e2f\u6fb3","\u603b\u7763","\u4e2d\u4f01","\u4e2d\u56fd\u516c\u6c11","\u6d77\u5916\u534e\u4eba","\u4e60\u8fd1\u5e73","\u603b\u4e66\u8bb0","\u56fd\u5bb6\u4e3b\u5e2d"]
    SOURCE_WEIGHT = {"\u592e\u89c6\u65b0\u95fb":5,"\u65b0\u6d6a\u56fd\u5185\u65b0\u95fb":4,"\u65b0\u4eac\u62a5":4,"\u6f8e\u6e43\u65b0\u95fb":4,"\u5fae\u535a":3,"\u767e\u5ea6":3,"\u4eca\u65e5\u5934\u6761":3,"\u77e5\u4e4e":2,"\u767e\u5ea6\u8d34\u5427":2,"\u5fae\u4fe1":2,"\u6296\u97f3":2,"IT\u4e4b\u5bb6":1}
    CCTV_LOW_PRIORITY_KW = ["\u9a7b","\u63d0\u9192","\u5730\u9707\u6b7b\u4ea1","\u5317\u7ea6","\u666e\u4eac","\u7279\u6717\u666e","\u54c8\u6885\u5185\u4f0a","\u4f0a\u6717","\u59d4\u5185\u745e\u62c9","\u53e4\u5df4","\u52a0\u7eb3","\u65af\u6d1b\u4f10\u514b","\u683c\u9675\u5170","\u521a\u679c","\u4e16\u536b\u7ec4\u7ec7","\u57c3\u535a\u62c9","\u610f\u5927\u5229","\u6cd5\u56fd","\u5fb7\u56fd","\u65e5\u672c","\u97e9\u56fd","\u5370\u5ea6","\u5370\u5c3c","\u5df4\u57fa\u65af\u5766","\u5409\u5c14\u5409\u65af","\u53d9\u5229\u4e9a","\u79d1\u5a01\u7279","\u4ee5\u8272\u5217","\u5df4\u52d2\u65af\u5766","\u4f0a\u62c9\u514b","\u571f\u8033\u5176","\u6c99\u7279","\u963f\u66fc","\u6b27\u8db3\u8054","\u56fd\u9645\u5965\u59d4\u4f1a","\u539f\u6cb9","\u5929\u7136\u6c14","\u80a1\u5e02","\u56fd\u503a"]

    items = parse_items(fetch_results)
    if not items:
        return {"items_json":"[]","to_llm_text":"","auto_out_json":"[]","stats_json": json.dumps({"raw_count":0,"llm_sent_count":0}, ensure_ascii=False)}

    normalized = []
    for i, raw_item in enumerate(items, 1):
        item = dict(raw_item)
        item["idx"] = i
        item["\u6765\u6e90"] = clean_text(item.get("\u6765\u6e90",""))
        item["\u6807\u9898"] = clean_text(item.get("\u6807\u9898",""))
        item["\u6458\u8981"] = clean_text(item.get("\u6458\u8981",""), MAX_DESC_CHARS)
        item["\u5a92\u4f53"] = clean_text(item.get("\u5a92\u4f53",""))
        item["url"] = clean_text(item.get("url",""))
        item["\u70ed\u5ea6"] = clean_text(item.get("\u70ed\u5ea6",""))
        item["\u6307\u6807\u7c7b\u578b"] = clean_text(item.get("\u6307\u6807\u7c7b\u578b",""))
        item["\u6392\u540d"] = item.get("\u6392\u540d","")
        if item["\u6807\u9898"]: normalized.append(item)

    to_llm_candidates, auto_out = [], []

    for item in normalized:
        src = item.get("\u6765\u6e90","")
        title = item.get("\u6807\u9898","")
        desc = item.get("\u6458\u8981","")
        media = item.get("\u5a92\u4f53","")
        text = title + " " + desc + " " + src + " " + media
        keep_hit = contains_any(text, KEEP_KW)

        if not keep_hit and contains_any(text, STRONG_DROP_KW):
            auto_out.append({**item, "\u5206\u7c7b":"L","\u51b2\u7a81\u5f3a\u5ea6":0,"\u6781\u6027":0,"\u4e3b\u4f53":"","\u57fa\u7840\u5206":0,"\u7efc\u5408\u8bc4\u5206":1,"\u6700\u7ec8\u5224\u5b9a":"\u6dd8\u6c70","\u5165\u9009\u7406\u7531":"\u81ea\u52a8\u6dd8\u6c70\uff1a\u5a31\u4e50\u4f53\u80b2\u751f\u6d3b\u5185\u5bb9","pre_filter":"\u81ea\u52a8\u6dd8\u6c70","pre_filter_reason":"STRONG_DROP_KW\u547d\u4e2d"})
            continue
        if not keep_hit and contains_any(text, WEAK_DROP_KW):
            auto_out.append({**item, "\u5206\u7c7b":"L","\u51b2\u7a81\u5f3a\u5ea6":0,"\u6781\u6027":0,"\u4e3b\u4f53":"","\u57fa\u7840\u5206":0,"\u7efc\u5408\u8bc4\u5206":1,"\u6700\u7ec8\u5224\u5b9a":"\u6dd8\u6c70","\u5165\u9009\u7406\u7531":"\u81ea\u52a8\u6dd8\u6c70\uff1a\u666e\u901a\u79d1\u6280\u6d88\u8d39\u5185\u5bb9","pre_filter":"\u81ea\u52a8\u6dd8\u6c70","pre_filter_reason":"WEAK_DROP_KW\u547d\u4e2d"})
            continue

        if desc:
            input_text = "\u3010\u6807\u9898\u3011" + title + "\n\u3010\u6458\u8981\u3011" + desc
        elif "\u77e5\u4e4e" in src or "\u8d34\u5427" in src:
            input_text = "\u3010\u6807\u9898\u3011" + title + "\n\uff08\u8bdd\u9898\u6765\u6e90\uff0c\u65e0\u6458\u8981\uff0c\u4fe1\u606f\u6709\u9650\uff09"
        else:
            input_text = "\u3010\u6807\u9898\u3011" + title + "\n\uff08\u4ec5\u6709\u6807\u9898\uff0c\u65e0\u6458\u8981\uff0c\u9700\u4fdd\u5b88\u5224\u65ad\uff09"
        if media: input_text += "\n\u3010\u5a92\u4f53\u3011" + media
        if item.get("\u70ed\u5ea6"):
            metric = item.get("\u6307\u6807\u7c7b\u578b") or "\u70ed\u5ea6"
            input_text += "\n\u3010" + metric + "\u3011" + item.get("\u70ed\u5ea6")
        item["_input"] = input_text

        priority = (100 if keep_hit else 0) + SOURCE_WEIGHT.get(src, 0) * 10 + max(0, 80 - int(item.get("\u6392\u540d") or 80)) / 80
        if src == "\u592e\u89c6\u65b0\u95fb" and contains_any(title + media, CCTV_LOW_PRIORITY_KW):
            china_kw = {"\u4e2d\u56fd","\u4e2d\u65b9","\u6d89\u534e","\u53f0\u6e7e","\u53f0\u6d77","\u5357\u6d77","\u4e60\u8fd1\u5e73","\u56fd\u53f0\u529e","\u56fd\u9632\u90e8","\u5916\u4ea4\u90e8"}
            if not contains_any(title + media, china_kw):
                priority //= 2
        item["_priority"] = priority
        item["pre_filter"] = "\u81ea\u52a8\u4fdd\u7559"
        item["pre_filter_reason"] = "KEEP_KW\u547d\u4e2d" if keep_hit else "\u5e38\u89c4"
        to_llm_candidates.append(item)

    to_llm_candidates.sort(key=lambda x: x.get("_priority", 0), reverse=True)
    to_llm = to_llm_candidates[:MAX_LLM_ITEMS]
    overflow = to_llm_candidates[MAX_LLM_ITEMS:]

    for item in overflow:
        auto_out.append({**item, "\u5206\u7c7b":"L","\u51b2\u7a81\u5f3a\u5ea6":0,"\u6781\u6027":0,"\u4e3b\u4f53":"","\u57fa\u7840\u5206":0,"\u7efc\u5408\u8bc4\u5206":1,"\u6700\u7ec8\u5224\u5b9a":"\u6dd8\u6c70","\u5165\u9009\u7406\u7531":"\u8d85\u51fa\u5355\u6279LLM\u4e0a\u9650\uff0c\u6682\u672a\u5206\u6790","pre_filter":"\u81ea\u52a8\u6dd8\u6c70","pre_filter_reason":"\u8d85\u51fa\u4e0a\u9650"})

    user_parts = []
    for item in to_llm:
        user_parts.append("\u5e8f\u53f7" + str(item["idx"]) + " [" + item["\u6765\u6e90"] + "] " + item["\u6807\u9898"] + "\n" + item["_input"])

    def public_item(item):
        return {k:v for k,v in item.items() if not str(k).startswith("_")}

    stats = {"raw_count": len(items), "valid_count": len(normalized), "auto_out_count": len(auto_out), "llm_candidate_count": len(to_llm_candidates), "llm_sent_count": len(to_llm), "overflow_count": len(overflow), "max_llm_items": MAX_LLM_ITEMS, "max_desc_chars": MAX_DESC_CHARS}

    return {"items_json": json.dumps([public_item(x) for x in normalized], ensure_ascii=False), "to_llm_text": "\n\n".join(user_parts), "auto_out_json": json.dumps([public_item(x) for x in auto_out], ensure_ascii=False), "stats_json": json.dumps(stats, ensure_ascii=False)}
