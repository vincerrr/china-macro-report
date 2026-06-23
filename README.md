# 中国宏观经济数据报告

每日自动更新的中国宏观经济数据展示网页。通过 AKShare 从官方渠道获取数据，使用大模型生成解读，输出静态 HTML 报告。

## 已覆盖指标（10 个）

### 增长
- **GDP** 同比（季度，国家统计局）
- **PMI** 制造业采购经理指数（月度，国家统计局）
- **规模以上工业增加值** 同比（月度，国家统计局）
- **社会消费品零售总额** 同比（月度，国家统计局）

### 物价
- **CPI** 同比（月度，国家统计局）
- **PPI** 同比（月度，国家统计局）

### 货币
- **USD/CNY 汇率**（每日，国家外汇管理局）
- **LPR 1年期**（月度，全国银行间同业拆借中心）
- **M2** 同比（月度，中国人民银行）
- **新增人民币贷款**（月度，中国人民银行）

### 暂不可用（AKShare 上游接口故障或缺失）
- 核心 CPI、失业率、新增就业、社融总量

## 目录结构

```
china-macro-report/
├── src/
│   ├── config.py        # 指标配置、路径、API 配置
│   ├── fetcher.py       # AKShare 数据拉取
│   ├── store.py         # SQLite 存储层
│   ├── analyzer.py      # 火山方舟 LLM API 调用
│   ├── reporter.py      # Jinja2 + Tailwind + ECharts HTML 渲染
│   └── pipeline.py      # 主流程编排
├── data/
│   ├── macro.db         # SQLite 数据库（持久化，入仓）
│   └── latest.json      # 当前快照（供前端/调试）
├── output/
│   └── index.html       # 生成的报告页面
├── .github/workflows/
│   └── daily-update.yml # 每日定时调度
├── DEPLOYMENT.md        # 部署指南
├── .env                 # 环境变量（gitignore，含 API Key）
├── .env.example
├── .gitignore
└── requirements.txt
```

## 本地运行

```powershell
# 一次性安装依赖
pip install -r requirements.txt

# 执行完整流水线（拉数据 → LLM 解读 → 生成 HTML）
$env:PYTHONPATH = "."
python -m src.pipeline

# 在浏览器打开报告
Start-Process output/index.html
```

## 配置

复制 `.env.example` 为 `.env`，填入：
- `GLM_API_KEY` — 火山方舟 API Key
- `GLM_MODEL` — 接入点 ID（形如 `ep-xxxxxxxx`）
- `GLM_API_BASE` — `https://ark.cn-beijing.volces.com/api/v3/`

## 部署到 GitHub Pages（每日自动更新）

详见 [DEPLOYMENT.md](DEPLOYMENT.md)。简要：

1. 推到 GitHub 公开仓库
2. 在 Settings → Secrets 配置 3 个环境变量
3. 启用 GitHub Pages（Source 选 GitHub Actions）
4. 每天北京时间 09:00 自动跑，部署到 `https://<用户名>.github.io/china-macro-report/`

## 后续计划

- 接入失败指标的替代数据源（核心 CPI 直爬统计局、新增就业从人社部新闻稿提取等）
- 多指标联动综述（每日 LLM 跨指标总结）
- 发布日历（显示下一次更新预期日期）
- 移动端优化、自定义域名等
