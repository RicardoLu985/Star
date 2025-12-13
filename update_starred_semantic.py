#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# update_starred_semantic.py
# 修改版：支持默认分类外置配置、生成完整 overrides_template

import os
import json
import time
import logging
import requests
import re
import hashlib
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Optional, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("starred-updater")

# ======================= 配置 =======================
MANUAL_USERNAME = ""
MANUAL_TOKEN = ""

OUTPUT_MD = "starred.md"
OUTPUT_HTML = "docs/index.html"
OVERRIDES_PATH = "overrides.json"
OVERRIDES_TEMPLATE = "overrides_template.json"
CATEGORY_DEFAULTS_PATH = "category_defaults.json"
STATS_JSON = "stats.json"
GITHUB_API_ACCEPT = "application/vnd.github.mercy-preview+json"


# ======================= 工具函数 =======================
def ensure_dir(path: str) -> None:
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def short_date(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "N/A"
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except:
        return iso_str.split("T")[0] if "T" in iso_str else iso_str

def running_in_ci() -> bool:
    return os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

def get_config() -> tuple[str, str]:
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

def build_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": GITHUB_API_ACCEPT,
        "User-Agent": "starred-updater/2.0"
    })
    return s


# ======================= 数据获取 =======================

def fetch_url(session: requests.Session, url: str) -> Optional[Dict[str, Any]]:
    for attempt in range(3):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 403:
                log.warning("⏳ API 限流，60秒后重试...")
                time.sleep(60)
            elif r.status_code == 404:
                log.debug(f"资源不存在: {url}")
                return None
        except Exception as e:
            log.debug(f"请求失败 {url} (尝试 {attempt+1}/3): {e}")
            time.sleep(3)
    return None

def get_starred_repos(session: requests.Session, username: str) -> List[Dict[str, Any]]:
    repos = []
    url = f"https://api.github.com/users/{username}/starred?per_page=100"
    page = 1

    while url:
        log.info(f"📋 正在获取第 {page} 页 Starred...")
        data = fetch_url(session, url)
        if not data:
            break
        repos.extend(data)

        try:
            r = session.get(url)
            link = r.headers.get("Link", "")
            url = None
            if link:
                for part in link.split(","):
                    if 'rel="next"' in part:
                        url_match = re.search(r'<([^>]+)>', part)
                        if url_match:
                            url = url_match.group(1)
        except Exception as e:
            log.debug(f"解析分页链接失败: {e}")
            url = None
        page += 1

    log.info(f"共获取 {len(repos)} 个星标项目")
    return repos

def fetch_repo_topics(session: requests.Session, full_name: str) -> List[str]:
    data = fetch_url(session, f"https://api.github.com/repos/{full_name}/topics")
    return data.get("names", []) if isinstance(data, dict) else []

def fetch_latest_release(session: requests.Session, full_name: str) -> Optional[Dict[str, str]]:
    data = fetch_url(session, f"https://api.github.com/repos/{full_name}/releases/latest")
    if not data or not isinstance(data, dict):
        return None
    tag = data.get("tag_name") or data.get("name")
    url = data.get("html_url")
    date = data.get("published_at")
    return {"tag": tag, "url": url, "date": short_date(date)} if tag else None

