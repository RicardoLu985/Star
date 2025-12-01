#!/usr/bin/env python3
# update_starred_semantic.py
# Full-feature V2 — All enhancements integrated
# 2025-12
# Features:
# - overrides.json (exact repo mapping)
# - CLI / env / file / MANUAL token input (non-tty friendly)
# - caching of API requests (cache/*.json)
# - fetch topics, release, watchers, open issues, license
# - markdown (folding TOC with subcategories)
# - html (Tailwind + FontAwesome template you provided)
# - topics badges, language color, sort-by-stars toggle, dark mode toggle
# - generate overrides_template.json
# - simple auto-tagging and tech-stack inference
# - "其他" category always last
# - safe handling of rate limits & logging

import os
import sys
import json
import time
import argparse
import logging
import requests
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import re
import hashlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -------------------------
# Manual defaults (optional)
# -------------------------
MANUAL_USERNAME = ""  # set here if you want to hardcode locally
MANUAL_TOKEN = ""     # set here if you want to hardcode locally

# -------------------------
# Configurable constants
# -------------------------
CACHE_DIR = "cache"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour cache
OVERRIDES_PATH = "overrides.json"
OVERRIDES_TEMPLATE = "overrides_template.json"
OUTPUT_MD = "starred.md"
OUTPUT_HTML = os.path.join("docs", "index.html")
GITHUB_API_PREVIEW_HEADER = "application/vnd.github.mercy-preview+json"  # for topics

# -------------------------
# Icon / color map (FontAwesome + Tailwind color)
# Subcategories will inherit top-level mapping if not mapped specifically
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
# Category keyword map (lowercased)
# You can extend as needed.
# -------------------------
CATEGORY_MAP = {
    "AI": {
        "机器学习": ["pytorch", "tensorflow", "ml", "deep learning", "neural"],
        "自然语言处理": ["nlp", "transformer", "gpt", "llm", "huggingface"]
    },
    "Web 开发": {
        "前端": ["react", "vue", "vite", "svelte", "javascript", "typescript"],
        "后端": ["fastapi", "django", "flask", "node", "express"]
    },
    "DevOps & 工具": {
        "CI/CD": ["docker", "kubernetes", "k8s", "ci", "cd", "pipeline"],
        "效率工具": ["cli", "plugin", "utils", "tool"]
    },
    "脚本自动化": {
        "脚本/自动化": ["script", "automation", "bot", "crawler", "scraper"]
    },
    "学习资料": {
        "资料/教程": ["awesome", "tutorial", "guide", "learning", "notes"]
    }
}
# normalize keywords
for g, subs in list(CATEGORY_MAP.items()):
    for s, kws in list(subs.items()):
        subs[s] = [k.lower() for k in kws]

# -------------------------
# Language color map (small sample; fallback to gray)
# Source: GitHub linguist colors (subset)
# -------------------------
LANG_COLORS = {
    "javascript": "#f1e05a",
    "python": "#3572A5",
    "java": "#b07219",
    "typescript": "#2b7489",
    "go": "#00ADD8",
    "rust": "#dea584",
    "c": "#555555",
    "cpp": "#f34b7d",
    "html": "#e34c26",
    "css": "#563d7c",
    "shell": "#89e051",
    "ruby": "#701516"
}

# -------------------------
# Utilities
# -------------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def short_date(s):
    if not s:
        return "N/A"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except:
        return s.split("T")[0] if "T" in s else s

def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def cache_path_for(url):
    ensure_dir(CACHE_DIR)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.json")

def read_cache(url):
    path = cache_path_for(url)
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    if time.time() - mtime > CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except:
        return None

def write_cache(url, data):
    path = cache_path_for(url)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except Exception as e:
        logging.warning(f"写缓存失败 {path}: {e}")

# -------------------------
# Config retrieval (supports non-tty)
# Priority: CLI args > MANUAL constants > env vars > token file
# Also support --token-file
# -------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Update GitHub starred to md/html")
    p.add_argument("--username", help="GitHub username")
    p.add_argument("--token", help="GitHub token (PAT)")
    p.add_argument("--token-file", help="Read token from file path")
    p.add_argument("--no-cache", action="store_true", help="Disable cache for this run")
    return p.parse_args()

