import json, re, sys, os

from fetch_impl import fetch_tophub
from preprocess_impl import preprocess_items
from postprocess_impl import postprocess_results
from llm_client import evaluate_items

_this_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_this_dir, "clean_prompt.txt"), "r", encoding="utf-8") as _f:
    SYSTEM_PROMPT = _f.read()


def step_fetch(tophub_key, progress_cb=None):
    """调用 Tophub API 抓取舆情"""
    result = fetch_tophub(tophub_key)
    if progress_cb:
        progress_cb("抓取完成")
    return result


def step_preprocess(fetch_results, progress_cb=None):
    """关键词过滤 + 优先级排序"""
    result = preprocess_items(fetch_results)
    if progress_cb:
        s = json.loads(result["stats_json"])
        progress_cb(f"预处理完成: {s['raw_count']}条 -> LLM {s['llm_sent_count']}条, 自动淘汰 {s['auto_out_count']}条")
    return result


def step_fetch_articles(items, progress_cb=None):
    """抓取原文并评估质量"""
    from core import process_all
    items_list = items if isinstance(items, list) else json.loads(items)
    results, stats = process_all(items_list, progress_cb)
    if progress_cb:
        progress_cb(f"原文抓取完成: {stats['success']}/{stats['total']} 成功")
    return {"items": results, "stats": stats}


def _enrich_with_articles(to_llm_text, fetch_results):
    """将抓取到的原文内容注入到 LLM 输入中"""
    items = fetch_results.get("items", []) if isinstance(fetch_results, dict) else fetch_results
    content_map = {}
    for item in items:
        idx = item.get("idx")
        full_text = item.get("full_text") or ""
        if full_text and len(full_text) > 200:
            content_map[str(idx)] = full_text[:2000]
    if not content_map:
        return to_llm_text
    parts = to_llm_text.split("\n\n")
    enriched = []
    for part in parts:
        if not part.strip():
            continue
        m = re.match(r"序号(\d+)", part)
        if m and m.group(1) in content_map:
            part += "\n【原文】" + content_map[m.group(1)]
        enriched.append(part)
    return "\n\n".join(enriched)


def step_llm_evaluate(to_llm_text, progress_cb=None, fetch_results=None):
    """调用 DeepSeek 评估条目（分批调用，避免截断）"""
    if not to_llm_text or not to_llm_text.strip():
        return {"raw_output": "", "error": "无可评估的条目"}
    
    # 如果有抓取结果，将原文内容注入到 LLM 输入中
    if fetch_results:
        enriched = _enrich_with_articles(to_llm_text, fetch_results)
        if enriched != to_llm_text:
            if progress_cb:
                progress_cb(f"已注入原文: {len(enriched.split(chr(10)+chr(10)))} 条带原文信息")
            to_llm_text = enriched
    
    # 拆分为单条，记录序号到文本块的映射
    items = [p for p in to_llm_text.split("\n\n") if p.strip()]
    total = len(items)
    batch_size = 60
    blocks = {}
    expected = set()
    for part in items:
        m = re.match(r"序号(\d+)", part)
        if m:
            idx = int(m.group(1))
            expected.add(idx)
            blocks[idx] = part

    def _parse_covered(text):
        covered = set()
        for line in (text or "").splitlines():
            m = re.match(r"\s*(\d+)\|", line)
            if m:
                covered.add(int(m.group(1)))
        return covered

    if progress_cb:
        progress_cb(f"正在分批调用 DeepSeek API 评估 ({total}条, 每批{batch_size}条)...")

    all_parts = []
    batches = (total + batch_size - 1) // batch_size
    for i in range(0, total, batch_size):
        batch = items[i:i+batch_size]
        batch_num = i // batch_size + 1
        batch_text = "\n\n".join(batch)
        if progress_cb:
            progress_cb(f"  正在调用 Batch {batch_num}/{batches} ({len(batch)}条)...")
        result = evaluate_items(SYSTEM_PROMPT, batch_text)
        if result is None:
            if progress_cb:
                progress_cb(f"  Batch {batch_num} API调用失败", "error")
            return {"raw_output": "", "error": f"API调用失败 (batch {batch_num})"}
        all_parts.append(result)
        if progress_cb:
            progress_cb(f"  Batch {batch_num}/{batches} 完成")

    combined = "\n".join(all_parts)

    # 漏行回填：找到缺失序号，单独重新请求，最多补 2 轮
    for round_no in range(1, 3):
        covered = _parse_covered(combined)
        missing = sorted(expected - covered)
        if not missing:
            break
        if progress_cb:
            progress_cb(f"漏行回填 Round {round_no}: 缺失 {len(missing)} 条，重新请求")
        missing_blocks = [blocks[i] for i in missing if i in blocks]
        for j in range(0, len(missing_blocks), batch_size):
            chunk = missing_blocks[j:j+batch_size]
            result = evaluate_items(SYSTEM_PROMPT, "\n\n".join(chunk))
            if result is None:
                if progress_cb:
                    progress_cb("  回填批次 API 调用失败", "error")
                break
            combined = combined + "\n" + result

    covered = _parse_covered(combined)
    if progress_cb:
        progress_cb(f"LLM 评估完成: 覆盖 {len(covered)}/{len(expected)} 条")

    return {"raw_output": combined}