def enrich_repos(session: requests.Session, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    log.info("🔍 开始富化仓库信息...")
    for i, repo in enumerate(repos, 1):
        full = repo["full_name"]
        repo["_topics"] = fetch_repo_topics(session, full)
        repo["_release"] = fetch_latest_release(session, full)

        if "pushed_at" not in repo or not repo["pushed_at"]:
            repo["pushed_at"] = repo.get("updated_at", "")

        log.debug(f"已处理 {i}/{len(repos)}: {full}")

    log.info("✅ 仓库信息富化完成")
    return repos


# ======================= Overrides 读取 =======================

def load_overrides() -> Dict[str, Any]:
    defaults = {
        "repos": {},
        "category_emoji": {},
        "category_icons": {}
    }

    if not os.path.exists(OVERRIDES_PATH):
        return defaults

    try:
        with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "repos" not in data:
                data = {"repos": data, "category_emoji": {}, "category_icons": {}}
            for key in defaults:
                if key not in data:
                    data[key] = defaults[key]
            return data
    except Exception as e:
        log.error(f"加载 overrides.json 失败: {e}")
        return defaults


# ======================= Category defaults（外置配置） =======================

def load_category_defaults():
    if not os.path.exists(CATEGORY_DEFAULTS_PATH):
        log.warning("category_defaults.json 未找到，将使用脚本内部默认值。")
        return {
            "category_order": [],
            "category_icons": {},
            "category_map": {}
        }
    try:
        with open(CATEGORY_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"读取 category_defaults.json 失败，将采用空配置: {e}")
        return {
            "category_order": [],
            "category_icons": {},
            "category_map": {}
        }


# ======================= 自动 Tags =======================

def auto_tags_for_repo(repo: Dict[str, Any]) -> List[str]:
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
    if lang:
        tags.add(lang)
    return sorted(tags)


# ========== 下一部分（Part 2）准备继续 ==========
# ======================= 分类逻辑：动态分类 + 外置配置 =======================

def get_dynamic_categories():
    overrides = load_overrides()
    category_defaults = load_category_defaults()

    # 来自 category_defaults.json 的外置配置
    category_order = category_defaults.get("category_order", []).copy()
    category_icons = category_defaults.get("category_icons", {}).copy()
    category_map = category_defaults.get("category_map", {}).copy()

    # 自动检测 overrides 中新增的自定义 group
    custom_groups = set()
    for repo_info in overrides.get("repos", {}).values():
        group = repo_info.get("group", "")
        if group and group not in category_order:
            custom_groups.add(group)

    # 将新 group 插入到倒数第二（"其他工具"前）
    for group in custom_groups:
        if group not in category_order:
            if "其他工具" in category_order:
                idx = max(0, category_order.index("其他工具"))
                category_order.insert(idx, group)
            else:
                category_order.append(group)

    # 为新增 group 自动生成图标（若未定义）
    for group in custom_groups:
        if group not in category_icons:
            if "影音" in group or "视频" in group or "音乐" in group:
                category_icons[group] = ["fa-film", "text-pink-500"]
            elif "AI" in group or "智能" in group:
                category_icons[group] = ["fa-robot", "text-red-500"]
            elif "学习" in group or "教程" in group:
                category_icons[group] = ["fa-graduation-cap", "text-teal-500"]
            elif "工具" in group:
                category_icons[group] = ["fa-tools", "text-indigo-500"]
            else:
                category_icons[group] = ["fa-folder", "text-blue-500"]

    # 为新增 group 创建空子分类（防止 KeyError）
    for group in custom_groups:
        if group not in category_map:
            category_map[group] = {"其他": []}

    return category_order, category_icons, category_map


def categorize_repos_mixed(repos: List[Dict[str, Any]], overrides: Dict[str, Any]):
    category_order, category_icons, category_map = get_dynamic_categories()

    tree = defaultdict(lambda: defaultdict(list))

    for repo in repos:
        full = repo["full_name"]
        blob = " ".join([
            full.lower(),
            (repo.get("description") or "").lower(),
            " ".join([t.lower() for t in repo.get("_topics", [])])
        ])

        # overrides 优先
        if full in overrides:
            override = overrides[full]
            g = override.get("group") or "其他工具"
            s = override.get("sub") or "其他"
            tree[g][s].append(repo)
            continue

        matched = False
        # 使用 category_defaults.json 的映射规则
        for group, subs in category_map.items():
            for sub, kws in subs.items():
                if any(kw and kw.lower() in blob for kw in kws):
                    tree[group][sub].append(repo)
                    matched = True
                    break
            if matched:
                break

        # 默认 fallback
        if not matched:
            lang = repo.get("language") or "其他"
            tree["其他工具"][f"{lang} 项目"].append(repo)

    # 按 category_order 输出排序好的结构
    ordered = {}
    for g in category_order:
        if g in tree:
            ordered[g] = dict(sorted(tree[g].items(), key=lambda x: len(x[1]), reverse=True))

    # 若 "其他工具" 不在序列但存在结果，则追加
    if "其他工具" in tree and "其他工具" not in ordered:
        ordered["其他工具"] = dict(sorted(tree["其他工具"].items(), key=lambda x: len(x[1]), reverse=True))

    return ordered


# ======================= 工具函数：生成安全锚点 =======================

def make_safe_id(text: str) -> str:
    text = text.replace("&", "and")
    text = re.sub(r'[^\w\s-]', '', text)
    text = text.replace(' ', '-').lower()
    text = re.sub(r'[-]+', '-', text)
    return text.strip('-')


# ======================= override 回退逻辑 =======================

def get_override_value(repo_full_name: str, overrides: Dict[str, Any], key: str, default_value: str) -> str:
    override_info = overrides.get(repo_full_name, {})
    value = override_info.get(key, "")
    return value if value else default_value


# ======================= 显示名生成函数 =======================

def get_display_name(repo_full_name: str, overrides: Dict[str, Any], repo: Dict[str, Any]) -> str:
    """
    获取项目的显示名
    优先级：
    1. overrides.json 中的 rename
    2. repo["name"]
    3. 不再使用 owner/repo 格式
    """
    # 优先使用 overrides.json 中的 rename
    rename = overrides.get(repo_full_name, {}).get("rename", "")
    if rename:
        return rename

    # 否则使用 repo["name"]
    return repo.get("name", repo_full_name)


# ======================= Markdown 生成 =======================

def generate_markdown(categorized, repos, overrides, category_emoji):
    now = datetime.now().strftime("%Y-%m-%d")
    total = len(repos)

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write('<a id="top"></a>\n\n')
        f.write('# 🌟 我的 GitHub 星标项目整理\n\n')
        f.write(f'> 自动生成 · 最后更新：{now} · 总项目数：{total}\n\n')

        f.write('## 📊 分类统计\n\n')
        category_order, _, _ = get_dynamic_categories()
        for g in category_order:
            if g in categorized:
                cnt = sum(len(v) for v in categorized[g].values())
                f.write(f'- **{g}**：{cnt} 项\n')
        f.write('\n')

        f.write('<details>\n<summary>📂 目录（点击展开/收起）</summary>\n\n')
        for g in category_order:
            if g in categorized:
                safe_id = make_safe_id(g)
                f.write(f'- **[{g}](#{safe_id})**\n')
                for s in categorized[g]:
                    sub_id = make_safe_id(s)
                    f.write(f'  - [{s}](#{sub_id})\n')
        f.write('\n</details>\n\n')

        f.write('---\n\n')

        for g in category_order:
            if g not in categorized:
                continue
            safe_id = make_safe_id(g)
            emoji = category_emoji.get(g, "")
            title = f"{emoji} {g}" if emoji else g
            f.write(f'<a id="{safe_id}"></a>\n')
            f.write(f'## {title}\n\n')

            for s, items in categorized[g].items():
                sub_id = make_safe_id(s)
                f.write(f'<a id="{sub_id}"></a>\n')
                f.write(f'<details>\n<summary>🔽 {s} ({len(items)}项)</summary>\n\n')

                for repo in sorted(items, key=lambda x: x.get("stargazers_count", 0), reverse=True):
                    full = repo["full_name"]
                    url = repo["html_url"]

                    original_desc = repo.get("description") or "无描述"
                    desc = get_override_value(full, overrides, "custom_description", original_desc)
                    desc = desc.replace("|", "\\|")

                    display_name = get_display_name(full, overrides, repo)

                    stars = repo["stargazers_count"]
                    forks = repo["forks_count"]
                    last_updated = short_date(repo.get("pushed_at"))
                    rel = repo.get("_release")
                    rel_txt = f"📦 [{rel['tag']}]({rel['url']})" if rel and rel.get("tag") else "📦 无 Release"

                    topics = " ".join([f"`{t}`" for t in repo.get("_topics", [])])
                    tags_line = " ".join([f"`{t}`" for t in auto_tags_for_repo(repo)])

                    f.write(f'#### [{display_name}]({url})\n')
                    f.write(f'> {desc}\n\n')
                    if topics:
                        f.write(f'- **Topics:** {topics}\n')
                    if tags_line:
                        f.write(f'- **Tags:** {tags_line}\n')
                    f.write(f'- ⭐ {stars} · 🍴 {forks} · 📅 最后更新 {last_updated} · {rel_txt}\n\n')

                f.write('<div style="text-align: right;">\n')
                f.write(f'<a href="#top">⬆️ 返回顶部</a> | <a href="#{safe_id}">⬆️ 返回分类</a>\n')
                f.write('</div>\n\n')
                f.write('</details>\n\n')

    with open(OUTPUT_MD, "a", encoding="utf-8") as f:
        f.write('\n---\n\n')
        f.write('<div style="text-align: center; padding: 30px 0;">\n')
        f.write(f'<a href="#top"><strong>⬆️ 返回顶部</strong></a>\n')
        f.write('</div>\n')

    log.info(f"Markdown 生成完成 → {OUTPUT_MD}")


# ========== 下一部分（Part 3）准备继续 ==========
# ======================= HTML 生成 =======================

def generate_html(categorized, repos, overrides, category_emoji):
    now = datetime.now().strftime("%Y-%m-%d")
    ensure_dir("docs")

    category_order, category_icons, _ = get_dynamic_categories()

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
        .back-to-top {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            width: 50px;
            height: 50px;
            background-color: #3b82f6;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s ease;
            z-index: 1000;
        }}
        .back-to-top.visible {{
            opacity: 1;
            visibility: visible;
        }}
        .back-to-top:hover {{
            background-color: #2563eb;
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
        }}
        .return-top-link {{
            color: #3b82f6;
            text-decoration: none;
            font-size: 0.9rem;
            margin-top: 1rem;
            display: inline-block;
        }}
        .return-top-link:hover {{
            text-decoration: underline;
        }}
        .section {{
            scroll-margin-top: 100px;
        }}
    </style>