def get_config():
    args = parse_args()
    username = args.username or (MANUAL_USERNAME.strip() if MANUAL_USERNAME else None) or os.getenv("STAR_USERNAME")
    token = args.token or (MANUAL_TOKEN.strip() if MANUAL_TOKEN else None) or os.getenv("STAR_TOKEN")
    if not token and args.token_file:
        try:
            with open(args.token_file, "r", encoding="utf-8") as fh:
                token = fh.read().strip()
        except Exception as e:
            logging.error(f"读取 token 文件失败: {e}")
    # fallback interactive if tty
    if (not username or not token) and sys.stdin.isatty():
        try:
            if not username:
                username = input("GitHub username: ").strip() or username
            if not token:
                token = input("GitHub token (PAT): ").strip() or token
        except Exception:
            pass
    if not username or not token:
        raise ValueError("缺少 GitHub 用户名或 Token。请通过 CLI / MANUAL / 环境变量 / token-file 提供。")
    return username, token, args.no_cache

# -------------------------
# Build requests session
# -------------------------
def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": GITHUB_API_PREVIEW_HEADER,
        "User-Agent": "starred-exporter"
    })
    return s

# -------------------------
# Fetch helpers (with optional caching)
# -------------------------
def fetch_url(session, url, use_cache=True):
    if use_cache and not getattr(fetch_url, "_no_cache", False):
        cached = read_cache(url)
        if cached is not None:
            return cached
    try:
        r = session.get(url, timeout=15)
    except Exception as e:
        logging.error(f"请求失败 {url}: {e}")
        raise
    if r.status_code == 200:
        data = r.json()
        if use_cache and not getattr(fetch_url, "_no_cache", False):
            write_cache(url, data)
        return data
    else:
        text = r.text
        logging.debug(f"请求 {url} 返回 {r.status_code}: {text}")
        return None

# -------------------------
# Get starred repos (paginated). signature: (session, username)
# -------------------------
def get_starred_repos(session, username):
    url = f"https://api.github.com/users/{username}/starred?per_page=100"
    repos = []
    page = 1
    while url:
        logging.info(f"Fetching starred page {page} ...")
        data = fetch_url(session, url)
        if data is None:
            break
        repos.extend(data)
        # handle pagination via Link header by parsing session.get directly for links
        # we need to perform a direct GET to read headers when caching disabled or first time
        # to be safe, do a direct request for headers
        # but we don't want to double-cache; thus do a no-cache HEAD-like request
        try:
            resp = session.get(url, timeout=10)
            next_url = None
            links = resp.headers.get("Link", "")
            if links:
                # parse Link header
                for part in links.split(","):
                    if 'rel="next"' in part:
                        m = re.search(r'<([^>]+)>', part)
                        if m:
                            next_url = m.group(1)
            url = next_url
        except:
            # fallback: stop
            url = None
        page += 1
    logging.info(f"Total starred repos fetched: {len(repos)}")
    return repos

# -------------------------
# Fetch per-repo extra metadata: topics, latest release, languages, license, watchers, open_issues
# Use caching and gentle error handling
# -------------------------
def get_repo_topics(session, full_name, use_cache=True):
    owner_repo = full_name
    url = f"https://api.github.com/repos/{owner_repo}/topics"
    data = fetch_url(session, url, use_cache=use_cache)
    if data and isinstance(data, dict):
        return data.get("names", [])
    return []

def get_repo_latest_release(session, full_name, use_cache=True):
    url = f"https://api.github.com/repos/{full_name}/releases/latest"
    data = fetch_url(session, url, use_cache=use_cache)
    if data and isinstance(data, dict):
        return {"tag": data.get("tag_name"), "url": data.get("html_url"), "published": short_date(data.get("published_at"))}
    return None

def get_repo_languages(session, full_name, use_cache=True):
    url = f"https://api.github.com/repos/{full_name}/languages"
    data = fetch_url(session, url, use_cache=use_cache)
    return data or {}

def get_repo_meta(session, full_name, use_cache=True):
    url = f"https://api.github.com/repos/{full_name}"
    data = fetch_url(session, url, use_cache=use_cache)
    if not data:
        return {}
    return {
        "watchers": data.get("subscribers_count") or data.get("watchers_count") or 0,
        "open_issues": data.get("open_issues_count", 0),
        "license": (data.get("license") or {}).get("name") if data.get("license") else None,
        "language": data.get("language")
    }

