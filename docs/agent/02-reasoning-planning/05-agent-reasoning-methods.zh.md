---
description: 比较 CoT、Self-Consistency、ToT、程序辅助推理与验证器搜索，区分参数训练和推理时计算，并说明收益的评估条件。
---

# 第五章：Agent 的模型推理与搜索方法

## 5.1 推理方法与 Agent 范式的关系

ReAct 和 CoT 是二选一吗？不是。前者组织行动与反馈循环，后者可以用于循环中的一次求解。推理方法和 Agent 设计范式位于不同层级：

> **推理方法决定一次求解如何生成、搜索和选择候选，Agent 范式决定系统如何组织模型、工具、状态和环境反馈。**

```mermaid
flowchart TB
    W[Workflow 编排层] --> A[Agent 控制范式]
    A --> R[模型推理与搜索方法]
    A --> T[Tools]
    A --> M[State / Memory]

    A --> REACT[ReAct]
    A --> PLAN[Plan-and-Execute]
    A --> REFLEX[Reflection / Reflexion]

    R --> COT[CoT]
    R --> DECOMP[任务分解]
    R --> SC[Self-Consistency]
    R --> TOT[ToT / Graph Search]
    R --> VER[Verifier-guided Reasoning]
```

例如：

- ReAct 每轮可以使用内部链式推理选择 Tool；
- Plan-and-Execute 的 Planner 可以使用任务分解或搜索多个计划；
- Reflection 可以使用验证器、评分模型或 Self-Refine；
- Workflow 的路由节点可以使用简单分类，不一定需要复杂推理。

推理方法是 Agent 的“局部决策算法”，Agent 范式是“系统级控制循环”。

## 5.2 什么是模型推理

中文“推理”常对应两个不同概念：**inference** 是用已训练模型进行前向计算和生成，**reasoning** 是围绕问题进行多步求解。本章讨论的是后者以及支持它的推理时计算策略；不是每次模型 inference 都包含可辨认的多步 reasoning。

以常见的自回归语言模型为例，给定输入 `x`，输出 Token 序列 `y = (y₁, …, yₙ)` 的联合概率可以分解为：

$$
P(y \mid x)=\prod_{t=1}^{n}P(y_t \mid x,y_1,\ldots,y_{t-1})
$$

所谓“推理方法”，并不是在模型外突然增加一种神秘能力，而是通过以下方式改变推理时的计算过程：

- 生成中间表示；
- 将问题分解为子问题；
- 采样多个候选；
- 搜索多个推理路径；
- 调用程序、检索或工具获得外部反馈；
- 使用验证器评分；
- 根据反馈重新生成。

放到工程系统里，更接近下面这个过程：

> **生成候选 → 获取证据 → 验证候选 → 分配更多计算 → 选择结果**

还要区分计算发生在哪个阶段：

| 机制 | 改变什么 | 应用这一步时是否更新参数 |
|---|---|---|
| SFT、RL、蒸馏 | 模型的生成策略或验证器 | 是 |
| CoT 提示、上下文示例 | 当前条件输入和中间生成 | 否 |
| Self-Consistency、ToT、Best-of-N | 候选数量、搜索状态和选择方式 | 通常否 |
| 工具反馈、Reflexion 记忆 | 证据、上下文和下一次尝试 | 否 |

训练得到的推理模型也可以使用推理时搜索。测试反馈用于挑选或修订候选，与将测试分数作为 RL 奖励、经优化器更新参数，是两件不同的事。

## 5.3 推理方法的总体分类

可以按照推理时组织计算的方式，将常见方法分成四组。它们不是必须逐级升级的能力阶梯，也可以组合使用：

```mermaid
flowchart TB
    R[推理时计算] --> S1[单路径推理]
    R --> S2[任务分解]
    R --> S3[多候选采样]
    R --> S4[搜索与验证]

    S1 --> DIRECT[Direct Answer]
    S1 --> COT[Chain of Thought]

    S2 --> LTM[Least-to-Most]
    S2 --> PS[Plan-and-Solve]

    S3 --> SC[Self-Consistency]
    S3 --> BON[Best-of-N]

    S4 --> TOT[Tree of Thoughts]
    S4 --> GOT[Graph of Thoughts]
    S4 --> MCTS[MCTS 类搜索]
    S4 --> VG[Verifier-guided]
```

在相同基础模型、相近单次生成长度下，可以粗略比较成本：

