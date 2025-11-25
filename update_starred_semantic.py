import os
import requests
from datetime import datetime

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

if __name__ == "__main__":
    try:
        username = os.getenv("STAR_USERNAME") or "你的用户名"
        token = os.getenv("STAR_TOKEN")
        if not token:
            raise ValueError("Environment variable STAR_TOKEN not set")
        repos = get_starred_repos(username, token)
        generate_markdown(repos)
    except Exception as e:
        print(f"[FATAL] Script failed: {e}")
        exit(1)
