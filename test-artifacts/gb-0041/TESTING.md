# 换位检验测试说明（gb-0041）

本目录存放对比检验（漏判差异换位检验）的测试与验证脚本，不混入源码。

## 测试文件

| 文件 | 内容 |
|---|---|
| `test_permutation.py` | 引擎单元测试：独立暴力枚举 oracle 对照（含30组随机用例）、统计量口径、分批确定性与重试一致、120轴承抽样模式、单元格上限分批、停算条件（真值不符/缺轴承归属/样本集合不一致） |
| `test_compare_api.py` | HTTP 全流程集成：真实登录与权限（viewer 403）、归属版本只增不改、创建校验（同批/已完成/故障标签/抽样范围）、精确枚举算齐、停算失败态、模拟中断后断点续算不重复计数、归属另出新版后仍按原版算齐 |
| `verify_seed_flow.py` | 种子演示全流程：seed 连跑幂等、worker 依次消费 analysis/comparison 双队列、120轴承分批抽样算齐、running 任务 recover 重排队 |
| `smoke_compare_page.mjs` | 前端页面冒烟：排队中不报告概率与换位总数、完成后才报告、失败显示停算原因与重试入口、新版归属提示仍按原版 |

## 运行方式

```bash
cd backend
python -m pytest ../test-artifacts/gb-0041/ -q      # 后端单元+集成（sqlite + 假队列，无需外部服务）
python ../test-artifacts/gb-0041/verify_seed_flow.py # 种子流程
node ../test-artifacts/gb-0041/smoke_compare_page.mjs # 前端页面冒烟（node ≥18）
```

集成测试通过环境变量指向临时 sqlite 与临时 artifacts 目录，并用内存假队列替换 Redis；不触碰真实服务。真实 Compose 环境（MySQL8 + Redis7）下由 worker 消费 `comparison:queue`，行为与测试一致。
