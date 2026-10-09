---
description: Compare function calling, Skills, and MCP through model output, task knowledge, and external capability integration, and see how the three can work together.
---

# Chapter 10: How Function Calling, MCP, and Skills Fit Together

## 10.1 Why are there three concepts?

The typical misconception is that these are competing solutions introduced by different vendors at different times, and you only need to choose one.

They are **three composable interface and content mechanisms**, not a technology stack in which every layer must depend on the next.

Start by asking **who is speaking in each case**:

| | Who is speaking | What they say |
|---|---|---|
| **Function Calling** | The model | “I want to call this function with these arguments.” |
| **MCP** | The tool service | “These are the functions I provide.” |
| **Skill** | The operating manual | “Use these tools and follow this procedure.” |

Different speakers, different counterparts, and different granularities explain the essential distinction.

### 10.1.1 Release milestones do not establish dependencies

```mermaid
flowchart TB
    FC["2023 · Function Calling"] --> MCP["2024 · MCP"]
    MCP --> SK["2025 · Agent Skill"]
```

These representative release milestones address different problems, not successive replacements: Function Calling lets a text-generating model request an external call; MCP reduces repeated integration work across applications; Agent Skills supply procedures for using available tools.

The timeline marks the releases of OpenAI Function Calling, MCP, and Anthropic Agent Skills. It does not date the origins of tool use, interface standardization, or reusable procedures. Their respective concerns are:

- Function calling addresses the **call interface**: the model and application need a structured way to express calls.
- MCP addresses repeated integration work by **standardizing** access to tools, resources, and prompt templates, so compatible applications can reuse server capabilities.
- Skills address repeated maintenance of task steps and standards by organizing **reusable knowledge and procedures**. They do not require tools to be connected through MCP first.

## 10.2 Identify the communicating parties

```mermaid
%%{init: {"flowchart": {"nodeSpacing": 12, "rankSpacing": 18, "padding": 8}}}%%
flowchart TB
    SK["3 · Skill procedure"] -.Optional.-> MCP["2 · MCP integration"]
    MCP -.Optional.-> FC["1 · Function Calling"]
```

Within the Skill layer, the agent scans and loads a knowledge module containing `SKILL.md`, scripts, and templates. Within MCP, Client and Server exchange JSON-RPC messages such as `tools/list` and `tools/call`. Within Function Calling, the model emits `tool_calls` JSON and the host returns tool messages. The cross-layer links are optional: a Skill may use MCP, and a host may translate MCP definitions and results to a model's function-calling format. These are bidirectional exchanges within each layer, not a mandatory three-step execution sequence.

Details of the illustrated steps and components:

- Knowledge module SKILL.md + scripts + templates

| Layer | Communicating parties | Nature | Granularity |
|---|---|---|---|
| Function Calling | Model ↔ host application | Format for an individual call | One function call |
| MCP | MCP client ↔ MCP server | Standardized tool packaging and discovery | A tool or set of tools |
| Skill | Agent ↔ knowledge module | Reusable packaging of procedures and standards | A complete class of tasks |

Notice the difference in granularity. Querying an order table is an **MCP tool**; code review or producing a data-analysis report is a **Skill**. A Skill may contain several steps, each of which may call multiple MCP tools. When an LLM drives the process, it commonly expresses its intent to call a tool through function calling or structured output.

## 10.3 Composition does not mean mandatory dependency

Counterexamples help reveal whether responsibilities have been confused:

```mermaid
%%{init: {"flowchart": {"nodeSpacing": 12, "rankSpacing": 18, "padding": 8}}}%%
flowchart TB
    S["Skill"] --> H["Host / Agent"]
    H --> M["MCP Client"]
    H --> LOCAL["Local function<br/>/ CLI / API"]
    F["Function<br/>Calling"] --> H
    RULE["Rule-based<br/>workflow /<br/>human action"] --> H

    style S fill:#e6f4ea
    style M fill:#e8f0fe
    style F fill:#fef7e0
```

Details of the illustrated steps and components:

- Skill Defines the procedure
- Host / Agent Selection and execution
- MCP Client Calls the server
- Function Calling Model proposes a call

All of these paths are possible:

- **Without native function calling**, a host can still trigger tools through structured text, rules, or human selection. The differences lie in reliability and adaptation cost.
- **MCP can work with function calling**. Many hosts convert MCP tools into model schemas, but MCP does not require this adaptation path. [Chapter 6](../02-mcp/06-mcp-vs-function-calling.md) examines that sequence in detail.
- **A Skill that requires external actions depends on the host providing the corresponding capabilities, not on a particular protocol**. It can use MCP, embedded functions, or other controlled integrations during execution.

Function calling with an executor can work on its own. A deterministic program can use MCP alone. A writing-only Skill can avoid external tools entirely. None of the three is a prerequisite for either of the others.

## 10.4 Three boundaries, three kinds of failure

| | Boundary | Typical failures |
|---|---|---|
| **Function Calling** | Model proposal → application execution | Wrong tool selected, semantically wrong arguments, unauthorized calls |
| **MCP** | Client → server | Incompatible versions, authentication failures, unknown outcomes after timeouts |
| **Skill** | Reusable knowledge → current task context | Incorrect activation, outdated instructions, missing script dependencies |

“The arguments are valid JSON,” “the server is reachable,” and “the Skill is loaded” each establish only that one stage passed. None proves that the whole task is complete.

## 10.5 A complete scenario connecting the three layers

