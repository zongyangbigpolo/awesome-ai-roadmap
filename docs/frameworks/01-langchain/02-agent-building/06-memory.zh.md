---
description: 按线程状态与跨线程 Store 设计记忆，区分上下文裁剪、状态删除、历史检查点清理和长期记忆权限治理。
---

# 第六章：LangChain 的短期记忆与长期记忆

## 6.1 应该记住什么

**记忆设计的第一步不是选数据库，而是确定作用域。**

假设用户正在规划杭州旅行：

| 信息 | 性质 | 归属 |
|---|---|---|
| 当前对话提到的日期、预算、下一步计划 | **只服务于这次任务** | 短期状态 |
| 一周后新建会话，Agent 仍知道他不吃辣、喜欢住地铁附近 | **跨会话仍然有效** | 长期记忆 |

```mermaid
%%{init: {"flowchart": {"nodeSpacing": 12, "rankSpacing": 18, "padding": 8}}}%%
flowchart TB
    A["当前线程进度"] --> B["State +<br/>Checkpointer"]
    C["未来其他线程仍可<br/>能用到的"] --> D["Store"]

    style B fill:#e8f0fe
    style D fill:#e6f4ea
```

图中各项的完整含义：

- 当前线程运行到了哪里
- 未来其他线程仍可能用到的 用户偏好与事实

## 6.2 短期记忆如何实现

`create_agent` 底层运行在 LangGraph 上。**Agent State 默认包含 `messages`**，也可以扩展订单号、当前步骤、工具调用次数等业务字段。

### 6.2.1 只有 State 还不够

**请求可能由不同服务实例处理，进程也可能重启**——因此需要 Checkpointer 持久化执行状态。

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

# Checkpointer 按 thread_id 保存线程内的 Agent State
agent = create_agent(
    model="<provider>:<your-model-id>",
    tools=[],
    checkpointer=InMemorySaver(),
)

# 两次调用复用同一个 thread_id，表示它们属于同一会话线程
config = {"configurable": {"thread_id": "chat-1001"}}

# 第一轮把用户姓名写入当前线程的 messages 状态
agent.invoke(
    {"messages": [{"role": "user", "content": "我叫小林"}]},
    config=config,
)

# 第二轮会先恢复同一线程之前保存的状态
result = agent.invoke(
    {"messages": [{"role": "user", "content": "我叫什么？"}]},
    config=config,
)
```

`InMemorySaver` 只适合本地演示。生产环境要换成持久化实现，否则进程退出后状态会丢失。

### 6.2.2 Checkpoint 保存的不只是聊天记录

**它保存的是图执行过程中的 State 快照**，因此还能支撑：

- 暂停恢复
- 人工审批
- 故障恢复

## 6.3 消息太多怎么办

Checkpointer 能保存历史，但每次是否把全部历史交给模型，要另外控制。消息越多，Token、延迟和干扰越大。

| 策略 | 作用 | 主要风险 |
|---|---|---|
| **仅在模型请求侧裁剪** | 只选择部分消息进入本次模型上下文，不提交状态更新 | **持久状态仍会继续增长** |
| **删除当前状态消息** | 通过 `RemoveMessage` 等更新当前 State | 后续上下文失去该信息，但**旧 checkpoint 可能仍保留原文** |
| **摘要** | 把早期历史压缩成简短语义摘要 | 可能遗漏细节或**逐轮失真** |

### 6.3.1 不能只按条数处理

- 客服 Agent 可能需要保护**当前工单和用户承诺**；
- 代码 Agent 可能需要保护**最新报错和修改记录**。

策略应同时考虑 Token 预算、消息角色和业务重要性（记忆压缩的通用方法见 [Agent 主题](../../../agent/README.zh.md)）。

还要保留工具调用协议的完整性：不能留下没有对应 AI 工具请求的 `ToolMessage`，也不能保留请求却删掉所需结果。摘要宜保留来源、未完成动作与不可丢失的承诺，而不只是泛化的聊天主题。合规删除则是另一条链路：当前 State、历史 checkpoint、Store、Trace、备份都需要按保留策略处理，`RemoveMessage` 不是物理擦除 API。

## 6.4 长期记忆如何实现

**新 `thread_id` 默认不会继承旧线程的 State——这是正确的线程隔离。** 如果某条信息需要跨线程使用，就应提炼后写入 Store。

### 6.4.1 Store 的定位结构

```
namespace = (tenant_id, user_id, memory_type)
key       = 某条记忆的稳定标识
value     = JSON 数据
```

| 读取方式 | 场景 |
|---|---|
| 精确读取 | **已知 key** |
| 向量搜索 | 需要从多条记忆中**按语义查找**（需配置向量索引） |

向量检索只是召回方式，不代表所有聊天记录都应该成为长期记忆。

### 6.4.2 长期记忆常见内容

| 类型 | 示例 |
|---|---|
| 用户事实与偏好 | 不吃辣、偏好中文、常用 Java |
| 历史经验 | 上次如何成功处理支付超时 |
| 经审核的工作规则 | 退款前必须核验订单归属；权威规则保留在受控策略库 |

这些分类有助于设计数据结构，但不意味着要把每段原始对话都永久保存。写入前仍要做**去重、脱敏、冲突处理和质量判断**。

用户偏好与安全策略必须分开存储和授权。模型从对话归纳出的「以后退款不用核验」不能覆盖系统的退款规则，否则长期记忆会把一次提示注入变成跨会话持续生效的权限漏洞。

## 6.5 如何跨线程读取

**工具可以通过 ToolRuntime 访问这些信息，但 `state`、`context` 和 `store` 仍要按作用域区分**（见 [第五章](05-tool-registration.zh.md)）：

| 入口 | 内容 |
|---|---|
| `runtime.state` | 当前线程的**短期状态** |
| `runtime.context` | **可信**用户身份和权限 |
| `runtime.store` | **跨线程**长期数据 |

```python
from dataclasses import dataclass

