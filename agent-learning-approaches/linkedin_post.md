How AI Agents Actually Learn: I Built a Benchmark to Find Out

Everyone talks about RAG. Everyone talks about fine-tuning. But when your AI agent needs to learn from experience — which approach actually works?

I built a benchmark framework (7 strategies, 14 tasks, 181 tests) to find out. No opinions. Just data.

The results surprised me:

1/ File-based rules (CLL) win 6 of 8 core tasks
Simple rules in a text file. Git-tracked. Zero infrastructure cost. 340 bytes of state vs 6.8 KB for RAG. Converges in 8 steps.

2/ RAG only wins at 50+ rules
Below that threshold, RAG's overhead provides zero benefit. The "just add a vector store" reflex is wrong for most agent use cases.

3/ The biggest weakness has a simple fix
CLL fails when patterns shift — old rules block new ones. Adding a drift detector (8-observation rolling window) takes it from 0.850 to 1.000. Three lines of code.

4/ Debate is the most robust allrounder
Dual-agent debate (CLL + RAG with trust model) wins no single task — but it is never worse than #4. When you cannot predict what your agent will face, Debate is the safest bet.

5/ Real LLM validation for 4 cents
150 API calls to Claude Haiku confirmed the same rankings. No simulation artifact — the benchmark holds with real models.

6/ Few-shot learning alone never works
ICL (sliding window of examples) ranked last on 7 of 8 tasks. It must be combined with persistent memory for any production use.

7/ Knowing WHY matters more than knowing WHO wins
My failure analysis engine shows: "CLL fails on adaptive tasks because blog->medium rules block blog->high after policy changes." That is actionable. A leaderboard is not.

The decision tree is simple:
- Stable rules, privacy matters -> CLL
- 50+ rules -> CLL + RAG hybrid
- Changing environment -> add drift detection
- Unpredictable mix -> Debate
- Never ICL alone

Full taxonomy covers 20 paradigms across 5 categories. Paper and benchmark code are open source.

What learning strategy does your agent use?

#AIAgents #MachineLearning #RAG #AgentArchitecture #ContextEngineering
