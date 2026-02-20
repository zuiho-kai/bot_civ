# SR-P2：SOUL.md 深度人格

> 状态：待开发
> 对应 IR：IR-M6.2 P2
> 已确认决策：DC-3（共存 personality_json 优先）、DC-4（M6.2 不做预设模板）、DC-5（M6.2 只读展示）

---

## 1. 功能目标

为 Agent 引入结构化人格定义（SOUL schema），替代单一 `persona` 文本字段，使 Agent 在对话中表现出稳定、有深度的人格特征。M6.2 阶段实现后端 schema + prompt 注入 + 前端只读展示。

---

## 2. SOUL Schema 定义（Pydantic）

文件：`server/app/api/schemas.py`，新增 `SoulPersonality` 类

```python
class SoulPersonality(BaseModel):
    """SOUL 结构化人格定义 — M6.2 Lenient 模式"""
    model_config = {"extra": "ignore"}  # 未知字段忽略 + warning log

    values: Optional[list[str]] = None           # 核心价值观（1~5 条）
    speaking_style: Optional[str] = None         # 说话风格描述
    knowledge_domains: Optional[list[str]] = None  # 擅长领域
    emotional_tendency: Optional[str] = None     # 情感倾向
    catchphrases: Optional[list[str]] = None     # 口头禅（0~3 条）
    relationships: Optional[dict[str, str]] = None  # 对其他 Agent 的态度
    taboos: Optional[list[str]] = None           # 行为禁区（0~3 条）
```

### 2.1 Lenient 校验规则

| 场景 | 处理 | 日志 |
|------|------|------|
| 所有字段缺失（空 `{}`） | 合法，等同无 personality_json | 无 |
| `values` 超 5 条 | 截断为前 5 条 | `WARNING SoulPersonality.values 超限: N 条，截断为 5` |
| `catchphrases` 超 3 条 | 截断为前 3 条 | 同上模式 |
| `taboos` 超 3 条 | 截断为前 3 条 | 同上模式 |
| 未知字段（如 `hobby`） | 忽略（`extra="ignore"`） | `WARNING SoulPersonality: 忽略未知字段 {'hobby'}` |
| `relationships` 引用不存在的 Agent name | **400 拒绝** | 无（直接返回错误） |
| 字段类型错误（如 `values` 传 int） | **422 Pydantic 校验失败** | 无（FastAPI 自动返回） |

### 2.2 Validator 实现

```python
@model_validator(mode="before")
@classmethod
def log_extra_fields(cls, data):
    if isinstance(data, dict):
        known = {"values","speaking_style","knowledge_domains",
                 "emotional_tendency","catchphrases","relationships","taboos"}
        extra = set(data.keys()) - known
        if extra:
            logger.warning("SoulPersonality: 忽略未知字段 %s", extra)
    return data

@model_validator(mode="after")
def lenient_truncate(self):
    for field, limit in [("values", 5), ("catchphrases", 3), ("taboos", 3)]:
        val = getattr(self, field)
        if val is not None and len(val) > limit:
            logger.warning("SoulPersonality.%s 超限: %d 条，截断为 %d", field, len(val), limit)
            setattr(self, field, val[:limit])
    return self
```

### 2.3 Relationships 业务校验

在 API 层（`agents.py`）执行，不在 Pydantic 内：

```python
async def _validate_relationships(personality_json: dict, db: AsyncSession):
    rels = personality_json.get("relationships", {})
    if not rels:
        return
    result = await db.execute(select(Agent.name))
    existing_names = {row[0] for row in result.all()}
    invalid = set(rels.keys()) - existing_names
    if invalid:
        raise HTTPException(400, f"relationships 引用不存在的 Agent: {invalid}")
```

## 3. DB 字段变更

文件：`server/app/models/tables.py`，`Agent` 类新增一行

```python
personality_json = Column(JSON, nullable=True)  # SOUL 结构化人格（M6.2）
```

位置：`stamina` 字段之后、`created_at` 之前。

> 无需 migration — Agent 表当前不存在于生产环境，`create_all` 直接建出带新字段的表。

## 4. API 变更

### 4.1 Schema 扩展（`schemas.py`）

```python
# AgentCreate 新增
personality_json: Optional[dict] = None

# AgentUpdate 新增
personality_json: Optional[dict] = None

# AgentOut 新增
personality_json: Optional[dict] = None
```

### 4.2 CRUD 改动（`agents.py`）

**`create_agent()`**：
1. 若 `data.personality_json` 非 None，用 `SoulPersonality(**data.personality_json)` 校验
2. 调用 `_validate_relationships()` 校验 relationships
3. 校验通过后 `agent.personality_json = soul.model_dump(exclude_none=True)`