| 类型 | 候选路径数 | 是否搜索 | 成本 |
|---|---:|---:|---:|
| Direct Answer | 1 | 否 | 低 |
| CoT | 1 | 否 | 低到中 |
| 任务分解 | 1 条主路径，多个子问题 | 有限 | 中 |
| Self-Consistency | 多条 | 仅聚合 | 中到高 |
| ToT / Graph Search | 多条 | 是 | 高 |
| Verifier-guided Search | 多条 | 是，并反复评分 | 高 |

更复杂的方法并不必然更好。只有当额外推理计算能够提升任务成功率时，增加复杂度才有价值。

表中不是固定排序：一次长内部推理可能比多个短候选更贵；批处理能减少往返但不会消除生成 Token，缓存也不会让验证免费。

## 5.4 Direct Answer：建立最简单基线

Direct Answer 让模型直接生成答案，不显式要求中间推理。

这是输出与提示方式，不是“模型未推理”的证明。带隐藏推理预算的模型，即便只输出一句话，也可能消耗大量内部推理 Token。

适合：

- 简单事实提取；
- 文本改写和格式转换；
- 分类边界清晰的任务；
- 模型已经非常熟悉的模式；
- 延迟要求严格的场景。

工程上先看它能不能当基线。直接调用如果已经稳定，就没必要再引入多轮推理、搜索或 Agent 循环。

```mermaid
flowchart LR
    X[输入] --> M[Model]
    M --> Y[答案]
```

## 5.5 Chain of Thought：链式推理

这里主要讨论 CoT 在推理层的机制与局限。CoT 与行动规划的边界见[第十一章](11-llm-agent-planning.zh.md)；可记录的轨迹不等于隐藏 CoT，见[第十四章](../05-production/14-agent-evaluation.zh.md)。

### 5.5.1 基本思想

CoT（Chain of Thought）通过生成中间推理步骤，将复杂问题拆成一条连续推理链：

```mermaid
flowchart LR
    Q[问题] --> S1[中间步骤 1]
    S1 --> S2[中间步骤 2]
    S2 --> S3[中间步骤 N]
    S3 --> A[答案]
```

从概率角度，可以将中间推理序列表示为辅助变量 $z$；当只关心最终答案时将其边缘化：

$$
P(y\mid x)=\sum_z P(y,z\mid x)
$$

单路径 CoT 实际上只生成一个候选推理 $z$，再根据它得到答案 $y$。

上式是联合分布的分解，不意味着一次 CoT 解码真的枚举了所有 `z`，也不意味着这些文本就是模型全部内部计算。原始 CoT prompting 通过带步骤的示例改变输入，不包含参数更新。

### 5.5.2 Few-shot CoT 与 Zero-shot CoT

#### Few-shot CoT

在 Prompt 中提供带有中间步骤的示例，让模型模仿类似推理结构。

#### Zero-shot CoT

不提供完整示例，只通过简短指令要求模型分步骤分析。历史上常见的提示是“Let's think step by step”。

