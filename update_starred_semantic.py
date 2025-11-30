# ============================================================
# update_starred_semantic.py
# 全功能版（2025）：智能分类 / overrides / release / 现代HTML / M3 Markdown
# 去掉搜索功能 / 统计卡片美化 / Release 合并到同一行
# ============================================================

import os, json, requests, logging
from datetime import datetime
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

MANUAL_USERNAME = ""
MANUAL_TOKEN = ""

# --------------------- 配置 ---------------------
def get_config():
    u = MANUAL_USERNAME.strip() or os.getenv("STAR_USERNAME")
    t = MANUAL_TOKEN.strip() or os.getenv("STAR_TOKEN")
    if not u or not t:
        raise ValueError("缺少 STAR_USERNAME / STAR_TOKEN 或手动填写 MANUAL_USERNAME/TOKEN")
    return u, t

def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "starred-exporter"
    })
    return s

# --------------------- GitHub API ---------------------
def get_starred_repos(session, username):
    url = f"https://api.github.com/users/{username}/starred"
    repos = []
    while url:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            raise Exception(f"API 错误: {r.status_code} {r.text}")
        repos.extend(r.json())
        url = r.links.get("next", {}).get("url")
    return repos

def format_date(s):
    if not s: return "N/A"
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%Y-%m-%d")
    except:
        return s[:10]

def get_latest_release(session, full):
    url = f"https://api.github.com/repos/{full}/releases/latest"
    r = session.get(url, timeout=10)
    if r.status_code != 200: return None
    d = r.json()
    return {
        "tag": d.get("tag_name"),
        "url": d.get("html_url"),
        "published": format_date(d.get("published_at"))
    }

# --------------------- overrides ---------------------
def load_overrides():
    if not os.path.exists("overrides.json"):
        return {"repos": {}}
    try:
        data = json.load(open("overrides.json","r",encoding="utf-8"))
        return {"repos": data.get("repos", {})}
    except:
        return {"repos": {}}

# --------------------- 分类规则 ---------------------
CATEGORY_MAP = {
    "AI": {
        "机器学习": ["pytorch","tensorflow","ml","deep learning"],
        "自然语言处理": ["nlp","transformer","gpt","llm","huggingface"]
    },
    "Web 开发": {
        "前端": ["react","vue","vite","svelte","javascript","typescript"],
        "后端": ["fastapi","django","flask","node","express"]
    },
    "DevOps & 工具": {
        "CI/CD": ["docker","k8s","kubernetes","ci","cd","pipeline"],
        "效率工具": ["cli","plugin","utils"]
    },
    "脚本自动化": {
        "脚本/自动化": ["script","automation","bot","crawler"]
    },
    "学习资料": {
        "资料/教程": ["awesome","tutorial","guide","learning"]
    }
}

for g,subs in CATEGORY_MAP.items():
    for s,kws in subs.items():
        subs[s] = [x.lower() for x in kws]

# --------------------- 分类逻辑 ---------------------
def categorize_repos(repos):
    overrides = load_overrides()["repos"]
    cat = defaultdict(lambda: defaultdict(list))

    for r in repos:
        full = r.get("full_name","")
        desc = (r.get("description") or "").lower()
        name = (r.get("name") or "").lower()
        topics = [t.lower() for t in r.get("topics", [])]
        blob = f"{full.lower()} {name} {desc} {' '.join(topics)}"

        # overrides
        if full in overrides:
            g = overrides[full]["category"]
            s = overrides[full]["subcategory"]
            cat[g][s].append(r)
            continue

        matched = False

        # topics
        if topics:
            tstr = " ".join(topics)
            for g,subs in CATEGORY_MAP.items():
                for s,kws in subs.items():
                    if any(k in tstr for k in kws):
                        cat[g][s].append(r)
                        matched = True
                        break
                if matched: break
            if matched: continue

        # fuzzy match
        for g,subs in CATEGORY_MAP.items():
            for s,kws in subs.items():
                if any(k in blob for k in kws):
                    cat[g][s].append(r)
                    matched = True
                    break
            if matched: break

        if not matched:
            cat["其他"]["其他"].append(r)

    # 让“其他”永远最后
    ordered = {}
    groups = sorted(cat.keys(), key=lambda x: (x=="其他"))
    for g in groups:
        ordered[g] = dict(sorted(cat[g].items(), key=lambda x: len(x[1]), reverse=True))
    return ordered

# --------------------- Markdown ---------------------
def safe(s):
    return s.replace("\n"," ").replace("|"," ") if s else ""