**`update_agent()`**：
1. 同上校验流程
2. `personality_json` 传 `None` 不清空（exclude_unset）；传 `{}` 清空为空对象

### 4.3 接口行为不变

- GET `/agents/` — 返回含 `personality_json` 字段（可为 null）
- GET `/agents/{id}` — 同上
- DELETE `/agents/{id}` — 无变化

## 5. System Prompt 注入

文件：`server/app/services/agent_runner.py`

### 5.1 新增结构化人格模板

```python
SOUL_PROMPT_TEMPLATE = """你是 {name}，一个聊天群里的成员。

## 你的人格档案
- 核心价值观：{values}
- 说话风格：{speaking_style}
- 擅长领域：{knowledge_domains}
- 情感倾向：{emotional_tendency}
- 口头禅：{catchphrases}
- 行为禁区：{taboos}
{relationships_block}
规则：
- 用自然、口语化的方式说话，严格符合你的说话风格和人格
- 回复简短（1-3句话），像真人聊天
- 不要自称AI或机器人
- 可以用 @名字 提及其他群成员
- 适当使用你的口头禅，但不要每句都用
- 绝对不做行为禁区中列出的事"""
```

### 5.2 注入逻辑改动

`AgentRunner.__init__()` 新增 `personality_json` 参数：

```python
def __init__(self, agent_id, name, persona, model, personality_json=None):
    ...
    self.personality_json = personality_json
```

`generate_reply()` 中 system_msg 构建逻辑：

```python
if self.personality_json:
    pj = self.personality_json
    system_msg = SOUL_PROMPT_TEMPLATE.format(
        name=self.name,
        values="、".join(pj.get("values", [])) or "无特别设定",
        speaking_style=pj.get("speaking_style", "自然随意"),
        knowledge_domains="、".join(pj.get("knowledge_domains", [])) or "无特别设定",
        emotional_tendency=pj.get("emotional_tendency", "中性"),
        catchphrases="、".join(pj.get("catchphrases", [])) or "无",
        taboos="、".join(pj.get("taboos", [])) or "无",
        relationships_block=_format_relationships(pj.get("relationships", {})),
    )
else:
    system_msg = SYSTEM_PROMPT_TEMPLATE.format(name=self.name, persona=self.persona)
```

`_format_relationships()` 辅助函数：

```python
def _format_relationships(rels: dict[str, str]) -> str:
    if not rels:
        return ""
    lines = "\n".join(f"  - {name}：{attitude}" for name, attitude in rels.items())
    return f"\n- 人际关系：\n{lines}\n"
```

### 5.3 AgentRunnerManager 传参

`get_or_create()` 签名新增 `personality_json=None`，透传给 `AgentRunner`。

调用方（`chat.py:delayed_send`、`agent_runner.py:batch_generate`）从 `Agent` 对象取 `personality_json` 传入。

## 6. 前端变更

### 6.1 类型扩展（`web/src/types.ts`）

```typescript
export interface Agent {
  // ... 现有字段 ...
  personality_json?: SoulPersonality | null
}

export interface SoulPersonality {
  values?: string[]
  speaking_style?: string
  knowledge_domains?: string[]
  emotional_tendency?: string
  catchphrases?: string[]
  relationships?: Record<string, string>
  taboos?: string[]
}
```

### 6.2 AgentCard 只读展示（`web/src/pages/AgentManager.tsx`）

`AgentCard` 组件在 `ac-persona` 下方新增 SOUL 人格展示区：

- 有 `personality_json` 时：逐字段展示非空项（价值观、说话风格、擅长领域、情感倾向、口头禅、行为禁区、人际关系），每项一行 label + value
- 无 `personality_json` 时：仍显示 `persona` 文本（向后兼容）
- M6.2 不做编辑功能，纯只读

## 7. 错误处理

| 场景 | 处理方式 | HTTP 状态码 |
|------|----------|-------------|
| `personality_json` 字段类型错误 | Pydantic 自动校验失败 | 422 |
| `relationships` 引用不存在的 Agent | `_validate_relationships()` 拒绝 | 400 |
| 超限字段（values > 5 等） | lenient 截断 + warning log | 200/201（正常返回） |
| 未知字段 | 忽略 + warning log | 200/201（正常返回） |
| 空 JSON `{}` | 合法，存入 DB | 200/201 |
| `personality_json` 为 null | 不存储，使用 persona fallback | 200/201 |
| DB 写入失败 | 事务回滚，返回 500 | 500 |

## 8. 改动清单（函数级）