# -------------------------
# Overrides loader
# -------------------------
def load_overrides(path=OVERRIDES_PATH):
    if not os.path.exists(path):
        return {"repos": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return {"repos": data.get("repos", {})}
    except Exception as e:
        logging.warning(f"加载 overrides.json 失败: {e}")
        return {"repos": {}}

# -------------------------
# Anchor helper for markdown/html IDs
# -------------------------
def make_anchor(text):
    if not text:
        return ""
    s = str(text).strip()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9\-_]', '', s)
    return s

# -------------------------
# Categorization (overrides exact match highest)
# -------------------------
def categorize_repos(repos, overrides_path=OVERRIDES_PATH):
    overrides = load_overrides(overrides_path).get("repos", {}) or {}
    categorized = defaultdict(lambda: defaultdict(list))
    for repo in repos:
        full = repo.get("full_name") or ""
        name = (repo.get("name") or "").lower()
        desc = (repo.get("description") or "").lower()
        topics = [t.lower() for t in (repo.get("topics") or [])]
        blob = " ".join([full.lower(), name, desc] + topics)
        # override exact repo
        if full in overrides:
            ov = overrides[full] or {}
            g = ov.get("category", "其他")
            s = ov.get("subcategory", "其他")
            categorized[g][s].append(repo)
            continue
        matched = False
        # topics match
        if topics:
            t_str = " ".join(topics)
            for g, subs in CATEGORY_MAP.items():
                for s, kws in subs.items():
                    if any(k in t_str for k in kws):
                        categorized[g][s].append(repo)
                        matched = True
                        break
                if matched: break
            if matched: continue
        # fuzzy match
        for g, subs in CATEGORY_MAP.items():
            for s, kws in subs.items():
                if any(k in blob for k in kws):
                    categorized[g][s].append(repo)
                    matched = True
                    break
            if matched: break
        # fallback
        if not matched:
            categorized["其他"]["其他"].append(repo)
    # sort groups by count desc, but ensure "其他" last
    ordered = {}
    groups = sorted(categorized.keys(), key=lambda x: (x == "其他", -sum(len(v) for v in categorized[x].values())))
    for g in groups:
        ordered[g] = dict(sorted(categorized[g].items(), key=lambda x: len(x[1]), reverse=True))
    return ordered

# -------------------------
# Auto-tagging simple rules (returns list of tags)
# -------------------------
AUTO_TAG_RULES = {
    "cli": ["cli", "command-line", "terminal"],
    "web": ["react", "vue", "frontend", "frontend", "javascript", "typescript", "html", "css"],
    "ml": ["pytorch", "tensorflow", "ml", "deep learning", "neural", "huggingface"],
    "nlp": ["nlp", "transformer", "gpt", "llm"],
    "devops": ["docker", "kubernetes", "ci", "cd", "pipeline"],
    "automation": ["automation", "bot", "script", "crawler"]
}
def auto_tags_for_repo(repo):
    txt = " ".join([str(repo.get("full_name","")), str(repo.get("description","")), " ".join(repo.get("topics") or [])]).lower()
    tags = set()
    for tag, kwlist in AUTO_TAG_RULES.items():
        for kw in kwlist:
            if kw in txt:
                tags.add(tag)
                break
    # include language as tag
    lang = (repo.get("language") or "").lower()
    if lang:
        tags.add(lang)
    return sorted(tags)

# -------------------------
# Tech-stack inference (very simple heuristics)
# -------------------------
def infer_stack(repo):
    txt = " ".join([str(repo.get("full_name","")), str(repo.get("description","")), " ".join(repo.get("topics") or [])]).lower()
    stack = []
    if any(k in txt for k in ["react","vue","svelte","angular"]):
        stack.append("frontend")
    if any(k in txt for k in ["fastapi","django","flask","express","spring"]):
        stack.append("backend")
    if any(k in txt for k in ["docker","kubernetes","k8s","helm"]):
        stack.append("docker/container")
    if any(k in txt for k in ["pytorch","tensorflow","ml","transformer","llm","huggingface"]):
        stack.append("ml")
    return stack

