# =====================
# update_starred_semantic.py — Part 1/3
# 核心：配置、API、分类、overrides、图标映射、Release 获取
# =====================

import os
import sys
import json
import requests
import logging
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------------
# 手动配置区（可选）
# ---------------------
# 本地调试时可在此写入用户名与 PAT，CI/CD（GitHub Actions）会使用环境变量 STAR_USERNAME/STAR_TOKEN
MANUAL_USERNAME = ""
MANUAL_TOKEN = ""

# ---------------------
# 图标映射（FontAwesome, Tailwind 颜色）
# 子分类默认继承父分类映射
# 若未来添加新分类，只需在此字典中声明
# ---------------------
ICON_MAP = {
    "AI": ("fa-brain", "red-500"),
    "Web 开发": ("fa-code", "blue-500"),
    "DevOps & 工具": ("fa-tools", "indigo-500"),
    "脚本自动化": ("fa-robot", "yellow-500"),
    "学习资料": ("fa-book-open", "teal-500"),
    "其他": ("fa-box-open", "gray-500")
}

# ---------------------
# 分类关键词（可按需扩展）
# 一级 -> 二级 -> 关键词列表（小写）
# ---------------------
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
    },
    # 注意：“其他” 不放在这里，分类函数会在没有匹配时放入 "其他"
}

# 将关键词全部转换为小写以便匹配
for g, subs in list(CATEGORY_MAP.items()):
    for s, kws in list(subs.items()):
        subs[s] = [k.lower() for k in kws]

# ---------------------
# 配置读取：MANUAL -> 交互（tty） -> 环境变量
# ---------------------
def get_config_interactive():
    username = MANUAL_USERNAME.strip() if isinstance(MANUAL_USERNAME, str) else ""
    token = MANUAL_TOKEN.strip() if isinstance(MANUAL_TOKEN, str) else ""

    # 允许在交互式终端中输入（仅在本地）
    try:
        if not username and sys.stdin.isatty():
            username = input("请输入 GitHub 用户名（回车跳过）：").strip() or ""
        if not token and sys.stdin.isatty():
            token = input("请输入 GitHub Token (PAT)（回车跳过）：").strip() or ""
    except Exception:
        # 如果输入失败（非交互环境），忽略
        pass

    # 最后 fallback 到环境变量（用于 GitHub Actions）
    username = username or os.getenv("STAR_USERNAME")
    token = token or os.getenv("STAR_TOKEN")

    if not username or not token:
        raise ValueError(
            "缺少 GitHub 用户名或 Token。请在脚本 MANUAL_* 填写，或交互输入（tty），或设置环境变量 STAR_USERNAME/STAR_TOKEN。"
        )
    return username, token

# ---------------------
# 构建 HTTP 会话（包含鉴权）
# ---------------------
def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "starred-exporter"
    })
    return s

# ---------------------
# 获取用户 starred 仓库（分页）
# 注意：GitHub API 有 rate limit；在大量仓库时请适当控制频率
# ---------------------
def get_starred_repos(session, username):
    url = f"https://api.github.com/users/{username}/starred"
    repos = []
    page = 1
    while url:
        logging.info(f"Fetching starred page {page} ...")
        resp = session.get(url, timeout=15)
        if resp.status_code == 401:
            raise Exception("401 Unauthorized: Token 无效或权限不足")
        if resp.status_code == 403:
            raise Exception(f"403 Forbidden: 可能是速率限制或权限问题，响应: {resp.text}")
        if resp.status_code != 200:
            raise Exception(f"GitHub API 请求失败：{resp.status_code} - {resp.text}")
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        url = resp.links.get("next", {}).get("url")
        page += 1
    logging.info(f"Fetched total {len(repos)} starred repos")
    return repos

# ---------------------
# 获取仓库最新 release（若无则返回 None）
# ---------------------
def format_date(date_str):
    if not date_str:
        return "N/A"
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return date_str.split("T")[0] if "T" in date_str else date_str

def get_latest_release(session, full_name):
    if not full_name:
        return None
    url = f"https://api.github.com/repos/{full_name}/releases/latest"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logging.warning(f"获取 release 失败 {full_name} - HTTP {resp.status_code}")
            return None
        d = resp.json()
        return {
            "tag": d.get("tag_name"),
            "url": d.get("html_url"),
            "published": format_date(d.get("published_at"))
        }
    except Exception as e:
        logging.warning(f"获取 release 出错 {full_name}: {e}")
        return None

