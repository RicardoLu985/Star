#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# update_starred_semantic.py
# 终极完美版（已去除 starred_at 时间，只保留仓库更新时间 + 彻底修复所有遗漏函数）

import os
import json
import time
import logging
import requests
import re
import hashlib
from collections import defaultdict, Counter
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("starred-updater")

# ======================= 配置 =======================
MANUAL_USERNAME = ""
MANUAL_TOKEN = ""

CACHE_DIR = "cache"
CACHE_TTL_SECONDS = 3600
OUTPUT_MD = "starred.md"
OUTPUT_HTML = "docs/index.html"
OVERRIDES_PATH = "overrides.json"
OVERRIDES_TEMPLATE = "overrides_template.json"
STATS_JSON = "stats.json"
GITHUB_API_ACCEPT = "application/vnd.github.mercy-preview+json"

# ======================= 分类 & 图标 =======================
CATEGORY_ORDER = ["AI", "Web 开发", "DevOps & 工具", "脚本自动化", "学习资料", "其他"]

CATEGORY_ICONS = {
    "AI": ("fa-robot", "text-red-500"),
    "Web 开发": ("fa-paint-brush", "text-purple-500"),
    "DevOps & 工具": ("fa-tools", "text-indigo-500"),
    "脚本自动化": ("fa-terminal", "text-yellow-600"),
    "学习资料": ("fa-graduation-cap", "text-teal-500"),
    "其他": ("fa-ellipsis-h", "text-gray-500"),
}

CATEGORY_MAP = {
    "AI": {
        "机器学习框架": ["pytorch", "tensorflow", "jax", "keras", "scikit-learn", "mxnet"],
        "大模型/LLM": ["llama", "gpt", "transformers", "huggingface", "langchain", "ollama", "vllm"],
        "AI 应用": ["stable-diffusion", "comfyui", "whisper", "auto-gpt", "privategpt"],
        "计算机视觉": ["opencv", "yolo", "detectron", "segment-anything"],
        "其他 AI": []
    },
    "Web 开发": {
        "前端框架": ["react", "vue", "svelte", "nextjs", "nuxt", "astro", "solidjs", "remix"],
        "后端框架": ["fastapi", "django", "flask", "express", "nest", "spring", "gin"],
        "全栈工具": ["tauri", "electron", "wails", "neutralino"],
        "UI 组件库": ["antd", "element-plus", "naive-ui", "shadcn", "daisyui", "mui", "chakra"],
        "其他 Web": []
    },
    "DevOps & 工具": {
        "容器与编排": ["docker", "kubernetes", "k8s", "helm", "podman"],
        "CI/CD": ["github-actions", "jenkins", "gitlab-ci", "drone", "argo"],
        "监控告警": ["prometheus", "grafana", "loki", "zabbix"],
        "基础设施": ["terraform", "pulumi", "ansible", "crossplane"],
        "其他 DevOps": []
    },
    "脚本自动化": {
        "爬虫/自动化": ["scrapy", "playwright", "selenium", "crawler", "bot"],
        "命令行工具": ["cli", "cobra", "typer", "click"],
        "其他脚本": []
    },
    "学习资料": {
        "Awesome 列表": ["awesome", "curated", "list"],
        "教程/文档": ["tutorial", "course", "learn", "guide", "handbook"],
        "算法与面试": ["leetcode", "algorithm", "interview"],
        "其他学习": []
    }
}

# ======================= 工具函数 =======================
def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def short_date(iso_str):
    if not iso_str:
        return "N/A"
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except:
        return iso_str.split("T")[0] if "T" in iso_str else iso_str

def cache_path_for(url: str):
    ensure_dir(CACHE_DIR)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.json")

