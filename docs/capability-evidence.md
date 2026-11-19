# Capability comparison: BEAR and related systems

All sources were read on 2026-10-30. Versions are listed in section 3. Marks for other systems rest only on the cited primary sources (official docs, the project repository, or the paper). ND means not documented.

Marks follow one rule per row. A mark is Partial when the capability exists but differs in a way a reviewer would care about. Each Partial entry in section 2 says how it differs.

## 1. Compact table

| Feature | Vector-store metadata filters (LlamaIndex `MetadataFilters`, Chroma `where`) | LangChain tool retrieval | LlamaIndex tool retrieval | ITR (Franko) | Hermes Agent tool search | NeMo Guardrails | BEAR |
|---|---|---|---|---|---|---|---|
| A. Hard gate declared on each item (all required tags in context) | Partial | No | No | No | Partial | No | Yes |
| B. Soft path beside the gate | Partial | Partial | Partial | Partial | Partial | No | Yes |
| C. One schema for instructions and tools | Partial | No | No | Partial | No | No | Yes |
| D. Mandatory items exempt from budget or top-k | No | Partial | Yes | Partial | Yes | No | Yes |
| E. Declared conflicts or supersedes, resolved deterministically | No | No | No | No | Partial† | No | Yes |
| F. Declared dependencies with closure | No | No | No | No | Partial† | No | Yes |
| G. Stated formal properties of selection, with tests | No | No | No | Partial | Partial | No | Yes |
| H. Same rules enforced at execution (allow, approve, block) | No | Partial‡ | Partial | No | Partial | Partial | Yes |
| I. Selection decision and reason given to the agent | No | Partial | No | Partial | Partial | No | Yes |
| J. Decision records that can be replayed or verified | No | Partial | No | No | Partial | Partial | Yes |

† Comes from Hermes skills, a separate mechanism for instruction documents. Tool search alone has neither feature and would be No. See section 4, item 1.

‡ Through LangChain's agent middleware (`HumanInTheLoopMiddleware`), not the tool retriever. See section 5.

BEAR column (from the project description, not researched here). These are the BEAR features behind each row.
- A. `required_tags`
- B. Soft scope plus a similarity threshold
- C. One item schema
- D. Mandatory items exempt from the cut (0.4.x)
- E. `conflicts_with` and `supersedes`
- F. `requires`, with closure
- G. Properties P1 to P6, checked on 2,000 random corpora
- H. `bear.gate` with allow, approve or block, in the Hermes plugin
- I. The Hermes plugin's annotations and withheld-tool notice
- J. `bear.audit` and `verify-audit`

## 2. Evidence

### 2.1 Vector-store metadata filters (LlamaIndex `MetadataFilters`, Chroma `where`)

Sources read for this column.
- [L1] LlamaIndex `vector_stores/types.py`, tag v0.14.25. https://github.com/run-llama/llama_index/blob/v0.14.25/llama-index-core/llama_index/core/vector_stores/types.py
- [L2] LlamaIndex `vector_stores/utils.py` (in-memory filter evaluation), tag v0.14.25. https://github.com/run-llama/llama_index/blob/v0.14.25/llama-index-core/llama_index/core/vector_stores/utils.py
- [L3] LlamaIndex `vector_stores/simple.py`, tag v0.14.25. https://github.com/run-llama/llama_index/blob/v0.14.25/llama-index-core/llama_index/core/vector_stores/simple.py
- [L4] LlamaIndex API reference, vector store. https://developers.llamaindex.ai/python/framework-api-reference/storage/vector_store/
- [C1] Chroma docs, Metadata Filtering (page metadata says last modified 2026-02-26). https://docs.trychroma.com/docs/querying-collections/metadata-filtering