</head>
<body class="max-w-4xl mx-auto px-4 py-8">
    <div id="top" class="section"></div>
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

    for g in category_order:
        if g in categorized:
            safe_id = make_safe_id(g)
            emoji = category_emoji.get(g, "")
            title = f"{emoji} {g}" if emoji else g
            html += f'''
                <a href="#{safe_id}" class="nav-link text-blue-600 hover:text-blue-800">{title}</a>'''

    html += '''
            </div>
        </div>
    </div>'''

    # 分类内容渲染
    for g in category_order:
        if g not in categorized:
            continue
        icon_name, icon_color = category_icons.get(g, ["fa-ellipsis-h", "text-gray-500"])
        safe_id = make_safe_id(g)
        emoji = category_emoji.get(g, "")
        title = f"{emoji} {g}" if emoji else g

        html += f'''
    <div id="{safe_id}" class="section category-card bg-white rounded-xl shadow-md p-6 mb-8">
        <div class="flex items-center mb-4">
            <i class="fas {icon_name} text-2xl mr-3 {icon_color}"></i>
            <h2 class="text-2xl font-semibold text-gray-800">{title}</h2>
        </div>'''

        for s, items in categorized[g].items():
            sub_id = make_safe_id(s)

            html += f'''
        <div id="{sub_id}" class="section mb-6">
            <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">{s}</h3>
            <div class="space-y-3">'''

            for repo in sorted(items, key=lambda x: x.get("stargazers_count", 0), reverse=True):
                full = repo["full_name"]
                url = repo["html_url"]

                original_desc = repo.get("description") or "暂无描述"
                raw_desc = get_override_value(full, overrides, "custom_description", original_desc)
                desc = raw_desc.replace('"', '&quot;').replace("'", '&#39;')

                display_name = get_display_name(full, overrides, repo)
                last_updated = short_date(repo.get("pushed_at"))

                html += f'''
                <div class="repo-card bg-gray-50 rounded-lg p-4">
                    <a href="{url}" class="text-lg font-medium text-blue-600 hover:underline">{display_name}</a>
                    <p class="text-gray-600 mt-1">{desc}</p>
                    <p class="text-xs text-gray-500 mt-2">最后更新于 {last_updated}</p>
                </div>'''

            html += '''
            </div>
        </div>'''

        html += f'''
        <div class="mt-6 pt-4 border-t text-right">
            <a href="#top" class="return-top-link">
                <i class="fas fa-arrow-up mr-1"></i> 返回顶部
            </a>
        </div>
    </div>'''

    # 说明部分
    info_icon_name, info_icon_color = category_icons.get("学习资料", ["fa-graduation-cap", "text-teal-500"])
    nav_icon_name, nav_icon_color = category_icons.get("脚本自动化", ["fa-terminal", "text-yellow-600"])
    edit_icon_name, edit_icon_color = category_icons.get("Web 开发", ["fa-paint-brush", "text-purple-500"])

    html += f'''
    <div class="bg-white rounded-xl shadow-md p-6 mb-8">
        <h2 class="text-2xl font-semibold mb-4 text-gray-800 flex items-center">
            <i class="fas {info_icon_name} text-2xl mr-2 {info_icon_color}"></i> 使用说明
        </h2>
        <div class="mb-6">
            <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2 flex items-center">
                <i class="fas {nav_icon_name} mr-2 {nav_icon_color}"></i> 目录导航
            </h3>
            <ul class="list-disc pl-5 space-y-2 text-gray-600">
                <li>点击目录中的链接可以直接跳转到对应部分</li>
                <li>每个部分末尾有"返回顶部"链接</li>
                <li>右下角的浮动按钮也可以快速返回顶部</li>
            </ul>
        </div>'''

    # 说明部分续
    html += f'''
        <div class="mb-6">
            <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2 flex items-center">
                <i class="fas {edit_icon_name} mr-2 {edit_icon_color}"></i> 编辑优势
            </h3>
            <ul class="list-disc pl-5 space-y-2 text-gray-600">
                <li>纯Markdown格式，无需任何HTML</li>
                <li>结构清晰，编辑维护简单</li>
                <li>在任何支持Markdown的编辑器或平台都能完美显示</li>
            </ul>
        </div>'''

    html += '''
        <div class="mt-6 pt-4 border-t text-right">
            <a href="#top" class="return-top-link">
                <i class="fas fa-arrow-up mr-1"></i> 返回顶部
            </a>
        </div>
    </div>

    <div class="bg-white rounded-xl shadow-md p-6 text-center text-gray-500 text-sm">
        最后更新: ''' + now + '''
    </div>

    <a href="#top" class="back-to-top" id="backToTop">
        <i class="fas fa-arrow-up"></i>
    </a>

    <script>
        window.addEventListener('scroll', function() {
            const backToTop = document.getElementById('backToTop');
            if (window.pageYOffset > 300) {
                backToTop.classList.add('visible');
            } else {
                backToTop.classList.remove('visible');
            }
        });
    </script>

</body>
</html>'''

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"HTML 已生成 → {OUTPUT_HTML}")