def read_cache(url: str):
    path = cache_path_for(url)
    if not os.path.exists(path): return None
    if time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS: return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def write_cache(url: str, data):
    try:
        with open(cache_path_for(url), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except:
        pass

# ======================= 强制本地/IDE 手动输入 =======================
def running_in_ci():
    return os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

def get_config():
    if MANUAL_USERNAME and MANUAL_TOKEN:
        return MANUAL_USERNAME, MANUAL_TOKEN

    env_user = os.getenv("STAR_USERNAME")
    env_token = os.getenv("STAR_TOKEN")
    if env_user and env_token:
        return env_user, env_token

    if not running_in_ci():
        u = input("请输入 GitHub 用户名: ").strip()
        t = input("请输入 GitHub Token (PAT): ").strip()
        if u and t:
            return u, t

    raise ValueError("无法获取 GitHub 凭证！")

def build_session(token: str):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": GITHUB_API_ACCEPT,
        "User-Agent": "starred-updater/2.0"
    })
    return s

# ======================= 数据获取 =======================
def fetch_url(session, url, use_cache=True):
    if use_cache:
        cached = read_cache(url)
        if cached is not None: return cached
    for _ in range(3):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if use_cache:
                    write_cache(url, data)
                return data
            elif r.status_code == 403:
                log.warning("API 限流，60秒后重试...")
                time.sleep(60)
        except Exception as e:
            log.debug(f"请求失败 {url}: {e}")
            time.sleep(3)
    return None

def get_starred_repos(session, username):
    repos = []
    url = f"https://api.github.com/users/{username}/starred?per_page=100"
    page = 1
    while url:
        log.info(f"正在获取第 {page} 页 Starred...")
        data = fetch_url(session, url)
        if not data: break
        repos.extend(data)
        try:
            link = session.get(url).headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = re.search(r'<([^>]+)>', part).group(1)
        except:
            url = None
        page += 1
    log.info(f"共获取 {len(repos)} 个星标项目")
    return repos

def fetch_repo_topics(session, full_name):
    data = fetch_url(session, f"https://api.github.com/repos/{full_name}/topics")
    return data.get("names", []) if isinstance(data, dict) else []

def fetch_latest_release(session, full_name):
    data = fetch_url(session, f"https://api.github.com/repos/{full_name}/releases/latest")
    if not data or not isinstance(data, dict): return None
    tag = data.get("tag_name") or data.get("name")
    url = data.get("html_url")
    date = data.get("published_at")
    return {"tag": tag, "url": url, "date": short_date(date)} if tag else None

def enrich_repos(session, repos):
    log.info("开始富化仓库信息...")
    for i, repo in enumerate(repos, 1):
        full = repo["full_name"]
        repo["_topics"] = fetch_repo_topics(session, full)
        repo["_release"] = fetch_latest_release(session, full)
    log.info("富化完成")
    return repos

# ======================= Overrides & Tags & 分类 =======================
def load_overrides():
    if not os.path.exists(OVERRIDES_PATH):
        return {}
    try:
        with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("repos", {}) if isinstance(data, dict) else data
    except Exception as e:
        log.error(f"加载 overrides.json 失败: {e}")
        return {}

def auto_tags_for_repo(repo):
    blob = " ".join([
        repo.get("full_name", "").lower(),
        (repo.get("description") or "").lower(),
        " ".join([t.lower() for t in repo.get("_topics", [])]),
        (repo.get("language") or "").lower()
    ])
    tags = set()
    rules = {
        "cli": ["cli", "command-line", "terminal"],
        "web": ["react", "vue", "frontend", "javascript", "typescript"],
        "ml": ["pytorch", "tensorflow", "ml", "deep learning", "llm"],
        "nlp": ["nlp", "transformer", "gpt", "huggingface"],
        "devops": ["docker", "kubernetes", "ci", "pipeline"],
        "automation": ["automation", "bot", "crawler"]
    }
    for tag, kws in rules.items():
        if any(kw in blob for kw in kws):
            tags.add(tag)
    lang = (repo.get("language") or "").lower()
    if lang: tags.add(lang)
    return sorted(tags)