对经过推理训练的模型，反复要求“逐步思考”不一定继续带来收益。[OpenAI 的 reasoning 提示建议](https://developers.openai.com/api/docs/guides/reasoning-best-practices)明确建议对其推理模型使用直接、清晰的任务指令，不必额外要求展开 CoT；这不是所有厂商、模型版本的统一规定。

### 5.5.3 不要把完整思维链当作可靠解释

模型生成的 CoT：

- 可能是事后合理化；
- 可能省略真正影响答案的因素；
- 可能包含看似合理但错误的步骤；
- 不一定忠实反映模型内部计算；
- 可能泄露不应公开的上下文或安全信息。

因此，生产系统不应把“输出了很长的推理过程”等同于“答案可靠”。

面向用户更推荐展示：

- 简洁的结论依据；
- 引用和数据来源；
- 结构化计划；
- Tool Call 与 Observation；
- 可复现的计算过程；
- 验证结果。

> **可验证证据比冗长思维链更重要。**

### 5.5.4 CoT 的适用场景

- 多步数学和逻辑问题；
- 需要顺序分析的规则任务；
- 简单任务分解；
- 单条路径足以解决的问题。

### 5.5.5 CoT 的局限

- 早期步骤错误会沿整条链传播；
- 只探索一条路径；
- 推理越长不代表越正确；
- 增加 Token、延迟和成本；
- 缺少外部验证时容易自洽但错误。

[原论文](https://arxiv.org/abs/2201.11903)的收益来自所测模型、规模和算术／常识／符号任务。不能由此推断任何模型加一句提示就具备可靠规划能力；解释忠实性研究也发现模型可能受提示中的偏置信息影响，却不在 CoT 中承认这些影响。

## 5.6 任务分解：先把问题变小

任务分解的目标不是让推理变得更长，而是降低每个子问题的难度。

### 5.6.1 Least-to-Most

Least-to-Most Prompting 先识别较简单的子问题，再按依赖顺序逐步解决。

```mermaid
flowchart LR
    Q[复杂问题] --> D[分解子问题]
    D --> E1[解决基础子问题]
    E1 --> E2[利用 E1 解决下一问题]
    E2 --> EN[解决最终问题]
```

适合：

- 后续步骤依赖前一步结果；
- 问题可以自然分解；
- 单次直接推理容易遗漏条件。

### 5.6.2 Plan-and-Solve

Plan-and-Solve 先生成解题计划，再按计划完成推理：

```text
Plan:
1. 提取已知条件
2. 确定需要计算的变量
3. 选择公式
4. 执行计算并检查
```

它与 Agent 层的 Plan-and-Execute 有相似思想，但层级不同：

| Plan-and-Solve | Plan-and-Execute |
|---|---|
| 主要用于模型内部问题求解 | 用于 Agent 系统任务执行 |
| 子步骤通常仍是模型推理 | 步骤可以调用 Tool、Agent 或 Workflow |
| 通常不改变外部环境 | 会接收真实环境反馈 |
| 生命周期较短 | 可以长时间运行并持久化状态 |

### 5.6.3 分解失败

分解也可能引入问题：

- 子问题划分错误；
- 忽略跨步骤约束；
- 子问题答案无法组合；
- 分解成本超过任务本身；
- 错误中间结果被后续步骤当作事实。

因此，分解后仍需要检查依赖、接口和最终组合结果。

## 5.7 Self-Consistency：多路径投票

Self-Consistency 不只生成一条推理链，而是通过采样得到多个候选路径，再聚合最终答案。

```mermaid
flowchart TB
    Q[问题] --> P1[推理路径 1]
    Q --> P2[推理路径 2]
    Q --> P3[推理路径 N]
    P1 --> V[答案聚合]
    P2 --> V
    P3 --> V
    V --> A[最终答案]
```

若第 $i$ 条路径得到答案 $y_i$，多数投票可以写为：

$$
\hat{y}=\arg\max_y \sum_{i=1}^{N} I(y_i=y)
$$

其中 $I$ 是指示函数。

实际实现需先规范化答案：单位、等价分数、大小写和选项编号不能直接按原始字符串比较；并列票或无法解析时要有明确回退规则。票数比例不是经过校准的正确概率。即使随机采样相互独立，同一模型仍可能把大部分概率放在同一个错误答案上，投票无法消除这种系统性偏差。

例如候选分别回答“0.5 小时”“30 分钟”和“60 分钟”，前两个应归为同一答案。但如果它们一个算单程、一个算往返，不能只靠数值换算就合并；答案规范化也要保留题目要求的对象和范围。

### 5.7.1 为什么可能有效

如果不同推理路径犯错的方式不完全相同，正确答案可能在多个样本中更稳定地出现。

### 5.7.2 适用条件

- 最终答案可以规范化和比较；
- 存在多个合理推理路径；
- 单次采样错误率较高；
- 可以接受多倍模型调用成本。

### 5.7.3 局限

- 多数意见也可能一致地错误；
- 候选之间可能高度相关，缺乏真正多样性；
- 开放式文本很难直接投票；
- 调用成本约随样本数增长；
- 不能替代外部事实验证。

## 5.8 Best-of-N：生成多个候选再评分

Best-of-N 生成 $N$ 个候选，再由评分函数或验证器选择最佳结果：

$$
y^*=\arg\max_{y_i} V(x,y_i)
$$

其中 $V$ 是验证器或评分函数。

```mermaid
flowchart TB
    Q[输入] --> C1[候选 1]
    Q --> C2[候选 2]
    Q --> CN[候选 N]
    C1 --> V[Verifier / Reward Model]
    C2 --> V
    CN --> V
    V --> BEST[最高分候选]
```

Self-Consistency 与 Best-of-N 的区别：

| Self-Consistency | Best-of-N |
|---|---|
| 通常聚合最终答案 | 对完整候选进行评分 |
| 不一定需要独立验证器 | 依赖评分函数或验证器 |
| 适合答案可投票的任务 | 适合候选质量可比较的任务 |

验证器可以是：

- 单元测试；
- 编译器；
- 数学或规则检查器；
- 模拟器；
- 人工评分；
- 独立模型；
- LLM-as-a-Judge。

应优先使用更接近真实成功标准的验证器。

必须区分“候选中存在正确答案”和“系统选中了正确答案”。用隐藏答案挑选出的 oracle best-of-N 只能作为上界，不能充当可部署系统的结果；增加 `N` 还可能更容易找到骗过评分器的候选。最终验收数据应与搜索时可用的测试、评分器训练数据分开。

## 5.9 Tree of Thoughts：搜索推理树

ToT（Tree of Thoughts）把中间推理状态视为搜索树节点，在每个节点扩展多个候选，并进行评分、选择或回溯。

原方法由外部控制程序维护部分解、候选和搜索策略，模型负责生成与评价文本单元。仅在一个 Prompt 中写“请模拟三位专家并回溯”，不等于实现了原论文的 ToT 搜索。

```mermaid
flowchart TB
    S0[初始状态] --> A1[候选 A]
    S0 --> B1[候选 B]
    S0 --> C1[候选 C]

    A1 --> A2[扩展 A1]
    A1 --> A3[扩展 A2]
    B1 --> B2[扩展 B1]
    B1 --> B3[扩展 B2]
    C1 --> C2[扩展 C1]

    A2 --> E[评分与选择]
    A3 --> E
    B2 --> E
    B3 --> E
    C2 --> E
```

### 5.9.1 核心组件

ToT 通常需要：

1. **State**：当前部分解；
2. **Generator**：扩展候选 Thought；
3. **Evaluator**：评价候选状态；
4. **Search Algorithm**：BFS、DFS、Beam Search 等；
5. **Termination**：找到可接受解或预算耗尽。

### 5.9.2 与 CoT 的区别

| CoT | ToT |
|---|---|
| 一条推理链 | 多条候选路径 |
| 通常不回溯 | 可以回溯 |
| 成本较低 | 成本较高 |
| 适合线性问题 | 适合需要探索和选择的问题 |

### 5.9.3 适用场景

- 规划问题；
- 谜题和组合搜索；
- 创意方案探索；
- 存在多个中间决策的复杂任务；
- 可以评价部分解质量的任务。

### 5.9.4 局限

- 分支数量可能指数增长；
- 中间状态评分可能不可靠；
- LLM 生成的候选可能缺乏多样性；
- 搜索成本和延迟高；
- 很多现实任务难以定义部分解评分。

生产实现通常使用 Beam Width、最大深度和预算剪枝限制搜索规模。

原论文主要实验是 24 点、创意写作和迷你填字，不是通用网页或仓库任务。其 24 点结果（GPT-4，CoT 4%、ToT 74%）对应特定题集、搜索宽度和评测设置，且预算不等同于单路径 CoT。报告的 74% 来自广度优先搜索、`b=5`、编号 901–1000 的 100 局；CoT 的 4% 是采样平均。部分解可评分是重要前提：若评分器把需要暂时绕路的正确分支过早剪掉，搜索反而找不到解。

## 5.10 Graph of Thoughts 与图搜索

树结构假设每条路径独立向下展开，但现实推理可能需要合并、复用或循环改进中间结果。

Graph of Thoughts 将推理状态组织成图：

```mermaid
flowchart LR
    A[候选分析 A] --> M[合并]
    B[候选分析 B] --> M
    C[外部证据 C] --> M
    M --> R[修订]
    R --> V[验证]
    V -->|不通过| R
    V -->|通过| O[输出]
```

图结构可以表达：

- 多个候选合并；
- 中间结果复用；
- 依赖关系；
- 反复修订；
- 并行推理。

但其编排和状态管理比 ToT 更复杂。工程系统可以用 DAG Workflow、状态图或任务图实现部分相似操作，不过这些通用图结构不自动等于原论文的 Graph of Thoughts：任务依赖图描述“先做什么”，推理图还要定义候选如何变换、合并和评分。不能仅凭采用了图框架就沿用论文的实验结论。

## 5.11 MCTS 类推理搜索

蒙特卡洛树搜索类方法通常在候选状态之间反复执行：

1. Selection：选择值得探索的节点；
2. Expansion：生成新的候选步骤；
3. Evaluation：评估候选质量；
4. Backpropagation：将评价反馈到祖先节点。

Selection 通常依据访问次数与累计价值，在探索新分支和利用高分分支之间取舍；Evaluation 可以是 rollout 的环境回报，也可以是学习到的价值估计。这里的 Backpropagation 是向树节点回传统计量，不是神经网络反向传播，不自动更新 LLM 权重。

```mermaid
flowchart LR
    S[Selection] --> E[Expansion]
    E --> V[Evaluation]
    V --> B[Backpropagation]
    B --> S
```

这类方法适合：

- 存在明确目标或奖励信号；
- 可以逐步模拟结果；
- 搜索空间较大；
- 允许较高推理预算。

对于开放式知识任务，如果评价函数本身不可靠，复杂搜索可能只是更昂贵地放大评分偏差。

行动搜索还要求状态可复制、重置或模拟。回溯文本不会撤销已发送的邮件、支付或数据库写入；有副作用的真实工具不能直接当作任意分支的 rollout 环境。

## 5.12 Program-Aided Reasoning：把计算交给程序

模型不擅长稳定执行长算术、精确状态更新和复杂符号操作。Program-Aided Language Models（PAL）或 Program of Thoughts（PoT）让模型生成程序，再由解释器执行。

```mermaid
sequenceDiagram
    participant U as User
    participant M as Model
    participant R as Runtime
    participant P as Python / Solver

    U->>M: 提交计算问题
    M-->>R: 生成程序或表达式
    R->>R: 安全校验
    R->>P: 在沙箱中执行
    P-->>R: 返回计算结果或错误
    R->>M: 提供执行结果
    M-->>U: 解释答案
```

适合：

- 数学计算；
- 数据分析；
- 日期和单位换算；
- 逻辑约束求解；
- 可以编码为程序的问题。

需要注意：

- 代码必须在受限沙箱中执行；
- 禁止未授权网络和文件访问；
- 应设置时间、内存和输出限制；
- 程序可执行不代表问题建模正确。

程序执行也不自动保证数值精确。例如计算单价 19.99 元、数量 3 的金额，应先明确使用十进制金额或整数分、在什么阶段舍入；二进制浮点可能产生表示误差，十进制计算也仍受精度与舍入规则约束。更关键的是，若模型漏掉折扣或税费，程序只是把错误公式算得更稳定。验收应同时覆盖业务公式、数值规则和边界输入。

## 5.13 Tool-Augmented Reasoning：用环境提供事实

推理不能弥补缺失或过时的事实。Agent 可以通过搜索、数据库、代码执行器和领域 API 获取外部证据。

```mermaid
flowchart LR
    Q[问题] --> M[Model]
    M --> NEED{需要外部信息?}
    NEED -->|否| A[生成答案]
    NEED -->|是| T[调用 Tool]
    T --> O[Observation]
    O --> M
```

工程上的工作主要集中在这些环节：

- 判断何时需要 Tool；
- 选择正确 Tool；
- 生成有效参数；
- 验证 Tool 返回值；
- 处理冲突和失败；
- 在答案中引用证据。

内部推理强，不代表外部事实可靠。对于实时信息和高风险事实，应优先使用权威数据源。

## 5.14 Retrieval-Augmented Reasoning

RAG 为模型提供外部知识，但检索与推理之间仍需协同：

1. 判断问题是否需要检索；
2. 生成或改写查询；
3. 检索候选文档；
4. 过滤和重排；
5. 基于证据推理；
6. 检查引用是否支持结论；
7. 必要时继续检索。

```mermaid
flowchart LR
    Q[问题] --> QR[Query Rewrite]
    QR --> RET[Retrieval]
    RET --> RR[Re-rank]
    RR --> REASON[Reason with Evidence]
    REASON --> CHECK{证据充分?}
    CHECK -->|否| QR
    CHECK -->|是| ANSWER[带引用答案]
```

多轮检索可以提升覆盖率，但也可能增加噪音。系统应记录哪些结论由哪些证据支持。

## 5.15 Verifier-Guided Reasoning

Verifier-Guided Reasoning 使用验证器指导候选生成、选择和修订。

设候选集合为 $Y=\lbrace y_1,\dots,y_N\rbrace$，验证器分数为：

$$
v_i=V(x,y_i,e_i)
$$

其中 $e_i$ 可以是测试结果、执行轨迹或外部证据。

结果奖励模型（ORM）通常给完整候选评分；过程奖励模型（PRM）给中间步骤提供更细的信号，适合剪枝或分配搜索预算。[Let's Verify Step by Step](https://arxiv.org/abs/2305.20050)研究了过程监督训练验证器。训练 PRM 会更新其参数，使用固定 PRM 排序候选则不会；PRM 分数也不是形式化证明，多个相关步骤的分数不能不加假设地乘成“答案正确概率”。

系统可以：

- 选择最高分候选；
- 对低分候选生成反馈；
- 将反馈加入下一轮生成；
- 在达到阈值后停止。

```mermaid
flowchart TB
    G[Generator] --> C[Candidates]
    C --> V[Verifier]
    V --> PASS{达到阈值?}
    PASS -->|是| OUT[输出]
    PASS -->|否| FB[结构化反馈]
    FB --> G
```

### 5.15.1 验证信号优先级

可以按任务成功条件考虑以下信号，而不是把它们当作固定可信度排名：

1. 真实环境结果；
2. 单元测试、编译器和约束求解器；
3. 确定性规则与 Schema；
4. 专门训练的 Reward Model；
5. 独立 LLM Judge；
6. 同一模型自我评分。

验证器越接近真实任务成功标准，搜索越有意义。

Schema 只能保证形状，编译器只能检查相应语言规则，测试通过只覆盖已测行为。安全策略或确定性验收失败应形成硬拒绝，不能被模型的综合高分抵消。

### 5.15.2 Verifier 的风险

- Reward Hacking；
- 评分规则覆盖不完整；
- Judge 偏好冗长或特定表达；
- Generator 与 Judge 共享相同错误；
- 对抗性候选欺骗评分器。

因此，不应只优化单一自动分数，还需要抽样人工审核和线上结果监控。

## 5.16 Self-Refine 与 Reflection

Self-Refine 让模型对自己的输出生成反馈，再根据反馈修订：

> **Generate → Feedback → Refine**

它是推理时的反馈修订方法，也可以作为第四章 Reflection 控制环的一部分。固定的“生成—点评—修订”循环仍可以是 Workflow；是否构成自主 Agent，要看模型是否动态决定行动路径，而不是只看有没有循环。

| 推理层 Self-Refine | Agent 层 Reflection |
|---|---|
| 优化一个候选输出 | 优化动作、轨迹或整个任务 |
| 生命周期通常较短 | 可以跨多个工具步骤 |
| 状态较少 | 保存任务状态和 Observation |
| 不一定调用外部工具 | 通常结合真实环境反馈 |

## 5.17 Reasoning Models 与推理时扩展

Reasoning Model 通常经过强化多步推理的后训练，应用不一定需要手工要求其输出冗长 CoT。例如 [DeepSeek-R1 技术报告](https://arxiv.org/abs/2501.12948)讨论了 RL 激励推理行为和蒸馏。模型能生成检查、回退式文本，不代表服务内部必然运行 ToT 或 MCTS；未公开的架构细节不应从回答外观反推。

推理时扩展（Inference-time Scaling）指为困难问题分配更多推理计算，例如：

- 增加内部推理预算；
- 生成更多候选；
- 使用搜索；
- 增加验证与修订轮次；
- 调用更多工具或模拟器。

可以将总推理预算抽象为：

$$
B=(T,N,D,K)
$$

其中：

- $T$：Token 或内部推理预算；
- $N$：候选数量；
- $D$：搜索深度；
- $K$：验证或修订轮数。

预算越高不意味着结果必然越好。系统需要根据任务难度动态分配计算，而不是对所有请求使用最大推理强度。

[推理时计算分配研究](https://arxiv.org/abs/2408.03314)显示，顺序修订与并行搜索的相对收益随题目难度改变。这个结论支持测量后路由，而不是仅凭模型自报“有信心”缩减预算；更高风险时应先加强验收和审批，并非自动加大搜索树。

运行时要决定的是：让一个候选多想一会儿，还是多生成几个候选再挑选。增加单次思考预算 `T` 与增加候选数 `N` 不是同一件事；前者给一条路径更多思考空间，后者还需要比较和验证候选。具体控制接口见 [LLM 第 17 章 §17.6.7](../../llm/04-prompt-reliability/17-cot.zh.md)。选择哪种方案，应按 §5.22 的方法固定总预算，把验证开销也算进去，再比较任务成功率与延迟。

工具调用前后的状态不能随意丢弃。OpenAI 不公开原始 CoT；Claude 返回的 thinking 内容可能是完整文本，也可能是摘要，取决于模型版本和接口。为继续工具调用，应保留并原样传回协议要求的 reasoning/thinking 状态项，包括不透明项。

保留这些协议数据，不等于把推理正文写进普通审计日志，更不能把它当作可靠证据。审计按[第 14 章 §14.7.1](../05-production/14-agent-evaluation.zh.md)依靠工具调用、可见观察、状态变化和专门生成且允许记录的简短理由，不要求模型暴露接口未公开的私有推理。

答案只有一句话，不代表这次调用便宜。OpenAI 的 reasoning token 按输出 token 计费，也占用上下文窗口，核算 `T` 的实际开销时不能漏掉这部分用量。

## 5.18 Adaptive Reasoning：按难度分配预算

Adaptive Reasoning 先估计任务难度或置信度，再选择推理策略：

```mermaid
flowchart TB
    Q[输入] --> E[难度与风险评估]
    E -->|简单、低风险| D[Direct Answer]
    E -->|中等| C[CoT / Decomposition]
    E -->|答案可聚合| S[Self-Consistency]
    E -->|复杂搜索| T[ToT / Graph Search]
    E -->|可验证、高风险| V[Verifier-guided]
```

动态路由可以降低平均成本：

- 简单问题直接回答；
- 中等问题采用单路径推理；
- 高难任务增加候选和验证；
- 高风险任务强制使用工具、规则或人工审核。

难度路由本身也需要评估，避免模型过度自信地把困难问题判断为简单问题。

## 5.19 推理方法如何嵌入 Agent 范式

| Agent 范式 | 可使用的推理方法 |
|---|---|
| ReAct | Direct、CoT、Tool-Augmented Reasoning |
| Plan-and-Execute | Decomposition、Plan-and-Solve、ToT、DAG Planning |
| Reflection | Self-Refine、Best-of-N、Verifier-guided |
| Reflexion | Reflection + 情景记忆 |
| Orchestrator-Workers | Decomposition、Routing、Parallel Sampling |
| Evaluator-Optimizer | Best-of-N、Verifier-guided、Self-Refine |

一种完整组合可能是：

```mermaid
flowchart TB
    G[目标] --> AR[Adaptive Reasoning Router]
    AR --> P[Planner<br/>Decomposition + ToT]
    P --> E[Executor<br/>ReAct + Tools]
    E --> V[Verifier<br/>Tests + Rules]
    V -->|局部失败| E
    V -->|计划失败| P
    V -->|通过| S[Synthesizer<br/>Best-of-N]
    S --> FINAL[最终成稿与证据核验]
    FINAL --> OUT[输出结果或报告未通过项]
```

最后一次综合也可能引入新错误，所以前面的测试通过不代表新生成的答案自动通过。成稿仍要核对引用、数值和任务约束；若未通过，按剩余预算修订或报告未完成。

## 5.20 如何选择推理方法

| 任务特征 | 推荐方法 |
|---|---|
| 简单、稳定、低风险 | Direct Answer |
| 需要顺序分析 | CoT |
| 可以拆成依赖子问题 | Least-to-Most / Plan-and-Solve |
| 单次答案不稳定且可投票 | Self-Consistency |
| 能生成多个候选并客观评分 | Best-of-N |
| 存在多个中间决策和回溯 | ToT |
| 中间结果需要合并和复用 | Graph / DAG Reasoning |
| 计算或符号操作较多 | PAL / PoT |
| 依赖实时或外部事实 | Tool-Augmented / Retrieval-Augmented |
| 有明确测试或规则 | Verifier-Guided |
| 输入难度差异很大 | Adaptive Reasoning |

还应考虑：

- 任务风险；
- 延迟目标；
- Token 和费用预算；
- 是否存在可靠验证器；
- 是否允许并行；
- 是否需要外部事实；
- 错误是否可逆。

## 5.21 生产级推理控制器

一个能落地的推理控制器通常至少有这些环节：

```mermaid
flowchart TB
    IN[Input] --> SAFE[输入与权限检查]
    SAFE --> ROUTER[难度 / 风险路由]

    ROUTER --> GEN[Candidate Generator]
    GEN --> TOOLS[Tools / Retrieval / Code]
    TOOLS --> GEN

    GEN --> VERIFY[Verifier]
    VERIFY --> SCORE[评分、置信度与证据检查]
    SCORE --> DEC{满足标准?}

    DEC -->|是| OUT[Answer + Evidence]
    DEC -->|否，可改进| REFINE[Refine / Search]
    REFINE --> GEN
    DEC -->|预算耗尽| PARTIAL[报告部分结果与限制]
    DEC -->|高风险| HUMAN[Human Review]

    GEN -.Trace.-> OBS[Observability]
    VERIFY -.Metrics.-> OBS
```

推理系统不只负责生成，还要负责验证、预算分配和失败报告。

## 5.22 推理质量评估

不能只看最终答案是否“像是正确”。至少应评估：

| 指标 | 含义 |
|---|---|
| Task Success | 是否真正完成任务 |
| Accuracy | 结论是否正确 |
| Evidence Grounding | 结论是否有证据支持 |
| Tool Correctness | Tool 选择和参数是否正确 |
| Robustness | 输入变化后是否保持稳定 |
| Calibration | 置信度是否与正确率匹配 |
| Latency | 推理和工具执行耗时 |
| Cost | Token、模型和工具费用 |
| Search Efficiency | 扩展了多少无效候选 |
| Safety | 是否越权或产生危险动作 |

对于 Agent，还应同时评估结果和轨迹：

- 最终答案正确，但是否调用了不必要的高风险工具？
- 任务完成了，但是否通过偶然路径成功？
- 多轮推理是否真正改善结果？
- 验证器是否能发现关键错误？

比较 Self-Consistency 和 Best-of-N 时，可以先让两者使用同一组候选，再分别投票和评分，从而区分“生成了更好的候选”与“选择器更有效”。评估完整系统时，还应计入内部推理、验证器、检索和修订成本，报告同预算下的成功率，而不只比较最终输出长度。

## 5.23 常见误区

### 误区一：推理过程越长，答案越正确

长输出可能只是重复或错误扩散。应通过验证结果而不是长度判断质量。

### 误区二：CoT 是所有任务的默认最佳方案

简单任务可能因额外推理而变慢，甚至出现过度分析。

### 误区三：多采样一定能提高正确率

如果多个样本共享相同偏差，多数投票仍会错误。

### 误区四：LLM Judge 就是客观验证器

LLM Judge 仍可能偏置、被欺骗或与生成器共享盲点。

### 误区五：搜索算法可以弥补错误评价函数

搜索会优化评价函数。如果评价标准错误，更强搜索可能更高效地找到“高分但错误”的答案。

### 误区六：暴露完整 Thought 才算可解释

生产可解释性更应依赖证据、动作、状态、引用和可复现验证。

## 5.24 设计检查表

### 任务分析

- 问题是否真的需要复杂推理？
- 能否拆成更简单的确定性步骤？
- 是否缺少外部事实或实时数据？
- 是否存在可执行的成功标准？

### 策略选择

- 单路径是否足够？
- 多候选能否被可靠聚合或评分？
- 是否需要搜索和回溯？
- 是否可以使用程序或 Tool 替代语言推理？

### 验证

- 是否有编译器、测试、规则或权威数据源？
- Judge 是否独立于 Generator？
- 是否检查引用与结论的一致性？
- 是否防范 Reward Hacking？

### 预算与终止

- 最大候选数是多少？
- 最大搜索深度是多少？
- 最大验证和修订轮数是多少？
- 超时或预算耗尽时如何报告？

### 安全与隐私

- 是否避免暴露隐藏思维链？
- 推理上下文是否包含敏感信息？
- 生成的程序是否在沙箱中运行？
- 高风险结论是否需要人工审核？

## 5.25 本章总结

可以按作用区分这些方法，而不是把它们看成固定的成本或能力排名：

1. **Direct Answer**：直接生成；
2. **CoT**：沿一条路径分步推理；
3. **Decomposition**：将复杂问题拆成子问题；
4. **Self-Consistency / Best-of-N**：生成并聚合多个候选；
5. **ToT / Graph Search**：搜索、评分和回溯多个路径；
6. **Program / Tool / Retrieval-Augmented**：引入外部计算和事实；
7. **Verifier-Guided**：用可验证反馈选择和改进结果；
8. **Adaptive Reasoning**：按难度、风险和预算动态选择方法。

这些方法最终服务于 Agent 的系统控制：

> **Agent 范式决定何时思考、行动和停止；推理方法决定每次决策投入多少计算以及如何选择结果。**

## 参考资料

- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903)
- [Large Language Models are Zero-Shot Reasoners](https://arxiv.org/abs/2205.11916)
- [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171)
- [Least-to-Most Prompting Enables Complex Reasoning in Large Language Models](https://arxiv.org/abs/2205.10625)
- [Tree of Thoughts: Deliberate Problem Solving with Large Language Models](https://arxiv.org/abs/2305.10601)
- [Graph of Thoughts: Solving Elaborate Problems with Large Language Models](https://arxiv.org/abs/2308.09687)
- [PAL: Program-aided Language Models](https://arxiv.org/abs/2211.10435)
- [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651)
- [Plan-and-Solve Prompting](https://arxiv.org/abs/2305.04091)
- [Program of Thoughts Prompting](https://arxiv.org/abs/2211.12588)
- [Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting](https://arxiv.org/abs/2305.04388)
- [Let's Verify Step by Step](https://arxiv.org/abs/2305.20050)
- [DeepSeek-R1](https://arxiv.org/abs/2501.12948)
- [Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters](https://arxiv.org/abs/2408.03314)
- [s1: Simple test-time scaling](https://arxiv.org/abs/2501.19393)
- [OpenAI: Reasoning best practices](https://developers.openai.com/api/docs/guides/reasoning-best-practices)
- [OpenAI: Reasoning models](https://developers.openai.com/api/docs/guides/reasoning)
- [Amazon Bedrock: Extended thinking](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-extended-thinking.html)（thinking 返回形式与工具调用时的状态回传要求）
- [Python 3.13: decimal — 精度、舍入与十进制计算](https://docs.python.org/3.13/library/decimal.html)