| 文件 | 函数/类 | 改动 |
|------|---------|------|
| `server/app/models/tables.py` | `Agent` 类 | 新增 `personality_json = Column(JSON, nullable=True)` |
| `server/app/api/schemas.py` | 新增 `SoulPersonality` | Pydantic model + lenient validators |
| `server/app/api/schemas.py` | `AgentCreate` | 新增 `personality_json: Optional[dict] = None` |
| `server/app/api/schemas.py` | `AgentUpdate` | 新增 `personality_json: Optional[dict] = None` |
| `server/app/api/schemas.py` | `AgentOut` | 新增 `personality_json: Optional[dict] = None` |
| `server/app/api/agents.py` | `create_agent()` | 新增 SoulPersonality 校验 + `_validate_relationships()` |
| `server/app/api/agents.py` | `update_agent()` | 同上 |
| `server/app/api/agents.py` | 新增 `_validate_relationships()` | 校验 relationships 引用的 Agent 是否存在 |
| `server/app/services/agent_runner.py` | 模块顶层 | 新增 `SOUL_PROMPT_TEMPLATE` + `_format_relationships()` |
| `server/app/services/agent_runner.py` | `AgentRunner.__init__()` | 新增 `personality_json` 参数 |
| `server/app/services/agent_runner.py` | `AgentRunner.generate_reply()` | system_msg 构建分支：有 personality_json 用 SOUL 模板，否则用 persona |
| `server/app/services/agent_runner.py` | `AgentRunnerManager.get_or_create()` | 新增 `personality_json` 参数透传 |
| `web/src/types.ts` | `Agent` 接口 | 新增 `personality_json?: SoulPersonality \| null` |
| `web/src/types.ts` | 新增 `SoulPersonality` 接口 | 7 个可选字段 |
| `web/src/pages/AgentManager.tsx` | `AgentCard` 组件 | 条件渲染 personality_json 只读展示 |

## 9. 测试用例

### 9.1 单元测试（UT）

文件：`tests/test_soul_personality.py`

```
test_soul_empty_json_is_valid()
  — SoulPersonality(**{}) 不抛异常，所有字段为 None

test_soul_full_valid_json()
  — 传入所有字段合法值，model_dump() 返回完整 dict

test_soul_values_truncate_to_5()
  — values 传 8 条 → 截断为 5 条，assert len(soul.values) == 5

test_soul_catchphrases_truncate_to_3()
  — catchphrases 传 6 条 → 截断为 3 条

test_soul_taboos_truncate_to_3()
  — taboos 传 5 条 → 截断为 3 条

test_soul_unknown_fields_ignored()
  — 传入 {"hobby": "coding", "values": ["善良"]} → hobby 被忽略，values 保留

test_soul_type_error_rejected()
  — values 传 [1, 2, 3] → Pydantic ValidationError

test_validate_relationships_invalid_agent(db_session)
  — relationships 引用 "不存在的Agent" → HTTPException 400

test_validate_relationships_valid_agent(db_session)
  — relationships 引用已存在的 Agent name → 不抛异常

test_validate_relationships_empty(db_session)
  — relationships 为空 dict → 不抛异常
```

文件：`tests/test_agent_runner_soul.py`

```
test_system_prompt_with_personality_json()
  — 构造 AgentRunner(personality_json={...})
  — 断言 system_msg 包含 "核心价值观" 和 "说话风格"，不包含旧模板的 "你的人格设定"

test_system_prompt_without_personality_json()
  — 构造 AgentRunner(personality_json=None)
  — 断言 system_msg 包含 "你的人格设定"（旧模板），不包含 "核心价值观"

test_format_relationships_empty()
  — _format_relationships({}) 返回空字符串

test_format_relationships_with_data()
  — _format_relationships({"小明": "好友"}) 返回包含 "小明：好友" 的字符串
```

### 9.2 系统测试（ST）

```
ST-1: 创建带 personality_json 的 Agent
  — POST /agents/ 传入完整 personality_json
  — 断言 201，返回体含 personality_json
  — GET /agents/{id} 断言 personality_json 一致

ST-2: 更新 personality_json
  — PUT /agents/{id} 传入新 personality_json
  — 断言 200，返回体 personality_json 已更新

ST-3: personality_json 为 null 时向后兼容
  — 创建不带 personality_json 的 Agent
  — 断言 AgentRunner 使用旧 SYSTEM_PROMPT_TEMPLATE

ST-4: relationships 引用不存在的 Agent 被拒绝
  — POST /agents/ 传入 relationships: {"幽灵Agent": "敌对"}
  — 断言 400，错误信息含 "不存在的 Agent"

ST-5: lenient 截断不影响创建
  — POST /agents/ 传入 values 含 10 条
  — 断言 201，返回体 values 长度 == 5
```

---

## 10. Schema 演进路线图

| 阶段 | 模式 | 行为 |
|------|------|------|
| M6.2 | Lenient | 超限截断 + warning log，未知字段忽略，空 JSON 合法 |
| M6.3 | Strict | 超限拒绝 400，未知字段拒绝 400，新增 `version` 字段 |