from langchain.tools import ToolRuntime, tool

@dataclass
class UserContext:
    # 用户身份由可信应用注入，不暴露给模型填写
    user_id: str
    tenant_id: str

@tool
def remember_preference(
    preference: str,
    runtime: ToolRuntime[UserContext],
) -> str:
    """保存当前用户明确要求记住的偏好。"""
    # namespace 将不同用户的长期记忆隔离开
    namespace = (runtime.context.tenant_id, runtime.context.user_id, "preferences")
    # key 为 main，本例只维护一条当前偏好记录
    runtime.store.put(namespace, "main", {"text": preference})
    return "偏好已保存"
```

这是工具片段，需像[第五章](05-tool-registration.zh.md)一样给 `create_agent` 接入 `context_schema=UserContext`、`store`，并在调用时传可信 `context`。模型只负责生成 `preference`，身份由已认证的应用注入，避免模型通过自填身份越权；业务服务仍需授权，namespace 本身不是安全隔离机制。

**两个不同 `thread_id` 的会话，在可信租户与用户身份相同且获得授权时，可访问同一个长期记忆 namespace**；其他用户或租户必须被服务端权限隔离。

## 6.6 什么时候写入长期记忆

长期记忆会带来收益，也会引入噪声、冲突和隐私风险；把每句闲聊都存进去通常得不偿失。

| 触发 | 写入时机 |
|---|---|
| 用户明确说「请记住」 | **主链路实时写入**，信息立即生效 |
| 普通对话中推断出的偏好和经验 | **会话结束后由后台任务**提炼、去重、脱敏再写入 |

**无论实时还是后台写入，都应保存来源、时间和置信度**，并支持更新、纠错和删除。

订单金额、账户余额和库存等实时事实仍应查询权威业务系统，不能用长期记忆代替真实数据库。

## 6.7 生产环境要注意什么

```mermaid
%%{init: {"flowchart": {"nodeSpacing": 12, "rankSpacing": 18, "padding": 8}}}%%
flowchart TB
    P1["① 数据能否可靠<br/>保存"]
    P2["② 这是谁的记忆"]
    P3["③ 维护记忆"]
    P4["④ 评估实际收益"]
    P1 --> P2 --> P3 --> P4

    style P2 fill:#fff3cd