# ---------------------
# overrides.json 支持（只实现精确 repo 指定）
# 格式：
# {
#   "repos": {
#       "owner/repo": { "category": "Web 开发", "subcategory": "前端" }
#   }
# }
# ---------------------
def load_overrides(path="overrides.json"):
    if not os.path.exists(path):
        return {"repos": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"repos": data.get("repos", {})}
    except Exception as e:
        logging.warning(f"加载 overrides.json 失败: {e}")
        return {"repos": {}}

# ---------------------
# 智能分类（优先 overrides.repos 精确匹配）
# 返回已排序的 dict：{ group: { sub: [repo,...], ... }, ... }
# “其他” 将在最后出现
# ---------------------
def categorize_repos_mixed(repos, overrides_path="overrides.json"):
    overrides = load_overrides(overrides_path).get("repos", {}) or {}
    categorized = defaultdict(lambda: defaultdict(list))

    for repo in repos:
        full_name = (repo.get("full_name") or "").strip()
        name = (repo.get("name") or "").lower()
        desc = (repo.get("description") or "").lower()
        topics = [t.lower() for t in repo.get("topics", [])] if isinstance(repo.get("topics"), list) else []
        text_blob = " ".join([full_name.lower(), name, desc] + topics)

        # 1. 精确 overrides（最高优先）
        if full_name in overrides:
            ov = overrides[full_name] or {}
            cat = ov.get("category", "其他")
            sub = ov.get("subcategory", "其他")
            categorized[cat][sub].append(repo)
            continue

        matched = False

        # 2. topics 优先匹配（如果存在）
        if topics:
            t_concat = " ".join(topics)
            for g, subs in CATEGORY_MAP.items():
                for s, kws in subs.items():
                    if any(k in t_concat for k in kws):
                        categorized[g][s].append(repo)
                        matched = True
                        break
                if matched:
                    break
            if matched:
                continue

        # 3. 名称/描述/owner 模糊匹配关键词
        for g, subs in CATEGORY_MAP.items():
            for s, kws in subs.items():
                if any(k in text_blob for k in kws):
                    categorized[g][s].append(repo)
                    matched = True
                    break
            if matched:
                break

        # 4. 兜底到其他
        if not matched:
            categorized["其他"]["其他"].append(repo)

    # 排序：按分类总数降序，同时保证 "其他" 在最后
    def group_key(item):
        name, subs = item
        if name == "其他":
            return (1, 0)  # 最后
        total = sum(len(v) for v in subs.values())
        return (0, -total)

    sorted_groups = dict(sorted(
        ((g, dict(sorted(subs.items(), key=lambda x: len(x[1]), reverse=True))) for g, subs in categorized.items()),
        key=group_key
    ))
    return sorted_groups

# End of Part 1/3
# =====================
# Part 2/3 — Markdown 输出（折叠目录 + 子分类跳转 + Release 同行）
# =====================

import re

def make_anchor(text):
    """
    把分类/子分类文本转换为稳定的锚点：
    - 保留中文/英文/数字
    - 用短横线连接空格
    - 移除非法字符
    """
    if not text:
        return ""
    s = str(text).strip()
    # 将空白替换为短横
    s = re.sub(r'\s+', '-', s)
    # 移除除中文、字母、数字、短横、下划线以外的字符
    s = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9\-_]', '', s)
    return s

def safe_text(s, maxlen=None):
    if not s:
        return ""
    t = str(s).replace('\r', ' ').replace('\n', ' ').replace('|', ' ')
    t = t.strip()
    if maxlen and len(t) > maxlen:
        return t[:maxlen-3] + "..."
    return t

