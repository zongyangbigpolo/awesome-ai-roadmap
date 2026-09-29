# AI 知识图谱

[English](README.md) | **简体中文**

这是一份英文优先、配有完整简体中文版的 AI 工程面试手册，覆盖模型原理、应用开发和生产治理。每个主题既解释概念，也讨论选型条件、失败场景和工程取舍，方便从基础问答深入到系统设计。文档按“主题 → 子模块 → 章节”组织，通过 MkDocs Material 发布为可搜索的 Wiki。

从头阅读可进入[中文书稿目录](docs/book/README.zh.md)，依次阅读前言、九篇正文和书末附页。网站与电子书共用章节源文件，在线阅读照旧。

日常内容修改先从英文主稿开始，对应的中文同步更新在**同一个 PR** 中审阅。CI 检查翻译是否齐全、配对版本是否过期，不会偷偷翻译整本书或自动刷新过期记录。合并后分别更新网站与两种语言的 EPUB 下载工件。不必为网页和 EPUB 各改一份稿，也不提交生成的 `.epub`；流程不会自动上传 KDP。

**下载 EPUB：** 打开 [Build EPUB 工作流](https://github.com/zongyangbigpolo/awesome-ai-roadmap/actions/workflows/epub.yml)，选择成功的运行，在 Artifacts 中选择 `ai-engineering-interview-en-epub` 或 `ai-engineering-interview-zh-CN-epub`，解压即可得到对应语言的 `.epub` 和构建记录。工件最长保留 90 天；过期后维护者可点 **Run workflow** 重建。依赖安装后，本地可运行 `python3 scripts/build_epub.py --language en` 或 `--language zh-CN`，详见[维护说明](book/README.zh.md)。**格式有效不等于具备 KDP 上架资格或已完成人工排版验收**。

**在线阅读：** [English](https://zongyangbigpolo.github.io/awesome-ai-roadmap/) | [简体中文](https://zongyangbigpolo.github.io/awesome-ai-roadmap/zh/)

**作者：** [Polo Li](https://github.com/zongyangbigpolo) · **许可：** [CC BY 4.0](LICENSE)

> **中文技术审校：2026-09-15；英文优先双语迁移：2026-09-20。** 技术版本、实验条件和资料核验时间见各章正文；编辑日期不表示所有接口都重新更新到了该日版本。

## 总体策略图

九个主题按“模型能力 → 协议接口 → 应用架构 → 框架实现 → 生产治理 → 现场交付”组织，共 143 个知识章节，每章都有英文和中文版。

```mermaid
flowchart TB
    subgraph L1["第一层 · 模型与多模态能力"]
        LLM["LLM · 23 章<br/>Transformer / 训练 / 推理 / 部署"]
        MM["多模态 AI · 10 章<br/>视觉 / 语音 / 图像与视频生成"]
    end

    subgraph L2["第二层 · 协议与接口"]
        TOOLS["Tools · 15 章<br/>Function Calling / MCP / Skill / A2A / 安全"]
    end

    subgraph L3["第三层 · 应用架构"]
        AGENT["Agent · 25 章<br/>Harness / 规划 / 记忆 / 编码 / 后训练"]
        RAG["RAG · 22 章<br/>索引 / 检索 / 多模态 / 结构化查询"]
    end

    subgraph L4["第四层 · 框架实现"]
        FW["框架与编排 · 23 章<br/>LangChain / LlamaIndex / DSPy / Semantic Kernel"]
    end

    subgraph L5["第五层 · 生产与治理"]
        ENG["AI Engineering · 13 章<br/>评测 / 可观测性 / 发布 / SLO / 成本"]
        SAFE["AI 安全与治理 · 10 章<br/>威胁 / 隔离 / 红队 / 审计"]
    end

    subgraph L6["第六层 · 现场交付"]
        FDE["FDE · 2 章<br/>发现 / 验收 / 集成 / 交付 / 复用"]
    end

    LLM --> MM
    LLM --> TOOLS
    TOOLS --> AGENT
    LLM --> RAG
    MM --> AGENT
    MM --> RAG
    AGENT --> FW
    RAG --> FW
    FW --> ENG
    ENG --> SAFE
    ENG --> FDE
    SAFE --> FDE
    FDE -.现场反馈.-> FW
    AGENT -.风险输入.-> SAFE
    RAG -.风险输入.-> SAFE
    RAG -.知识增强.-> AGENT
```

这是知识组织与阅读顺序，不是请求调用链，也不是必须逐层采用的技术栈。评测、安全和客户验收应从需求设计阶段参与，而不是等模型或应用做完后再补。

## 主题目录

| 层次 | 主题 | 目录 | 状态 |
|---|---|---|---|
| 底层原理 | LLM 相关知识点 | [`docs/llm/`](docs/llm/README.zh.md) | 23 章 |
| 模型能力 | 多模态 AI | [`docs/multimodal/`](docs/multimodal/README.zh.md) | 10 章 |
| 协议接口 | Tools 相关知识点 | [`docs/tools/`](docs/tools/README.zh.md) | 15 章 |
| 应用架构 | Agent 相关知识点 | [`docs/agent/`](docs/agent/README.zh.md) | 25 章 |
| 应用架构 | RAG 相关知识点 | [`docs/rag/`](docs/rag/README.zh.md) | 22 章 |
| 框架实现 | AI 框架与编排 | [`docs/frameworks/`](docs/frameworks/README.zh.md) | 23 章 |
| 生产工程 | AI Engineering / LLMOps | [`docs/engineering/`](docs/engineering/README.zh.md) | 13 章 |
| 安全治理 | AI 安全与治理 | [`docs/safety/`](docs/safety/README.zh.md) | 10 章 |
| 现场交付 | FDE | [`docs/fde/`](docs/fde/README.zh.md) | 2 章 |

完整目录、跨主题归属约定与推荐阅读路径见 [`docs/README.md`](docs/README.zh.md)。每个主题 README 维护子模块入口与模块关系，每个子模块 README 维护具体章节顺序。

## 如何用于面试准备

先按目标岗位选择主题，不必从头背完 143 章。复习一个概念时，合上文档解释它如何工作，再换一个约束试着推演：数据变大、延迟变紧、权限变化或工具失败后，原来的方案还成立吗？讲不清的部分再回到对应章节和原始资料。

系统设计题需要把几个主题连起来：例如企业知识助手不止涉及 RAG，还涉及工具权限、离线评测、发布回滚和客户验收。项目题则应结合自己实际做过的工作；文中的假设案例只用于练习设计和追问。

## 文档质量

仓库提供 `scripts/check_docs.py` 与 `scripts/check_mermaid.mjs`，用于检查章节编号、标题、代码与数学围栏、禁用 LaTeX 宏、内部链接、导航计数和 Mermaid 语法。写作与贡献约定见 [`CONTRIBUTING.md`](CONTRIBUTING.zh.md)，来源选择、引用和纠错方式见[编辑规范](docs/editorial-policy.zh.md)。
