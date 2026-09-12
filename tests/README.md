# 墨问仙途 · 测试体系

三层结构：**代码实现 → 已部署产物** 全覆盖，共 442 项用例。

| 层 | 目录 | 工具 | 数量 | 测什么 |
|---|---|---|---|---|
| 后端单元 | `tests/backend` | pytest | 377 | 天道引擎的全部纯逻辑：数值/判定/经济/状态清洗/NPC/接口契约/修炼节奏 |
| 前端单元 | `tests/frontend` | vitest + happy-dom | 65 | 存档持久化、仙缘令编解码、前后端常量一致性 |
| 线上端到端 | `tests/online` | pytest + httpx | 23 | 打真实 Vercel：健康度、静态资源、坊市、用丹、SSE、真实 AI、结局回归 |

## 快速开始

```bash
# 本地全部单测
python -m pytest tests/backend -q          # 后端（pytest.ini 已配好，直接跑即可）
npx vitest run                             # 前端

# 线上端到端（默认打 production 别名）
set ONLINE_BASE_URL=https://mowen-xiantu.vercel.app
python -m pytest tests/online -q -s

# 只跑不花钱的部分（跳过真实 AI 调用，约 8 秒）
python -m pytest tests/online -q -s -m "not slow"
```

首次跑前端需要先装依赖：`pnpm i`（本项目统一用 pnpm，勿用 npm，否则会多出
`package-lock.json` 导致 Vercel 切换包管理器）；后端：`pip install -r requirements-dev.txt`。

> 线上用例文件名是 `test_online_e2e.py` —— pytest 默认只收集 `test_*.py`，
> 之前叫 `online_e2e.py` 时会被静默跳过（报 “no tests ran” 而非失败），改名后才被收集到。

## 设计约定

**1. 测试环境禁止触碰真实 AI。**
`tests/backend/conftest.py` 里把 `server.API_KEY` 强制置空，所有用例跑在本地演武路径上，
跑一万次也不会产生任何 token 费用。只有 `tests/online` 才碰真实模型，且用 `-m slow` 标记隔离。

**2. 随机性必须可控。**
conftest 里每个用例前固定 `random.seed`；需要精确命中档位时用 `monkeypatch.setattr(random, ...)`，
不允许出现「跑十次有一次红」的用例。

**3. 前后端常量不允许漂移。**
`tests/frontend/constants.spec.ts` 直接解析 `server.py` 里的 `REALM_TABLE`，
与前端 `EXP_MAX` 逐项比对。修为曲线一旦两边不一致，这条会立刻变红 —— 这类偏差在构建和运行期都不报错。

**4. 洗完的状态必须收敛。**
所有涉及 `sanitize_state` 的用例都验证了幂等性（洗一次 == 洗两次），
以及恶意/越界输入（超长字符串、非 dict、`1e999`、伪造灵根）被安全处理而非 500。

**5. 两条入口口径一致。**
`/api/act` 与 `/api/act/stream` 共用 `_postprocess_turn` 与 `_ending_payload`，
两者对同一输入必须给出同构结果 —— 测试里有专门的比对用例守着这条线。

**6. 玩家看见的数字必须是真数字。**
`tests/backend/test_11_cultivation.py` 不仅测系数，还断言「所有单键到底的路线都跑不赢
需要取舍的专注流」—— 否则玩家会立刻收敛到一键最优解，整套节奏设计形同虚设。
`tests/frontend/cultivation.spec.ts` 则解析 `server.py` 的 `ACTION_CULTIVATE_COEFF`
与 `CULTIVATE_STREAK_TABLE` 逐条比对前端展示表，并校验 `CultivateInfo` 覆盖后端 detail 的每个字段
（后端加了字段、前端没接 → 界面会静默少显示一项）。冲关成功率提示与掷骰共用
`breakthrough_rate`，避免「界面写 60%、实际掷 40%」这类最伤信任的偏差。
