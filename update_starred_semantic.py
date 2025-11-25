#!/usr/bin/env python3
# update_starred_semantic.py
"""
Enhanced starred generator with semantic clustering + repo cards (release / language / license).
Fallback embedding strategies:
  1) OpenAI Embeddings (if OPENAI_API_KEY in env)
  2) sentence-transformers (if installed)
  3) TF-IDF vectors (scikit-learn) fallback

Outputs:
  - starred.md (Notion-like sections by semantic clusters)
  - README.md
  - docs/index.html (cards)
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import math
import re

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------- Config helpers ----------
def load_config(path="config.json"):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        raise FileNotFoundError(f"config not found: {p}")
    return json.load(open(p, "r", encoding="utf-8"))

def get_env_token():
    return os.environ.get("STAR_TOKEN") or os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")

# ---------- GitHub API ----------
def gh_get(url, token):
    headers = {
        "Accept": "application/vnd.github.mercy-preview+json"
    }
    if token:
        headers["Authorization"] = f"token {token}"
    r = requests.get(url, headers=headers)
    if r.status_code == 403 and 'rate limit' in r.text.lower():
        raise Exception("GitHub rate limited. Consider using a token.")
    return r

def get_my_starred(token, per_page=100):
    url = f"https://api.github.com/user/starred?per_page={per_page}"
    repos = []
    while url:
        r = gh_get(url, token)
        if r.status_code != 200:
            raise Exception(f"GitHub API error {r.status_code}: {r.text}")
        repos.extend(r.json())
        url = r.links.get('next', {}).get('url')
    return repos

def get_latest_release(full_name, token):
    url = f"https://api.github.com/repos/{full_name}/releases/latest"
    r = gh_get(url, token)
    if r.status_code == 200:
        data = r.json()
        return {"tag_name": data.get("tag_name"), "published_at": data.get("published_at")}
    # 404 => no release
    return None

# ---------- Text / features for embedding ----------
def repo_text_for_embedding(repo):
    parts = []
    parts.append(repo.get("full_name",""))
    parts.append(repo.get("description","") or "")
    topics = repo.get("topics") or []
    parts.append(" ".join(topics))
    lang = repo.get("language") or ""
    parts.append(lang)
    return " | ".join([p for p in parts if p]).strip()

# ---------- Embedding helpers ----------
def use_openai_embeddings(texts):
    # requires env OPENAI_API_KEY
    import os, time, json
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    model = "text-embedding-3-small"  # small, adjust if you prefer different
    embeddings = []
    # batch for safety
    batch = []
    for t in texts:
        batch.append(t)
    body = {"model": model, "input": batch}
    r = requests.post(url, headers=headers, json=body)
    if r.status_code != 200:
        raise Exception(f"OpenAI embeddings error {r.status_code}: {r.text}")
    res = r.json()
    for item in res["data"]:
        embeddings.append(item["embedding"])
    return embeddings

def use_sentence_transformers(texts, model_name="all-MiniLM-L6-v2"):
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        raise RuntimeError("sentence-transformers not installed")
    model = SentenceTransformer(model_name)
    embs = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return embs.tolist()

def use_tfidf_vectors(texts):
    # fallback: TF-IDF + TruncatedSVD to make dense
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    vec = TfidfVectorizer(max_features=2000, stop_words="english")
    X = vec.fit_transform(texts)
    # reduce to 64 dimensions
    svd = TruncatedSVD(n_components=min(64, X.shape[1]-1 if X.shape[1]>1 else 1))
    Xred = svd.fit_transform(X)
    return Xred.tolist()

def compute_embeddings(texts):
    # try OpenAI, then sentence-transformers, then TF-IDF
    if os.environ.get("OPENAI_API_KEY"):
        try:
            print("Using OpenAI embeddings...")
            return use_openai_embeddings(texts)
        except Exception as e:
            print("OpenAI embeddings failed:", e)
    try:
        print("Trying sentence-transformers...")
        return use_sentence_transformers(texts)
    except Exception as e:
        print("sentence-transformers not available or failed:", e)
    print("Falling back to TF-IDF vectors.")
    return use_tfidf_vectors(texts)

# ---------- Clustering ----------
def determine_n_clusters(n_repos):
    # heuristic: sqrt(n) capped
    if n_repos <= 6:
        return max(2, n_repos)
    k = int(math.sqrt(n_repos) + 0.5)
    return max(3, min(12, k))

def cluster_embeddings(embeddings, n_clusters):
    # simple KMeans clustering (works for small-medium n)
    from sklearn.cluster import KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)
    return labels

def extract_cluster_labels(repos_texts, labels):
    # generate a human-readable label for each cluster using top keywords (TF-IDF)
    cluster_texts = defaultdict(list)
    for t, lab in zip(repos_texts, labels):
        cluster_texts[lab].append(t)
    cluster_labels = {}
    for lab, texts in cluster_texts.items():
        full = " ".join(texts)
        # simple keyword extraction: count words not in stoplist
        words = re.findall(r"[a-zA-Z0-9\-]+", full.lower())
        stop = set(["the","and","for","with","a","of","in","to","by","on","is","an","tool","library","project"])
        cnt = Counter(w for w in words if w not in stop and len(w)>2)
        top = [w for w,_ in cnt.most_common(3)]
        label = " / ".join(top) if top else f"Cluster {lab+1}"
        cluster_labels[lab] = label.title()
    return cluster_labels

# ---------- Star rating ----------
def star_rating(n):
    if n >= 5000:
        return "★★★★★"
    if n >= 1000:
        return "★★★★"
    if n >= 300:
        return "★★★"
    if n >= 50:
        return "★★"
    return "★"

# ---------- Renderers ----------
def render_repo_card_md(r, release):
    name = r.get("full_name")
    url = r.get("html_url")
    desc = (r.get("description") or "").replace("|"," ")
    if len(desc) > 140:
        desc = desc[:137] + "..."
    lang = r.get("language") or "—"
    license = (r.get("license") or {}).get("name") if r.get("license") else "—"
    stars = r.get("stargazers_count", 0)
    pushed = r.get("pushed_at","")[:10] or r.get("updated_at","")[:10]
    release_str = ""
    if release:
        release_str = f"{release.get('tag_name')} ({release.get('published_at', '')[:10]})"
    return f"| [{name}]({url}) | {desc} | {lang} | {license} | {star_rating(stars)} | {stars} | {release_str} | {pushed} |"

def render_table_header():
    return "| 项目 | 描述 | 语言 | License | 星级 | Stars | Latest Release | 最后活跃 |\n|------|------|------|---------|:----:|------:|--------------|----------|"

def render_section_md(cluster_label, items, token):
    if not items:
        return f"## {cluster_label}\n\n（暂无项目）\n"
    lines = [f"## {cluster_label}\n<a id=\"{cluster_label.lower().replace(' ','-')}\"></a>\n\n> 本类仓库数量：{len(items)}\n\n"]
    lines.append(render_table_header())
    # sort by stars desc
    items_sorted = sorted(items, key=lambda r: r.get("stargazers_count",0), reverse=True)
    for r in items_sorted:
        rel = get_latest_release(r.get("full_name"), token)
        lines.append(render_repo_card_md(r, rel))
    lines.append("\n")
    return "\n".join(lines)

def render_full_md(template_text, index_md, sections_md, total, last_update):
    out = template_text.replace("<!-- CATEGORY_INDEX -->", index_md)
    out = out.replace("<!-- GENERATED_SECTIONS -->", sections_md)
    out = out.replace("{{last_update}}", last_update)
    out = out.replace("{{total}}", str(total))
    return out

# ---------- HTML page generator (cards, Notion-like) ----------
def generate_docs_html_from_md(md_text, title="Starred Repos"):
    # Basic conversion: we keep markdown blocks and wrap in a nice container.
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<style>
body{{font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial; background:#f6f7f8; color:#111; padding:36px}}
.container{{max-width:1100px;margin:0 auto;background:#fff;padding:28px;border-radius:10px;box-shadow:0 8px 30px rgba(10,10,10,0.06)}}
.header{{display:flex;justify-content:space-between;align-items:center}}
.meta{{color:#667085;font-size:13px}}
.card-table{{width:100%;border-collapse:collapse;margin-top:12px}}
.card-table th, .card-table td{{padding:10px;border-bottom:1px solid #eee;text-align:left}}
.card{{border-radius:8px;padding:12px;background:#fafafa;margin-bottom:10px;box-shadow:0 1px 0 rgba(0,0,0,0.03)}}
a{{color:#2563eb}}
.top{{position:fixed;right:20px;bottom:20px}}
.top a{{background:#111;color:#fff;padding:8px 10px;border-radius:6px}}
kbd{{
  background:#111;color:#fff;padding:2px 6px;border-radius:4px;font-size:12px;
}}
</style>
</head><body>
<div class="container">
  <div class="header">
    <h1>{title}</h1>
    <div class="meta">自动生成 • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
  </div>
  <div id="content">
  <pre style="white-space:pre-wrap;font-family:inherit">{md_text}</pre>
  </div>
</div>
<div class="top"><a href="#top">Top</a></div>
</body></html>"""
    return html

