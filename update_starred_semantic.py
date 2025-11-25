# update_starred_semantic.py
import os
import requests
from datetime import datetime
import logging
from collections import defaultdict

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 确保 docs 目录存在
os.makedirs('docs', exist_ok=True)

# 从环境变量获取配置
STAR_USERNAME = os.getenv("STAR_USERNAME")
STAR_TOKEN = os.getenv("STAR_TOKEN")
GITHUB_PROXY = os.getenv("GITHUB_PROXY")  # 可选代理配置

# 检查必要的环境变量
if not STAR_USERNAME:
    raise ValueError("STAR_USERNAME 环境变量未设置")
if not STAR_TOKEN:
    raise ValueError("STAR_TOKEN 环境变量未设置")

# 配置请求会话
session = requests.Session()
session.headers.update({
    'Authorization': f'token {STAR_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'GitHub Starred Projects Exporter'
})

# 如果设置了代理，配置代理
if GITHUB_PROXY:
    session.proxies.update({
        'http': GITHUB_PROXY,
        'https': GITHUB_PROXY
    })
    logging.info(f"使用代理: {GITHUB_PROXY}")

def get_starred_repos(username):
    """获取用户的所有星标仓库，支持分页"""
    url = f'https://api.github.com/users/{username}/starred'
    repos = []
    page = 1

    while url:
        try:
            logging.info(f"正在获取第 {page} 页星标项目...")
            response = session.get(url, timeout=10)

            # 检查响应状态码
            if response.status_code == 401:
                raise Exception("认证失败，请检查你的 GitHub Token 是否有效")
            if response.status_code == 403:
                raise Exception("API 速率限制 exceeded，请稍后再试或使用代理")
            if response.status_code != 200:
                raise Exception(f"API 请求失败: {response.status_code} - {response.text}")

            # 添加当前页的仓库
            page_repos = response.json()
            if not page_repos:
                break

            repos.extend(page_repos)
            logging.info(f"已获取 {len(repos)} 个星标项目")

            # 获取下一页的 URL
            url = response.links.get('next', {}).get('url')
            page += 1

        except requests.exceptions.RequestException as e:
            logging.error(f"请求出错: {e}")
            raise
        except Exception as e:
            logging.error(f"获取星标项目失败: {e}")
            raise

    return repos

def categorize_by_language(repos):
    """按编程语言对仓库进行分类"""
    categorized = defaultdict(list)

    for repo in repos:
        language = repo.get('language') or 'Unknown'
        categorized[language].append(repo)

    # 按仓库数量降序排序
    sorted_categories = sorted(categorized.items(), key=lambda x: len(x[1]), reverse=True)
    return dict(sorted_categories)

def format_date(date_string):
    """格式化日期显示"""
    if not date_string:
        return "N/A"
    try:
        date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return date_obj.strftime("%Y-%m-%d")
    except:
        return date_string