# -------------------------
# Markdown generation (folded TOC with subcategories; release in-line; topics display)
# -------------------------
def safe_md(s, maxlen=None):
    if not s:
        return ""
    t = str(s).replace("\r"," ").replace("\n"," ").replace("|"," ")
    if maxlen and len(t) > maxlen:
        return t[:maxlen-3] + "..."
    return t

def generate_markdown(repos, categorized, output=OUTPUT_MD):
    now = now_str()
    total = len(repos)
    with open(output, "w", encoding="utf-8") as f:
        f.write('<a id="top"></a>\n\n')
        f.write("# 🌟 我的 GitHub 星标项目整理\n\n")
        f.write(f"> 自动生成 · 最后更新：{now} · 总项目数：{total}\n\n")
        # TOC with subcategories (folded)
        f.write("<details>\n<summary>📂 目录（点击展开/收起）</summary>\n\n")
        for g, subs in categorized.items():
            f.write(f"- **[{g}](#{make_anchor(g)})**\n")
            for s in subs.keys():
                f.write(f"  - [{s}](#{make_anchor(s)})\n")
        f.write("\n</details>\n\n")
        # sections
        for g, subs in categorized.items():
            f.write(f"## {g}\n\n")
            for s, items in subs.items():
                f.write(f'<a id="{make_anchor(s)}"></a>\n')
                f.write(f"<details>\n<summary>🔽 {s} （{len(items)} 项）</summary>\n\n")
                for repo in sorted(items, key=lambda x: x.get("stargazers_count",0), reverse=True):
                    full = repo.get("full_name")
                    url = repo.get("html_url")
                    desc = safe_md(repo.get("description") or "无描述", maxlen=240)
                    stars = repo.get("stargazers_count",0)
                    forks = repo.get("forks_count",0)
                    updated = short_date(repo.get("updated_at"))
                    rel = repo.get("_latest_release")
                    rel_txt = f"📦 [{rel['tag']}]({rel['url']})" if rel and rel.get("tag") else "📦 无 Release"
                    topics = repo.get("topics") or []
                    topics_line = " ".join([f"`{t}`" for t in topics]) if topics else ""
                    tags = auto_tags_for_repo(repo)
                    tags_line = " ".join([f"`{t}`" for t in tags]) if tags else ""
                    meta_line = f"⭐ {stars} · 🍴 {forks} · 📅 {updated} · {rel_txt}"
                    f.write(f"#### [{full}]({url})\n")
                    f.write(f"> {desc}\n\n")
                    if topics_line:
                        f.write(f"- **Topics:** {topics_line}\n")
                    if tags_line:
                        f.write(f"- **Tags:** {tags_line}\n")
                    f.write(f"- {meta_line}\n\n")
                f.write("</details>\n\n")
    logging.info(f"Markdown generated: {output}")

