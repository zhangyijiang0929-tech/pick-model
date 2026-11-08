# pick-model

**别为批处理任务多付 30 倍的钱。**

给一段任务描述，判断它该用哪个档位的模型，并算出期望成本。同样是 500 次抽取，T1 和 T2 差 35 倍——这个 skill 告诉你什么时候可以放心降，什么时候降了一定会后悔。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
[![validate](https://github.com/zhangyijiang0929-tech/pick-model/actions/workflows/validate.yml/badge.svg)](https://github.com/zhangyijiang0929-tech/pick-model/actions/workflows/validate.yml)

```bash
curl -fsSL https://raw.githubusercontent.com/zhangyijiang0929-tech/pick-model/main/install.sh | bash
```

一个 Agent Skill：读入提示词 → 五维打分 → 落 T1/T2/T3 → 从你自己的价目表挑出**期望成本最低**的那个模型。

它输出的不是"建议用强一点的模型"，而是一张能直接做决定的卡片：

```
T2 · 中等任务 → claude-sonnet-5.5

理由：单轮写作 + 输入约 40k，无多步推理需求，T3 属于溢价
粗估：40k / 5k ≈ $0.13/次（含 2% 重试风险）
降档代价：换 deepseek-v4-pro ≈ $0.08/次，但长文结构完整性会掉，中段容易跑题
升档门槛：若这份分析要直接给客户看（错误不可自查），升 T3
```

## 为什么不是"简单任务用便宜模型"

这句话是对的，但按它做会亏钱。真实的成本结构是：

```
期望成本 = 单次成本 / (1 - 失败率) + 失败率 × 返工成本
```

一个失败率 8% 的便宜模型，如果每次失败要人花 5 分钟收拾，一天跑 2000 次，返工成本会吃掉全部节省。所以核心判断不是"任务简单不简单"，而是：

**这个任务出错，会不会被自动发现？**

- 会被发现（有测试、有 schema 校验、有对照答案）→ 放心降档，降得越狠赚得越多
- 不会发现（写给人看的文档、给客户的报告、没有测试的代码）→ 不要降档，省下的钱只是把成本推迟到返工

这个 skill 把这条判断写成了一条硬规则：**容错要求维度打满 2 分，一票升到 T3，不管其他维度多低。**

## 为什么是打分而不是让模型"感觉一下"

因为不可核对。用户在看到一个结论之后，第一个问题永远是"凭什么"。

所以这里用五个可指认的维度打分，每个 0/1/2：

| 维度 | 0 分 | 1 分 | 2 分 |
|---|---|---|---|
| 推理步数 | 单步映射 | 2–3 步可验证 | 4 步以上或不可验证 |
| 输入规模 | < 8k | 8k–60k | > 60k |
| 任务类型 | 抽取/改写/分类 | 写作/总结/常规编码 | 架构/复杂调试/证明 |
| 容错要求 | 错了能看出来且重跑便宜 | 能看出来但重跑贵 | 看不出来 |
| 工具与多轮 | 单轮无工具 | 少量工具 | 长链条 agent |

总分 0–3 → T1，4–7 → T2，8–10 → T3。落在 3/4 或 7/8 边界，取高档。

完整锚点和三个示例见 [`references/scoring.md`](references/scoring.md)。

## 安装

一行装好（默认装到 `~/.workbuddy/skills`，已存在会先备份再覆盖）：

```bash
curl -fsSL https://raw.githubusercontent.com/zhangyijiang0929-tech/pick-model/main/install.sh | bash
```

或者手动 clone。skill 目录结构通用，只要求 `SKILL.md` 在目录根部：

```bash
# 全局安装
git clone https://github.com/zhangyijiang0929-tech/pick-model.git ~/.workbuddy/skills/pick-model

# 项目内安装
git clone https://github.com/zhangyijiang0929-tech/pick-model.git ./.workbuddy/skills/pick-model
```

装完 30 秒自检，确认价目表能读、模型数对得上：

```bash
python3 ~/.workbuddy/skills/pick-model/scripts/estimate.py --check
```

其他位置用环境变量指定：

```bash
PICK_MODEL_DEST=~/my-agent/skills ./install.sh
```

## 用法

在对话里直接问，或者显式调用：

```
/pick-model 从 500 张收据的 OCR 文本里抽出商户名、日期、金额、税号，输出 JSON
```

skill 会输出卡片。想手动算成本也可以直接用脚本（无第三方依赖）：

```bash
python3 scripts/estimate.py --in 20000 --out 3000

# 指定档位、加入返工成本
python3 scripts/estimate.py --in 200000 --out 8000 --tier T2 --rework 2.5

# 只校验价目表
python3 scripts/estimate.py --check

# JSON 输出，接你自己的流水线
python3 scripts/estimate.py --in 20000 --out 3000 --json
```

实际输出：

```
配置：11 个模型 · 价目更新于 2026-11-08（0 天前）
估算：输入 20,000 / 输出 3,000 tokens · 返工成本 $0.00/次

档位  模型                        单次成本     期望成本   本档倍数
------------------------------------------------------------------
T1    qwen3.7-flash                $0.0010      $0.0011       1.0x
T1    deepseek-v4-flash            $0.0020      $0.0021       2.0x
T1    claude-haiku-5.5             $0.0035      $0.0036       3.4x
T1    gpt-6-luna                   $0.0035      $0.0036       3.4x
T2    deepseek-v4-pro              $0.0383      $0.0395       1.0x
T2    glm-5.3                      $0.0412      $0.0429       1.1x
T2    claude-sonnet-5.5            $0.0700      $0.0714       1.8x
T2    gemini-3.1-pro               $0.0760      $0.0784       2.0x
T3    claude-opus-5.5              $0.1400      $0.1421       1.0x
T3    gpt-5.6-sol                  $0.1400      $0.1421       1.0x
T3    claude-fable-5.1             $0.3500      $0.3535       2.5x
```

## 维护价目表

价格和模型只存在一个地方：[`references/models.yaml`](references/models.yaml)。改价、加模型都只改这个文件。

```yaml
models:
  - id: claude-sonnet-5.5
    name: Claude Sonnet 5.5
    vendor: Anthropic
    tier: T2
    price_in: 2.00        # USD / 1M 输入 tokens
    price_out: 10.00      # USD / 1M 输出 tokens
    context: 1000000
    fail_rate: 0.02       # 这一档做这类任务需要重做的概率
    tags: [写作, 代码, 长文]
    note: 通用性最好的一档，写作与代码都不出错
```

两条约定：

- 改完 `updated:` 日期。超过 90 天，脚本会自动打印过期警告。
- **`fail_rate` 是唯一的主观参数**，也是影响结论最大的参数。仓库给的是社区经验估计，你应当用自己的 eval 结果替换它。

内置价目为 2026-11 从 llmpricing.dev / llmrates.ai / costperprompt.com 交叉核对的公开 API 刊例价。**刊例价会变，你的实际结算价还可能不同（有折扣、有缓存价、有批处理价）。当成起点，不要当成事实。**

## 设计取舍

**只给建议，不自动切换模型。** 这是有意的。skill 运行在当前会话里，无法改变自己所在的模型；假装能切换，只会让用户以为省了钱而实际上没有。它只负责给出判断，切换动作交给调用方。

**不做单次任务的精算表演。** 单次写一篇文章，T1 和 T3 差 $0.13。为了这 $0.13 花三分钟读卡片不划算。这个 skill 真正赚钱的场景是**批量任务**：500 次调用、每次省 $0.06，就是 $30。用户来问单次任务时，可以提醒他这一点。

**价目表解析器只支持受限的 YAML 子集。** 因为它故意选择了"遇到不认识的结构就报错退出"，而不是猜。算错的成本数字比不算更糟。

## 局限

- 判断依赖任务描述的质量。描述含糊时，它会给出保守（偏高）的档位——这是有意的，宁可多花钱也别给错结论。
- `fail_rate` 是估计值，不是测量值。它的准确度取决于你校准它的认真程度。
- 只覆盖文本模型。图像、语音、embedding 没有纳入。
- 档位是三档。真实世界比三档细，但三档是大多数人能真正用起来的粒度。

## 贡献

最有价值的贡献不是改代码，是**更新价目表**和**用真实 eval 校准失败率**。带样本量的数字比任何讨论都有用。细节见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

MIT。见 [LICENSE](LICENSE)。
