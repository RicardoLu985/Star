# update_starred_semantic.py
# 部分 1/3 — 导入、配置、API、overrides、分类（精确 repo 覆盖优先）
import os
import sys
import json
import requests
import logging
from datetime import datetime
from collections import defaultdict

# 日志配置
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --------------------------
# 手动配置区（可选）
# --------------------------
# 本地测试时可以直接填写。这两个值优先级最低（会被交互输入覆盖）。
MANUAL_USERNAME = ""   # 例如 "RicardoLu985"
MANUAL_TOKEN = ""      # 例如 "ghp_xxx..."

# --------------------------
# 获取配置（MANUAL -> 交互 -> 环境变量）
# --------------------------
def get_config_interactive():
    username = MANUAL_USERNAME.strip() if isinstance(MANUAL_USERNAME, str) else ""
    token = MANUAL_TOKEN.strip() if isinstance(MANUAL_TOKEN, str) else ""

    # 交互输入（仅在 tty 环境下）
    try:
        if not username and sys.stdin.isatty():
            username = input("请输入 GitHub 用户名（回车跳过）：").strip() or ""
        if not token and sys.stdin.isatty():
            token = input("请输入 GitHub Token (PAT)（回车跳过）：").strip() or ""
    except Exception:
        # 在某些非交互环境 input 可能失败，忽略
        pass

    # fallback 到环境变量（用于 Actions）
    username = username or os.getenv("STAR_USERNAME")
    token = token or os.getenv("STAR_TOKEN")

    if not username or not token:
        raise ValueError(
            "缺少 GitHub 用户名或 Token。请在脚本 MANUAL_* 填写，或交互输入（终端），或设置环境变量 STAR_USERNAME/STAR_TOKEN。"
        )
    return username, token

# --------------------------
# 构建会话
# --------------------------
def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "starred-exporter"
    })
    return s

# --------------------------
# 获取 starred repos（分页）
# --------------------------
def get_starred_repos(session, username):
    url = f"https://api.github.com/users/{username}/starred"
    repos = []
    page = 1
    while url:
        logging.info(f"Fetching starred page {page} ...")
        resp = session.get(url, timeout=15)
        if resp.status_code == 401:
            raise Exception("401 Unauthorized: Token 可能无效")
        if resp.status_code == 403:
            # 403 可能是 rate limit 或访问受限
            raise Exception(f"403 Forbidden: 访问被拒绝或速率限制。响应：{resp.text}")
        if resp.status_code != 200:
            raise Exception(f"GitHub API 请求失败：{resp.status_code} - {resp.text}")

        data = resp.json()
        if not data:
            break
        repos.extend(data)
        url = resp.links.get("next", {}).get("url")
        page += 1

    logging.info(f"Total starred repos fetched: {len(repos)}")
    return repos

# --------------------------
# 获取最新 release（若无返回 None）
# --------------------------
def format_date(date_str):
    if not date_str:
        return "N/A"
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return date_str.split("T")[0] if "T" in date_str else date_str

def get_latest_release(session, full_name):
    """
    full_name: "owner/repo"
    返回 dict: { "tag":..., "url":..., "published":... } 或 None
    """
    if not full_name:
        return None
    url = f"https://api.github.com/repos/{full_name}/releases/latest"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logging.warning(f"[Release] 获取失败 {full_name} - HTTP {resp.status_code}")
            return None
        d = resp.json()
        return {
            "tag": d.get("tag_name"),
            "url": d.get("html_url"),
            "published": format_date(d.get("published_at"))
        }
    except Exception as e:
        logging.warning(f"[Release] Exception for {full_name}: {e}")
        return None