def generate_markdown(repos, categorized, output="starred.md"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)
    w = open(output,"w",encoding="utf-8")

    w.write(f"# 🌟 我的 GitHub 星标项目\n\n")
    w.write(f"> 最后更新：{now} · 总项目数：{total}\n\n")

    # 现代 M3 风格卡片统计
    w.write("## 分类统计\n\n")
    for g,subs in categorized.items():
        count = sum(len(v) for v in subs.values())
        w.write(f"### {g} — `{count}` 项\n\n")

    # 内容
    for g,subs in categorized.items():
        w.write(f"\n## {g}\n")
        for s,items in subs.items():
            w.write(f"\n### {s}\n\n")
            for r in sorted(items,key=lambda x:x.get("stargazers_count",0),reverse=True):
                full = r.get("full_name","")
                url = r.get("html_url","")
                desc = safe(r.get("description","无描述"))
                stars = r.get("stargazers_count",0)
                forks = r.get("forks_count",0)
                updated = format_date(r.get("updated_at"))
                rel = r.get("_latest_release")

                rel_txt = (
                    f"📦 [{rel['tag']}]({rel['url']})"
                    if rel else "📦 无 Release"
                )

                # Release 合并到同一行
                meta = f"⭐ {stars} · 🍴 {forks} · 📅 {updated} · {rel_txt}"

                w.write(f"#### [{full}]({url})\n")
                w.write(f"> {desc}\n\n")
                w.write(f"{meta}\n\n")

    w.close()
    logging.info("Markdown 完成")


# --------------------- HTML ---------------------
def generate_html(repos, categorized, output="docs/index.html"):
    os.makedirs("docs", exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)

    css = """
:root{--bg:#fafafa;--fg:#222;--card:#fff;--border:#e5e7eb;--sec:#6b7280;--pr:#2563eb;}
@media(prefers-color-scheme:dark){
:root{--bg:#1f1f20;--fg:#eee;--card:#26272b;--border:#3b3b44;--sec:#aaa;}}
body{background:var(--bg);color:var(--fg);font-family:-apple-system,Segoe UI,Roboto;margin:0;padding:20px;max-width:1100px;margin:auto;}
h1{text-align:center;margin:0;margin-bottom:6px;}
.info{text-align:center;color:var(--sec);margin-bottom:30px;}
.group{margin-top:40px;font-size:1.6rem;}
.sub{margin-top:20px;font-size:1.25rem;}
.repo{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 20px;margin:12px 0;}
.repo a{color:var(--pr);font-weight:bold;text-decoration:none;}
.desc{color:var(--sec);margin:6px 0 10px;}
.meta{color:var(--sec);font-size:.9rem;}
.stat-card{padding:14px 16px;background:var(--card);border:1px solid var(--border);
border-radius:12px;margin:10px 0;font-size:1.05rem;}
"""

    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='UTF-8'>")
    html.append(f"<style>{css}</style></head><body>")

    html.append(f"<h1>🌟 GitHub 星标项目</h1>")
    html.append(f"<div class='info'>最后更新：{now} · 总项目数：{total}</div>")

    # ---- 统计卡片（现代风） ----
    html.append("<div>")
    for g,subs in categorized.items():
        count = sum(len(v) for v in subs.values())
        html.append(f"<div class='stat-card'>{g} — {count} 项</div>")
    html.append("</div>")

    # ---- 内容部分 ----
    for g,subs in categorized.items():
        html.append(f"<div class='group'>{g}</div>")
        for s,items in subs.items():
            html.append(f"<div class='sub'>{s}</div>")
            for r in sorted(items,key=lambda x:x.get("stargazers_count",0),reverse=True):
                full = r.get("full_name","")
                url = r.get("html_url","")
                desc = r.get("description","无描述")
                stars = r.get("stargazers_count",0)
                forks = r.get("forks_count",0)
                updated = format_date(r.get("updated_at"))
                rel = r.get("_latest_release")

                rel_txt = (
                    f"📦 <a href='{rel['url']}' target='_blank'>{rel['tag']}</a>"
                    if rel else "📦 无 Release"
                )

                meta = f"⭐ {stars} · 🍴 {forks} · 📅 {updated} · {rel_txt}"

                html.append(
                    f"<div class='repo'>"
                    f"<div><a href='{url}' target='_blank'>{full}</a></div>"
                    f"<div class='desc'>{desc}</div>"
                    f"<div class='meta'>{meta}</div>"
                    f"</div>"
                )

    html.append("</body></html>")
    open(output,"w",encoding="utf-8").write("".join(html))
    logging.info("HTML 生成完成")

# --------------------- main ---------------------
def main():
    username, token = get_config()
    session = build_session(token)

    repos = get_starred_repos(session, username)

    for r in repos:
        full = r.get("full_name")
        r["_latest_release"] = get_latest_release(session, full)

    categorized = categorize_repos(repos)

    generate_markdown(repos, categorized, "starred.md")
    generate_html(repos, categorized, "docs/index.html")

    logging.info("全部完成")

if __name__ == "__main__":
    main()
