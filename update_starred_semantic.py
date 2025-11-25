# update_starred_semantic.py
import os
import requests
from datetime import datetime

# 确保 docs 目录存在
os.makedirs('docs', exist_ok=True)

STAR_USERNAME = os.getenv("STAR_USERNAME")
STAR_TOKEN = os.getenv("STAR_TOKEN")

if not STAR_USERNAME:
    raise ValueError("STAR_USERNAME is not set")
if not STAR_TOKEN:
    raise ValueError("STAR_TOKEN is not set")

# 获取 starred 仓库
def get_starred_repos(username, token):
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/users/{username}/starred'
    repos = []
    while url:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            raise Exception(f"API error: {r.text}")
        repos.extend(r.json())
        url = r.links.get('next', {}).get('url')
    return repos

# 生成 Markdown
def generate_markdown(repos, output_file='starred.md'):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('# 我的 GitHub 星标项目\n\n')
        f.write(f'> 更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'> 总项目数: {len(repos)}\n\n')
        for repo in repos:
            f.write(f'- [{repo["full_name"]}]({repo["html_url"]})\n')

# 生成 HTML（放在 docs/ 下，用于 GitHub Pages）
def generate_html():
    with open('docs/index.html', 'w', encoding='utf-8') as f:
        f.write("""
<!DOCTYPE html>
<html>
<head>
<title>GitHub Starred</title>
<meta charset="UTF-8">
<style>
body { font-family: Arial; padding: 20px; background: #f5f5f5; }
h1 { color: #333; }
</style>
</head>
<body>
<h1>GitHub Starred Projects</h1>
<p>此页面由 workflow 自动生成。</p>
</body>
</html>
""")

if __name__ == "__main__":
    repos = get_starred_repos(STAR_USERNAME, STAR_TOKEN)
    generate_markdown(repos)
    generate_html()