def generate_markdown(repos, categorized, output="starred.md"):
    """
    输出风格说明：
    - 顶部说明 + 更新时间 + 总数
    - 折叠目录（显示子分类）
    - 每个一级分类为一级标题（##）
      - 每个二级分类作为一个 <details> 折叠块，summary 可点击展开/收起
      - 在每个二级分类上方放一个锚点（id）以支持目录跳转
    - Repo 列表为卡片风（#### repo），Meta（stars/forks/updated/release）在同一行
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)

    with open(output, "w", encoding="utf-8") as f:
        # Header
        f.write('<a id="top"></a>\n\n')
        f.write('# 🌟 我的 GitHub 星标项目整理\n\n')
        f.write('> 此文件由脚本自动生成，分类按功能/方向（支持 overrides.json 精确覆盖）。\n\n')
        f.write(f'> **最后更新**：{now}  ·  **总项目数**：{total}\n\n')

        # 目录（折叠，显示子分类）
        f.write('<details>\n<summary>📂 目录（点击展开/收起）</summary>\n\n')
        for group, subs in categorized.items():
            group_anchor = make_anchor(group)
            f.write(f'- **[{group}](#{group_anchor})**\n')
            for sub in subs.keys():
                sub_anchor = make_anchor(sub)
                f.write(f'  - [{sub}](#{sub_anchor})\n')
        f.write('\n</details>\n\n')

        # 具体分组内容
        for group, subs in categorized.items():
            # 一级标题
            group_anchor = make_anchor(group)
            f.write(f'## {group}\n\n')

            for sub, items in subs.items():
                sub_anchor = make_anchor(sub)
                # 二级折叠（可展开查看里面所有项目），同时提供锚点以支持跳转
                f.write(f'<a id="{sub_anchor}"></a>\n')
                f.write(f'<details>\n<summary>🔽 {sub} （{len(items)} 项）</summary>\n\n')

                # 列出仓库（按 star 降序）
                for repo in sorted(items, key=lambda r: r.get('stargazers_count', 0), reverse=True):
                    full = repo.get('full_name') or ""
                    url = repo.get('html_url') or ""
                    desc = safe_text(repo.get('description') or "无描述", maxlen=200)
                    stars = repo.get('stargazers_count', 0)
                    forks = repo.get('forks_count', 0)
                    updated = format_date(repo.get('updated_at'))

                    release = repo.get('_latest_release')
                    if release and release.get('tag'):
                        release_text = f"📦 [{safe_text(release.get('tag'))}]({release.get('url')})"
                    else:
                        release_text = "📦 无 Release"

                    meta_line = f"⭐ {stars} · 🍴 {forks} · 📅 {updated} · {release_text}"

                    f.write(f'#### [{full}]({url})\n')
                    f.write(f'> {desc}\n\n')
                    f.write(f'- {meta_line}\n\n')

                f.write('</details>\n\n')

        # Footer
        f.write('---\n\n[回到顶部](#top)\n')

    logging.info(f"Markdown 生成完成：{output}")
# =====================
# Part 3/3 — HTML 输出（Tailwind 卡片风） + main()
# =====================

def html_escape(s):
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))

def generate_html(repos, categorized, group_icons, output="docs/index.html"):
    """
    最终 HTML：
    - 完整复刻你提供的 Tailwind 模板结构
    - 动态生成分类目录 / 分类卡片
    - 每个 repo 使用卡片样式，meta 行与 release 同行
    """
    now = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(os.path.dirname(output), exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitHub Stars 整理</title>
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
.category-card {{
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.category-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
}}
.repo-card {{
    transition: all 0.2s ease;
    border-left: 4px solid transparent;
}}
.repo-card:hover {{
    border-left-color: #3b82f6;
    background-color: #f1f5f9;
}}
.nav-link {{
    position: relative;
}}
.nav-link::after {{
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    width: 0;
    height: 2px;
    background-color: #3b82f6;
    transition: width 0.3s ease;
}}
.nav-link:hover::after {{
    width: 100%;
}}
.back-to-top {{
    position: fixed;
    bottom: 20px;
    right: 20px;
    opacity: 0;
    transition: opacity 0.3s ease;
}}
.back-to-top.visible {{
    opacity: 1;
}}
</style>
</head>
<body class="max-w-5xl mx-auto px-4 py-8">

<header class="mb-12 text-center">
    <h1 class="text-3xl md:text-4xl font-bold text-gray-800 mb-4">🌟 GitHub Stars 整理</h1>
    <p class="text-lg text-gray-600 max-w-2xl mx-auto">自动分类 · 最新 Release · 清爽卡片式展示</p>
</header>

<!-- 顶部目录导航 -->
<div class="bg-white rounded-xl shadow-md p-6 mb-8">
    <h2 class="text-2xl font-semibold mb-4 text-gray-800">📂 目录导航</h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">""")

        # 目录导航
        for group in categorized.keys():
            anchor = make_anchor(group)
            f.write(f"""
        <a href="#{anchor}" class="nav-link text-blue-600 hover:text-blue-800">{html_escape(group)}</a>""")

        f.write("""
    </div>
</div>
""")

        # 分类展示区
        for group, subs in categorized.items():
            group_anchor = make_anchor(group)
            icon = group_icons.get(group, "fa-folder")

            f.write(f"""
<!-- 分类卡片：{group} -->
<div id="{group_anchor}" class="category-card bg-white rounded-xl shadow-md p-6 mb-8">
    <div class="flex items-center mb-4">
        <i class="fas {icon} text-2xl mr-3 text-blue-500"></i>
        <h2 class="text-2xl font-semibold text-gray-800">{html_escape(group)}</h2>
    </div>
""")

            # 子分类
            for sub, items in subs.items():
                f.write(f"""
    <div class="mb-6">
        <h3 class="text-xl font-medium mb-3 text-gray-700 border-b pb-2">{html_escape(sub)}（{len(items)}）</h3>
        <div class="space-y-3">""")

                # Repo 列表
                for repo in sorted(items, key=lambda r: r.get("stargazers_count", 0), reverse=True):
                    full = repo.get("full_name")
                    url = repo.get("html_url")
                    desc = html_escape(safe_text(repo.get("description") or "无描述", 150))

                    stars = repo.get("stargazers_count", 0)
                    forks = repo.get("forks_count", 0)
                    updated = format_date(repo.get("updated_at"))

                    release = repo.get("_latest_release")
                    if release and release.get("tag"):
                        release_html = f"""📦 <a class="text-blue-600" href="{release['url']}">{html_escape(release['tag'])}</a>"""
                    else:
                        release_html = "📦 无 Release"

                    f.write(f"""
            <div class="repo-card bg-gray-50 rounded-lg p-4">
                <a href="{url}" class="text-lg font-medium text-blue-600 hover:underline">{html_escape(full)}</a>
                <p class="text-gray-600 mt-1">{desc}</p>
                <div class="text-sm text-gray-500 mt-2">⭐ {stars} · 🍴 {forks} · 📅 {updated} · {release_html}</div>
            </div>
""")

                f.write("""
        </div>
    </div>
""")

            f.write("""
    <div class="mt-6 text-right">
        <a href="#" class="text-blue-600 hover:text-blue-800 inline-flex items-center">
            <i class="fas fa-arrow-up mr-1"></i> 返回顶部
        </a>
    </div>
</div>
""")

        # 页脚
        f.write(f"""
<div class="bg-white rounded-xl shadow-md p-6 text-center text-gray-500 text-sm">
    最后更新: {now}
</div>

<div class="text-center text-gray-400 text-xs mt-8 mb-4">
    页面自动生成 · 仅供个人整理使用
</div>

<a href="#" class="back-to-top bg-blue-500 text-white p-3 rounded-full shadow-lg">
    <i class="fas fa-arrow-up"></i>
</a>

<script>
// 返回顶部按钮显示/隐藏
window.addEventListener('scroll', function() {{
    const btn = document.querySelector('.back-to-top');
    if (window.pageYOffset > 300) btn.classList.add('visible');
    else btn.classList.remove('visible');
}});
</script>

</body>
</html>
""")

    logging.info(f"HTML 生成完成：{output}")


# ============== main() ==============
def main():
    logging.info("⭐ 开始执行 GitHub Stars 自动整理")

    username, token = get_config_interactive()

    # 正确构建 session
    session = build_session(token)

    # 正确传入（session, username）
    repos = get_starred_repos(session, username)

    # 提前获取 Release 并写入 repo 对象
    for repo in repos:
        repo['_latest_release'] = get_latest_release(session, repo.get("full_name"))

    categorized = categorize_repos_mixed(repos)

    # group_icons 原脚本不存在 → 使用 ICON_MAP
    group_icons = {k: v[0] for k, v in ICON_MAP.items()}

    generate_markdown(repos, categorized, output="starred.md")
    generate_html(repos, categorized, group_icons, output="docs/index.html")

    logging.info("🎉 所有文件已生成完毕！")

if __name__ == "__main__":
    main()
