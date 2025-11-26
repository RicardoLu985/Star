# update_starred_semantic.py

import os
import requests
from datetime import datetime
import logging
from collections import defaultdict

# =============================
# 配置日志
# =============================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

os.makedirs('docs', exist_ok=True)

# =============================
# 环境变量
# =============================
STAR_USERNAME = os.getenv("STAR_USERNAME")
STAR_TOKEN = os.getenv("STAR_TOKEN")
GITHUB_PROXY = os.getenv("GITHUB_PROXY")  # 可选

if not STAR_USERNAME:
    raise ValueError("STAR_USERNAME 环境变量未设置")
if not STAR_TOKEN:
    raise ValueError("STAR_TOKEN 环境变量未设置")

# =============================
# API 会话配置
# =============================
session = requests.Session()
session.headers.update({
    'Authorization': f'token {STAR_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'GitHub Starred Projects Exporter'
})

if GITHUB_PROXY:
    session.proxies.update({'http': GITHUB_PROXY, 'https': GITHUB_PROXY})
    logging.info(f"使用代理: {GITHUB_PROXY}")

# =============================
# 功能分类关键词（方案 A）
# =============================
CATEGORY_KEYWORDS = {
    "前端相关": [
        "frontend", "front-end", "react", "vue", "svelte", "vite",
        "webpack", "javascript", "typescript", "css", "html"
    ],
    "后端服务": [
        "backend", "api", "server", "spring", "django", "flask",
        "express", "fastapi", "node", "service"
    ],
    "AI / 机器学习": [
        "ai", "ml", "machine learning", "model", "deep learning",
        "neural", "transformer", "llm", "nlp", "cv"
    ],
    "数据处理 / 数据库": [
        "data", "dataset", "csv", "sql", "database", "mysql",
        "postgres", "etl", "analytics", "big data"
    ],
    "运维 / DevOps / CI-CD": [
        "docker", "kubernetes", "k8s", "devops", "ci", "cd",
        "github actions", "pipeline", "deployment"
    ],
    "工具 / 工具库 / CLI": [
        "cli", "tool", "library", "utils", "debug", "helper",
        "extension", "plugin"
    ],
    "脚本 / 自动化": [
        "script", "automation", "bot", "crawler", "scraper"
    ],
    "系统 / 底层": [
        "os", "kernel", "system", "driver", "shell", "rust", "c++"
    ],
    "学习 / 教程 / 笔记": [
        "awesome", "tutorial", "notes", "learning", "guide"
    ],
    "未分类": []
}

# =============================
# API：获取 starred repos
# =============================
def get_starred_repos(username):
    url = f'https://api.github.com/users/{username}/starred'
    repos = []
    page = 1

    while url:
        logging.info(f"获取第 {page} 页星标项目…")
        resp = session.get(url, timeout=10)

        if resp.status_code == 401:
            raise Exception("认证失败，请检查 STAR_TOKEN")
        if resp.status_code == 403:
            raise Exception("API 速率限制，请稍后再试")
        if resp.status_code != 200:
            raise Exception(f"请求失败：{resp.status_code} - {resp.text}")

        page_repos = resp.json()
        if not page_repos:
            break

        repos.extend(page_repos)
        url = resp.links.get('next', {}).get('url')
        page += 1

    return repos

# =============================
# 功能分类（关键词匹配）
# =============================
def categorize_by_topic(repos):
    categorized = defaultdict(list)

    for repo in repos:
        text = (repo.get("name", "") + " " + (repo.get("description") or "")).lower()

        matched = False
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                categorized[category].append(repo)
                matched = True
                break

        if not matched:
            categorized["未分类"].append(repo)

    # 按项目数量排序
    return dict(sorted(categorized.items(), key=lambda x: len(x[1]), reverse=True))

# =============================
# 日期格式化
# =============================
def format_date(date_string):
    if not date_string:
        return "N/A"
    try:
        return datetime.fromisoformat(date_string.replace('Z', '+00:00')).strftime("%Y-%m-%d")
    except:
        return date_string

# =============================
# Markdown 输出
# =============================
def generate_markdown(repos, output_file="starred.md"):
    categorized = categorize_by_topic(repos)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 🌟 我的 GitHub Star 项目（按功能分类）\n\n")
        f.write(f"> 📅 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"> ⭐ 总项目数：{len(repos)}\n")
        f.write(f"> 🗂 功能分类数：{len(categorized)}\n\n")

        # 分类统计
        f.write("## 📊 功能分类统计\n\n")
        f.write("| 分类 | 项目数 |\n|------|--------|\n")
        for cat, items in categorized.items():
            f.write(f"| {cat} | {len(items)} |\n")
        f.write("\n---\n\n")

        # 按分类列出项目
        for category, items in categorized.items():
            f.write(f"## {category}（{len(items)}）\n\n")
            for repo in items:
                desc = repo.get("description") or "无描述"
                f.write(f"### [{repo['full_name']}]({repo['html_url']})\n")
                f.write(f"> {desc}\n\n")
                f.write(f"- ⭐ Stars：{repo.get('stargazers_count', 0)}\n")
                f.write(f"- 🍴 Forks：{repo.get('forks_count', 0)}\n")
                f.write(f"- 📅 更新时间：{format_date(repo.get('updated_at'))}\n\n")
            f.write("\n---\n\n")

    logging.info(f"Markdown 已生成：{output_file}")

# =============================
# HTML 输出
# =============================
def generate_html(repos, output_file="docs/index.html"):
    categorized = categorize_by_topic(repos)

    html = []

    # 头部
    html.append(f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>GitHub Star 项目</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial;
    background: #fafafa;
    padding: 20px;
    max-width: 1000px;
    margin: auto;
}}
.card {{
    background: white;
    padding: 15px 20px;
    margin-bottom: 15px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}}
h1 {{
    text-align: center;
}}
.category-title {{
    font-size: 22px;
    margin-top: 40px;
    border-bottom: 3px solid #eee;
    padding-bottom: 5px;
}}
.repo-title a {{
    color: #0366d6;
    font-weight: bold;
    text-decoration: none;
}}
.repo-title a:hover {{
    text-decoration: underline;
}}
.meta {{
    color: #666;
    font-size: 14px;
}}
.desc {{
    margin: 8px 0;
    color: #444;
}}
</style>
</head>
<body>

<h1>🌟 GitHub Stars（按功能分类）</h1>
<p class="meta">📅 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · ⭐ 共 {len(repos)} 个项目</p>
    """)

    # 按功能分类展示
    for category, items in categorized.items():
        html.append(f'<div class="category-title">{category}（{len(items)}）</div>')

        for repo in items:
            desc = repo.get("description") or "无描述"
            html.append(f"""
            <div class="card">
                <div class="repo-title">
                    <a href="{repo['html_url']}" target="_blank">{repo['full_name']}</a>
                </div>
                <div class="desc">{desc}</div>
                <div class="meta">
                    ⭐ {repo.get('stargazers_count', 0)} 
                    🍴 {repo.get('forks_count', 0)} 
                    📅 {format_date(repo.get('updated_at'))}
                </div>
            </div>
            """)

    # 页脚
    html.append("""
</body>
</html>
""")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

    logging.info(f"HTML 已生成：{output_file}")

# =============================
# 主函数
# =============================
def main():
    logging.info("开始获取 GitHub 星标项目…")
    repos = get_starred_repos(STAR_USERNAME)

    logging.info(f"共获取 {len(repos)} 个项目")
    generate_markdown(repos)
    generate_html(repos)
    logging.info("所有文件已生成")

if __name__ == "__main__":
    main()
