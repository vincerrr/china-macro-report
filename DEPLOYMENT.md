# 部署指南

把本地项目部署到 GitHub Actions + GitHub Pages，实现**每日自动更新 + 公网访问**。

---

## 总览

```
GitHub Actions (每天 UTC 01:00 = 北京 09:00 触发)
    ↓
拉取最新宏观数据 (AKShare)
    ↓
火山方舟 GLM-5.2 生成解读
    ↓
更新 SQLite + 生成 HTML
    ↓
commit 回仓库（持久化）+ 部署到 GitHub Pages
    ↓
公网 URL：https://<你的用户名>.github.io/china-macro-report/
```

**全部免费**：GitHub Actions 公开仓库无限免费分钟数；GitHub Pages 免费托管。

---

## 部署步骤

### 1. 创建 GitHub 仓库

1. 登录 [github.com](https://github.com)，点右上角 **+ → New repository**
2. 仓库名：`china-macro-report`（或你喜欢的名字）
3. 可见性：**Public**（公开仓库才能免费用 GitHub Actions 调度）
4. **不要**勾选 "Initialize with README"（我们要从本地推上去）
5. 点 **Create repository**

### 2. 把本地代码推到 GitHub

在本项目目录 (`D:\File\VibeCodingProject\china-macro-report`) 打开 PowerShell：

```powershell
# 初始化 git（如果还没初始化）
git init
git branch -M main

# 添加远程地址（把 YOUR_USERNAME 换成你的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/china-macro-report.git

# 提交所有文件
git add .
git commit -m "chore: initial commit"
git push -u origin main
```

> ⚠️ **检查 .env 没有被推上去**：`.gitignore` 已经把 `.env` 排除，但还是要确认 — 在 GitHub 仓库页面打开后，**不应该**看到 `.env` 文件。

### 3. 配置 GitHub Secrets（保护 API Key）

GitHub Actions 跑的时候需要访问火山方舟 API，但 API Key 不能写在代码里。要用 GitHub Secrets：

1. 进入仓库页面 → **Settings**（顶部菜单最右）→ **Secrets and variables** → **Actions**
2. 点 **New repository secret**，依次添加 3 个：

| Name | Value |
|------|-------|
| `GLM_API_KEY` | `b93aed60-985f-48b1-b7da-539599c842ae` |
| `GLM_MODEL` | `ep-20260622182439-r8bvr` |
| `GLM_API_BASE` | `https://ark.cn-beijing.volces.com/api/v3/` |

> 这些值就是你本地 `.env` 里的内容。

### 4. 启用 GitHub Pages

1. 仓库 → **Settings** → **Pages**（左侧菜单）
2. **Source** 选择：**GitHub Actions**（不是 "Deploy from a branch"）
3. 保存

### 5. 触发首次部署

进入 **Actions** 标签页：

1. 左侧选择 **Daily Macro Update** workflow
2. 右上角点 **Run workflow** → **Run workflow**
3. 等 2-3 分钟，workflow 跑完后会看到绿色 ✓
4. 部署 URL 出现在 **Settings → Pages** 页面顶部，类似：
   ```
   https://YOUR_USERNAME.github.io/china-macro-report/
   ```

打开这个 URL 就能看到你的宏观数据报告了。

---

## 之后的更新机制

- **自动**：每天北京时间 09:00 自动跑（GitHub Actions Cron）
- **手动**：在 Actions 标签页点 **Run workflow** 立即触发
- **本地开发**：照常 `python -m src.pipeline`，本地 commit 推 main 分支即可

---

## 故障排查

### Workflow 失败显示 "API key not configured"
→ 检查 Secrets 是否正确添加，名字必须是 `GLM_API_KEY`（区分大小写）

### GitHub Pages 显示 404
→ 检查 Settings → Pages 的 Source 是否选了 "GitHub Actions"，而不是分支

### Workflow 跑成功但页面没更新
→ 浏览器强制刷新（Ctrl+F5），GitHub Pages 有 CDN 缓存

### 想改变运行时间
→ 编辑 `.github/workflows/daily-update.yml` 的 `cron` 行：
- `'0 1 * * *'` → 每天 UTC 01:00（北京 09:00）
- `'0 23 * * *'` → 每天 UTC 23:00（北京次日 07:00）
- `'0 1,13 * * *'` → 每天两次（UTC 01:00 和 13:00）

---

## 后续可选优化

- **接入 Vercel**：如果想要更专业的托管（自定义域名、更快的 CDN），可以把 GitHub 仓库连接到 [vercel.com](https://vercel.com)。免费层够用。
- **失败通知**：在 workflow 末尾加上失败时发邮件 / 推送到企业微信的步骤
- **多时段调度**：不同指标发布时间不同，可以设置多个 cron 时间点（如统计局上午 9 点、央行下午 4 点）
