import os
import sys
import requests
import logging
import json
from datetime import datetime
from collections import defaultdict

# 日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -----------------------------------------------------
# 🧩 【手动配置区】（可为空，脚本自动 fallback）
# -----------------------------------------------------
MANUAL_USERNAME = "RicardoLu985"   # 例如 "RicardoLu985"
MANUAL_TOKEN = ""       # 例如 "ghp_xxx..."

# -----------------------------------------------------
# 🎛 Token / Username 获取（手动 → 输入 → 环境变量）
# -----------------------------------------------------
def get_config_interactive():
    username = MANUAL_USERNAME.strip()
    token = MANUAL_TOKEN.strip()

    # 若没有手动定义，则尝试交互输入
    if not username and sys.stdin.isatty():
        username = input("请输入 GitHub 用户名（回车跳过）：").strip() or ""
    if not token and sys.stdin.isatty():
        token = input("请输入 GitHub Token（回车跳过）：").strip() or ""

    # 最终 fallback 到环境变量（用于 GitHub Actions）
    username = username or os.getenv("STAR_USERNAME")
    token = token or os.getenv("STAR_TOKEN")

    if not username or not token:
        raise ValueError("缺少 GitHub 用户名或 Token，请填写 MANUAL_，或输入，或设置环境变量。")

    return username, token


# -----------------------------------------------------
# GitHub API 会话
# -----------------------------------------------------
def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "starred-exporter"
    })
    return s


# -----------------------------------------------------
# 获取 starred 仓库列表（分页）
# -----------------------------------------------------
def get_starred_repos(session, username):
    url = f"https://api.github.com/users/{username}/starred"
    repos = []
    page = 1

    while url:
        logging.info(f"获取星标仓库第 {page} 页...")
        resp = session.get(url, timeout=10)

        if resp.status_code == 401:
            raise Exception("401 Unauthorized，Token 可能无效")
        if resp.status_code == 403:
            raise Exception("403 Forbidden，可能遇到 API 速率限制")
        if resp.status_code != 200:
            raise Exception(f"GitHub API 错误 {resp.status_code}：{resp.text}")

        data = resp.json()
        if not data:
            break

        repos.extend(data)
        url = resp.links.get("next", {}).get("url")
        page += 1

    logging.info(f"共获取到 {len(repos)} 个星标项目")
    return repos
# -----------------------------------------------------
# 🧩 获取仓库最新 Release（美化显示用）
# -----------------------------------------------------
def get_latest_release(session, full_name):
    url = f"https://api.github.com/repos/{full_name}/releases/latest"
    try:
        resp = session.get(url, timeout=10)

        if resp.status_code == 404:
            return None  # 无 Release

        if resp.status_code != 200:
            logging.warning(f"[Release] 获取失败 {full_name} - {resp.status_code}")
            return None

        data = resp.json()
        return {
            "tag": data.get("tag_name"),
            "url": data.get("html_url"),
            "published": format_date(data.get("published_at"))
        }
    except Exception as e:
        logging.warning(f"[Release] 获取出错 {full_name} - {e}")
        return None


# -----------------------------------------------------
# ❗️ 分类规则（可扩展）
# -----------------------------------------------------
CATEGORY_MAP = {
    "AI": {
        "机器学习": ["pytorch", "tensorflow", "ml", "neural", "deep learning"],
        "自然语言处理": ["nlp", "transformer", "bert", "gpt", "huggingface", "llm"]
    },
    "Web 开发": {
        "前端": ["react", "vue", "vite", "svelte", "webpack", "frontend"],
        "后端": ["api", "backend", "fastapi", "django", "flask", "node", "express"]
    },
    "DevOps & 工具": {
        "CI/CD": ["github actions", "ci", "cd", "pipeline", "docker", "kubernetes"],
        "效率工具": ["cli", "utils", "helper", "plugin", "extension"]
    },
    "脚本 / 自动化": {
        "脚本 / 自动化": ["script", "automation", "crawler", "scraper", "bot"]
    },
    "学习资料": {
        "学习资料": ["awesome", "tutorial", "guide", "learning"]
    },
    "其他": {
        "其他": []
    }
}

