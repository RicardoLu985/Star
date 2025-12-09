# 📚 GitHub Starred Repos Auto Organizer

[![GitHub stars](https://img.shields.io/github/stars/RicardoLu985/Star?style=social)](https://github.com/RicardoLu985/Star/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/RicardoLu985/Star?style=social)](https://github.com/RicardoLu985/Star/network/members)
[![GitHub issues](https://img.shields.io/github/issues/RicardoLu985/Star)](https://github.com/RicardoLu985/Star/issues)
[![GitHub license](https://img.shields.io/github/license/RicardoLu985/Star)](https://github.com/RicardoLu985/Star/blob/main/LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)

自动拉取 → 语义聚类 → 生成美观 Markdown + Notion 风可视化页面，定时自动更新，彻底解放你的 Star 列表！

An intelligent organizer for your GitHub starred repositories — zero manual maintenance, updated daily!

**在线预览 / Live Demo** ➡️  [https://github.com/RicardoLu985/Star/blob/main/starred.md](https://github.com/RicardoLu985/Star/blob/main/starred.md)

**Github Page** ➡️ [https://ricardolu985.github.io/Star/](https://ricardolu985.github.io/Star/)

自动化整理 GitHub Star 项目的 Python 工具

## ✨ 核心特性

一个 **智能、高可维护、完全自动化** 的 GitHub Stars 整理系统：

- 每次运行自动抓取你的 Starred Repos
- 自动识别分类、自动打标签、自动补充 Topics
- 支持自定义分类、重命名项目、定义描述
- 自动生成 **starred.md** 与 **漂亮的网页版 index.html**
- 可本地运行，也可 GitHub Actions 自动运行
- 支持 Tailwind + FontAwesome 优雅 UI
- 新增分类可自动生成图标（以及解释规则）
- 内置自定义 overrides.json
- 全程无需你人工移动项目，只需 star 即可

------

## 🖼️ 效果截图

![demo](https://github.com/RicardoLu985/Star/blob/main/assets/demo.png)
![html](https://github.com/RicardoLu985/Star/blob/main/assets/html.png)

----

## 🌟 功能特性

### ✅ **多渠道配置支持**

- 脚本内 MANUAL_USERNAME / MANUAL_TOKEN
- 环境变量 STAR_USERNAME / STAR_TOKEN
- 本地运行直接键盘输入
- GitHub Actions 自动读取 secrets

### 🎯 **智能分类系统**

- 内置多层级 AI/Web/DevOps/学习资料 等分类
- 自动按 repo 内容（名称/描述/topics/language）识别
- 支持自定义分类与子分类（overrides.json）
- 新分类自动插入“其他”之前
- “其他”永远保证在最后

### 🧩 **自动标签系统**

根据以下信息生成机器识别 tags：

- 语言（Python/TS/Go/...）
- topics
- 描述关键词
- 技术栈特征（ml、nlp、cli、devops、automation 等）

### 🏷️ **Topics 自动抓取**

从 API 获取 repo topics 并展示在 Markdown 和 HTML 中。

### 📝 **根据 overrides.json 补充信息**

支持：

| 字段               | 作用                 | 示例                                                         |
| ------------------ | -------------------- | ------------------------------------------------------------ |
| repos              | 指定分组 group / sub | "jiji262/douyin-downloader": {"group": "DevOps & 工具", "sub": "效率工具"} |
| rename_repo        | 自定义显示名称       | "jiji262/douyin-downloader": "音符下载神器"                  |
| category_emoji     | Group 标题前 emoji   | "DevOps & 工具": "🔧"                                         |
| custom_description | 替换 Markdown 描述   | "jiji262/douyin-downloader": "抖音视频下载神器"              |

并且会自动生成一个 `overrides_template.json` 方便新用户填写。

### 📄 **双输出：Markdown + HTML**

运行后自动生成：

| 文件              | 描述                                                  |
| ----------------- | ----------------------------------------------------- |
| `starred.md`      | 结构清晰，纯 Markdown，可直接用于 README              |
| `docs/index.html` | 漂亮的网页 UI，附带返回顶部、平滑滚动、分类导航等功能 |

### 📊 **stats.json 自动生成**

包含：

- 总项目数
- 按分类统计
- 按语言统计

### ⚡ **无缓存模式**

所有信息实时抓取。

------

## 📁 Repository 结构

```
.
├── update_starred_semantic.py   # ⭐ 主脚本
├── overrides.json               # 自定义规则
├── starred.md                   # 自动生成 Markdown
├── docs/
│   └── index.html               # 自动生成网页 UI
├── stats.json                   # 自动统计文件
└── .github/workflows/
    └── update-starred.yml       # GitHub Actions 自动运行
```

------

## 🚀 使用方法

### 方式 1：本地运行（最简单）

```py
python update_starred_semantic.py
```

如果 MANUAL_USERNAME / MANUAL_TOKEN 未设置，将自动提示你输入。

### 方式 2：使用环境变量

```py
export STAR_USERNAME=你的GitHub用户名
export STAR_TOKEN=你的PAT
python update_starred_semantic.py
```

### 方式 3：GitHub Actions 自动运行（推荐）

1. Fork 本仓库
2. Settings → Secrets and variables → Actions 添加以下 Secrets：

| Secret 名              | 必填 | 说明                                      |
| ---------------------- | ---- | ----------------------------------------- |
| `GH_PAT`               | 是   | 具有 `repo`+`workflow` 权限的 PAT         |
| `STAR_USERNAME`        | 否   | 具体应根据根据yml文件是否配置用户名而定   |
| `STAR_TOKEN`           | 是   | 读取 Starred 列表的 Token（可与上面共用） |
| `OPENAI_API_KEY`       | 否   | 更精准聚类（推荐）                        |
| `USE_SENT_TRANSFORMER` | 否   | 设为 `true` 使用本地模型（无需 OpenAI）   |

1. 手动跑一次 Actions → 几分钟后自动生成所有文件
2. 开启 GitHub Pages（Source 选 `gh-pages` 分支的 `/docs` 文件夹）

即可定时运行，并提交自动更新。

------

## 🛠️ 自定义规则1：overrides.json

### 字段说明

```json
{
  "repos": {
    "作者/repo": {
      "group": "主分类",
      "sub": "子分类"
    }
  },
  "rename_repo": {
    "作者/repo": "自定义项目名称"
  },
  "category_emoji": {
    "分类": "😀"
  },
  "custom_description": {
    "作者/repo": "自定义描述"
  }
}
```

------

## 🛠️ 自定义规则2：update_starred_semantic.py

在 `update_starred_semantic.py` 中，您可以修改分类规则：

```py
DEFAULT_CATEGORY_MAP = {
    "AI": {
        "机器学习框架": ["pytorch", "tensorflow", "jax"],
        "大模型/LLM": ["llama", "gpt", "transformers"]
    },
    "Web 开发": {
        "前端框架": ["react", "vue", "svelte"],
        "后端框架": ["fastapi", "django", "flask"]
    }
}
```

## 🎨 分类新增时，图标如何生成？

脚本使用以下规则自动给分类选图标：

| 关键词             | 默认图标 |
| ------------------ | -------- |
| AI / 智能          | 🤖        |
| 影音 / 视频 / 音乐 | 🎬        |
| 工具               | 🛠️        |
| 学习 / 教程        | 📚        |
| 其他               | ❓        |

如果你新增了分类，如：

```
"影音娱乐增强版"
```

脚本会自动判断含“影音” → 自动选 `fa-film`。

如果没有匹配任何关键词 → 默认使用：

```
fa-folder (蓝色)
```

因此你无需担心图标问题，脚本已经全自动处理。

------

## 📦 HTML 页面效果

- Tailwind.css 美化
- 卡片悬停动画
- 返回顶部按钮
- 平滑滚动
- 分类导航栅格布局
- 中英文兼容字体（Noto Sans SC）
- 响应式布局（手机/平板/PC）

------

## 📌 需要哪些权限？

你的 GitHub Token 需要：

| 权限                | 用途               |
| ------------------- | ------------------ |
| `workflow` + `repo` | 读取你 star 的项目 |

无需写权限，因为文档更新由 Actions 自动提交。

------

## 🧪 开发调试（IDE 支持）

脚本自动根据是否有 TTY 判断是：

- 本地 IDE 运行 → 输入用户名与 token
- CI 环境运行 → 强制读取变量或手动设置

不会阻塞 IDE。

--------

## 🤝 贡献指南

欢迎为项目贡献！请遵循以下步骤：

1. Fork 项目仓库
2. 创建新分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -am 'Add some feature'`)
4. 推送分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

**提交格式**：

- `feat`: 新功能
- `fix`: 修复问题
- `docs`: 文档更新
- `chore`: 构建/依赖更新

-----

## 📄 许可证

[MIT License](https://github.com/RicardoLu985/Star/blob/main/LICENSE) © 2025 RicardoLu

----

## 🙌 致谢

- GitHub API
- OpenAI & Sentence Transformers
- 所有被 Star 的优秀项目作者
- 所有的开源AI

如果这个工具让你重新爱上自己的 Star 列表，麻烦顺手点个 Star 鼓励一下作者呀 ✨

------

Made with ❤️ by [RicardoLu](https://github.com/RicardoLu985)