import os
import requests
from datetime import datetime
import traceback

def get_starred_repos(username, token):
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/users/{username}/starred'
    repos = []
    try:
        while url:
            response = requests.get(url, headers=headers)
            if response.status_code == 404:
                raise Exception(f"User not found or invalid token: {response.text}")
            elif response.status_code != 200:
                raise Exception(f"API error: {response.status_code} - {response.text}")
            repos.extend(response.json())
            url = response.links.get('next', {}).get('url')
    except Exception as e:
        print(f"[ERROR] Failed to fetch starred repos: {e}")
        raise
    return repos

def generate_markdown(repos, output_file='starred.md'):
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('# 我的 GitHub 星标项目\n\n')
            f.write(f'> 更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'> 总项目数: {len(repos)}\n\n')
            f.write('| 项目名 | 描述 | 星标数 | 最后更新 |\n')
            f.write('|--------|------|--------|----------|\n')
            for repo in sorted(repos, key=lambda r: r['stargazers_count'], reverse=True):
                name = f'[{repo["full_name"]}]({repo["html_url"]})'
                desc = (repo['description'][:100] + '...') if repo['description'] else ''
                stars = repo['stargazers_count']
                updated = repo['updated_at'][:10]
                f.write(f'| {name} | {desc} | {stars} | {updated} |\n')
        print(f"[INFO] Markdown 文件生成完成: {output_file}")
    except Exception as e:
        print(f"[ERROR] Failed to generate markdown: {e}")
        raise

def generate_placeholder_html(output_file='docs/index.html'):
    os.makedirs('docs', exist_ok=True)
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
<title>GitHub Starred</title>
<meta charset="UTF-8">
<style>
body { font-family: Arial, sans-serif; }
h1 { color: #333; }
</style>
</head>
<body>
<h1>GitHub Starred Projects</h1>
<p>此页面由 workflow 自动生成。</p>
</body>
</html>""")
        print(f"[INFO] Placeholder HTML 生成完成: {output_file}")
    except Exception as e:
        print(f"[ERROR] Failed to generate HTML: {e}")
        raise

if __name__ == "__main__":
    print("[DEBUG] STAR_USERNAME:", os.getenv("STAR_USERNAME"))
    print("[DEBUG] STAR_TOKEN is set:", "Yes" if os.getenv("STAR_TOKEN") else "No")

    try:
        username = os.getenv("STAR_USERNAME")
        token = os.getenv("STAR_TOKEN")
        if not username:
            raise ValueError("STAR_USERNAME is not set")
        if not token:
            raise ValueError("STAR_TOKEN is not set")

        repos = get_starred_repos(username, token)
        generate_markdown(repos)
        generate_placeholder_html()
    except Exception as e:
        print("[FATAL] Script failed with exception:")
        traceback.print_exc()
        exit(1)