def step_enrich_articles(postprocess_result, progress_cb=None, fetch_items=None):
    """对入选条目进行原文填充（搜索兜底）"""
    from core import fetch_with_search, _looks_like_feed, _title_match, _title_entity_match, _article_too_old
    import json

    fetch_map = {}
    if fetch_items:
        for fi in (fetch_items.get("items", []) if isinstance(fetch_items, dict) else fetch_items):
            try:
                fidx = int(fi.get("idx"))
            except Exception:
                continue
            if fi.get("full_text"):
                fetch_map[fidx] = fi
    
    result_json = json.loads(postprocess_result["result_json"])
    selected = [r for r in result_json if r.get("\u6700\u7ec8\u5224\u5b9a") == "\u5165\u9009"]
    
    if progress_cb:
        progress_cb(f"\u539f\u6587\u586b\u5145: \u5171 {len(selected)} \u6761\u5f85\u5904\u7406")
    
    enriched = []
    for item in selected:
        idx = item.get("idx", "?")
        source = item.get("\u6765\u6e90", "")
        current_quality = item.get("fetch_quality", "")
        
        # \u77e5\u4e4e/\u8d34\u5427\u8df3\u8fc7
        if source in ("\u77e5\u4e4e", "\u767e\u5ea6\u8d34\u5427"):
            if progress_cb:
                progress_cb(f"  #{idx} [{source}] \u8bdd\u9898\u6e90\u8df3\u8fc7")
            enriched.append(item)
            continue
        
        # \u5df2\u6709\u53ef\u7528\u539f\u6587\u7684\u76f4\u63a5\u590d\u7528\uff0c\u4f46\u5fc5\u987b\u901a\u8fc7\u6709\u6548\u6027\u6821\u9a8c\uff0c\u5426\u5219\u91cd\u65b0\u6293\u53d6
        if current_quality in ("real_article", "partial"):
            try:
                src = fetch_map.get(int(idx))
            except Exception:
                src = None
            src_text = (src or {}).get("full_text") or ""
            if src_text and not _looks_like_feed(src_text) and _title_match(item.get("\u6807\u9898", ""), src_text) and _title_entity_match(item.get("\u6807\u9898", ""), src_text) and not _article_too_old(src_text):
                item["full_text"] = src_text
                item["fetch_status"] = src.get("fetch_status", "")
                item["matched_url"] = src.get("matched_url", "")
                if progress_cb:
                    progress_cb(f"  #{idx} [{source}] \u5df2\u6709\u53ef\u7528\u539f\u6587")
                enriched.append(item)
                continue
            if progress_cb:
                progress_cb(f"  #{idx} [{source}] \u65e7\u6b63\u6587\u6821\u9a8c\u672a\u901a\u8fc7\uff0c\u91cd\u65b0\u6293\u53d6")
        
        if progress_cb:
            progress_cb(f"  #{idx} [{source}] \u641c\u7d22\u4e2d...")
        
        result = fetch_with_search(item, progress_cb)
        item["full_text"] = result.get("full_text")
        item["fetch_quality"] = result.get("fetch_quality", "unavailable")
        item["fetch_status"] = result.get("fetch_status", "")
        enriched.append(item)
    
    success = len([r for r in enriched if r.get("fetch_quality") == "real_article"])
    downgraded = 0
    for r in enriched:
        if r.get("fetch_quality") == "topic_source":
            continue
        if not r.get("full_text") and r.get("\u6700\u7ec8\u5224\u5b9a") == "\u5165\u9009":
            r["\u6700\u7ec8\u5224\u5b9a"] = "\u5f85\u89c2\u5bdf"
            r["\u539f\u6587\u56de\u586b"] = "\u5931\u8d25: " + (r.get("fetch_status") or "\u672a\u83b7\u53d6\u5230\u539f\u6587")
            downgraded += 1
    if progress_cb:
        progress_cb(f"\u539f\u6587\u586b\u5145\u5b8c\u6210: {success}/{len(selected)} \u6761\u6210\u529f\uff0c\u56de\u586b\u5931\u8d25\u964d\u7ea7 {downgraded} \u6761")
    
    return {"enriched": enriched, "stats": {"total": len(selected), "success": success, "downgraded": downgraded}}

def step_postprocess(llm_raw, items_json, auto_out_json, progress_cb=None, fetch_items=None):
    """解析 LLM 输出，计算评分，合并结果，去重"""
    result = postprocess_results(llm_raw, items_json, auto_out_json, fetch_items)
    if progress_cb:
        r = json.loads(result["result_json"])
        selected = [i for i in r if i.get("最终判定") == "入选"]
        watching = [i for i in r if i.get("最终判定") == "待观察"]
        progress_cb(f"后处理完成: 入选 {len(selected)}条, 待观察 {len(watching)}条")
    return result


def run_full_pipeline(tophub_key, progress_cb=None):
    """完整的抓取+清洗流程"""
    state = {"step": 0, "data": None}

    if progress_cb:
        progress_cb("=== Step 1: 抓取 ===")
    fetch_result = step_fetch(tophub_key, progress_cb)
    state["step"] = 1
    state["fetch_result"] = fetch_result

    if progress_cb:
        progress_cb("=== Step 2: 预处理 ===")
    pre_result = step_preprocess(fetch_result, progress_cb)
    state["step"] = 2
    state["pre_result"] = pre_result

    if progress_cb:
        progress_cb("=== Step 3: 原文抓取 ===")
    items_for_fetch = json.loads(pre_result["items_json"])
    fetch_art_result = step_fetch_articles(items_for_fetch, progress_cb)
    state["step"] = 3
    state["fetch_art_result"] = fetch_art_result

    if progress_cb:
        progress_cb("=== Step 4: LLM 评估 ===")
    llm_result = step_llm_evaluate(pre_result["to_llm_text"], progress_cb)
    state["step"] = 4
    state["llm_result"] = llm_result

    if progress_cb:
        progress_cb("=== Step 5: 后处理 ===")
    post_result = step_postprocess(
        llm_result["raw_output"],
        pre_result["items_json"],
        pre_result["auto_out_json"],
        progress_cb
    )
    state["step"] = 5
    state["post_result"] = post_result

    if progress_cb:
        progress_cb("=== 全部完成 ===")
    return state