def generate_markdown(repos, output_file='starred.md'):
    """生成美化的 Markdown 文件"""
    # 按语言分类
    categorized_repos = categorize_by_language(repos)

    with open(output_file, 'w', encoding='utf-8') as f:
        # 头部信息
        f.write('# 🌟 我的 GitHub 星标项目\n\n')
        f.write(f'> 📅 更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'> 🔢 总项目数: {len(repos)}\n')
        f.write(f'> 🗂️  语言分类: {len(categorized_repos)}\n\n')

        # 项目统计信息
        f.write('## 📊 项目统计\n\n')
        f.write('| 编程语言 | 项目数量 |\n')
        f.write('|----------|----------|\n')
        for lang, lang_repos in categorized_repos.items():
            f.write(f'| {lang} | {len(lang_repos)} |\n')
        f.write('\n')

        # 按语言分类的项目列表
        f.write('## 📋 项目列表\n\n')

        for language, lang_repos in categorized_repos.items():
            # 语言标题
            f.write(f'### {language}\n\n')

            # 项目列表
            for repo in lang_repos:
                # 基本信息
                name = repo['full_name']
                url = repo['html_url']

                # --- 这里是修复的核心代码 ---
                # 安全地处理可能为 None 的 description
                description = repo.get('description')
                # 如果 description 不是 None，就调用 strip()，否则设为空字符串
                description = description.strip() if description is not None else ''
                # 如果处理后的 description 是空字符串，就用 '无描述' 代替
                description = description or '无描述'
                # --- 修复结束 ---

                # 统计信息
                stars = repo.get('stargazers_count', 0)
                forks = repo.get('forks_count', 0)
                last_updated = format_date(repo.get('updated_at'))

                # 构建项目条目
                f.write(f'#### [{name}]({url})\n')
                f.write(f'> {description}\n\n')
                f.write(f'📊 星标: {stars} · 分支: {forks} · 更新: {last_updated}\n\n')

        # 页脚
        f.write('---\n\n')
        f.write(f'⚠️  此页面由 GitHub Actions 自动生成，最后更新于 {datetime.now().strftime("%Y-%m-%d")}\n')

    logging.info(f"Markdown 文件已生成: {output_file}")

def generate_html(repos, output_file='docs/index.html'):
    """生成美化的 HTML 页面"""
    # 按语言分类
    categorized_repos = categorize_by_language(repos)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub 星标项目</title>
    <style>
        :root {
            --primary-color: #24292e;
            --secondary-color: #f3f4f6;
            --accent-color: #0366d6;
            --text-color: #333;
            --light-text: #666;
            --border-color: #e1e4e8;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }
        
        body {
            background-color: #fafbfc;
            color: var(--text-color);
            line-height: 1.6;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 40px;
            padding: 20px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: var(--primary-color);
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .header-meta {
            color: var(--light-text);
            font-size: 0.9rem;
            margin-top: 10px;
        }
        
        .header-meta span {
            margin: 0 10px;
        }
        
        .stats-section {
            background-color: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .stat-card {
            background-color: var(--secondary-color);
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 1.8rem;
            font-weight: bold;
            color: var(--accent-color);
            margin-bottom: 5px;
        }
        
        .stat-label {
            color: var(--light-text);
            font-size: 0.9rem;
        }
        
        .language-section {
            margin-bottom: 40px;
        }
        
        .language-header {
            background-color: var(--primary-color);
            color: white;
            padding: 15px 20px;
            border-radius: 8px 8px 0 0;
            font-size: 1.2rem;
            font-weight: 600;
        }
        
        .repo-list {
            background-color: white;
            border-radius: 0 0 8px 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .repo-card {
            padding: 15px;
            border-bottom: 1px solid var(--border-color);
        }
        
        .repo-card:last-child {
            border-bottom: none;
        }
        
        .repo-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .repo-name {
            font-size: 1.1rem;
            font-weight: 600;
        }
        
        .repo-name a {
            color: var(--accent-color);
            text-decoration: none;
        }
        
        .repo-name a:hover {
            text-decoration: underline;
        }
        
        .repo-stats {
            font-size: 0.8rem;
            color: var(--light-text);
        }
        
        .repo-stats span {
            margin-left: 10px;
        }
        
        .repo-description {
            color: var(--light-text);
            margin-bottom: 10px;
            font-size: 0.95rem;
        }
        
        .repo-meta {
            display: flex;
            font-size: 0.8rem;
            color: var(--light-text);
        }
        
        .repo-meta div {
            margin-right: 15px;
        }
        
        footer {
            text-align: center;
            margin-top: 50px;
            padding: 20px;
            color: var(--light-text);
            font-size: 0.9rem;
            border-top: 1px solid var(--border-color);
        }
        
        @media (max-width: 768px) {
            .stats-grid {
                grid-template-columns: 1fr;
            }
            
            .repo-header {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .repo-stats {
                margin-top: 5px;
            }
        }
    </style>
</head>
<body>
    <header>
        <h1>🌟 GitHub 星标项目</h1>
        <div class="header-meta">
            <span>📅 更新时间: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</span>
            <span>🔢 总项目数: """ + str(len(repos)) + """</span>
            <span>🗂️  语言分类: """ + str(len(categorized_repos)) + """</span>
        </div>
    </header>
    
    <section class="stats-section">
        <h2>📊 项目统计</h2>
        <div class="stats-grid">
            """ + "".join([f"""
            <div class="stat-card">
                <div class="stat-value">{len(repos)}</div>
                <div class="stat-label">总项目数</div>
            </div>
            """ for _ in range(1)]) + """
            """ + "".join([f"""
            <div class="stat-card">
                <div class="stat-value">{len(lang_repos)}</div>
                <div class="stat-label">{language}</div>
            </div>
            """ for language, lang_repos in list(categorized_repos.items())[:3]]) + """
        </div>
    </section>
    
    """ + "".join([f"""
    <section class="language-section">
        <div class="language-header">{language} ({len(lang_repos)} 个项目)</div>
        <div class="repo-list">
            {''.join([f'''
            <div class="repo-card">
                <div class="repo-header">
                    <div class="repo-name">
                        <a href="{repo['html_url']}" target="_blank">{repo['full_name']}</a>
                    </div>
                    <div class="repo-stats">
                        <span>⭐ {repo.get('stargazers_count', 0)}</span>
                        <span>🍴 {repo.get('forks_count', 0)}</span>
                    </div>
                </div>
                <div class="repo-description">
                    {repo.get('description').strip() if repo.get('description') is not None else '无描述'}
                </div>
                <div class="repo-meta">
                    <div>📅 更新: {format_date(repo.get('updated_at'))}</div>
                    <div>👤 作者: {repo['owner']['login']}</div>
                </div>
            </div>
            ''' for repo in lang_repos])}
        </div>
    </section>
    """ for language, lang_repos in categorized_repos.items()]) + """
    
    <footer>
        ⚠️  此页面由 GitHub Actions 自动生成，最后更新于 """ + datetime.now().strftime("%Y-%m-%d") + """
    </footer>
</body>
</html>
        """)

    logging.info(f"HTML 文件已生成: {output_file}")

def main():
    """主函数"""
    try:
        logging.info("开始获取 GitHub 星标项目...")

        # 获取星标项目
        repos = get_starred_repos(STAR_USERNAME)

        if not repos:
            logging.warning("未找到任何星标项目")
            return

        logging.info(f"成功获取 {len(repos)} 个星标项目")

        # 生成文件
        generate_markdown(repos)
        generate_html(repos)

        logging.info("所有文件生成完成！")

    except Exception as e:
        logging.error(f"程序执行失败: {e}")
        raise

if __name__ == "__main__":
    main()