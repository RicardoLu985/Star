# ============================================================
# update_starred_semantic.py
# 全功能版（2025）：自动分类 / overrides / release / 现代HTML / 搜索
# ============================================================

import os, sys, json, requests, logging
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

MANUAL_USERNAME = ""
MANUAL_TOKEN = ""

# ------------------ 配置读取 ------------------
def get_config():
    u = MANUAL_USERNAME.strip() or os.getenv("STAR_USERNAME")
    t = MANUAL_TOKEN.strip() or os.getenv("STAR_TOKEN")
    if not u or not t:
        raise ValueError("缺少 STAR_USERNAME / STAR_TOKEN 或手动填写 MANUAL_USERNAME/TOKEN。")
    return u, t

def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "starred-exporter"
    })
    return s

# ------------------ GitHub API ------------------
def get_starred_repos(session, username):
    url = f"https://api.github.com/users/{username}/starred"
    repos, page = [], 1
    while url:
        r = session.get(url, timeout=15)
        if r.status_code == 403:
            raise Exception("API 403，可能到达 Rate Limit")
        if r.status_code != 200:
            raise Exception(f"API 错误: {r.status_code} {r.text}")
        data = r.json()
        if not data:
            break
        repos.extend(data)
        url = r.links.get("next", {}).get("url")
        page += 1
    return repos

def format_date(s):
    if not s: return "N/A"
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%Y-%m-%d")
    except: return s[:10]

def get_latest_release(session, full):
    url = f"https://api.github.com/repos/{full}/releases/latest"
    r = session.get(url, timeout=10)
    if r.status_code == 404: return None
    if r.status_code != 200: return None
    d = r.json()
    return {
        "tag": d.get("tag_name"),
        "url": d.get("html_url"),
        "published": format_date(d.get("published_at"))
    }

# ------------------ overrides ------------------
def load_overrides():
    if not os.path.exists("overrides.json"):
        return {"repos": {}}
    try:
        d = json.load(open("overrides.json","r",encoding="utf-8"))
        return {"repos": d.get("repos", {})}
    except:
        return {"repos": {}}

# ------------------ 分类规则 ------------------
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
    for s,k in subs.items():
        subs[s] = [x.lower() for x in k]

# ------------------ 智能分类（支持 overrides）------------------
def categorize_repos(repos):
    overrides = load_overrides()["repos"]
    categorized = defaultdict(lambda: defaultdict(list))

    for repo in repos:
        full = (repo.get("full_name") or "").strip()
        name = (repo.get("name") or "").lower()
        desc = (repo.get("description") or "").lower()
        topics = [t.lower() for t in repo.get("topics", [])]
        blob = " ".join([full.lower(), name, desc] + topics)

        # 1) 精确覆盖
        if full in overrides:
            oc = overrides[full]["category"]
            osub = overrides[full]["subcategory"]
            categorized[oc][osub].append(repo)
            continue

        # 2) topics 匹配
        matched = False
        if topics:
            tstr = " ".join(topics)
            for g,subs in CATEGORY_MAP.items():
                for s,kws in subs.items():
                    if any(k in tstr for k in kws):
                        categorized[g][s].append(repo)
                        matched = True
                        break
                if matched: break
            if matched: continue

        # 3) 模糊匹配
        for g,subs in CATEGORY_MAP.items():
            for s,kws in subs.items():
                if any(k in blob for k in kws):
                    categorized[g][s].append(repo)
                    matched = True
                    break
            if matched: break

        # 4) 兜底
        if not matched:
            categorized["其他"]["其他"].append(repo)

    # --- “其他” 永远放最后 ---
    ordered = {}
    for g in sorted(categorized.keys(), key=lambda x: (x=="其他", -sum(len(v) for v in categorized[x].values()))):
        ordered[g] = dict(sorted(
            categorized[g].items(),
            key=lambda x: len(x[1]),
            reverse=True
        ))
    return ordered

# ------------------ Markdown 输出 ------------------
def safe_text(s): return s.replace("\n"," ").replace("|"," ") if s else ""