| Row | Mark | Evidence |
|---|---|---|
| A | No | Filters belong to the query, not to the records. In LlamaIndex the query object carries `filters: Optional[MetadataFilters] = None` [L1, line 257]. Chroma says "The `where` argument in `get` and `query` is used to filter records by their metadata" [C1]. A record cannot state "admit me only if the context holds tags X and Y". The `ALL` operator does not do this either. `ALL = "all"  # Contains all (array of strings)` [L1, line 76] tests that the record's list contains every query value. That is the reverse direction of a requirement gate. See the emulation note below the table. |
| B | Partial | Retrieval is a filter followed by similarity top-k over the survivors. The in-memory store says "Prefilter nodes based on the query filter and node ID restrictions" [L3, line 260]. There is no second path. A record that passes the filter still has to win on similarity. A record that lacks the filtered key fails most operators. The in-memory store returns true for a missing value only for `NE` and `NIN` [L2, line 118]. Chroma's `$nin` matches "(or the attribute's key is not present)" [C1]. |
| C | Partial | A record is text plus metadata, so prompt fragments and tool descriptions can share one collection with a type field. The store has no notion of a tool (no callable, no parameter schema). It does not route results to a system prompt or to a tools array. |
| D | No | A query returns the filtered top-k. Neither `MetadataFilters` [L1] nor Chroma's `where` [C1] has a pinned or always-returned record. |
| E | No | Each record is tested against the filter on its own. The APIs have no relation between records. |
| F | No | Same reason as E. |
| G | No | Operator meanings are given as code comments [L1] and docs [C1]. No property of selection is stated or tested as such. |
| H | No | A vector-store query has no execution step. |
| I | No | The result is a list of records and scores. Nothing explains why a record was excluded. |
| J | No | No decision record is produced. |

Emulation note for row A (so a reviewer cannot say "you can do this with filters"). A gate "record tags ⊆ context tags" can be written per query as "the record contains none of the tags outside the context". In LlamaIndex this is `MetadataFilters(filters=[MetadataFilter(key="required_tags", operator=FilterOperator.ANY, value=list(U - C))], condition=FilterCondition.NOT)`, where U is the full tag vocabulary. The in-memory store implements `NOT` as "Match when none of the filters match" [L2, lines 187 to 189]. It treats a missing key as no match for `ANY` [L2, line 118], so ungated records pass. The same store rejects nested filters with "Nested MetadataFilters are not supported." [L2, line 164]. Support for `NOT` and `ANY` differs by backend. Chroma could use `$and` over `{"required_tags": {"$not_contains": t}}` for each t outside the context. Chroma says "Empty arrays are not allowed" [C1], so ungated records must omit the key. Chroma does not document how `$not_contains` treats a missing key. Either way the gate lives in the query, needs the whole vocabulary at query time, and is not declared by the item.

### 2.2 LangChain tool retrieval

Sources read for this column.
- [B1] `langgraph-bigtool` README (LangChain organization, package 0.0.3, last commit 2026-10-15). https://github.com/langchain-ai/langgraph-bigtool
- [B2] `langgraph_bigtool/graph.py` on `main`. https://github.com/langchain-ai/langgraph-bigtool/blob/main/langgraph_bigtool/graph.py
- [M1] LangChain docs, built-in middleware (langchain 1.4.7). https://docs.langchain.com/oss/python/langchain/middleware/built-in
- [M2] `LLMToolSelectorMiddleware` source. https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/middleware/tool_selection.py
- [T1] LangChain docs, Tools, section "Dynamic tool selection". https://docs.langchain.com/oss/python/langchain/tools
- [TT] LangGraph docs, time travel. https://docs.langchain.com/oss/python/langgraph/use-time-travel

