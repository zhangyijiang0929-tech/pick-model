# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.2.0] - 2026-11-08

### 新增
- `install.sh` 支持 `curl | bash` 一行安装：无本地仓库时自动 clone
- `.github/workflows/validate.yml`：SKILL.md 前置字段校验、价目表解析、估算冒烟测试、价目过期告警，矩阵覆盖 Python 3.9 / 3.12
- `CONTRIBUTING.md`：把贡献引导到更新价目与校准 `fail_rate`，而非改代码

### 变更
- README 首屏改为痛点开头（批处理任务档位差价 35 倍），安装命令提至 badge 下方
- `install.sh` 在非交互环境下改为**先备份再覆盖**（`pick-model.bak.<时间戳>`），不再交互式询问，也不会静默删除已有目录

### 修复
- 中文表头与 ASCII 模型名混排时的列宽错位（按 East Asian Width 计算显示宽度）

## [0.1.0] - 2026-11-08

### 新增
- 五维复杂度打分（推理步数 / 输入规模 / 任务类型 / 容错要求 / 工具与多轮），0/1/2 分制
- 三档落档规则与边界升档；容错要求 = 2 时一票升 T3
- `references/models.yaml`：11 个模型的价目与失败率假设，价目标注来源与更新日期
- `scripts/estimate.py`：期望成本计算（含 `fail_rate / (1 - fail_rate)` 重试期望与返工成本），零第三方依赖，支持 `--check` / `--tier` / `--rework` / `--json`
- 价目表超过 90 天未更新时自动告警