# ======================= stats.json 生成 =======================

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
    log.info("📊 stats.json 已导出")


# ========== 下一部分（Part 4）准备继续 ==========
# ======================= overrides_template.json（改进版本） =======================

def write_overrides_template(repos, overrides, path=OVERRIDES_TEMPLATE):
    template = {
        "repos": {},
        "category_emoji": {},
        "category_icons": {}
    }

    # 始终包含 1 个示例项目
    example_repo = next(iter(repos), None) if repos else None
    if example_repo:
        full = example_repo["full_name"]
        template["repos"][full] = {
            "//": "示例：group=一级分类，sub=子分类，rename=显示名，custom_description=自定义描述",
            "group": "示例分类",
            "sub": "示例子类",
            "rename": "示例项目名称",
            "custom_description": "这是一个示例说明"
        }

    # 检查是否存在未分组项目（既没有 group 也没有 sub）
    ungrouped_exists = False
    for repo in repos:
        full = repo["full_name"]
        repo_override = overrides.get(full, {})
        if not repo_override.get("group") and not repo_override.get("sub"):
            ungrouped_exists = True
            break

    # 如果存在未分组项目，追加这些项目（无注释）
    if ungrouped_exists:
        for repo in repos:
            full = repo["full_name"]
            repo_override = overrides.get(full, {})

            # 如果该项目没有分组信息，则添加到模板
            if not repo_override.get("group") and not repo_override.get("sub"):
                if full not in template["repos"]:  # 避免重复添加示例项目
                    template["repos"][full] = {
                        "group": "",
                        "sub": "",
                        "rename": "",
                        "custom_description": ""
                    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=4, ensure_ascii=False)

    log.info(f"📄 overrides_template.json 已生成，共包含 {len(template['repos'])} 项模板")


# ======================= Main 流程 =======================

def main():
    username, token = get_config()
    log.info(f"🚀 开始整理用户：{username} 的 Github 仓库")

    session = build_session(token)

    repos = get_starred_repos(session, username)
    repos = enrich_repos(session, repos)

    overrides_data = load_overrides()
    overrides = overrides_data.get("repos", {})
    category_emoji = overrides_data.get("category_emoji", {})

    categorized = categorize_repos_mixed(repos, overrides)

    generate_markdown(categorized, repos, overrides, category_emoji)
    generate_html(categorized, repos, overrides, category_emoji)

    dump_stats_json(repos, categorized)

    write_overrides_template(repos, overrides)

    log.info("🎉 全部流程已完成！")


# ======================= 入口 =======================

if __name__ == "__main__":
    main()