# 转小写
for g, subs in CATEGORY_MAP.items():
    for s, kws in subs.items():
        subs[s] = [k.lower() for k in kws]


# -----------------------------------------------------
# 🧠 混合分类（topics → keywords → fallback）
# -----------------------------------------------------
def categorize_repos_mixed(repos):
    categorized = defaultdict(lambda: defaultdict(list))

    # 加载人工分类 overrides.json（如果存在）
    overrides = {}
    if os.path.exists("overrides.json"):
        try:
            with open("overrides.json", "r", encoding="utf-8") as f:
                overrides = json.load(f)
            logging.info(f"加载了 {len(overrides)} 条人工分类 overrides")
        except Exception as e:
            logging.warning(f"加载 overrides.json 失败: {e}")

    for repo in repos:
        full_name = repo.get("full_name", "")
        # 检查人工 overrides
        if full_name in overrides:
            ov = overrides[full_name]
            category = ov.get("category", "其他")
            subcategory = ov.get("subcategory", "其他")
            categorized[category][subcategory].append(repo)
            continue

        name = (repo.get("name") or "").lower()
        full = full_name.lower()
        desc = (repo.get("description") or "").lower()
        topics = [t.lower() for t in repo.get("topics", []) if isinstance(t, str)]
        text = " ".join([name, full, desc] + topics)

        matched = False

        # 1）先用 topics 匹配
        for g, subs in CATEGORY_MAP.items():
            for s, kws in subs.items():
                if any(k in topics for k in kws):
                    categorized[g][s].append(repo)
                    matched = True
                    break
            if matched:
                break

        if matched:
            continue

        # 2）再用描述/名称模糊匹配
        for g, subs in CATEGORY_MAP.items():
            for s, kws in subs.items():
                if any(k in text for k in kws):
                    categorized[g][s].append(repo)
                    matched = True
                    break
            if matched:
                break

        # 3）兜底放到“其他”
        if not matched:
            categorized["其他"]["其他"].append(repo)

    # 排序：按分类数量降序，但“其他”放到最后
    other = categorized.pop("其他", None)
    sorted_cats = sorted(
        categorized.items(),
        key=lambda x: sum(len(lst) for lst in x[1].values()),
        reverse=True
    )
    if other:
        sorted_cats.append(("其他", other))

    result = {}
    for g, subs in sorted_cats:
        sorted_subs = dict(sorted(subs.items(), key=lambda x: len(x[1]), reverse=True))
        result[g] = sorted_subs

    return result
# -----------------------------
# 🔧 日期格式
# -----------------------------
def format_date(s):
    if not s:
        return "N/A"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except:
        return s.split("T")[0]