# --------------------------
# overrides.json 支持（方法一：精确 repo 指定）
# 文件格式示例：
# {
#   "repos": {
#       "facebook/react": { "category": "Web 开发", "subcategory": "前端" },
#       "openai/gpt-4": { "category": "AI", "subcategory": "大模型" }
#   }
# }
# --------------------------
def load_overrides(path="overrides.json"):
    if not os.path.exists(path):
        return {"repos": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            repos = data.get("repos", {}) if isinstance(data, dict) else {}
            return {"repos": repos}
    except Exception as e:
        logging.warning(f"加载 overrides.json 失败: {e}")
        return {"repos": {}}

# --------------------------
# 分类规则（预设 CATEGORY_MAP）
# （你可以根据需要在这里扩展关键词）
# --------------------------
CATEGORY_MAP = {
    "AI": {
        "机器学习": ["pytorch", "tensorflow", "ml", "deep learning", "neural"],
        "自然语言处理": ["nlp", "transformer", "gpt", "llm", "huggingface"]
    },
    "Web 开发": {
        "前端": ["react", "vue", "vite", "svelte", "javascript", "typescript"],
        "后端": ["api", "backend", "fastapi", "django", "flask", "node", "express"]
    },
    "DevOps & 工具": {
        "CI/CD": ["docker", "kubernetes", "k8s", "ci", "cd", "pipeline"],
        "效率工具": ["cli", "tool", "plugin", "utils"]
    },
    "脚本 / 自动化": {
        "脚本 / 自动化": ["script", "automation", "bot", "crawler", "scraper"]
    },
    "学习资料": {
        "学习资料": ["awesome", "tutorial", "guide", "learning", "notes"]
    },
    "其他": {
        "其他": []
    }
}

# normalize keywords to lowercase
for g, subs in CATEGORY_MAP.items():
    for s, kws in subs.items():
        subs[s] = [k.lower() for k in kws]

# --------------------------
# 混合分类（先检查 overrides.repos 精确匹配；否则 topics/keywords 匹配；否则归入其他）
# 返回结构：{ group: { sub: [repo, ...], ... }, ... } （普通 dict，已按组排序）
# --------------------------
def categorize_repos_mixed(repos, overrides_path="overrides.json"):
    overrides = load_overrides(overrides_path)
    repo_overrides = overrides.get("repos", {}) or {}

    categorized = defaultdict(lambda: defaultdict(list))

    for repo in repos:
        full_name = (repo.get("full_name") or "").strip()
        name = (repo.get("name") or "").lower()
        desc = (repo.get("description") or "").lower()
        topics = [t.lower() for t in repo.get("topics", [])] if isinstance(repo.get("topics"), list) else []
        text = " ".join([full_name.lower(), name, desc] + topics)

        # 1) 精确 repo override（最高优先）
        if full_name in repo_overrides:
            ov = repo_overrides[full_name] or {}
            cat = ov.get("category", "其他")
            sub = ov.get("subcategory", "其他")
            categorized[cat][sub].append(repo)
            continue

        matched = False

        # 2) topics 匹配（如果 topics 存在）
        if topics:
            tstr = " ".join(topics)
            for g, subs in CATEGORY_MAP.items():
                for s, kws in subs.items():
                    if any(k in tstr for k in kws):
                        categorized[g][s].append(repo)
                        matched = True
                        break
                if matched:
                    break
            if matched:
                continue

        # 3) name/description/owner 模糊匹配关键词
        for g, subs in CATEGORY_MAP.items():
            for s, kws in subs.items():
                if any(k in text for k in kws):
                    categorized[g][s].append(repo)
                    matched = True
                    break
            if matched:
                break

        # 4) 兜底
        if not matched:
            categorized["其他"]["其他"].append(repo)

    # sort groups by number of repos desc, and subs by size desc
    sorted_groups = dict(sorted(
        ((g, dict(sorted(subs.items(), key=lambda x: len(x[1]), reverse=True))) for g, subs in categorized.items()),
        key=lambda x: sum(len(lst) for lst in x[1].values()),
        reverse=True
    ))
    return sorted_groups

# End of part 1/3
# ===========================
# Part 2/3 — Markdown 输出（M3 风格：统计表 + 卡片）
# ===========================

def safe_text(s, maxlen=None):
    """清理并返回安全的纯文本（用于 md/表格列），去掉换行、管道符等"""
    if not s:
        return ""
    text = str(s).replace("\r", " ").replace("\n", " ").replace("|", " ")
    text = text.strip()
    if maxlen and len(text) > maxlen:
        return text[:maxlen-3] + "..."
    return text

def generate_markdown(repos, categorized, output="starred.md"):
    """
    生成 Markdown（M3 风格）：
      - 顶部统计（更新时间 / 总数）
      - 分类统计表（一级/二级）
      - 可折叠目录（按一级分组显示二级）
      - 每个二级以卡片形式列出（标题、描述、meta、Release）
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)

    with open(output, "w", encoding="utf-8") as f:
        # 顶部与说明
        f.write('<a id="top"></a>\n\n')
        f.write('# 我的 GitHub 星标项目整理 ✨\n\n')
        f.write('> **说明**：此文件由脚本自动生成，按功能/方向分类（支持 overrides.json 精确覆盖）。\n')
        f.write(f'> **最后更新**：{now}\n')
        f.write(f'> **总项目数**：{total}\n\n')

        # 分类统计表
        f.write('## 📊 分类统计\n\n')
        f.write('| 一级分类 | 子分类（示例） | 项目数 |\n')
        f.write('|----------|---------------|-------:|\n')
        for group, subs in categorized.items():
            cnt = sum(len(v) for v in subs.values())
            sample = ", ".join([f"{k}({len(v)})" for k, v in list(subs.items())[:3]])
            f.write(f'| {group} | {safe_text(sample)} | {cnt} |\n')
        f.write('\n')

        # 折叠目录（一级 -> 二级）
        f.write('<details>\n<summary>📂 目录（点击展开/收起）</summary>\n\n')
        for group, subs in categorized.items():
            group_count = sum(len(v) for v in subs.values())
            f.write(f'<details>\n<summary>📁 {group}（{group_count}）</summary>\n\n')
            for sub in subs.keys():
                anchor = sub.replace(" ", "").replace("/", "")
                f.write(f'- [{sub}](#{anchor})\n')
            f.write('\n</details>\n')
        f.write('\n</details>\n\n')

        # 详细内容（按一级 -> 二级）
        for group, subs in categorized.items():
            f.write(f'## {group}\n\n')
            for sub, items in subs.items():
                anchor = sub.replace(" ", "").replace("/", "")
                f.write(f'### {sub}\n\n')

                # 每个 repo 使用卡片样式（标题 + 引用 + metadata + Release）
                for repo in sorted(items, key=lambda r: r.get("stargazers_count", 0), reverse=True):
                    full = repo.get("full_name") or ""
                    url = repo.get("html_url") or ""
                    desc = safe_text(repo.get("description") or "无描述", maxlen=240)
                    stars = repo.get("stargazers_count", 0)
                    forks = repo.get("forks_count", 0)
                    updated = format_date(repo.get("updated_at"))

                    # Release 信息（如果存在）
                    release = repo.get("_latest_release")
                    if release and release.get("tag"):
                        rel_line = f"📦 最新版本：[{safe_text(release.get('tag'))}]({release.get('url')})（{release.get('published','N/A')}）"
                    else:
                        rel_line = "📦 无 Release"

                    # 写入卡片
                    f.write(f'#### [{full}]({url})\n')
                    f.write(f'> {desc}\n\n')
                    f.write(f'- ⭐ {stars} · 🍴 {forks} · 📅 {updated}\n')
                    f.write(f'- {rel_line}\n\n')

                # 小间隔
                f.write('\n')

        # 页脚回到顶部
        f.write('---\n\n[回到顶部](#top)\n')

    logging.info(f"Markdown 已生成：{output}")

# End of part 2/3
# ===========================
# Part 3/3 — 全新 HTML 输出（现代 UI） + main()
# ===========================

def generate_html(repos, categorized, output="docs/index.html"):
    """
    现代化 HTML 输出（卡片式 UI + 深色模式 + 分类折叠 + 自适应布局）
    """
    os.makedirs("docs", exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)

    html = []

    # ---------------------------
    # <head> 部分：CSS + 深色模式
    # ---------------------------
    html.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>GitHub 星标项目</title>
<style>
:root {{
    --bg: #f7f7f9;
    --fg: #222;
    --card-bg: #fff;
    --card-border: #e5e7eb;
    --primary: #2563eb;
    --secondary: #6b7280;
    --hover-bg: #f0f0f5;
}}

@media (prefers-color-scheme: dark) {{
    :root {{
        --bg: #1e1e20;
        --fg: #e3e3e3;
        --card-bg: #2b2b2f;
        --card-border: #3d3d43;
        --hover-bg: #3a3a3f;
    }}
}}

body {{
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial;
    line-height: 1.6;
    margin: 0;
    padding: 20px;
    max-width: 1100px;
    margin-left: auto;
    margin-right: auto;
}}

h1 {{
    text-align: center;
    margin-bottom: 20px;
    font-size: 2.2rem;
}}

.header-info {{
    text-align: center;
    color: var(--secondary);
    margin-bottom: 35px;
}}

.section-title {{
    font-size: 1.25rem;
    margin: 35px 0 15px 0;
    font-weight: bold;
}}

details {{
    margin: 12px 0;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 10px 14px;
}}

details[open] {{
    background: var(--card-bg);
    border-color: var(--primary);
}}

summary {{
    cursor: pointer;
    font-size: 1.1rem;
    color: var(--primary);
}}

.repo-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 14px;
    transition: background 0.2s, transform 0.2s;
}}

.repo-card:hover {{
    background: var(--hover-bg);
    transform: translateY(-2px);
}}

.repo-title a {{
    color: var(--primary);
    font-weight: bold;
    text-decoration: none;
    font-size: 1.05rem;
}}

.repo-title a:hover {{
    text-decoration: underline;
}}

.repo-desc {{
    color: var(--secondary);
    margin: 6px 0 10px 0;
}}

.repo-meta {{
    font-size: 0.9rem;
    color: var(--secondary);
}}

.meta-line {{
    margin-bottom: 4px;
}}

.group-title {{
    font-size: 1.7rem;
    margin-top: 45px;
    margin-bottom: 20px;
}}

.sub-title {{
    font-size: 1.3rem;
    margin-top: 25px;
    margin-bottom: 14px;
}}

hr {{
    border: none;
    border-top: 1px solid var(--card-border);
    margin: 50px 0 30px 0;
}}
</style>
</head>
<body>

<h1>🌟 我的 GitHub 星标项目</h1>
<div class="header-info">
    📅 最后更新：{now} &nbsp;·&nbsp; 🔢 总项目数：{total}
</div>
""")

    # ---------------------------
    # 分类统计区
    # ---------------------------
    html.append("<div class='section-title'>📊 分类统计</div>")
    html.append("<details open><summary>展开 / 收起</summary><ul>")

    for group, subs in categorized.items():
        count = sum(len(v) for v in subs.values())
        html.append(f"<li><b>{group}</b> · {count} 个项目</li>")
    html.append("</ul></details>")

    # ---------------------------
    # 分组内容
    # ---------------------------
    for group, subs in categorized.items():
        html.append(f"<div class='group-title'>{group}</div>")

        for subcat, items in subs.items():
            html.append(f"<div class='sub-title'>{subcat}</div>")

            for repo in sorted(items, key=lambda r: r.get("stargazers_count", 0), reverse=True):
                full = repo.get("full_name", "")
                url = repo.get("html_url", "")
                desc = repo.get("description") or "无描述"
                stars = repo.get("stargazers_count", 0)
                forks = repo.get("forks_count", 0)
                updated = format_date(repo.get("updated_at"))

                release = repo.get("_latest_release")
                if release and release.get("tag"):
                    release_html = (
                        f"📦 最新版本：<a href='{release['url']}' "
                        f"target='_blank'>{release['tag']}</a>（{release['published']}）"
                    )
                else:
                    release_html = "📦 无 Release"

                # 卡片 HTML
                html.append(f"""
<div class="repo-card">
    <div class="repo-title"><a href="{url}" target="_blank">{full}</a></div>
    <div class="repo-desc">{desc}</div>
    <div class="repo-meta">
        <div class="meta-line">⭐ {stars} · 🍴 {forks} · 📅 {updated}</div>
        <div class="meta-line">{release_html}</div>
    </div>
</div>
""")

    html.append("<hr><div style='text-align:center;color:var(--secondary);'>此页面由脚本自动生成</div>")
    html.append("</body></html>")

    # 写入文件
    with open(output, "w", encoding="utf-8") as fh:
        fh.write("".join(html))

    logging.info(f"HTML 已生成：{output}")

# ===========================
# main()
# ===========================
def main():
    try:
        username, token = get_config_interactive()
        session = build_session(token)

        logging.info(f"开始获取 {username} 的 starred 项目 …")
        repos = get_starred_repos(session, username)

        # 添加最新 release 信息
        logging.info("获取每个仓库的最新 Release …")
        for repo in repos:
            full = repo.get("full_name")
            repo["_latest_release"] = get_latest_release(session, full)

        # 分类（已包括 overrides.json.repos 的精确覆盖）
        categorized = categorize_repos_mixed(repos)

        # 输出 Markdown + HTML
        generate_markdown(repos, categorized, output="starred.md")
        generate_html(repos, categorized, output="docs/index.html")

        logging.info("全部生成完毕！")
    except Exception as e:
        logging.error(f"执行失败：{e}")
        raise

if __name__ == "__main__":
    main()
