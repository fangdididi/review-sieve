# Review Sieve（审查筛子）

[English](README.md) | **简体中文**

一个让 AI 助手"老老实实接收 PR 审查"的技能。当一个 PR 同时收到审查机器人、额外请来的 AI 模型、同事和负责人的评论时，审查筛子把它们整理成一份台账：每条意见都要有结论，而结论必须有你在当前提交上亲自拿到的证据；PR 守在写明的范围围栏内；审查轮数有上限；并帮你起草每个讨论串的回复。

适用于 Claude Code、Codex、Cursor，以及任何能读取 `SKILL.md` 的智能体。辅助脚本是纯 Python 3，无任何依赖。

## 解决什么问题

多人审查的 PR 通常以两种方式失败：要么每条建议都照改，diff 翻倍、审查没完没了；要么评论被不加理由地打发掉，真 bug 照样上线。这两种都不是"审查"出了问题，而是"接收审查"出了问题。这个技能专门解决怎样把审查接收好。

## 功能

- **先写范围围栏。** 一句话目标、范围内路径、明确的不做事项和风险等级，在读任何评论之前写好。
- **六种结论。** `FIX`、`WRONG`、`LATER`、`ASK`、`STALE`、`DUP`，每种都有各自必须的凭据。
- **证据标签。** `[ran]`、`[read]`、`[traced]`。审查者有多肯定、有多少人附和，都不算证据。
- **过期检查。** 在旧提交上提出的意见，必须在当前 head 上重新核实。
- **负责人保护。** 负责人本人的意见永远不由助手否决，而是变成一个具体的问题交还给他。
- **打破死循环。** 已经用证据拒绝过、却第三次被提出的意见，交给人来定。
- **轮数预算和膨胀提醒。** 3 轮（敏感改动 5 轮），nit 换不来新一轮；diff 超过 1.5 倍时发出提醒。
- **回复草稿和后续任务。** 先说结论的回复、可选的"助手代写"标注，以及范围外问题的待办清单。

## 安装

把整个文件夹复制到你的智能体技能目录：

```bash
git clone https://github.com/fangdididi/review-sieve
# Claude Code
cp -R review-sieve ~/.claude/skills/review-sieve
# Codex
cp -R review-sieve ~/.codex/skills/review-sieve
# Cursor（项目级技能）
mkdir -p .cursor/skills && cp -R review-sieve .cursor/skills/review-sieve
```

其他智能体：让它读取 `SKILL.zh-CN.md`（或 `SKILL.md`），并把 `scripts/` 文件夹放在旁边。

## 使用方法

对你的智能体说类似这样的话：

> "这个 PR 有两个机器人和小王留的 14 条评论，用审查筛子处理一下。"

助手会写出 `.review/ledger.json`，逐条核实意见，修复真实且在范围内的问题，起草回复，并在检查结果允许时停下。你也可以自己运行检查：

```bash
python3 scripts/sieve.py lint .review/ledger.json       # 缺结论、缺证据、缺回复
python3 scripts/sieve.py gate .review/ledger.json       # CLEAR / CLEAR_WITH_NITS / KEEP_GOING / NEEDS_HUMAN
python3 scripts/sieve.py gate --json .review/ledger.json
python3 scripts/sieve.py replies --note "🤖 助手代 @我 回复" .review/ledger.json
python3 scripts/sieve.py followups .review/ledger.json
```

退出码：`0` 正常，`1` 发现问题（或检查未通过），`2` 台账无法读取。

## 示例

```text
$ python3 scripts/sieve.py gate examples/coupon-reminder.zh.ledger.json
NEEDS_HUMAN
  - diff grew 2.2x since round 1: look for fixes that could be declined or narrowed
  - waiting on a person for: Z2
  - same finding keeps coming back: Z4
  rounds 3/5, findings 4, pending 0
```

- `examples/coupon-reminder.zh.ledger.json`（中文）：优惠券到期提醒只发一次。处于第 3 轮的敏感 PR，有一个等负责人回答的问题、一条反复出现的机器人意见，以及范围膨胀。
- `examples/retry-backoff.ledger.json`（英文）：webhook 失败重试。六条意见，涵盖真 blocker、误报、范围外的 bug、重复项和一个 nit，结果为 `CLEAR_WITH_NITS`。

## 文件结构

```text
review-sieve/
├── SKILL.md                 # 技能说明（英文）
├── SKILL.zh-CN.md           # 技能说明（中文）
├── README.md                # 英文 README
├── README.zh-CN.md          # 本文件
├── LICENSE                  # MIT
├── scripts/
│   └── sieve.py             # lint / gate / replies / followups
├── examples/
│   ├── retry-backoff.ledger.json
│   └── coupon-reminder.zh.ledger.json
└── tests/
    └── test_sieve.py        # 57 个测试：python3 -m unittest discover -s tests
```

## 许可证

MIT © fangdididi
