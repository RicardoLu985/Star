# Star ✨

[![GitHub stars](https://img.shields.io/github/stars/RicardoLu985/Star?style=social)](https://github.com/RicardoLu985/Star/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/RicardoLu985/Star?style=social)](https://github.com/RicardoLu985/Star/network/members)
[![GitHub issues](https://img.shields.io/github/issues/RicardoLu985/Star)](https://github.com/RicardoLu985/Star/issues)
[![GitHub license](https://img.shields.io/github/license/RicardoLu985/Star)](https://github.com/RicardoLu985/Star/blob/main/LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)

**个人 GitHub Starred 仓库智能整理工具**  
自动拉取 → 语义聚类 → 生成美观 Markdown + Notion 风可视化页面，每天自动更新，彻底解放你的 Star 列表！

An intelligent organizer for your GitHub starred repositories — zero manual maintenance, updated daily!

**在线预览 / Live Demo** → [https://github.com/RicardoLu985/Star/blob/main/starred.md](https://github.com/RicardoLu985/Star/blob/main/starred.md)

## ✨ 核心特性

- 每周五自动拉取所有 Starred 仓库（含私有）
- 语义聚类（OpenAI 或本地 Sentence Transformer）
- 自动归档长时间不活跃项目
- 生成 `starred.md` + 超美观的交互式 HTML 页面（Notion 风格卡片）
- 支持 **overrides.json** 手动干预：改分类、改名字、隐藏仓库、强制归入某类
- 完全 GitHub Actions 驱动，零本地运行
- 星标数星级可视化、最新 Release、语言、许可证、最后活跃时间一目了然

## 🖼️ 效果截图

![demo](https://github.com/RicardoLu985/Star/blob/main/assets/demo.png)
![html](https://github.com/RicardoLu985/Star/blob/main/assets/html.png)

## 🚀 一键部署到你自己的账号

1. Fork 本仓库
2. Settings → Secrets and variables → Actions 添加以下 Secrets：

| Secret 名              | 必填 | 说明                                      |
| ---------------------- | ---- | ----------------------------------------- |
| `GH_PAT`               | 是   | 具有 `repo`+`workflow` 权限的 PAT         |
| `STAR_TOKEN`           | 是   | 读取 Starred 列表的 Token（可与上面共用） |
| `OPENAI_API_KEY`       | 否   | 更精准聚类（推荐）                        |
| `USE_SENT_TRANSFORMER` | 否   | 设为 `true` 使用本地模型（无需 OpenAI）   |

3. 手动跑一次 Actions → 几分钟后自动生成所有文件
4. 开启 GitHub Pages（Source 选 `gh-pages` 分支的 `/docs` 文件夹）

## 🛠️ 重要文件说明

Star/ 

├── starred.md                  # 自动生成的 Markdown 报告 

├── docs/index.html             # Notion 风格可视化页面 

├── update_starred_semantic.py  # 核心脚本 

├── config.json                 # 全局配置（聚类数量、归档天数等） 

├── overrides.json              # ⭐ 手动自定义规则（最高优先级） 

├── star_template.md            # Markdown 模板 

└── .github/workflows/update_stars.yml

### overrides.json —— 你的“分类遥控器”（最强大功能）

即使 AI 聚类再聪明，也总有几个项目想自己说了算。  
`overrides.json` 会**完全覆盖**自动聚类的结果，支持以下操作：

```json
{
  "repos": {
     "btjawa/BiliTools": { "group": "影音娱乐", "sub": "追番神器" }
//    "用户名/仓库名"：{"group": "分组名", "sub": "子分组名"}
  }
}
```

只要改这个文件，下次 Actions 运行时就会立刻生效，无需改任何代码！

⚙️ config.json 部分可配置项

{
  "max_clusters": 20,
  "min_cluster_size": 3,
  "archive_days": 360,
  "max_repos_per_cluster": 50,
  "use_openai": true
}

🤝 贡献

欢迎 PR！聚类优化、UI 美化、新功能都非常欢迎～

## 📄 许可证

[MIT License](https://github.com/RicardoLu985/Star/blob/main/LICENSE) © 2025 RicardoLu

## 🙌 致谢

- GitHub API
- OpenAI & Sentence Transformers
- 所有被 Star 的优秀项目作者
- 所有的开源AI

如果这个工具让你重新爱上自己的 Star 列表，麻烦顺手点个 Star 鼓励一下作者呀 ✨

------

Made with ❤️ by [RicardoLu](https://github.com/RicardoLu985)