The old LangGraph how-to for many tools (https://langchain-ai.github.io/langgraph/how-tos/many-tools/) now redirects to the generic Tools page [T1]. `langgraph-bigtool` is the maintained embedding-based tool retriever from the LangChain organization. LangChain 1.x also ships an LLM-based selector [M1] and provider-side tool search (`ProviderToolSearchMiddleware`) [M1]. The marks below are for embedding retrieval. Rows where the other two mechanisms change the picture say so.

| Row | Mark | Evidence |
|---|---|---|
| A | No | Tools carry no condition fields. bigtool's `create_agent` takes `filter`, documented as "Optional key-value pairs with which to filter results" [B2, line 65]. That filter is fixed per agent. LangChain's dynamic tool selection filters `request.tools` in developer code "based on authentication state, user permissions, feature flags, or conversation stage" [T1]. The condition lives in middleware, not on the tool. |
| B | Partial | Similarity is the only path. The README's retriever is `store.search(("tools",), query=query, limit=2)` [B1], and the default is `limit: int = 2` [B2, line 49]. No gate sits beside it. |
| C | No | Tools only. The registry is "a dict mapping string IDs to tools or callables" [B2, line 63]. Prompt fragments are not retrieved. |
| D | Partial | bigtool binds only `[retrieve_tools, *selected_tools]` [B2, line 87], so no registry tool is always present. LangChain's `LLMToolSelectorMiddleware` does have pinning. Its `always_include` takes "Tool names to always include regardless of selection. These do not count against the max_tools limit." [M1, M2 lines 183 to 185]. That selector asks an LLM to choose, so it is not embedding retrieval. |
| E | No | Neither tools nor store items have relation fields [B1, B2]. |
| F | No | Same reason as E. |
| G | No | No property of selection is stated [B1]. |
| H | No | bigtool builds its executor over the whole registry, `tool_node = ToolNode(tool for tool in tool_registry.values())` [B2, line 99]. It routes every non-retrieval call to that node without checking `selected_tool_ids` [B2, lines 129 to 148]. LangChain's `HumanInTheLoopMiddleware` can "Pause agent execution for human approval, editing, or rejection of tool calls before they execute" [M1]. It is configured per tool name and is not linked to retrieval. |
| I | Partial | bigtool answers each retrieval call with a tool message `f"Available tools: {tool_names}"` [B2, line 38]. The agent learns what was retrieved. It is not told what was withheld or why. |
| J | Partial | bigtool keeps `selected_tool_ids` in graph state [B2, line 22], and LangGraph checkpoints support replay [TT]. Replay re-runs nodes, so "LLM calls, API requests, and interrupts fire again and may return different results" [TT]. No selection reasons are stored. Nothing verifies a past decision. |

### 2.3 LlamaIndex tool retrieval

Sources read for this column.
- [X1] LlamaIndex example "Retrieval-Augmented Agents". https://developers.llamaindex.ai/python/examples/agent/openai_agent_retrieval/
- [X2] `agent/workflow/base_agent.py`, tag v0.14.25. https://github.com/run-llama/llama_index/blob/v0.14.25/llama-index-core/llama_index/core/agent/workflow/base_agent.py
- [X3] LlamaIndex docs, human in the loop. https://developers.llamaindex.ai/python/framework/understanding/agent/human_in_the_loop/
- [X4] LlamaIndex docs, instrumentation and agent state. https://developers.llamaindex.ai/python/framework/module_guides/observability/instrumentation/ and https://developers.llamaindex.ai/python/framework/understanding/agent/state/

| Row | Mark | Evidence |
|---|---|---|
| A | No | The retriever ranks tools by similarity. The example passes `tool_retriever=obj_index.as_retriever(similarity_top_k=2)` [X1]. Tools carry no condition fields. Any filtering would be a per-query metadata filter on the underlying index, with the limits in 2.1. |
| B | Partial | Similarity top-k is the only path [X1]. No gate sits beside it. |
| C | No | `tool_retriever` returns tools. The system prompt is a separate fixed field, `system_prompt: Optional[str]` [X2, line 99]. `ObjectIndex` can index "arbitrary objects" [X1], but the agent consumes only tools from it. |
| D | Yes | In source, `get_tools` starts from the fixed list and appends retrieved tools. It runs `tools = [*self.tools] if self.tools else []`, then `tools.extend(retrieved_tools)` [X2, lines 283 to 292]. Fixed tools are always passed and do not count toward `similarity_top_k`. Caveat. The field is documented as "The tool retriever for the agent, can be provided instead of tools" [X2, line 107]. So this is source behavior, not a documented pinning feature. It covers tools only. |
| E | No | No relation fields on tools or index nodes [X1, X2]. |
| F | No | Same reason as E. |
| G | No | No property of selection is stated [X1]. |
| H | Partial | At call time, `call_tool` runs the retriever again with the tool name as the query, `tools = await self.get_tools(ev.tool_name)`, and returns an error output if the name is absent [X2, lines 645 to 656]. So a call-time membership check exists. It uses a different query from the selection step, so it can admit a tool that was never offered. It has no approval outcome. LlamaIndex documents human confirmation as a pattern written inside a tool, "such as confirming a tool call" [X3]. That pattern is separate from retrieval. |
| I | No | The model sees only the bound tools. A call to a tool outside the set returns "Tool {ev.tool_name} not found. Please select a tool that is available." [X2, line 650]. It gives no reason. |
| J | No | Instrumentation emits events and spans [X4]. The workflow context "is serializable" for later resumption [X4]. No record of tool-selection decisions for replay or verification is documented. |

### 2.4 ITR (Instruction-Tool Retrieval, Franko)

Sources read for this column.
- [P] Franko, arXiv:2602.17046v1, HTML version. https://arxiv.org/html/2602.17046v1
- [R] Repository README (package `instruction-tool-retrieval` 0.1.1, MIT). https://github.com/uriafranko/ITR
- [S1] `itr/selection/budget_selector.py`. https://github.com/uriafranko/ITR/blob/main/itr/selection/budget_selector.py
- [S2] `itr/__init__.py` (class `ITR`). https://github.com/uriafranko/ITR/blob/main/itr/__init__.py
- [S3] `itr/assembly/prompt_builder.py`. https://github.com/uriafranko/ITR/blob/main/itr/assembly/prompt_builder.py
- [S4] `itr/core/types.py`. https://github.com/uriafranko/ITR/blob/main/itr/core/types.py
- [S5] `tests/unit/test_budget_selector.py`. https://github.com/uriafranko/ITR/blob/main/tests/unit/test_budget_selector.py

The repository has 6 commits. The last is dated 2025-09-30. `main` therefore equals the released 0.1.1 code.

| Row | Mark | Evidence |
|---|---|---|
| A | No | Instruction chunks carry "metadata (domain, policy type, recency)" [P, §3.2]. Tools have a `preconditions: List[str]` field [S4], but no code path in the 0.1.1 corpus, retrievers or selector reads it. The paper says "Rare but critical tools can be conditionally “always-eligible” via domain classifiers" [P, §3.7]. That forces eligibility. It is not a requirement gate. |
| B | Partial | Hybrid dense plus BM25 retrieval, then cross-encoder reranking, then greedy budget selection [P, §3.2 to §3.4], [R]. Similarity only, with no gate beside it. In 0.1.1, `step()` returns `confidence_score=0.8,  # Placeholder confidence` and does not call `handle_fallback` [S2]. Only the CLI calls it. |
| C | Partial | The paper "treats instructions and tools as first-class retrievable objects" [P, §1]. One pipeline and one joint token budget cover both [S1]. They still use two corpora (𝒜 and ℬ) [P, §3.2] and two schemas, `InstructionFragment` and `Tool` [S4]. |
| D | Partial | The paper describes a "Safety/Legal overlay (always on, small)" [P, §3.6]. It also advises "Expose safety + logging tools always" and lists "pinning rare critical tools" as a mitigation [P, §7]. The budget constraint ∑sᵢ + ∑tⱼ ≤ B (Eq. 4) states no exemption [P, §3.4]. In 0.1.1 the selector reserves `safety_overlay_tokens` [S1], but the prompt builder inserts no overlay [S3]. Safety fragments get `value *= 2.0  # Boost safety fragments` and still compete under k and the budget [S1]. No item is guaranteed a place. |
| E | No | No conflict or supersedes fields in the paper or in the schemas [P, S4]. |
| F | No | Tool pre- and postconditions are free text [P, §3.2], [S4]. Selection does not use them. |
| G | Partial | The paper states the selection objective with a budget constraint (Eq. 4) and says "a greedy selection by re-ranker score per token works well" [P, §3.4]. Section 6 is a "Cost Model and Theory Sketch" about tokens and accuracy, not about selection properties. Unit tests check budget and k limits on fixed inputs, for example `assert total_tokens <= available_budget` [S5]. No other property is stated. There are no randomized or property-based tests. |
| H | No | The only control in the paper is a prompt. The routing note asks the model "to avoid hidden tools" [P, §3.6]. The library covers selection and prompt assembly only [R]. It has no execution component. |
| I | Partial | The paper's routing note tells the model that tools are hidden and to request "tool discovery" if needed [P, §3.6]. It does not say which tools are hidden or why. The 0.1.1 routing note only gives a count, `f"You have access to {num_tools} tools. ..."` [S3]. |
| J | No | The paper recommends "Log selected chunks/tools, sufficiency scores, fallbacks, and errors" [P, §12]. The library's `log_retrieval` helper records counts and a confidence value, not item IDs. `ITR.step()` does not call it [S2]. Replay and verification are not described. |

### 2.5 Hermes Agent tool search (Nous Research, v0.22.x)

Sources read for this column. All are at tag v0.22.2, the version in the manuscript. The tool-search page at v0.22.5 is identical except for one connectors paragraph.
- [H1] Tool Search page, source. https://github.com/NousResearch/hermes-agent/blob/v0.22.2/website/docs/user-guide/features/tool-search.md (rendered at https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-search)
- [H2] Hooks page, `pre_tool_call` section. https://github.com/NousResearch/hermes-agent/blob/v0.22.2/website/docs/user-guide/features/hooks.md
- [H3] Developer guide, adding tools and tools runtime. https://github.com/NousResearch/hermes-agent/blob/v0.22.2/website/docs/developer-guide/adding-tools.md and https://github.com/NousResearch/hermes-agent/blob/v0.22.2/website/docs/developer-guide/tools-runtime.md
- [H4] Skills page. https://github.com/NousResearch/hermes-agent/blob/v0.22.2/website/docs/user-guide/features/skills.md
- [H5] Regression tests. https://github.com/NousResearch/hermes-agent/blob/v0.22.2/tests/tools/test_tool_search.py

Confirmed mechanism. Tool search defers MCP and non-core plugin tools, plus built-ins named in `tools.tool_search.defer`. The model sees three bridge tools, `tool_search(queries, limit?)`, `tool_describe(names)` and `tool_call(calls)` [H1]. Retrieval is "BM25 over tokenized tool name, source name (the MCP server or plugin toolset the tool belongs to, ...), description, and parameter names" with English Snowball stemming [H1, Implementation details].

| Row | Mark | Evidence |
|---|---|---|
| A | Partial | Hermes has item-declared hard conditions, but not on task context. For tools, a `check_fn` runs when tool definitions are built, and "if it returns `False`, the tool is silently excluded" [H3, adding-tools]. Typical checks are "API key present", "Service running" and "Dependency installed" [H3, tools-runtime]. For skills, `requires_toolsets` means the "Skill is **hidden** when the listed toolsets are unavailable", and `platforms` restricts the operating system [H4]. These conditions test installation, platform and tool availability. They are not context tags. `check_fn` is arbitrary code. The tool-search ranking itself has no condition fields [H1]. |
| B | Partial | The soft path is lexical BM25 driven by a query the model writes [H1]. "A tool is a result only if it contains the query's rarest token" [H1]. There is no gate beside it. Non-deferred tools are always present (see D). |
| C | No | Tool search covers tools only. Instructions live in skills, a separate progressive-disclosure mechanism with `skills_list()`, `skill_view(name)` and a `SKILL.md` schema [H4]. |
| D | Yes | "Hermes keeps its working-set core tools (`terminal`, `read_file`, `write_file`, ...) loaded directly by default" [H1]. Deferral is set by the `defer` list, and "`defer: []` keeps every tool eager" [H1]. Non-deferred tools skip search and its `limit`. Tested by `test_core_tools_never_defer` [H5]. |
| E | Partial† | Tool search has no conflict or supersedes fields [H1]. Hermes skills declare `fallback_for_toolsets` and `fallback_for_tools`. With them the "Skill is **hidden** when the listed toolsets are available" [H4]. That is a declared, deterministic precedence of a tool over a fallback skill. It depends on availability and sits outside tool search. Connector name twins are also deduplicated by rule ("search keeps that twin, drops the other, and logs a warning") [H1]. That is a naming rule, not a declared relation. |
| F | Partial† | Skills declare `requires_tools` and `requires_toolsets` [H4]. The dependency is enforced by hiding the skill, not by bringing in the tool. There is no closure. Composite toolsets expand into tools ("expands composite toolsets into individual tool names") [H3, tools-runtime]. That is configuration grouping, not item prerequisites. |
| G | Partial | The docs state behavior rules, such as "an exact tool-name query always matches" and the toolset scoping rule [H1]. The regression suite checks them on fixed cases (`test_exact_name_match_bypasses_coverage`, `test_search_catalog_is_scoped_to_session_toolsets`, `test_core_tools_never_defer`) [H5]. The rules are not stated formally. There are no randomized or property-based tests. |
| H | Partial | One rule is shared by discovery and execution. "`tool_search`, `tool_describe`, and `tool_call` only ever see and invoke tools the session was actually granted" [H1]. When `tool_call` runs, "Pre-tool-call hooks, guardrails, approval prompts, and post-tool-call hooks all run against the real tool name" [H1]. Each entry "gets its own scope check, schema validation, hooks, approval and result" [H1]. A `pre_tool_call` hook can block or approve. A "`block` requires a non-empty `message` and short-circuits the tool with that text as the error returned to the model" [H2, line 572]. The shared rule is only the session's toolset grant. Hook and approval policies are configured separately from tool search, which has no per-item rule to re-check. |
| I | Partial | At tier 1 the bridge carries "a skills-style manifest of every deferred tool (name + short description, degrading to names-only when over budget)" [H1]. An empty search group "includes an `available_sources` summary of the connected servers so a lexical miss is not mistaken for a missing capability" [H1]. Tools removed by `check_fn` are "silently excluded" [H3]. No notice says that a tool is withheld in this context, or why. A hook's block message is the native channel for such a reason [H2]. |
| J | ND | The tool-search page describes no record of search or deferral decisions [H1]. Hermes keeps sessions ("FTS5 session search with LLM summarization for cross-session recall", README), and the activity feed shows the unwrapped tool [H1]. Replay or verification of selection decisions is not documented. |

### 2.6 NVIDIA NeMo Guardrails

Sources read for this column. The docs default to "Latest". The newest release index listed is v0.24.1, and the Tool Calling page is the same in both.
- [N1] Guardrail types. https://docs.nvidia.com/nemo/guardrails/v0.24.1/about-nemo-guardrails-library/rail-types
- [N2] Guardrails configuration and configuration reference. https://docs.nvidia.com/nemo/guardrails/v0.24.1/configure-guardrails/yaml-schema/guardrails-configuration and https://docs.nvidia.com/nemo/guardrails/v0.24.1/configure-guardrails/configuration-reference
- [N3] Tool Calling (IORails tool rails), v0.24.1. https://docs.nvidia.com/nemo/guardrails/v0.24.1/configure-guardrails/guardrail-catalog/tool-calling
- [N4] Logging. https://docs.nvidia.com/nemo/guardrails/v0.24.1/observability/logging
- [N5] README. https://github.com/NVIDIA-NeMo/Guardrails

| Row | Mark | Evidence |
|---|---|---|
| A | No | NeMo does not select instructions or tools into the context. Its rails act on messages, retrieved chunks and tool calls. "Input rails apply guardrails before the LLM is called by validating and sanitizing user inputs" and "Execution rails control and validate tool/function calls, their arguments, and results" [N1]. No item declares conditions. |
| B | No | Similarity search serves dialog intent matching (`rails.dialog.user_messages.embeddings_only`, "Use only embeddings for intent matching") [N2] and knowledge-base chunks, which "Retrieval rails filter and validate" [N1]. It does not admit instructions or tools. |
| C | No | Rails, Colang flows, prompts and actions are separate configuration types [N2]. |
| D | No | There is no retrieval budget or top-k over context items. |
| E | No | No declared relation between context items. See section 4, item 6. |
| F | No | Same reason as E. |
| G | No | No property of selection is stated. The tool rails "fail closed" [N3], which is a property of validation, not of selection. |
| H | Partial | "Tool call validation checks every tool call the model emits against the tools you declared" [N3]. "A call must name an allowed tool and supply arguments that satisfy that tool's JSON Schema" [N3]. The allowlist is the tool set declared on the same request, so a host that declares only its selected tools gets that set enforced at call time. The outcomes are allow or block. Approval is not documented. The rails "run only on the IORails engine, which is opt-in and experimental" and support only the OpenAI Chat Completions format [N3]. NeMo has no selection logic of its own for these checks to mirror. On the default engine, execution rails "Control custom action and tool invocations" through Colang flows [N2]. |
| I | No | "When a rail blocks, IORails returns the refusal message `I'm sorry, I can't respond to that.`" for a non-streaming request [N3]. The turn stops. The model is not told which tool was refused or why. Streaming returns a `guardrails_violation` error payload [N3]. |
| J | Partial | `options.log` returns "Detailed information about rails activated during generation" [N4]. Each activated rail exposes `decisions`, and a `stop` flag shows which rail stopped a request [N4]. `explain()` gives a "Quick summary of the last generation" on `LLMRails` [N4]. Replay or verification of these records is not documented. |

## 3. Citation details

**ITR (bib key `franko2025itr`)**
- Title. "Dynamic System Instructions and Tool Exposure for Efficient Agentic LLMs". The title does not contain "ITR". ITR is the method's name in the abstract.
- Author. Uria Franko (single author).
- arXiv:2602.17046 [cs.AI], v1. The abstract page shows "Submitted on 1 Dec 2025". The 2602 prefix normally means February 2026, so the paper was probably announced then. Year 2025 matches the submission date. Some styles may print 2026.
- DOI 10.48550/arXiv.2602.17046. URL https://arxiv.org/abs/2602.17046
- Code. https://github.com/uriafranko/ITR (named in the paper, §1, contribution 5). MIT licence. PyPI package `instruction-tool-retrieval` 0.1.1, uploaded 2025-09-24. The README still says the PyPI package is "Coming Soon". The repository calls itself research code ("This framework was developed to support research findings").
- The existing entry in `sample-base.bib` matches these details.

**Hermes Agent**
- Official repository. https://github.com/NousResearch/hermes-agent (MIT licence). Built by Nous Research.
- Docs. https://hermes-agent.nousresearch.com/docs/ . Tool search page. https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-search
- Releases. v0.22.0 "The Threshold Release" (notes dated 2026-10-13, published 2026-10-14). v0.22.2 published 2026-10-15 (the manuscript's version). v0.22.5 published 2026-10-23 (latest on 2026-10-30).
- The repository has no CITATION.cff and no BibTeX. A suitable entry is shown below.

```bibtex
@misc{nous2026hermes,
  title        = {{Hermes Agent}},
  author       = {{Nous Research}},
  year         = {2026},
  howpublished = {\url{https://github.com/NousResearch/hermes-agent}},
  note         = {Version 0.22.2. Documentation at \url{https://hermes-agent.nousresearch.com/docs/}}
}
```

- History of tool search, from the commit log of the docs page. It was introduced on 2026-05-29 ("feat(tools): progressive tool disclosure for MCP and plugin tools"). Bridge dispatch was scoped to the session's toolsets the same day. Multi-query search, batched describe and Snowball stemming came on 2026-08-25. The v0.22.0 notes say rarely used built-ins such as `computer_use`, `session_search` and `image_generate` "sit behind `tool_search` by default". Earlier single-call signatures (`tool_search(query, limit?)`, `tool_describe(name)`, `tool_call(name, arguments)`) still appear on third-party mirrors such as hermesagent.org.cn and neura.market. Those mirrors also give some different defaults. Cite the official page only.

**NeMo Guardrails**
- Traian Rebedea, Razvan Dinu, Makesh Narsimhan Sreedhar, Christopher Parisien, Jonathan Cohen. "NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails". Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing: System Demonstrations, Singapore, December 2023, pages 431 to 445. Association for Computational Linguistics.
- DOI 10.18653/v1/2023.emnlp-demo.40. https://aclanthology.org/2023.emnlp-demo.40 . Also arXiv:2310.10501.
- Software. https://github.com/NVIDIA-NeMo/Guardrails (formerly NVIDIA/NeMo-Guardrails). Latest release v0.24.1 (2026-09-16). Docs https://docs.nvidia.com/nemo/guardrails/latest/

**LlamaIndex (for both LlamaIndex columns)**
- Jerry Liu. LlamaIndex. 2022. https://github.com/run-llama/llama_index . Version read is `llama-index-core` 0.14.25 (tag v0.14.25, 2026-09-21).
- Warning. The README's BibTeX gives `doi = {10.5281/zenodo.1234}`. On 2026-10-30 doi.org returned 404 for it. Do not cite that DOI. The existing `liu2022llamaindex` entry has no DOI, which is correct.

**LangChain**
- Harrison Chase. LangChain. Released 2022-10-17 (from the repository's CITATION.cff). https://github.com/langchain-ai/langchain . Version read is `langchain` 1.4.7. The existing `chase2022langchain` entry matches.
- Tool retriever. `langgraph-bigtool`, LangChain organization, package 0.0.3. https://github.com/langchain-ai/langgraph-bigtool . No CITATION.cff was checked for it. Cite it as software by URL if the paper names it.

**Chroma**
- Chroma (chroma-core). https://github.com/chroma-core/chroma . Docs https://docs.trychroma.com . No CITATION.cff in the repository. PyPI `chromadb` 1.5.9 is current. The filtering page shows no version.

## 4. Cells not fully settled

1. **Hermes, rows E and F (scope of the column).** The user framed the column as tool search. Tool search alone has no conflicts, supersedes or dependencies, so E and F would be No. The Partial marks come from Hermes skills (`fallback_for_*`, `requires_*`). A Hermes-aware reviewer may count those. Decide whether the column means "tool search" or "Hermes Agent". Row A stays Partial either way, because `check_fn` applies to tools.
2. **Hermes, row A detail.** The docs do not say whether a `requires_toolsets` list means all of the listed toolsets or any of them. They say only that the skill is hidden "when the listed toolsets are unavailable".
3. **LlamaIndex tool retrieval, row D.** The Yes rests on source code (`tools` plus `tool_retriever` are combined). The field's own description says the retriever "can be provided instead of tools". If the paper should count only documented behavior, mark Partial.
4. **LlamaIndex tool retrieval, row H.** The Partial rests on source code. The call-time check re-runs the retriever with the tool name as the query. A strict reading of "same rules" could make this No. I kept Partial because the check does block calls with an error.
5. **LangChain column, which component.** Marks use `langgraph-bigtool` for embedding retrieval. Row D is Partial only because of `LLMToolSelectorMiddleware`'s `always_include`, which is LLM-based. For embedding retrieval alone, D is No. LangChain also has `ProviderToolSearchMiddleware`, which defers tools behind a model provider's server-side search. I did not evaluate it as a separate column.
6. **NeMo, rows E and F.** I did not check Colang 2.x flow-level features such as flow priorities or overrides. They concern dialog flows, not context items, so they should not change the marks. A reviewer might still raise them.
7. **NeMo, row H.** The tool-call allowlist exists only on the experimental IORails engine. On the default `LLMRails` engine the docs show execution rails (`check tool input`, `check tool output`) but I did not read what those flows check.
8. **ITR, paper versus library.** The paper describes an always-on overlay, confidence-gated fallback and a discovery request. Library 0.1.1 implements less (no overlay text, placeholder confidence, fallback only from the CLI). Marks for B, D and I describe both. If the paper should cite only the paper's design, D and I stay Partial. If only the library, I would drop to No and D to Partial at best (token reservation only).
9. **Hermes, row J.** ND. The docs say nothing about records of tool-search decisions. Session transcripts exist, but I found no documented replay or verification.
10. **Chroma emulation note.** Chroma does not document how `$not_contains` treats a record that lacks the key. This affects only the emulation note in 2.1, not the marks.

## 5. Changes after the check of 19 Nov 2026

A reviewer agent re-read every cell against the public sources on 19 Nov 2026, and the paper session re-checked the points below before changing the manuscript's Table 1. The record is in the paper repo, `checks/error-check-2026-11-19.md` (findings T1 to T10).

- **Row A, vector-store filters: No to Partial.** The paper's own baseline (Sec 4.6) writes BEAR's gate as a LlamaIndex containment filter over a per-item `required` metadata field. So a store can express the gate when each item stores its required tags and the caller builds the filter for each query. The store still has no notion of a gate that an item declares. Elasticsearch `terms_set` with `minimum_should_match_field` and PostgreSQL array containment (`<@`) allow the same pattern.
- **Row H, LangChain: No to Partial‡.** `langgraph-bigtool` does not re-check a call against the selected set. LangChain's `HumanInTheLoopMiddleware` can approve, edit or reject a call (https://docs.langchain.com/oss/python/langchain/human-in-the-loop, "Skip executing this tool call entirely and return rejection feedback to the agent"). That is agent middleware, not the tool retriever, and the mark carries a footnote saying so. The Hermes column already counted the same kind of hook.
- **Row J, Hermes: ND to Partial.** Hermes v0.22.2 documents session storage of every message with its `tool_calls` (https://github.com/NousResearch/hermes-agent/blob/v0.22.2/website/docs/developer-guide/session-storage.md). No replay or verification of a selection is documented, which is why the mark is Partial, as for LangChain.
- **Rows E and F, NeMo Guardrails.** This file always said No. The manuscript's table said ND by mistake and now says No. Colang 2 has flow priorities and override flows, which act on dialog flows, not on context items.
- **Row I, NeMo Guardrails, and versions.** The marks are for v0.24.1, and the NeMo links above are now pinned to it. v0.25.0 (released 2026-11-19) adds a hooks server whose deny carries a reason for the agent's model ("with the reason prefixed with `NeMo Guardrails: `", https://docs.nvidia.com/nemo/guardrails/latest/run-guardrailed-inference/using-hooks-server/results-and-errors.md). Row I would be Partial at v0.25.0. The table's caption says so.
- **Section 4, item 2 is settled.** The Hermes docs do say it: a skill "is hidden when ANY listed toolset is not available" (`creating-skills.md` at v0.22.2).
- **ITR, rows D and I.** Still Partial, crediting the paper's design. The released library 0.1.1 implements less, and the table's caption now says so.
- Not changed: LangChain row D (Partial. `always_include` exists only in the LLM-based selector) and LlamaIndex row J (No. It keeps no selection list).
- Later versions seen on 19 Nov: Hermes Agent v0.23.2 (no cell changes), langchain 1.5.2, llama-index-core 0.14.26 (the cited file is unchanged).