# -------------------------
# HTML generation (Tailwind template you provided; dynamic data)
# Enhanced: Dark mode toggle, sort-by-stars, topics badges, language color, extra meta
# -------------------------
def html_escape(s):
    return (str(s) if s is not None else "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def get_icon_for_group(group):
    # return fa-icon and tailwind color class
    if group in ICON_MAP:
        return ICON_MAP[group]
    # fallback: use "fa-folder" gray
    return ("fa-folder", "gray-500")

def generate_html(repos, categorized, output=OUTPUT_HTML):
    now = datetime.now().strftime("%Y-%m-%d")
    ensure_dir(os.path.dirname(output) or ".")
    with open(output, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitHub Stars 简洁整理</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
body {{ font-family: 'Noto Sans SC', sans-serif; background-color: #f8fafc; color: #1e293b; scroll-behavior: smooth; }}
.dark body {{ background-color: #0b1220; color:#e5e7eb; }}
.category-card {{ transition: transform 0.2s ease, box-shadow 0.2s ease; }}
.category-card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); }}
.repo-card {{ transition: all 0.15s ease; border-left: 4px solid transparent; }}
.repo-card:hover {{ border-left-color: #3b82f6; background-color: #f1f5f9; }}
.dark .repo-card:hover {{ background-color: rgba(255,255,255,0.03); }}
.nav-link {{ position: relative; }}
.nav-link::after {{ content:''; position:absolute; bottom:-2px; left:0; width:0; height:2px; background-color:#3b82f6; transition: width .3s ease; }}
.nav-link:hover::after {{ width:100%; }}
.back-to-top {{ position: fixed; bottom:20px; right:20px; opacity:0; transition: opacity .3s ease; }}
.back-to-top.visible {{ opacity:1; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; margin-right:6px; margin-top:6px; }}
.lang-dot {{ width:10px; height:10px; border-radius:999px; display:inline-block; margin-right:6px; }}
</style>
</head>
<body class="max-w-5xl mx-auto px-4 py-8">

<header class="mb-6 text-center">
  <h1 class="text-3xl md:text-4xl font-bold text-gray-800 mb-2">🌟 GitHub Stars 整理</h1>
  <p class="text-sm text-gray-600">自动分类 · Release · Topics · Tags · Dark Mode · Sort</p>
</header>

<div class="flex justify-between items-center mb-6">
  <div class="text-gray-600">最后更新: {now} · 共 {len(repos)} 项</div>
  <div class="space-x-2">
    <button id="darkToggle" class="bg-gray-200 px-3 py-1 rounded text-sm">切换主题</button>
    <button id="sortToggle" class="bg-blue-500 text-white px-3 py-1 rounded text-sm">⭐ 按星数排序</button>
  </div>
</div>

<div class="bg-white rounded-xl shadow-md p-6 mb-8">
  <h2 class="text-2xl font-semibold mb-4">📂 目录导航</h2>
  <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">""")
        # TOC (groups + subcats)
        for g, subs in categorized.items():
            anchor = make_anchor(g)
            f.write(f'<a href="#{anchor}" class="nav-link text-blue-600 hover:text-blue-800">{html_escape(g)}</a>')
        f.write("</div></div>\n")

        # Group cards
        for g, subs in categorized.items():
            anchor = make_anchor(g)
            fa_icon, color_cls = get_icon_for_group(g)
            color_class = "text-blue-500"
            # map tailwind color token to actual class only used for icon color; we'll inline a reasonable default mapping
            # Choose color via the ICON_MAP mapping's second token if present
            ctoken = ICON_MAP.get(g, (None, "blue-500"))[1]
            # convert e.g. red-500 to a hex-ish set (approx)
            color_map_simple = {
                "red-500":"#ef4444","blue-500":"#3b82f6","indigo-500":"#6366f1",
                "yellow-500":"#f59e0b","teal-500":"#14b8a6","gray-500":"#6b7280"
            }
            icon_color = color_map_simple.get(ctoken, "#3b82f6")
            f.write(f"""
<div id="{anchor}" class="category-card bg-white rounded-xl shadow-md p-6 mb-8">
  <div class="flex items-center mb-4">
    <i class="fas {fa_icon} text-2xl mr-3" style="color:{icon_color}"></i>
    <h2 class="text-2xl font-semibold text-gray-800">{html_escape(g)}</h2>
  </div>
""")
            # dashboard mini cards for subcounts
            f.write('<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 mb-4">')
            for s, items in subs.items():
                f.write(f'<div class="stat-card p-4 bg-gray-50 rounded-lg"><div class="font-medium">{html_escape(s)}</div><div class="text-sm text-gray-500">{len(items)} 项</div></div>')
            f.write('</div>')
            # subcategories and repos
            for s, items in subs.items():
                f.write(f'<div class="mb-6"><h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">{html_escape(s)}（{len(items)}）</h3>')
                f.write('<div class="space-y-3 repo-list">')
                # keep original order index for restoration
                for i, repo in enumerate(sorted(items, key=lambda x: x.get("stargazers_count",0), reverse=False)):
                    full = repo.get("full_name")
                    url = repo.get("html_url")
                    desc = html_escape(repo.get("description") or "无描述")
                    stars = repo.get("stargazers_count",0)
                    forks = repo.get("forks_count",0)
                    updated = short_date(repo.get("updated_at"))
                    rel = repo.get("_latest_release")
                    rel_html = f'📦 <a class="text-blue-600" href="{rel["url"]}" target="_blank">{html_escape(rel["tag"])}</a>' if rel and rel.get("tag") else "📦 无 Release"
                    topics = repo.get("topics") or []
                    topics_html = ""
                    if topics:
                        topics_html = '<div class="mt-2">'
                        for t in topics:
                            topics_html += f'<span class="badge bg-blue-100 text-blue-700">{html_escape(t)}</span>'
                        topics_html += '</div>'
                    meta_line = f'⭐ {stars} · 🍴 {forks} · 📅 {updated} · {rel_html}'
                    # language color
                    lang = (repo.get("language") or "") or ""
                    lang_color = LANG_COLORS.get((lang or "").lower(), "#9ca3af")
                    lang_html = f'<span class="lang-dot" style="background:{lang_color}"></span>{html_escape(lang)}' if lang else ""
                    # extra meta: watchers, open_issues, license (if present)
                    watchers = repo.get("_meta", {}).get("watchers")
                    open_issues = repo.get("_meta", {}).get("open_issues")
                    license_name = repo.get("_meta", {}).get("license")
                    extra = ""
                    if watchers is not None:
                        extra += f' · 👀 {watchers}'
                    if open_issues is not None:
                        extra += f' · ❗ {open_issues}'
                    if license_name:
                        extra += f' · 📝 {html_escape(license_name)}'
                    tags = auto_tags_for_repo(repo)
                    tags_html = ""
                    if tags:
                        tags_html = '<div class="mt-2">'
                        for t in tags:
                            tags_html += f'<span class="badge bg-gray-100 text-gray-700">{html_escape(t)}</span>'
                        tags_html += '</div>'
                    f.write(f'''
    <div class="repo-card bg-gray-50 rounded-lg p-4" data-index="{i}" data-stars="{stars}">
      <a href="{url}" class="text-lg font-medium text-blue-600 hover:underline">{html_escape(full)}</a>
      <p class="text-gray-600 mt-1">{desc}</p>
      {topics_html}
      <div class="text-sm text-gray-500 mt-2">{meta_line}{extra}</div>
      <div class="text-xs text-gray-500 mt-1">{lang_html}</div>
      {tags_html}
    </div>
''')
                f.write('</div></div>')
            f.write("""
  <div class="mt-6 text-right">
    <a href="#top" class="text-blue-600 hover:text-blue-800 inline-flex items-center"><i class="fas fa-arrow-up mr-1"></i> 返回顶部</a>
  </div>
</div>
""")
        # footer + scripts
        f.write(f"""
<div class="bg-white rounded-xl shadow-md p-6 text-center text-gray-500 text-sm">
  页面自动生成 · 最后更新: {now}
</div>

<a href="#top" class="back-to-top bg-blue-500 text-white p-3 rounded-full shadow-lg" id="backBtn"><i class="fas fa-arrow-up"></i></a>

          # -------------------------
          # Main flow
          # -------------------------
          def main():
              try:
                  username, token, no_cache_flag = get_config()
                  if no_cache_flag:
                      fetch_url._no_cache = True
                  session = build_session(token)
                  # fetch starred repos
                  repos = get_starred_repos(session, username)
                  # enrich repos: topics, release, meta, languages
                  logging.info("Enriching repos with topics, release, meta (may take a while)...")
                  for repo in repos:
                      full = repo.get("full_name")
                      # only fetch when missing to avoid excessive requests
                      repo["topics"] = get_repo_topics(session, full, use_cache=not getattr(fetch_url, "_no_cache", False))
                      repo["_latest_release"] = get_repo_latest_release(session, full, use_cache=not getattr(fetch_url, "_no_cache", False))
                      meta = get_repo_meta(session, full, use_cache=not getattr(fetch_url, "_no_cache", False))
                      repo["_meta"] = meta
                      # language field: prefer repo.language, fallback meta.language
                      repo["language"] = repo.get("language") or meta.get("language")
                  # categorize (overrides honored)
                  categorized = categorize_repos(repos)
                  # generate overrides template for user convenience
                  generate_overrides_template(repos)
                  # outputs
                  generate_markdown(repos, categorized, output=OUTPUT_MD)
                  generate_html(repos, categorized, output=OUTPUT_HTML)
                  logging.info("All done.")
              except Exception as e:
                  logging.exception(f"执行失败：{e}")
                  raise
          
          if __name__ == "__main__":
              main()
