---
description: Explains how human approval pauses and resumes execution, binds operation arguments, identities, and versions, and handles expiry, duplicate notifications, and environmental changes.
---

# Chapter 22: Human-in-the-Loop Approval and Interruptible Execution

## 22.1 How does waiting for approval differ from execution failure?

Waiting for approval is an expected control state; execution failure means a step did not complete as agreed. An approval wait must display the proposed operation and await a decision. A retry mechanism must not treat it as an exception and repeatedly execute it. A short pause can remain in-process. A long wait, or one that must survive process changes, needs persistent, recoverable state as in Chapter 21. The ask rules and approval callbacks in Chapter 20 are entry points, but a callback does not automatically provide a durable approval workflow.

## 22.2 Why involve a human?

MCP 2026-07-28 Tools<sup>[【285】](../../book/references.md#ref-285)</sup> recommends enabling people to deny tool calls and providing tool visibility, invocation indicators, and confirmation prompts. It uses **SHOULD** and explicitly does not mandate a particular interaction model. This is neither a protocol requirement to show a prompt for every call nor a credential that authorizes tool use. The harness must choose automatic execution, per-operation confirmation, or outright denial according to impact and preauthorized scope. Both complete automation and confirmation at every step have costs.

## 22.3 Designing interruption points: where to pause

Not every node is a useful interruption point. Production systems commonly place human checkpoints at the following boundaries:

- **Before irreversible or high-impact operations:** sending external communications, moving funds, deleting data, or merging into the main branch. Such actions cannot simply be undone after execution.
- **When the permission chain matches an ask rule or a tool requires user interaction** (Sections 20.2 and 20.3): the tool or organizational policy declares that the operation always requires confirmation.
- **When the model has insufficient confidence in its judgment:** for example, the reflection mechanism in Chapter 12 identifies significant uncertainty and asks a person for direction rather than guessing and continuing.
- **At important multi-agent coordination points:** for example, when a subtask's output needs human review before a downstream agent uses it.

Too few interruption points leave work insufficiently reviewed; too many cause confirmation fatigue. A model's self-reported confidence is not a calibrated risk probability. Approval triggers should also consider operational impact, authorization scope, missing evidence, and policy rules.

## 22.4 Implementing interruption: from exceptions to explicit state

Human-in-the-loop interruption commonly takes two implementation forms:

- **Callback-based:** at a step in the permission chain, such as the `canUseTool` callback in Section 20.2, the harness synchronously or asynchronously calls an external function, waits for approval or rejection, and then decides whether to execute. This suits short pauses where the caller can remain waiting.
- **Explicit suspension state:** save the approval wait as Chapter 17's `Interrupted` state, end the current execution, and release compute resources that can be reconstructed. LangGraph's `interrupt()` supports this pattern, but requires a checkpointer and a stable `thread_id`; cross-process recovery requires a durable backend. Resuming the same thread with `Command(resume=...)` **restarts the containing node from its beginning**. The resume value becomes available only when execution reaches `interrupt()`. Code before it therefore runs again. Actions such as sending approval notifications also need deduplication; a pause is not a memory snapshot at an arbitrary point in the program.

## 22.5 Designing the approval payload

The approval interface should show the actual objects, arguments, diff, and scope of impact, accompanied by a concise plan and evidence—not a request for hidden chain of thought. It should also explain what happens after approval or rejection. Return values should use explicit, schema-defined actions such as `approve`, `reject`, and `edit`, not truthiness conversions such as `bool("false")`. Approval after editing arguments requires revalidation, and the approver, version, and source must be written to the durable record.

## 22.6 Resuming from the interruption rather than starting over

An approval should bind the task ID, tool and version, normalized-argument digest, target-object version, approver identity, expiry, and a single-use identifier. On resumption, recheck permissions, budget, and target state. If those remain valid, continue the specific approved operation rather than having the model generate a new call that inherits the old approval.

If a payee account, file version, or permission changes during the wait, the original approval may be invalid and require replanning or renewed approval. Approval is not permanent authorization. Duplicate webhooks must not execute the same operation twice either; combine an approval-consumption record with business idempotency.

## 22.7 Asynchronous approval and long waits

Long approval waits should generally not occupy an entire session process. The harness saves the waiting state and the pending approval notification, then an independent dispatcher notifies the approver. A reply triggers recovery. Saving first and then sending can leave a task waiting forever if a crash occurs between the two; sending first and then saving can produce a reply that cannot be correlated. Store the waiting record and notification intent in the same transaction, retry delivery through an outbox of pending notifications, and deduplicate by approval ID. Timeout, rejection, and approval all need traceable state transitions.

## 22.8 Balancing human attention, cost, and efficiency

Human involvement adds waiting time and consumes approver attention. Low-risk, preauthorized repetitive operations are good candidates for automation; high-impact operations should retain confirmation tied to their specific targets. Only an authorized policy owner may expand automatic approval. A recent improvement in the model's success rate is not sufficient grounds for it to grant itself more authority. The permission modes in Chapter 20 are different host-provided policy combinations, not an efficiency dial that can be freely turned toward “more automatic.”

## 22.9 Common mistakes

- **Catching and swallowing the framework's interruption signal.** LangGraph's `interrupt()` uses a special exception internally to suspend execution. Business code must not swallow it as an ordinary failure. Requiring durable suspension state does not prohibit using exceptions to implement it.
- **Showing only a summary, without actual objects, normalized arguments, diffs, or evidence.** The approver cannot judge the impact, and approval can become habitual. Supply the basis for the decision, not private chain of thought.
- **Reducing the approval result to a Boolean.** This loses richer human feedback, such as “approved, but change these arguments.”
- **Blocking synchronously throughout a long approval wait.** This occupies unnecessary compute resources. Use the asynchronous release-and-resume pattern from Section 22.7.
- **Reusing old approval after replanning.** Environmental changes may require a new plan, but new arguments, targets, or tool versions require renewed authorization and cannot inherit the previous operation's approval.
- **Adding so many interruption points that every step asks a question.** This cancels out the efficiency benefits of automation. Choose interruption points by risk, as in Section 22.3.

## 22.10 Chapter summary

Human-in-the-loop handling is a recoverable control point, not a simple Boolean switch. Callbacks work for short pauses; long waits should persist state and release resources. On recovery, verify the operation bound to the approval, its permissions, and its object versions. Environmental changes can require replanning, but a new operation cannot inherit an old approval. Risk-based decisions and explicit arguments matter more than frequent prompts.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-agent-22) for this chapter’s sources, reading suggestions, and source notes.
