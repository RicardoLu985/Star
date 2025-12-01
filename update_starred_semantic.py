#!/usr/bin/env python3
# update_starred_semantic.py
# Full-feature V3（无暗黑模式）
# — 支持 overrides.json，自定义分类
# — 支持 CLI / 环境变量 / MANUAL 常量
# — topics / release / meta / tags 全部支持
# — HTML + Markdown 输出（无 Dark Mode）
# — 本地缓存（cache/*.json）
# — 支持 Sort By Stars
# — 自动生成 overrides_template.json

import os
import sys
import json
import time
import argparse
import logging
import requests
from collections import defaultdict
from datetime import datetime
import re
import hashlib

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# -------------------------
# Manual default config（可选）
# -------------------------
MANUAL_USERNAME = ""
MANUAL_TOKEN = ""

# -------------------------
# Constants
# -------------------------
CACHE_DIR = "cache"
CACHE_TTL_SECONDS = 3600
OUTPUT_MD = "starred.md"
OUTPUT_HTML = "docs/index.html"
OVERRIDES_PATH = "overrides.json"
OVERRIDES_TEMPLATE = "overrides_template.json"
GITHUB_API_ACCEPT = "application/vnd.github.mercy-preview+json"

# -------------------------
# Category Icons
# -------------------------
ICON_MAP = {
    "AI": ("fa-brain", "red-500"),
    "Web 开发": ("fa-code", "blue-500"),
    "DevOps & 工具": ("fa-tools", "indigo-500"),
    "脚本自动化": ("fa-robot", "yellow-500"),
    "学习资料": ("fa-book-open", "teal-500"),
    "其他": ("fa-box-open", "gray-500")
}

# -------------------------
# Keyword-based Category Map
# -------------------------
CATEGORY_MAP = {
    "AI": {
        "机器学习": ["pytorch", "tensorflow", "ml", "deep learning"],
        "自然语言处理": ["nlp", "transformer", "gpt", "llm"]
    },
    "Web 开发": {
        "前端": ["react", "vue", "vite", "svelte"],
        "后端": ["fastapi", "django", "flask", "node", "express"]
    },
    "DevOps & 工具": {
        "CI/CD": ["docker", "kubernetes", "pipeline"],
        "效率工具": ["plugin", "tool", "cli"]
    },
    "脚本自动化": {
        "脚本/自动化": ["script", "automation", "crawler", "scraper"]
    },
    "学习资料": {
        "资料/教程": ["awesome", "tutorial", "guide"]
    }
}
for g in CATEGORY_MAP:
    for s in CATEGORY_MAP[g]:
        CATEGORY_MAP[g][s] = [k.lower() for k in CATEGORY_MAP[g][s]]

# -------------------------
# Language Color Map
# -------------------------
LANG_COLORS = {
    "python": "#3572A5",
    "javascript": "#f1e05a",
    "typescript": "#2b7489",
    "go": "#00ADD8",
    "java": "#b07219",
    "rust": "#dea584",
    "c": "#555555",
    "cpp": "#f34b7d",
    "shell": "#89e051"
}

# -------------------------
# Helpers
# -------------------------
def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def short_date(s):
    if not s:
        return "N/A"
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%Y-%m-%d")
    except:
        return s.split("T")[0] if "T" in s else s

def cache_path(url):
    ensure_dir(CACHE_DIR)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, key + ".json")

def read_cache(url):
    path = cache_path(url)
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def write_cache(url, data):
    path = cache_path(url)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except:
        pass

# -------------------------
# CLI Config
# -------------------------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--username")
    p.add_argument("--token")
    p.add_argument("--token-file")
    p.add_argument("--no-cache", action="store_true")
    return p.parse_args()

def get_config():
    args = parse_args()

    username = (
            args.username or
            MANUAL_USERNAME or
            os.getenv("STAR_USERNAME")
    )

    token = (
            args.token or
            MANUAL_TOKEN or
            os.getenv("STAR_TOKEN")
    )

    if not token and args.token_file:
        try:
            token = open(args.token_file, "r", encoding="utf-8").read().strip()
        except:
            pass

    if (not username or not token) and sys.stdin.isatty():
        if not username:
            username = input("GitHub Username: ").strip()
        if not token:
            token = input("GitHub Token: ").strip()

    if not username or not token:
        raise ValueError("必须提供 GitHub 用户名和 Token")

    return username, token, args.no_cache