def categorize_repos_mixed(repos, overrides):
    tree = defaultdict(lambda: defaultdict(list))
    for repo in repos:
        full = repo["full_name"]
        blob = " ".join([
            full.lower(),
            (repo.get("description") or "").lower(),
            " ".join([t.lower() for t in repo.get("_topics", [])])
        ])

        if full in overrides:
            g = overrides[full].get("group") or "其他"
            s = overrides[full].get("sub") or "其他"
            tree[g][s].append(repo)
            continue

        matched = False
        for group, subs in CATEGORY_MAP.items():
            for sub, kws in subs.items():
                if any(kw and kw in blob for kw in kws):
                    tree[group][sub].append(repo)
                    matched = True
                    break
            if matched: break
        if not matched:
            lang = repo.get("language") or "其他"
            tree["其他"][f"{lang} 项目"].append(repo)

    ordered = {}
    for g in CATEGORY_ORDER:
        if g in tree:
            ordered[g] = dict(sorted(tree[g].items(), key=lambda x: len(x[1]), reverse=True))
    if "其他" in tree and "其他" not in ordered:
        ordered["其他"] = dict(sorted(tree["其他"].items(), key=lambda x: len(x[1]), reverse=True))
    return ordered

# ======================= Markdown 生成（已去除 starred_at，只保留仓库更新时间）======================
def generate_markdown(categorized, repos):
    now = datetime.now().strftime("%Y-%m-%d")
    total = len(repos)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write('<a id="top"></a>\n\n')
        f.write('# 🌟 我的 GitHub 星标项目整理\n\n')
        f.write(f'> 自动生成 · 最后更新：{now} · 总项目数：{total}\n\n')

        f.write('## 📊 分类统计\n\n')
        for g in CATEGORY_ORDER:
            if g in categorized:
                cnt = sum(len(v) for v in categorized[g].values())
                f.write(f'- **{g}**：{cnt} 项\n')
        f.write('\n')

        f.write('<details>\n<summary>📂 目录（点击展开/收起）</summary>\n\n')
        for g in CATEGORY_ORDER:
            if g in categorized:
                safe_id = g.replace(" ", "-").lower()
                f.write(f'- **[{g}](#{safe_id})**\n')
                for s in categorized[g]:
                    sub_id = s.replace(" ", "-").lower()
                    f.write(f'  - [{s}](#{sub_id})\n')
        f.write('\n</details>\n\n')

        for g in CATEGORY_ORDER:
            if g not in categorized: continue
            f.write(f'## {g}\n\n')
            for s, items in categorized[g].items():
                safe_id = s.replace(" ", "-").lower()
                f.write(f'<a id="{safe_id}"></a>\n')
                f.write(f'<details>\n<summary>🔽 {s} （{len(items)} 项）</summary>\n\n')
                for repo in sorted(items, key=lambda x: x.get("stargazers_count", 0), reverse=True):
                    full = repo["full_name"]
                    url = repo["html_url"]
                    desc = (repo.get("description") or "无描述").replace("|", "\\|")
                    stars = repo["stargazers_count"]
                    forks = repo["forks_count"]
                    repo_updated = short_date(repo.get("updated_at"))  # 只保留仓库更新时间
                    rel = repo.get("_release")
                    rel_txt = f"📦 [{rel['tag']}]({rel['url']})" if rel and rel.get("tag") else "📦 无 Release"
                    topics = " ".join([f"`{t}`" for t in repo.get("_topics", [])])
                    tags_line = " ".join([f"`{t}`" for t in auto_tags_for_repo(repo)])

                    f.write(f'#### [{full}]({url})\n')
                    f.write(f'> {desc}\n\n')
                    if topics:
                        f.write(f'- **Topics:** {topics}\n')
                    if tags_line:
                        f.write(f'- **Tags:** {tags_line}\n')
                    f.write(f'- ⭐ {stars} · 🍴 {forks} · 📅 更新于 {repo_updated} · {rel_txt}\n\n')
                f.write('</details>\n\n')
    log.info(f"Markdown 生成完成 → {OUTPUT_MD}")