# ---------- Main ----------
def main():
    cfg = load_config()
    token = get_env_token()
    if not token:
        print("ERROR: STAR_TOKEN / GH_PAT / GITHUB_TOKEN not found in env. Set it and re-run.")
        sys.exit(1)

    repos = get_my_starred(token, per_page=cfg.get("per_page",100))
    # filter blacklist
    blacklist = set(cfg.get("blacklist",[]))
    repos = [r for r in repos if r.get("full_name") not in blacklist]

    # prepare texts
    texts = [repo_text_for_embedding(r) for r in repos]
    if not texts:
        print("No starred repos found.")
        return

    # compute embeddings (with intelligent fallback)
    embeddings = compute_embeddings(texts)

    # clusters
    n_clusters = determine_n_clusters(len(repos))
    print(f"Clustering into ~{n_clusters} clusters (repos={len(repos)})")
    labels = cluster_embeddings(embeddings, n_clusters)

    # Build cluster buckets
    buckets = defaultdict(list)
    for repo, lab in zip(repos, labels):
        buckets[lab].append(repo)

    # derive friendly labels
    cluster_labels = extract_cluster_labels(texts, labels)

    # Build index md and sections
    # Order clusters by size
    ordered = sorted(buckets.keys(), key=lambda k: -len(buckets[k]))
    index_lines = []
    sections = []
    for lab in ordered:
        label = cluster_labels.get(lab, f"Cluster {lab+1}")
        anchor = label.lower().replace(" ", "-")
        index_lines.append(f"- [{label}](#{anchor})")
        sections.append(render_section_md(label, buckets[lab], token))

    index_md = "\n".join(index_lines) + "\n"
    sections_md = "\n".join(sections)
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(repos)

    # read template
    tpl_path = os.path.join(ROOT, cfg.get("template_file","star_template.md"))
    if not os.path.exists(tpl_path):
        print("Template missing; creating minimal template.")
        open(tpl_path,"w",encoding="utf-8").write("<a id=\"top\"></a>\n# Starred\n\n<!-- CATEGORY_INDEX -->\n\n<!-- GENERATED_SECTIONS -->\n")
    tpl = open(tpl_path,"r",encoding="utf-8").read()
    out_md = render_full_md(tpl, index_md, sections_md, total, last_update)

    # Archived: simple policy via config threshold
    archived_lines = []
    if cfg.get("auto_archive_if_inactive", True):
        cutoff = datetime.utcnow() - timedelta(days=cfg.get("archive_threshold_days",365))
        archived = []
        active = []
        for r in repos:
            pushed = r.get("pushed_at") or r.get("updated_at") or ""
            try:
                pushed_dt = datetime.strptime(pushed[:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                pushed_dt = None
            if pushed_dt and pushed_dt < cutoff:
                archived.append(r)
            else:
                active.append(r)
        if archived:
            arch_table = ["\n\n## Archived\n", "| 项目 | 描述 | Stars | 最后活跃 |", "|------|------:|------:|----------|"]
            for r in archived:
                arch_table.append(f"| [{r['full_name']}]({r['html_url']}) | {(r.get('description') or '').replace('|',' ')} | {r.get('stargazers_count',0)} | {r.get('pushed_at','')[:10]} |")
            out_md += "\n".join(arch_table) + "\n"

    # write outputs
    with open(os.path.join(ROOT, cfg.get("output_markdown","starred.md")), "w", encoding="utf-8") as f:
        f.write(out_md)
    if cfg.get("generate_readme", True):
        readme = f"# {cfg.get('author','')} 的 GitHub 星标仓库\n\n自动生成：最后更新 {last_update}\n\n查看 [starred.md](./{cfg.get('output_markdown','starred.md')}) 或 GitHub Pages。\n"
        open(os.path.join(ROOT, cfg.get("output_readme","README.md")), "w", encoding="utf-8").write(readme)

    if cfg.get("generate_pages", True):
        md_for_html = out_md  # we keep markdown inside a <pre> wrapper for simplicity
        html = generate_docs_html_from_md(md_for_html, title=f"{cfg.get('author','')}'s Starred Repos")
        docs_path = os.path.join(ROOT, cfg.get("pages_output","docs/index.html"))
        os.makedirs(os.path.dirname(docs_path), exist_ok=True)
        open(docs_path,"w",encoding="utf-8").write(html)

    print("Done. Generated:", cfg.get("output_markdown","starred.md"))
    if cfg.get("generate_pages", True):
        print("Pages:", cfg.get("pages_output","docs/index.html"))

if __name__ == "__main__":
    main()