# -------------------------
# Build session
# -------------------------
def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": GITHUB_API_ACCEPT,
        "User-Agent": "starred-exporter"
    })
    return s

# -------------------------
# Fetch URL (with caching)
# -------------------------
def fetch_url(session, url, use_cache=True):
    if use_cache and not getattr(fetch_url, "_no_cache", False):
        cached = read_cache(url)
        if cached is not None:
            return cached

    r = session.get(url, timeout=15)
    if r.status_code != 200:
        return None

    data = r.json()
    if use_cache and not getattr(fetch_url, "_no_cache", False):
        write_cache(url, data)
    return data

# -------------------------
# Fetch starred repos
# -------------------------
def get_starred_repos(session, username):
    url = f"https://api.github.com/users/{username}/starred?per_page=100"
    repos = []
    page = 1

    while url:
        logging.info(f"Fetching page {page}...")
        data = fetch_url(session, url)
        if not data:
            break
        repos.extend(data)

        # extract next page
        resp = session.get(url)
        links = resp.headers.get("Link", "")
        next_url = None
        for part in links.split(","):
            if 'rel="next"' in part:
                m = re.search(r'<([^>]+)>', part)
                if m:
                    next_url = m.group(1)
        url = next_url
        page += 1

    logging.info(f"Total repos: {len(repos)}")
    return repos
# ============================================================
# Part 2 — Repo 富化（topics / release / license）+ Overrides
# ============================================================

# -------------------------
# Fetch topics
# -------------------------
def fetch_topics(session, full_name):
    """
    GET /repos/{owner}/{repo}/topics
    """
    url = f"https://api.github.com/repos/{full_name}/topics"
    data = fetch_url(session, url)
    if not data or "names" not in data:
        return []
    return data["names"]


# -------------------------
# Fetch latest release
# -------------------------
def fetch_release(session, full_name):
    """
    GET /repos/{owner}/{repo}/releases/latest
    """
    url = f"https://api.github.com/repos/{full_name}/releases/latest"
    data = fetch_url(session, url)
    if not data or "tag_name" not in data:
        return None
    return {
        "tag": data.get("tag_name"),
        "name": data.get("name") or "",
        "url": data.get("html_url") or "",
        "date": short_date(data.get("published_at"))
    }


# -------------------------
# Repo 富化（topics / release / license）
# -------------------------
def enrich_repos(session, repos):
    for repo in repos:
        full = repo.get("full_name")

        # topics
        repo["_topics"] = fetch_topics(session, full)

        # release
        repo["_release"] = fetch_release(session, full)

        # license
        lic = repo.get("license")
        repo["_license"] = lic["spdx_id"] if isinstance(lic, dict) else None

        # language color
        lang = (repo.get("language") or "").lower()
        repo["_lang_color"] = LANG_COLORS.get(lang)

    return repos


# ============================================================
# Overrides Loader（固定分类）
# ============================================================

def load_overrides():
    """
    读取 overrides.json
    格式：
    {
        "owner/repo": {
            "group": "AI",
            "sub": "Deep Learning"
        },
        ...
    }
    """
    if not os.path.exists(OVERRIDES_PATH):
        logging.warning("未找到 overrides.json，将生成模板文件")
        generate_overrides_template()
        return {}

    try:
        return json.load(open(OVERRIDES_PATH, "r", encoding="utf-8"))
    except:
        logging.error("overrides.json 解析失败")
        return {}


def generate_overrides_template():
    """
    自动生成一个 overrides_template.json（仅示例）
    """
    example = {
        "owner/repo": {
            "group": "AI",
            "sub": "机器学习"
        }
    }
    with open(OVERRIDES_TEMPLATE, "w", encoding="utf-8") as f:
        json.dump(example, f, indent=4, ensure_ascii=False)
    logging.info(f"已生成 {OVERRIDES_TEMPLATE}")


# ============================================================
# 混合分类器：Overrids > keyword-based > language fallback
# ============================================================

