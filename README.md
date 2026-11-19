# 桐弦声检故障判读册

GaussianNB与分层交叉验证、混淆矩阵和后验解释。为桐弦研究协作组的12位分析与业务人员提供从样本核对、独立worker计算到批准快照交付的完整工作流。

## 真实业务场景

合成声学特征→故障类型判读→复检批注；真实训练/验证分离、训练内标准化、类先验展示。团队原先将 `acoustic-bayes-202611-01.csv` 复制到多份人工表格，复核时再逐项对照。三个痛点是口径不可追溯、重复计算易错、业务说明与结果脱节。上游提供合成业务观察，系统承担研究和复核，下游业务人员读取批准快照。全部演示数据是固定随机种子生成的模拟数据。

## 业务模块

1. 业务总览：批次、样本、任务与批准交付账册。
2. 声检批次：创建/修改来源说明、查看样本、用真实业务字段追加记录；列表分页。
3. 分析配置：冻结来源、参数和全部样本，进入Redis队列。
4. 完整结果：真实算法摘要、专属诊断、全部CSV导出和可恢复失败态。
5. 对比检验：同批两项研究的折外判读按样本配对，同一轴承的样本整体换位，检验两类指定故障漏判件数差异是否偶然；轴承归属按版本管理，更正另出一版。
6. 复检批注：分析师草案→负责人批准→阅读者下载批准快照。
7. 审计：登录、来源修改、任务worker完成、业务说明批准等事件。

