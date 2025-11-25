谨以此来纪念我那小而不成熟的学习之旅。
仅限个人学习使用，不负责任何法律责任。
To commemorate my humble and budding learning journey.
For personal educational use only. No legal liability assumed.

# 我的 GitHub Star 仓库 ⭐

本仓库用于记录和展示我收藏的 GitHub Star 仓库，自动化生成并智能分类（语义聚类 + Embeddings）。  
每个项目带有：最新 Release / 语言 / License / Star 数 / 最后活跃时间。

---

## 🔹 自动更新

- 使用 GitHub Actions 每天自动拉取 Star 列表并更新 Markdown / HTML 页面
- 支持手动触发 Actions
- 自动归档长期不活跃仓库（默认 360 天未更新）
- Markdown 文件：[`starred.md`](./starred.md)
- 可视化页面：GitHub Pages (`docs/index.html`)

---

## 🔹 快捷访问 GitHub Pages

点击下面按钮直接访问可视化页面（Notion 风格卡片展示）：

[![Open Pages](https://img.shields.io/badge/Open-Pages-blue?style=for-the-badge&logo=github)](https://RicardoLu985.github.io/Star/)

> ⚠️ 注意：GitHub Pages 默认指向 `docs/index.html`，请确保 Pages 设置选择 `main` 分支下的 `/docs` 文件夹。

---

## 🔹 使用说明

1. **更新 Star**
    - 修改或添加 GitHub Secrets：
        - `GH_PAT` → 自动推送更新
        - `STAR_TOKEN` → 访问 Star 列表
        - `OPENAI_API_KEY` → (可选) 更智能的语义聚类
        - `USE_SENT_TRANSFORMER` → (可选) 本地 embeddings fallback
2. **触发 Actions**
    - 自动：每天 UTC 2 点
    - 手动：仓库 → Actions → `Update Starred (Semantic)` → Run workflow
3. **查看 Markdown / 页面**
    - [`starred.md`](./starred.md) → Markdown 查看
    - [GitHub Pages](https://RicardoLu985.github.io/Star/) → 可视化卡片

---

## 🔹 输出文件

| 文件/目录 | 用途 |
|-----------|------|
| `starred.md` | 自动生成 Markdown，按语义分类展示 |
| `docs/index.html` | 可视化 Notion 风格页面（GitHub Pages） |
| `star_template.md` | Markdown 模板文件 |
| `update_starred_semantic.py` | 拉取 Star + 聚类 + 输出的主脚本 |
| `.github/workflows/update_stars.yml` | Actions 自动更新 workflow |
| `config.json` | 配置文件，控制聚类、归档、输出路径等 |

---

## 🔹 页面示例

- 每个项目显示：
    - 仓库名（点击跳转）
    - 描述
    - Star 数 / 自动星级
    - 最新 Release（如有）
    - 语言 / License
    - 最后活跃时间

> 所有内容均由脚本自动生成，无需手动维护。