# -----------------------------
# 📝 生成 Markdown（M3 风格）
# -----------------------------
def generate_markdown(repos, categorized, output="starred.md"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(output, "w", encoding="utf-8") as f:
        f.write('<a id="top"></a>\n\n')
        f.write("# 我的 GitHub 星标项目整理 ✨\n\n")
        f.write(f"> **最后更新**：{now}\n")
        f.write(f"> **总项目数**：{len(repos)}\n\n")

        # 统计表
        f.write("## 📊 分类统计\n\n")
        f.write("| 分类 | 子分类 | 项目数 |\n|------|--------|--------|\n")
        for g, subs in categorized.items():
            cnt = sum(len(s) for s in subs.values())
            sample = ", ".join([f"{k}({len(v)})" for k, v in list(subs.items())[:3]])
            f.write(f"| {g} | {sample} | {cnt} |\n")

        # 目录
        f.write("\n<details><summary>📂 目录</summary>\n\n")
        for g, subs in categorized.items():
            f.write(f"### {g}\n")
            for s in subs.keys():
                anchor = s.replace(" ", "").replace("/", "")
                f.write(f"- [{s}](#{anchor})\n")
            f.write("\n")
        f.write("</details>\n\n")

        # 分类内容
        for g, subs in categorized.items():
            f.write(f"## {g}\n\n")
            for s, items in subs.items():
                anchor = s.replace(" ", "").replace("/", "")
                f.write(f"### {s}\n\n")

                for repo in items:
                    full = repo.get("full_name", "")
                    url = repo.get("html_url", "")
                    desc = (repo.get("description") or "无描述").strip()

                    stars = repo.get("stargazers_count", 0)
                    forks = repo.get("forks_count", 0)
                    updated = format_date(repo.get("updated_at"))

                    release = repo.get("_latest_release")
                    if release:
                        rel_text = f"📦 最新版本：[{release['tag']}]({release['url']})（{release['published']}）"
                    else:
                        rel_text = "📦 无 Release"

                    f.write(f"#### [{full}]({url})\n")
                    f.write(f"> {desc}\n\n")
                    f.write(f"- ⭐ {stars} · 🍴 {forks} · 📅 {updated}\n")
                    f.write(f"- {rel_text}\n\n")

        f.write("\n---\n[回到顶部](#top)\n")

    logging.info(f"Markdown 生成完成：{output}")
# -----------------------------
# 🌐 HTML（保持现有卡片知识库风 + Release 显示）
# -----------------------------
def generate_html(repos, categorized, output="docs/index.html"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs("docs", exist_ok=True)

    html = []
    html.append(f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>GitHub 星标项目（功能分类）</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{
    background:#fafafa;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial;
    max-width:1100px;margin:auto;padding:24px;
    line-height:1.6;
}}
.card {{
    background:#ffffff;
    padding:14px;border-radius:8px;
    margin-bottom:10px;
    box-shadow:0 1px 3px rgba(0,0,0,0.06);
}}
a {{ color:#0366d6;text-decoration:none; }}
.meta {{ color:#666;font-size:13px;margin-top:6px; }}
.section-title {{ font-size:20px;margin-top:28px;margin-bottom:10px; }}
.subsection {{ font-size:16px;margin-top:12px;margin-bottom:4px; }}
</style>
</head>
<body>
<h1>🌟 我的 GitHub 星标项目（按功能分类）</h1>
<div class="meta">更新时间：{now} · 共 {len(repos)} 个项目</div>
""")

    for g, subs in categorized.items():
        html.append(f'<div class="section-title">{g}</div>')
        for s, items in subs.items():
            html.append(f'<div class="subsection">{s}（{len(items)}）</div>')

            for repo in items:
                name = repo.get("full_name")
                url = repo.get("html_url")
                desc = repo.get("description") or "无描述"
                stars = repo.get("stargazers_count", 0)
                forks = repo.get("forks_count", 0)
                updated = format_date(repo.get("updated_at"))

                release = repo.get("_latest_release")
                if release:
                    rel_html = f' · 📦 <a href="{release["url"]}" target="_blank">{release["tag"]}</a>（{release["published"]}）'
                else:
                    rel_html = " · 📦 无"

                html.append(f"""
<div class="card">
  <a href="{url}" target="_blank">{name}</a>
  <div>{desc}</div>
  <div class="meta">⭐ {stars} · 🍴 {forks} · 📅 {updated}{rel_html}</div>
</div>
""")

    html.append("</body></html>")

    with open(output, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

    logging.info(f"HTML 生成完成：{output}")


# -----------------------------
# 🚀 主流程
# -----------------------------
def main():
    username, token = get_config_interactive()
    session = build_session(token)

    repos = get_starred_repos(session, username)

    # 获取 Release
    logging.info("正在获取各仓库 Release 信息…")
    for repo in repos:
        repo["_latest_release"] = get_latest_release(session, repo.get("full_name"))

    categorized = categorize_repos_mixed(repos)

    generate_markdown(repos, categorized, "starred.md")
    generate_html(repos, categorized, "docs/index.html")

    logging.info("全部生成完成！")


if __name__ == "__main__":
    main()