# ======================= 你指定的极简美观 HTML 生成（只显示仓库更新时间）======================
def generate_html(categorized, repos):
    now = datetime.now().strftime("%Y-%m-%d")
    ensure_dir("docs")

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Stars 简洁整理方案</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
        body {{
            font-family: 'Noto Sans SC', sans-serif;
            background-color: #f8fafc;
            color: #1e293b;
            scroll-behavior: smooth;
        }}
        .category-card {{ transition: transform 0.2s ease, box-shadow 0.2s ease; }}
        .category-card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1); }}
        .repo-card {{ transition: all 0.2s ease; border-left: 4px solid transparent; }}
        .repo-card:hover {{ border-left-color: #3b82f6; background-color: #f1f5f9; }}
        .nav-link {{ position: relative; }}
        .nav-link::after {{ content: ''; position: absolute; bottom: -2px; left: 0; width: 0; height: 2px; background-color: #3b82f6; transition: width 0.3s ease; }}
        .nav-link:hover::after {{ width: 100%; }}
        .back-to-top {{ position: fixed; bottom: 20px; right: 20px; opacity: 0; transition: opacity 0.3s ease; }}
        .back-to-top.visible {{ opacity: 1; }}
    </style>
</head>
<body class="max-w-4xl mx-auto px-4 py-8">
    <header class="mb-12 text-center">
        <h1 class="text-3xl md:text-4xl font-bold text-gray-800 mb-4">GitHub Stars 简洁整理方案</h1>
        <p class="text-lg text-gray-600 max-w-2xl mx-auto">一个简单高效的文档方案，保持编辑简单的同时确保目录索引功能完整可靠</p>
    </header>

    <div class="bg-white rounded-xl shadow-md p-6 mb-8">
        <h2 class="text-2xl font-semibold mb-4 text-gray-800">🌟 My GitHub Stars Collection</h2>
        <div class="mb-8">
            <h3 class="text-xl font-medium mb-3 text-gray-700 flex items-center">
                <i class="fas fa-list-ul mr-2 text-blue-500"></i> 目录导航
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">'''

    for g in CATEGORY_ORDER:
        if g in categorized:
            safe_id = g.replace(" ", "-").lower()
            html += f'''
                <a href="#{safe_id}" class="nav-link text-blue-600 hover:text-blue-800">{g}</a>'''

    html += '''
            </div>
        </div>
    </div>'''

    for g in CATEGORY_ORDER:
        if g not in categorized: continue
        icon_name, icon_color = CATEGORY_ICONS.get(g, ("fa-ellipsis-h", "text-gray-500"))
        safe_id = g.replace(" ", "-").lower()

        html += f'''
    <div id="{safe_id}" class="category-card bg-white rounded-xl shadow-md p-6 mb-8">
        <div class="flex items-center mb-4">
            <i class="fas {icon_name} text-2xl mr-3 {icon_color}"></i>
            <h2 class="text-2xl font-semibold text-gray-800">{g}</h2>
        </div>'''

        for s, items in categorized[g].items():
            html += f'''
        <div class="mb-6">
            <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">{s}</h3>
            <div class="space-y-3">'''

            for repo in sorted(items, key=lambda x: x.get("stargazers_count", 0), reverse=True):
                full = repo["full_name"]
                url = repo["html_url"]
                desc = (repo.get("description") or "暂无描述").replace('"', '&quot;').replace("'", '&#39;')
                repo_updated = short_date(repo.get("updated_at"))
                html += f'''
                <div class="repo-card bg-gray-50 rounded-lg p-4">
                    <a href="{url}" class="text-lg font-medium text-blue-600 hover:underline">{full}</a>
                    <p class="text-gray-600 mt-1">{desc}</p>
                    <p class="text-xs text-gray-500 mt-2">仓库更新于 {repo_updated}</p>
                </div>'''

            html += '''
            </div>
        </div>'''

        html += '''
        <div class="mt-6 text-right">
            <a href="#" class="text-blue-600 hover:text-blue-800 inline-flex items-center">
                <i class="fas fa-arrow-up mr-1"></i> 返回顶部
            </a>
        </div>
    </div>'''

    html += f'''
    <div class="bg-white rounded-xl shadow-md p-6 mb-8">
        <h2 class="text-2xl font-semibold mb-4 text-gray-800 flex items-center">
            <i class="fas fa-info-circle mr-2 text-blue-500"></i> 使用说明
        </h2>
        <div class="mb-6">
            <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">目录导航</h3>
            <ul class="list-disc pl-5 space-y-2 text-gray-600">
                <li>点击目录中的链接可以直接跳转到对应部分</li>
                <li>每个部分末尾有"返回顶部"链接</li>
            </ul>
        </div>
        <div class="mb-6">
            <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">编辑优势</h3>
            <ul class="list-disc pl-5 space-y-2 text-gray-600">
                <li>纯Markdown格式，无需任何HTML</li>
                <li>结构清晰，编辑维护简单</li>
                <li>在任何支持Markdown的编辑器或平台都能完美显示</li>
            </ul>
        </div>
        <div>
            <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">整理建议</h3>
            <ul class="list-disc pl-5 space-y-2 text-gray-600">
                <li>按分类顺序逐个整理</li>
                <li>每次star新项目时立即添加到对应位置</li>
                <li>每月回顾一次，删除不再需要的项目</li>
            </ul>
        </div>
    </div>

    <div class="bg-white rounded-xl shadow-md p-6 text-center text-gray-500 text-sm">
        最后更新: {now}
    </div>
    <div class="text-center text-gray-400 text-xs mt-8 mb-4">
        网页由问小白AI生成，仅供参考；最后更新时间为{now}；问小白的网址：wenxiaobai.com
    </div>

    <a href="#" class="back-to-top bg-blue-500 text-white p-3 rounded-full shadow-lg">
        <i class="fas fa-arrow-up"></i>
    </a>

    <script>
        window.addEventListener('scroll', function() {{
            const backToTop = document.querySelector('.back-to-top');
            if (window.pageYOffset > 300) {{
                backToTop.classList.add('visible');
            }} else {{
                backToTop.classList.remove('visible');
            }}
        }});
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function (e) {{
                e.preventDefault();
                document.querySelector(this.getAttribute('href')).scrollIntoView({{
                    behavior: 'smooth'
                }});
            }});
        }});
    </script>
</body>
</html>'''

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"极简美观 HTML 已生成 → {OUTPUT_HTML}")

# ======================= stats.json =======================
def dump_stats_json(repos, categorized):
    lang_counter = Counter((r.get("language") or "Unknown") for r in repos)
    data = {
        "total": len(repos),
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
        "by_category": {g: sum(len(v) for v in subs.values()) for g, subs in categorized.items()},
        "by_language": dict(lang_counter.most_common())
    }
    with open(STATS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"stats.json 已导出")

# ======================= 主函数 =======================
def main():
    username, token = get_config()

    log.info("开始执行 GitHub Stars 自动整理")

    session = build_session(token)

    repos = get_starred_repos(session, username)
    if not repos:
        log.error("未获取到星标项目")
        return

    repos = enrich_repos(session, repos)
    overrides = load_overrides()
    categorized = categorize_repos_mixed(repos, overrides)

    generate_markdown(categorized, repos)
    generate_html(categorized, repos)
    dump_stats_json(repos, categorized)

    if not os.path.exists(OVERRIDES_PATH):
        top30 = sorted(repos, key=lambda x: x.get("stargazers_count", 0), reverse=True)[:30]
        template = {r["full_name"]: {"group": "", "sub": ""} for r in top30}
        with open(OVERRIDES_TEMPLATE, "w", encoding="utf-8") as f:
            json.dump({"repos": template}, f, ensure_ascii=False, indent=2)
        log.info(f"已生成 overrides_template.json")

    log.info("🎉 所有任务完成！双输出完美就绪！")

if __name__ == "__main__":
    main()