def generate_markdown(repos, categorized, output="starred.md"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)

    w = open(output,"w",encoding="utf-8")
    w.write(f"# 我的 GitHub 星标项目 ✨\n\n")
    w.write(f"> 自动生成 · 最后更新：{now} · 总项目：{total}\n\n")

    w.write("## 📊 分类统计\n\n")
    w.write("| 分类 | 项目数 |\n|----|----:|\n")
    for g,subs in categorized.items():
        cnt = sum(len(v) for v in subs.values())
        w.write(f"| {g} | {cnt} |\n")
    w.write("\n")

    for g,subs in categorized.items():
        w.write(f"## {g}\n\n")
        for s,items in subs.items():
            w.write(f"### {s}\n\n")
            for r in sorted(items,key=lambda x:x.get("stargazers_count",0),reverse=True):
                full = r.get("full_name","")
                url = r.get("html_url","")
                desc = safe_text(r.get("description","无描述"))
                stars = r.get("stargazers_count",0)
                forks = r.get("forks_count",0)
                updated = format_date(r.get("updated_at"))
                rel = r.get("_latest_release")
                rel_line = f"📦 最新版本：[{rel['tag']}]({rel['url']})（{rel['published']}）" if rel else "📦 无 Release"

                w.write(f"#### [{full}]({url})\n")
                w.write(f"> {desc}\n\n")
                w.write(f"- ⭐ {stars} · 🍴 {forks} · 📅 {updated}\n")
                w.write(f"- {rel_line}\n\n")
    w.close()
    logging.info("Markdown 生成完成")

# ------------------ HTML 输出（现代 UI + 搜索 + 动画）------------------
def generate_html(repos, categorized, output="docs/index.html"):
    os.makedirs("docs",exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)

    css = """
:root{--bg:#f7f7f9;--fg:#222;--card:#fff;--border:#e5e7eb;--pr:#2563eb;--sec:#6b7280;}
@media(prefers-color-scheme:dark){
:root{--bg:#1e1e20;--fg:#eee;--card:#2b2b2f;--border:#3b3b44;--sec:#aaa;}}
body{background:var(--bg);color:var(--fg);font-family:-apple-system,Segoe UI,Roboto;padding:20px;max-width:1100px;margin:auto;}
h1{text-align:center;margin-bottom:5px;font-size:2rem;}
.info{text-align:center;color:var(--sec);margin-bottom:25px;}
.search-box{position:sticky;top:0;background:var(--bg);padding:10px 0;margin-bottom:15px;}
.search-input{width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:8px;font-size:1rem;}
.group-title{font-size:1.6rem;margin-top:40px;}
.sub-title{font-size:1.25rem;margin-top:20px;}
.repo{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px 20px;margin:14px 0;transition:.2s;}
.repo:hover{background:#efefef22;}
.repo a{color:var(--pr);font-weight:bold;text-decoration:none;}
.repo-desc{color:var(--sec);margin:6px 0 8px;}
.repo-meta{color:var(--sec);font-size:.9rem;}
"""

    js = """
function search(){
  let q=document.getElementById("search").value.toLowerCase();
  document.querySelectorAll(".repo").forEach(el=>{
    let txt=el.dataset.full.toLowerCase()+" "+el.dataset.desc.toLowerCase();
    el.style.display=txt.includes(q)?"block":"none";
  });
}
"""

    html = []
    html.append(f"<!DOCTYPE html><html><head><meta charset='UTF-8'><style>{css}</style>")
    html.append(f"<script>{js}</script></head><body>")
    html.append(f"<h1>🌟 GitHub 星标项目</h1>")
    html.append(f"<div class='info'>最后更新：{now} · 总项目：{total}</div>")

    # 搜索框
    html.append("<div class='search-box'><input id='search' class='search-input' placeholder='搜索...' oninput='search()'/></div>")

    # 分类内容
    for g,subs in categorized.items():
        html.append(f"<div class='group-title'>{g}</div>")
        for s,items in subs.items():
            html.append(f"<div class='sub-title'>{s}</div>")
            for r in sorted(items,key=lambda x:x.get("stargazers_count",0),reverse=True):
                full = r.get("full_name","")
                url = r.get("html_url","")
                desc = r.get("description","无描述")
                stars = r.get("stargazers_count",0)
                forks = r.get("forks_count",0)
                updated = format_date(r.get("updated_at"))
                rel = r.get("_latest_release")
                line = f"📦 最新版本：<a href='{rel['url']}' target='_blank'>{rel['tag']}</a>（{rel['published']}）" if rel else "📦 无 Release"

                html.append(
                    f"<div class='repo' data-full='{full}' data-desc='{desc}'>"
                    f"<div><a href='{url}' target='_blank'>{full}</a></div>"
                    f"<div class='repo-desc'>{desc}</div>"
                    f"<div class='repo-meta'>⭐ {stars} · 🍴 {forks} · 📅 {updated}<br>{line}</div>"
                    f"</div>"
                )

    html.append("</body></html>")
    open(output,"w",encoding="utf-8").write("".join(html))
    logging.info("HTML 生成完成")

# ------------------ main ------------------
def main():
    username,token=get_config()
    session=build_session(token)

    repos=get_starred_repos(session,username)

    # release
    for r in repos:
        full=r.get("full_name")
        r["_latest_release"]=get_latest_release(session,full)

    categorized = categorize_repos(repos)
    generate_markdown(repos,categorized,"starred.md")
    generate_html(repos,categorized,"docs/index.html")
    logging.info("全部完成。")

if __name__ == "__main__":
    main()