def categorize_repos_mixed(repos):
    """
    最核心分类器：
    1. overrides.json（最高优先级）
    2. 根据 description / topics / name 关键词匹配
    3. fallback：按语言归类
    4. 最后：其他
    """

    overrides = load_overrides()

    categorized = defaultdict(lambda: defaultdict(list))

    for repo in repos:
        full = repo.get("full_name")
        name = repo.get("name", "").lower()
        desc = (repo.get("description") or "").lower()
        topics = repo.get("_topics", [])
        topics_l = [t.lower() for t in topics]
        lang = (repo.get("language") or "其他").strip()

        # ------------------------------------
        # 1. Overrides（固定分类）
        # ------------------------------------
        if full in overrides:
            g = overrides[full].get("group", "其他")
            s = overrides[full].get("sub", "未分类")
            categorized[g][s].append(repo)
            continue

        # ------------------------------------
        # 2. Keyword 分类
        # ------------------------------------
        matched = False
        for group, subcats in CATEGORY_MAP.items():
            for sub, keywords in subcats.items():
                # name / desc / topics 任意命中即可
                joined = " ".join([name, desc] + topics_l)

                if any(k in joined for k in keywords):
                    categorized[group][sub].append(repo)
                    matched = True
                    break
            if matched:
                break

        if matched:
            continue

        # ------------------------------------
        # 3. Fallback：按语言分类
        # ------------------------------------
        g = f"{lang} 相关"
        s = lang
        categorized[g][s].append(repo)

    # ------------------------------------
    # 4. 把“其他”移到最后
    # ------------------------------------
    ordered = {}
    for g in categorized:
        if g != "其他":
            ordered[g] = categorized[g]
    if "其他" in categorized:
        ordered["其他"] = categorized["其他"]

    return ordered
# ============================================================
# Part 3 — Markdown & HTML 生成器（无暗黑模式）
# ============================================================

def safe_md(s, maxlen=None):
    if not s:
        return ""
    t = str(s).replace("\r", " ").replace("\n", " ").replace("|", " ")
    t = t.strip()
    if maxlen and len(t) > maxlen:
        return t[:maxlen-3] + "..."
    return t

# -------------------------
# Markdown generator
# -------------------------
def generate_markdown(repos, categorized, output=OUTPUT_MD):
    """
    - TOC (折叠) 显示子分类（选 B）
    - 每个二级分类使用 <details> 折叠
    - release inline
    - topics & auto tags 展示
    """
    now = now_str()
    total = len(repos)
    with open(output, "w", encoding="utf-8") as f:
        f.write('<a id="top"></a>\n\n')
        f.write('# 🌟 我的 GitHub 星标项目整理\n\n')
        f.write(f'> 自动生成 · 最后更新：{now} · 总项目数：{total}\n\n')

        # TOC
        f.write('<details>\n<summary>📂 目录（点击展开/收起）</summary>\n\n')
        for g, subs in categorized.items():
            f.write(f'- **[{g}](#{make_anchor(g)})**\n')
            for s in subs.keys():
                f.write(f'  - [{s}](#{make_anchor(s)})\n')
        f.write('\n</details>\n\n')

        # content
        for g, subs in categorized.items():
            f.write(f'## {g}\n\n')
            for s, items in subs.items():
                f.write(f'<a id="{make_anchor(s)}"></a>\n')
                f.write(f'<details>\n<summary>🔽 {s} （{len(items)} 项）</summary>\n\n')
                for repo in sorted(items, key=lambda x: x.get('stargazers_count',0), reverse=True):
                    full = repo.get('full_name')
                    url = repo.get('html_url')
                    desc = safe_md(repo.get('description') or "无描述", maxlen=220)
                    stars = repo.get('stargazers_count', 0)
                    forks = repo.get('forks_count', 0)
                    updated = short_date(repo.get('updated_at'))
                    rel = repo.get('_release') or {}
                    rel_txt = f"📦 [{rel.get('tag')}]({rel.get('url')})" if rel and rel.get('tag') else "📦 无 Release"

                    topics = repo.get('_topics') or []
                    topics_line = " ".join([f"`{t}`" for t in topics]) if topics else ""
                    tags = auto_tags_for_repo(repo)
                    tags_line = " ".join([f"`{t}`" for t in tags]) if tags else ""

                    f.write(f'#### [{full}]({url})\n')
                    f.write(f'> {desc}\n\n')
                    if topics_line:
                        f.write(f'- **Topics:** {topics_line}\n')
                    if tags_line:
                        f.write(f'- **Tags:** {tags_line}\n')
                    f.write(f'- ⭐ {stars} · 🍴 {forks} · 📅 {updated} · {rel_txt}\n\n')
                f.write('</details>\n\n')
    logging.info(f"Markdown generated: {output}")