The user asks in Chinese: **“帮我分析最近三个月的销售数据，找出下滑的产品线，给改进建议。”** In English: “Analyze sales data from the last three months, identify declining product lines, and suggest improvements.”

```mermaid
%%{init: {"flowchart": {"nodeSpacing": 10, "rankSpacing": 12, "padding": 6}}}%%
flowchart TB
    S0["Load matching Skill"]
    S1["Authorize data query"]
    S2["Fetch via MCP"]
    S3["Authorize execution"]
    S4["Analyze via MCP"]
    S5["Report from template"]
    S0 --> S1 --> S2 --> S3 --> S4 --> S5
```

Complete exchange, including phase notes:

| Participants | Message or action |
| --- | --- |
| User → Agent | Analyze sales data and suggest improvements |
| Agent → Skill layer | Scan Skill metadata |
| Skill layer → Agent (return) | Match the data-analysis report Skill |
| Agent → Skill layer | Load the SKILL.md body |
| Skill layer → Agent (return) | Procedure: fetch data → analyze trends → write from template |
| Note: Agent, MCP Servers | Step 1: Fetch data |
| Agent → Model | Task + procedure + available tool definitions |
| Model → Agent (return) | tool_calls: query_database(sql=...) |
| Agent → Agent | Validate query scope, arguments, and user authorization |
| Agent → MCP Client | Route the call |
| MCP Client → MCP Servers | tools/call → database Server |
| MCP Servers → MCP Client (return) | Query results |
| MCP Client → Agent (return) | Results |
| Agent → Model | Return results in a tool message |
| Note: Agent, MCP Servers | Step 2: Analyze trends |
| Model → Agent (return) | tool_calls: run_python(code=...) |
| Agent → Agent | Check execution permissions, isolation, and resource budgets |
| Agent → MCP Client | Route the call |
| MCP Client → MCP Servers | tools/call → Python executor Server |
| MCP Servers → MCP Client (return) | Analysis results |
| MCP Client → Agent (return) | Results |
| Agent → Model | Return results in a tool message |
| Note: Agent, Skill layer | Step 3: Write using the Skill template |
| Model → Agent (return) | Structured analysis report |
| Agent → User (return) | Return the report |

Within this process, the three responsibilities are:

- **The Skill guides the procedure**: fetch data, analyze it, then write the report using a template. State who defines business alert thresholds; an arbitrary percentage is not statistical significance.
- **MCP provides interfaces for capability discovery and invocation**: the client obtains tool lists from known servers, and the host filters them by authorization and task. Establishing a connection does not automatically place every tool in the model's context.
- **Function calling mediates the model's use of tools**: each `tool_calls` output and the corresponding results returned in `tool` messages.

The host must also validate which sales data the user may access, constrain SQL, isolate the Python executor, and retain the data's time range and source. Manage the versions of MCP 2026-07-28, the Agent Skills file format, and the model's tool API separately. An upgrade at any layer requires regression testing of the complete chain.

The diagram shows the successful path. If the query fails, do not proceed to generate sales conclusions. If the data covers only part of the requested period, state the actual scope. If the analysis script fails, retain the data already retrieved and report the missing step. A decline in sales does not establish its cause; improvement recommendations must distinguish conclusions supported by the data from hypotheses that still need testing.

## 10.6 Common mistakes

### 10.6.1 Treating them as three competing solutions

They can appear together or be used independently. First determine whether the problem concerns model output, capability integration, or procedure reuse.

### 10.6.2 Misstating the dependency direction

A more accurate description is that the host orchestrates capabilities according to Skill instructions; MCP standardizes some capability integrations; and function calling is a common way for a model to express tool selection. The mechanisms compose, but do not form a mandatory one-way dependency chain.

### 10.6.3 Assuming all three are required

Alternative implementation paths exist when any one is absent. Small projects may still need standardization or procedure reuse, so project size alone is not a sufficient criterion.

### 10.6.4 Confusing granularity

One Skill does not equal one tool. It can describe a whole class of tasks or simply organize writing standards. The format specifies neither whether tools are called nor how many calls are made.

### 10.6.5 Calling MCP “Anthropic's version of function calling”

MCP is neither an alternative implementation of function calling nor a protocol built on top of it. The same MCP server can serve different hosts. When a host uses a model tool interface, it can translate tool definitions into the provider's function-calling schema, but other invocation paths are possible.

### 10.6.6 Reciting definitions without explaining collaboration

When explaining the three mechanisms, walking through a concrete scenario that connects them usually communicates more than reciting three separate definitions.

## 10.7 Summary

1. **The three mechanisms compose; they do not form a mandatory dependency stack**.
2. **Identify the speaker to distinguish them quickly**: the model says “I want to call,” the service says “I provide,” and the manual says “follow this procedure.”
3. **Release dates do not establish dependencies**. These problems and approaches existed before the particular products were released.
4. **A host can follow a Skill to orchestrate MCP or other capabilities**. MCP tools can be triggered by a model proposal or a deterministic workflow; calls still need validation before execution.
5. **Their granularities differ substantially**: one call / one tool / a complete class of tasks.
6. **Not all three are necessary**. Function calling plus an executor can work on its own. Whether to introduce MCP or Skills depends on interface and procedure reuse, not a project-size threshold.
7. **The complete call chain must include authorization, failure recovery, and evidence for results**, rather than depicting only the successful path.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-tools-10) for this chapter’s sources, reading suggestions, and source notes.