```

图中各项的完整含义：

- ① 数据能否可靠保存 内存实现随进程退出而丢失 线上要数据库型 Checkpointer 和 Store 表结构与迁移纳入部署流程
- ② 这是谁的记忆 thread_id / tenant_id / user_id 必须来自可信身份体系 不信任模型生成的身份 不允许客户端随意指定别人的 namespace
- ③ 记忆会过时、冲突、被纠正 去重、更新、过期淘汰 支持用户查看/更正/导出/删除 敏感信息默认不记，需保存的加密并限权 日志与 Trace 不能成为另一个泄漏口
- ④ 记忆是否真的改善结果 不能只看写入了多少条

### 6.7.1 评测必须沿整条链路走

| 环节 | 检查 |
|---|---|
| 写入 | 这条信息**是否值得写入** |
| 召回 | 相关问题**能否召回**，无关问题**会不会误召回** |
| 使用 | 注入模型后**是否真正改善答案** |

只有写入、召回和使用三步都有效，记忆才不是一个不断膨胀的数据库。

## 6.8 旧 Memory 还能用吗

旧教程常见的 `ConversationBufferMemory`、`ConversationSummaryMemory` 属于 **Chain 时代的抽象**，目前主要位于 `langchain-classic`，适合维护存量项目。

**v1 新项目更推荐**：

| 职责 | 方式 |
|---|---|
| 管理线程内状态 | **AgentState + Checkpointer** |
| 管理跨线程长期记忆 | **Store + namespace/key** |
| 管理裁剪、摘要和写入策略 | **Middleware 或图节点** |

这套方式把状态作用域、持久化和记忆治理拆得更清楚，也更适合有工具调用、暂停恢复和多用户隔离要求的 Agent。

## 6.9 常见错误

### 6.9.1 先选数据库再想作用域

**第一步是判断这条信息是线程内的还是跨线程的。**

### 6.9.2 用 `InMemorySaver` 上生产

**进程退出状态全丢。**

### 6.9.3 以为 Checkpoint 只是聊天记录

**它是图执行的 State 快照**，正因如此才能支撑暂停恢复和人工审批。

### 6.9.4 把「能保存」等同于「都要塞给模型」

Token、延迟和干扰都会上升，**必须裁剪/删除/摘要**。

### 6.9.5 按固定条数裁剪

**当前工单、用户承诺、最新报错**这类消息不能被机械裁掉。

### 6.9.6 混淆裁剪与删除

仅裁剪模型请求不减少持久状态；删除当前 State 不等于删除历史 checkpoint。先说清改的是哪一层，再讨论恢复和隐私。

### 6.9.7 把所有聊天记录写进向量库

**向量检索只是召回方式**，不代表什么都该长期保存。

### 6.9.8 让模型生成 `user_id`

会被提示注入诱导访问他人数据，**身份必须来自可信 Context**。

### 6.9.9 用长期记忆代替权威数据库

**余额、库存、订单金额这类实时事实必须现查。**

### 6.9.10 记忆只写不治理

**没有去重、更新、过期和用户可删除能力**，记得越多风险越大。

### 6.9.11 评测只统计写入条数

**要看召回准确率和是否真的改善了答案。**

## 6.10 本章总结

1. **两条主线**：短期记忆是线程级 State，由 Checkpointer 按 `thread_id` 保存；长期记忆是跨线程数据，由 Store 按 namespace / key 管理；
2. **记忆设计第一步是确定作用域**，不是选数据库；
3. **Checkpoint 保存的是 State 快照**，因此还能支撑暂停恢复、人工审批、故障恢复；
4. **历史管理三策略**：请求侧裁剪（状态仍增长）、状态删除（历史 checkpoint 未必清除）、摘要（可能失真）；
5. **裁剪要按 Token 预算 + 消息角色 + 业务重要性**，不能只数条数；
6. **新线程不继承旧 State 是正确的隔离**，跨线程信息要提炼后写入 Store；
7. **Store 用 namespace + key 定位**，精确读取与向量搜索并存；
8. **ToolRuntime 三入口不可混用**：state / context / store；
9. **写入时机二分**：明确要求实时写，推断出的偏好后台提炼写；
10. **实时事实不能用长期记忆代替权威系统**；
11. **生产四关**：可靠持久化 → 可信身份隔离 → 记忆治理与隐私 → 沿写入/召回/使用三步评测；
12. **旧 Memory 类属 Chain 时代**，已入 `langchain-classic`。

LangChain 的记忆按作用域分成两套机制：线程内用 State 和持久化 Checkpointer 保存执行进度，线程外用 Store 积累经过筛选的信息。namespace 负责定位，服务端授权负责防止串户；裁剪、摘要和保留策略则分别控制模型上下文与存储增长。

## 参考资料

<!-- centralized-bibliography -->
本章的参考资料、阅读建议与来源说明见[集中参考资料章节](../../../book/references.zh.md#reading-frameworks-06)。