# -------------------------
# HTML generator (Tailwind, no dark mode)
# -------------------------
def html_escape(s):
    return (str(s) if s is not None else "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def get_icon_and_color(group):
    if group in ICON_MAP:
        return ICON_MAP[group]  # (icon, tailwind-color token)
    return ("fa-folder", "blue-500")

def color_token_to_hex(token):
    mapping = {
        "red-500":"#ef4444","blue-500":"#3b82f6","indigo-500":"#6366f1",
        "yellow-500":"#f59e0b","teal-500":"#14b8a6","gray-500":"#6b7280"
    }
    return mapping.get(token, "#3b82f6")

def generate_html(repos, categorized, output=OUTPUT_HTML):
    """
    Generate an HTML page closely following the Tailwind template you provided.
    Features:
      - TOC grid of groups (links to anchors)
      - For each group: icon + subcategory mini-stat cards + repo cards
      - topics badges, tags, language dot, release inline
      - per-repo data-index & data-stars for client-side sorting
      - sort-by-stars button (client-side)
      - no dark mode
    """
    now = datetime.now().strftime("%Y-%m-%d")
    ensure_dir(os.path.dirname(output) or ".")
    with open(output, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>GitHub Stars 整理</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
body {{ font-family: 'Noto Sans SC', sans-serif; background-color:#f8fafc; color:#1e293b; scroll-behavior:smooth; }}
.category-card{{transition:transform .18s,box-shadow .18s;}} .category-card:hover{{transform:translateY(-2px);box-shadow:0 10px 25px -5px rgba(0,0,0,0.1);}}
.repo-card{{transition:all .15s;border-left:4px solid transparent}} .repo-card:hover{{border-left-color:#3b82f6;background-color:#f1f5f9}}
.nav-link::after{{content:'';position:absolute;bottom:-2px;left:0;width:0;height:2px;background-color:#3b82f6;transition:width .3s}}
.nav-link:hover::after{{width:100%}}
.back-to-top{{position:fixed;bottom:20px;right:20px;opacity:0;transition:opacity .3s}} .back-to-top.visible{{opacity:1}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;margin-right:6px;margin-top:6px}}
.lang-dot{{width:10px;height:10px;border-radius:999px;display:inline-block;margin-right:6px}}
.stat-card{{
  padding:14px 16px;background:#ffffff;border:1px solid #e6edf3;border-radius:8px;margin:6px 0;
}}
</style>
</head>
<body class="max-w-5xl mx-auto px-4 py-8">
<header class="mb-6 text-center">
  <h1 class="text-3xl md:text-4xl font-bold text-gray-800 mb-2">🌟 GitHub Stars 整理</h1>
  <p class="text-sm text-gray-600">自动分类 · Release · Topics · Tags · Sort</p>
</header>

<div class="flex justify-between items-center mb-6">
  <div class="text-gray-600">最后更新: {now} · 共 {len(repos)} 项</div>
  <div class="space-x-2">
    <button id="sortToggle" class="bg-blue-500 text-white px-3 py-1 rounded text-sm">⭐ 按星数排序</button>
  </div>
</div>

<div class="bg-white rounded-xl shadow-md p-6 mb-8">
  <h2 class="text-2xl font-semibold mb-4">📂 目录导航</h2>
  <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">""")
        # TOC (groups + subcats)
        for g, subs in categorized.items():
            f.write(f'<a href="#{make_anchor(g)}" class="nav-link text-blue-600 hover:text-blue-800">{html_escape(g)}</a>')
        f.write("</div></div>\n")

        # groups
        for g, subs in categorized.items():
            anchor = make_anchor(g)
            fa_icon, token = get_icon_and_color(g)
            icon_color = color_token_to_hex(token)
            f.write(f'''
<div id="{anchor}" class="category-card bg-white rounded-xl shadow-md p-6 mb-8">
  <div class="flex items-center mb-4">
    <i class="fas {fa_icon} text-2xl mr-3" style="color:{icon_color}"></i>
    <h2 class="text-2xl font-semibold text-gray-800">{html_escape(g)}</h2>
  </div>
  <!-- subcategory stats -->
  <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 mb-4">''')
            for s, items in subs.items():
                f.write(f'<div class="stat-card"><div class="font-medium">{html_escape(s)}</div><div class="text-sm text-gray-500">{len(items)} 项</div></div>')
            f.write('</div>')  # end stats grid

            # list subcats
            for s, items in subs.items():
                f.write(f'<div class="mb-6"><h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">{html_escape(s)}（{len(items)}）</h3>')
                f.write('<div class="space-y-3 repo-list">')
                # repo cards
                for idx, repo in enumerate(sorted(items, key=lambda r: r.get('stargazers_count',0), reverse=True)):
                    full = repo.get('full_name')
                    url = repo.get('html_url')
                    desc = html_escape(repo.get('description') or "无描述")
                    stars = repo.get('stargazers_count',0)
                    forks = repo.get('forks_count',0)
                    updated = short_date(repo.get('updated_at'))
                    rel = repo.get('_release') or {}
                    rel_html = f'📦 <a class="text-blue-600" href="{rel.get("url")}" target="_blank">{html_escape(rel.get("tag"))}</a>' if rel and rel.get("tag") else "📦 无 Release"
                    topics = repo.get('_topics') or []
                    topics_html = ""
                    if topics:
                        topics_html = '<div class="mt-2">'
                        for t in topics:
                            topics_html += f'<span class="badge bg-blue-100 text-blue-700">{html_escape(t)}</span>'
                        topics_html += '</div>'
                    # language dot
                    lang = (repo.get('language') or "") or ""
                    lang_color = LANG_COLORS.get((lang or "").lower(), "#9ca3af")
                    lang_html = f'<span class="lang-dot" style="background:{lang_color}"></span>{html_escape(lang)}' if lang else ""
                    tags = auto_tags_for_repo(repo)
                    tags_html = ""
                    if tags:
                        tags_html = '<div class="mt-2">'
                        for t in tags:
                            tags_html += f'<span class="badge bg-gray-100 text-gray-700">{html_escape(t)}</span>'
                        tags_html += '</div>'
                    meta_line = f'⭐ {stars} · 🍴 {forks} · 📅 {updated} · {rel_html}'
                    f.write(f'''
    <div class="repo-card bg-gray-50 rounded-lg p-4" data-index="{idx}" data-stars="{stars}">
      <a href="{url}" class="text-lg font-medium text-blue-600 hover:underline">{html_escape(full)}</a>
      <p class="text-gray-600 mt-1">{desc}</p>
      {topics_html}
      <div class="text-sm text-gray-500 mt-2">{meta_line}</div>
      <div class="text-xs text-gray-500 mt-1">{lang_html}</div>
      {tags_html}
    </div>
''')
                f.write('</div></div>')
            f.write('''
  <div class="mt-6 text-right">
    <a href="#top" class="text-blue-600 hover:text-blue-800 inline-flex items-center"><i class="fas fa-arrow-up mr-1"></i> 返回顶部</a>
  </div>
</div>
''')

        # footer + scripts
        f.write(f'''
<div class="bg-white rounded-xl shadow-md p-6 text-center text-gray-500 text-sm">
  页面自动生成 · 最后更新: {now}
</div>

<a href="#top" class="back-to-top bg-blue-500 text-white p-3 rounded-full shadow-lg" id="backBtn"><i class="fas fa-arrow-up"></i></a>

<script>
// back to top visibility
window.addEventListener('scroll', function(){{
  const b = document.getElementById('backBtn');
  if(window.pageYOffset > 300) b.classList.add('visible'); else b.classList.remove('visible');
}});

// sort toggle
(function(){{
  const toggle = document.getElementById('sortToggle');
  let sorted = false;
  toggle.addEventListener('click', function(){{
    sorted = !sorted;
    this.textContent = sorted ? '📚 恢复默认顺序' : '⭐ 按星数排序';
    document.querySelectorAll('.category-card').forEach(cat => {{
      cat.querySelectorAll('.repo-list').forEach(container => {{
        const nodes = Array.from(container.querySelectorAll('.repo-card'));
        nodes.sort((a,b) => {{
          const sa = parseInt(a.getAttribute('data-stars')||'0',10);
          const sb = parseInt(b.getAttribute('data-stars')||'0',10);
          if(sorted) return sb - sa;
          return (parseInt(a.getAttribute('data-index')||'0',10) - parseInt(b.getAttribute('data-index')||'0',10));
        }});
        nodes.forEach(n => container.appendChild(n));
      }});
    }});
  }});
}})();
</script>

</body>
</html>
''')
    logging.info(f"HTML generated: {output}")
# ============================================================
# overrides.json 自动生成（增强版）
# ============================================================

OVERRIDES_TEMPLATE = {
    "_description": "为特定 repo 指定固定分类（最高优先级）。",
    "_example": {
        "facebook/react": {
            "group": "前端开发",
            "subgroup": "核心框架"
        },
        "tensorflow/tensorflow": {
            "group": "AI 与数据科学",
            "subgroup": "深度学习"
        }
    }
}

def ensure_overrides_template(path="overrides.json"):
    """如果 overrides.json 不存在，自动创建模板。"""
    if os.path.exists(path):
        logging.info("overrides.json 已存在，跳过模板生成。")
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(OVERRIDES_TEMPLATE, f, ensure_ascii=False, indent=2)

    logging.info("已自动生成 overrides.json 模板，请按需编辑。")
# ============================================================
# 应用 overrides.json
# ============================================================

def apply_overrides(repo, overrides):
    """返回 (group, subgroup) ，如果 overrides 匹配，则强制覆盖。"""
    full = repo.get("full_name")
    if not full or full not in overrides:
        return None

    slot = overrides[full]
    return (slot.get("group"), slot.get("subgroup"))
# ============================================================
# 最终分类函数（合并 overrides + semantic 分类 + fallback）
# ============================================================

def finalize_category(repo, overrides):
    """
    返回最终 group / subgroup
    优先级：
      1. overrides.json
      2. MD/Topics/language 自动分类
      3. fallback: 其他/未分类
    """
    ov = apply_overrides(repo, overrides)
    if ov:
        return ov

    auto_g, auto_s = classify_repo(repo)
    if not auto_g:
        return ("其他", "未分类")
    if not auto_s:
        return (auto_g, "通用")
    return (auto_g, auto_s)
def build_category_tree(repos, overrides):
    """
    构建 { group: { subgroup: [repo, ...] } }
    自动将 “其他” 放到最后。
    """
    tree = {}

    for repo in repos:
        g, s = finalize_category(repo, overrides)
        tree.setdefault(g, {})
        tree[g].setdefault(s, [])
        tree[g][s].append(repo)

    # sort group, but put “其他” last
    sorted_groups = sorted([g for g in tree.keys() if g != "其他"]) + (["其他"] if "其他" in tree else [])

    ordered_tree = {}
    for g in sorted_groups:
        ordered_tree[g] = {}
        for s in sorted(tree[g].keys()):
            ordered_tree[g][s] = tree[g][s]

    return ordered_tree
# ============================================================
# main() — 完整自动化流程
# ============================================================

def main():
    logging.info("⭐ 开始执行 GitHub Stars 自动整理")

    username, token = load_config()
    ensure_overrides_template()   # ⬅ 自动创建模板（如果不存在）

    # 读取 overrides
    try:
        with open("overrides.json", "r", encoding="utf-8") as f:
            overrides = json.load(f)
    except Exception as e:
        logging.error(f"overrides.json 加载失败: {e}")
        overrides = {}

    # 获取 stars
    repos = get_starred_repos(username, token)
    logging.info(f"共获取到 {len(repos)} 个星标仓库")

    # 获取 Release + topics
    for repo in repos:
        rname = repo.get("full_name")
        repo["_topics"] = get_repo_topics(rname, token)
        repo["_release"] = get_latest_release(rname, token)

    # 分类
    categorized = build_category_tree(repos, overrides)

    # 生成 Markdown + HTML
    generate_markdown(repos, categorized, OUTPUT_MD)
    generate_html(repos, categorized, OUTPUT_HTML)

    logging.info("🎉 全部完成！")


if __name__ == "__main__":
    main()