## 快速启动

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
# 可重复执行，不覆盖人工修改
docker compose exec -T backend python -m scripts.seed_demo
```

访问 [前端](http://localhost:18245)；[API文档](http://localhost:19245/docs)。数据库仅演示用途映射 `17745`。首次准备依赖和初始化数据库需要等待健康状态：`docker compose ps`，五个服务均需healthy。

| 组件 | 技术与职责 |
|---|---|
| frontend | 原生 HTML / CSS / JS ES Modules，Nginx代理 `/api/` |
| backend | Python3.11 / FastAPI / SQLAlchemy / JWT |
| worker | 独立Python进程，Redis BLPOP队列，持久化结果/CSV/心跳 |
| db | MySQL8，命名卷持久化 |
| redis | Redis7，AOF命名卷 |

恰好五服务，均配置healthcheck；后端/worker依赖数据库与Redis健康，前端依赖后端健康；worker与后端共享 `artifacts` 命名卷。重置演示环境：`docker compose down -v --remove-orphans`，会删除本项目卷。

## 账号与权限

所有演示账号密码：`Research2026!`。

| 邮箱 | 角色 | 权限 |
|---|---|---|
| admin@acoustic-bayes.demo | admin | 全部录入/执行、批准业务说明 |
| analyst@acoustic-bayes.demo | analyst | 录入来源/样本、执行、提交说明，无批准权 |
| viewer@acoustic-bayes.demo | viewer | 只读、导出结果及已批准快照 |

时间在数据库/API中以UTC存储，总览与审计页面明确转换为Asia/Shanghai北京时间。

JWT有效期8小时；PBKDF2盐化哈希保存密码；角色每请求从数据库读取。访客写操作403，匿名访问业务数据401，重复样本409，非法业务字段422，重复批准409。每客户端/路径写请求90次/分钟，超限429。生产使用需修改JWT及演示数据库凭据。

## 实体与字段

AcousticBatch / AcousticSample / ClassifierRun / InspectionNote 是核心实体；另有User和Audit。对比检验引入 BearingAttribution（轴承归属版本）与 ComparisonJob（换位检验任务）。数据库实际表：`acoustic_batches` → `acoustic_samples` → `classifier_runs` → `inspection_notes`，以及 `bearing_attributions`、`comparison_jobs`。样本以固定字段JSON保存，后端按以下字段严格验证，不接受未知字段替代必填值：均方根振幅（`rms`）、频谱质心 Hz（`centroid`）、峭度（`kurtosis`）、复核类型（`label`）。

实体贯穿 `backend/src/models`、`schemas`、`services`、`controllers`、`routes`，以及 `frontend/src/api/research.js`、`stores/research.js` 和 `pages`。`Source.key` 与 `(Record.source_id, reference)` 为自然键；来源改名不会修改已冻结任务输入。业务说明在创建时保存结果快照，批准后从该快照导出。归属版本以 `(source_id, version)` 唯一，只增不改：归属更正另出一版，已启动的检验中断后仍按原版恢复，重试不重复计数。

## 算法与口径

GaussianNB与分层交叉验证、混淆矩阵和后验解释，全部计算位于 `backend/src/services/algorithm.py`，前端不拟合模型、不生成模拟结果。输入是冻结业务观察及参数，输出summary、专属诊断、逐行计算明细、seed与输入SHA256。CSV包含全部结果行；页面仅预览前30行。参数：

- `folds`：分层交叉验证折数，默认 `3`。
- `smoothing`：方差平滑系数，默认 `1e-09`。

分层交叉验证，每折只在训练行拟合均值与方差；后验概率是模型分布，不是检修结论。

### 漏判差异换位检验

两项同批研究的折外判读按样本编号配对；真值不符或缺轴承归属即停算（任务标failed并保存原因）。统计量为两类指定故障漏判件数绝对差的最大值；同一轴承的样本一起交换两侧判读，求换位后达到或超过实测差的概率。轴承不超过20个（或换位空间不大于抽样数）时精确枚举全部换位；轴承上百个时按固定种子分批随机抽样（默认20万种，单批内存受单元格上限约束），不枚举全部换位。每批内容完全确定并逐批落库：worker中断后按原版归属从断点批次恢复，失败重试不重复计数。同版算齐后页面才报告概率和换位总数。全部计算位于 `backend/src/services/permutation.py` 与 `compare.py`，前端不拟合、不估计。

失败态：业务字段缺失/非有限数值、参数越界、样本不足、退化特征或结构错误均明确拒绝或将任务标failed，错误消息保存在任务中。可回到来源或配置修正后重新执行，历史失败记录保留。

已知边界：独立同分布、特征条件独立和高斯类条件是假设；后验未校准。演示数据刻意有分离度，准确率不代表真实设备效果。使用分层折外验证，不提供外部最终测试集。

## 演示数据与一天剧本

固定seed=42，3个来源 ` TX-202611-01/02/03`，每来源240条，共720条业务记录；三个账号、首轮种子研究与首轮对照研究（folds=5）、每批次初始轴承归属v1（相邻两条样本同轴承，共120个轴承），以及首批的“首轮漏判换位检验”（指定故障：轴承磨损/转子偏心）。自然键检查后仅插入缺失数据，连跑seed不重复、不覆盖用户修改。`SEED_DEMO=true` 时启动自动执行；失败记录日志但不阻塞服务。首轮任务与换位检验同样由独立worker真实计算。

1. 09:00 负责人查看三份来源和720条样本。
2. 09:10 分析师选择 `TX-202611-01 秋季常规组`，核对 `acoustic-bayes-202611-01.csv`。
3. 09:15 在“声检批次”核对均方根振幅（`rms`）、频谱质心 Hz（`centroid`）、峭度（`kurtosis`）、复核类型（`label`），追加编号 `TX-NEW-001` 的样本。
4. 09:20 新建“十一月复核研究”，按默认参数冻结241条输入。
5. 09:21 独立worker消费Redis队列，返回实算结果与输入校验和。
6. 09:25 分析师查看专属诊断及逐行结果，并下载CSV复算。
7. 09:30 在“对比检验”选择首轮两项研究，按归属v1检验轴承磨损/转子偏心的漏判差异；现场复核后录入归属更正v2，旧检验仍按v1算齐。
8. 09:35 提交“十一月业务复核意见”，负责人核对并批准。
9. 09:40 viewer下载批准快照，查看审计中的worker完成与批准事件。

## 目录与本地开发

```text
frontend/src/api, stores, types, components/common, hooks, pages, router, utils, constants
backend/src/routes, controllers, services, models, schemas, middlewares, utils, constants, config
backend/scripts/seed_demo.py
backend/migrations/001_initial.sql
```

本地后端：Python3.11虚拟环境安装 `backend/requirements.txt`，设置 `DATABASE_URL`、`REDIS_URL`、`ARTIFACT_DIR`，在backend目录运行 `uvicorn src.main:app --reload`；另开终端运行 `python -m src.worker`。原生前端无需编译，推荐以Compose Nginx访问，保证 `/api/` 代理。前端为Google Fonts双字体、oklch色板，离线字体回退serif；1280/768/390响应布局。

| 环境变量 | 默认与说明 |
|---|---|
| COMPOSE_PROJECT_NAME | `acoustic-bayes`，隔离容器/网络/命名卷 |
| FRONTEND_PORT / BACKEND_PORT / DB_PORT | `18245 / 19245 / 17745` |
| SEED_DEMO | `true` |
| JWT_SECRET | `.env.example`演示值，部署前修改 |
| DATABASE_URL / REDIS_URL | Compose内部连接，定义在compose的env锚点 |
| ARTIFACT_DIR | `/artifacts`，后端worker共享 |

共享枚举：`backend/src/constants/enums.py` 与 `frontend/src/constants/enums.js` 都定义 admin/analyst/viewer、queued/running/completed/failed、draft/approved。后端service检查对应字符串；README为全量值说明。共享前端组件table/status/chart/business跨总览、结果、配置与复核复用；actions hook和format utils负责交互/格式。后端errors与rate_limit是两个中间件。

测试及截图在批根 `test-artifacts/gb-0041/`，不混入源码。独立算法oracle、HTTP完整流程和真实Playwright浏览器流程见该目录 `TESTING.md`。License：MIT。
