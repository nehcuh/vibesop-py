 现状诊断（Pre-context）
  从当前代码库状态来看，VibeSOP 已经具备了以下基础能力：
   能力                                  当前状态       你问题的映射
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   7层路由引擎                           ✅ 成熟        问题2的底层基础已具备，但缺少「无匹配时自动退化」逻辑
   SkillLoader / 解析器                  ✅ 基本可用    问题4缺少作用域隔离，问题5缺少开关机制
   FeedbackCollector                     ⚠️ 存在但浅层   问题3缺少评估→淘汰→改进的闭环
   HealthMonitor                         ⚠️ 存在但被动   问题3缺少主动评估体系
   InstinctLearner / PreferenceBooster   ⚠️ 实验性       问题2的上下文感知有雏形，但未产品化
   Registry Sync                         ⚠️ 单向同步     问题1缺少主动发现和市场机制
   技能分享/社区                         ❌ 无          问题6完全空白
  核心矛盾：当前架构是「静态技能集合 + 路由匹配」，而你期望的是「动态技能生态 + 智能生命周期管理」。
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  RALPLAN-DR 审议
  1. 原则（Principles）
  • 渐进增强：用户不应被迫理解技能系统才能使用 VibeSOP
  • 上下文即权限：技能可见性由当前项目/会话/用户上下文决定
  • 数据驱动改进：技能质量必须由真实使用数据定义，而非作者自评
  • 低摩擦插拔：启用/禁用技能的认知成本应低于 3 秒
  • 自治淘汰：系统应能识别并建议弃用低质量技能，而非无限累积
  2. 决策驱动因素（Decision Drivers）
   因素            权重   说明
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   用户体验        高     技能系统的存在不应增加认知负担
   向后兼容        高     v4.x 用户应平滑升级
   工程复杂度      中     避免过度设计，优先闭环
   隐私/数据主权   高     使用数据不应强制上传
   社区生态        中     分享机制决定长期价值
  3. 可行方案
  方案 A：渐进修补（Extend Current）
  在现有 UnifiedRouter + SkillManager 上逐个打补丁：
  • 给 SkillConfig 加 scope 字段
  • 给 SkillRegistry 加 enabled 开关
  • 给 FeedbackCollector 加评分维度
  优点：风险低，v4.3 即可交付部分功能 缺点：架构债累积，6 个问题之间缺少统一抽象
  方案 B：Skill Runtime 重构（引入 SkillOS）
  将技能系统提升为一级子系统，引入：
  • SkillRuntime：作用域 + 生命周期管理
  • SkillMarket：发现/安装/更新
  • SkillEvaluator：效果评估 + 淘汰
  • SkillFeedbackLoop：autoresearch 改进
  优点：6 个问题统一解决，长期架构清晰 缺点：v5.0 才能交付，v4→v5 迁移成本高
  方案 C：分层演进（Hybrid）⭐
  推荐。分 3 个阶段，每个阶段解决 2 个问题：
   阶段    版本   解决问题   核心交付
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   阶段1   v5.0   4, 5       作用域系统 + 技能开关 + 项目级技能
   阶段2   v5.1   3, 6       评估体系 + 反馈闭环 + 技能市场 MVP
   阶段3   v5.2   1, 2       智能推荐 + 自动退化 + 主动发现
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  Architect Review（反面论证）
  对「方案 C」的质疑：
  ▌ "分阶段演进看起来合理，但有一个根本风险：阶段 1 的作用域系统如果没有预留阶段 2 的评估数据接口，会导致阶段 2 返工。当前 SkillConfig 是静态 YAML，没有版本历史、没有使用埋点字段。如果 v5.0 不加这些
  ▌ 预埋，v5.1 就得改数据模型。"
  反驳/应对：
  • v5.0 的作用域设计必须包含 usage_stats 和 version_history 预留字段
  • SkillConfig 需要增加 evaluation_context 扩展槽，即使初期为空
  ▌ "自动退化到普通 Agent（问题2）是一个产品决策，不是技术问题。如果退化逻辑设计不好，用户会困惑：『为什么有时候用技能，有时候不用？』"
  反驳/应对：
  • 退化必须显式透明：路由结果中标注 layer: FALLBACK_LLM，让用户知道发生了什么
  • 提供 vibesop config set fallback.always_ask true 让用户控制行为
  ▌ "Karpathy 的 autoresearch 理念应用到技能改进上，需要 LLM 调用权限。这会带来成本和延迟问题。"
  反驳/应对：
  • 反馈闭环应该是异步后台任务，不是阻塞流程
  • 提供本地模型选项（ollama）用于轻量改进，云端模型用于深度重构
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  Critic Evaluation
   检查项            方案 C 评分   说明
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   原则-选项一致性   ✅            分层演进符合渐进增强原则
   可行性模拟        ⚠️             v5.0 工作量约 2-3 周，v5.1 工作量约 3-4 周，v5.2 依赖前两个阶段的稳定性
   风险              ⚠️             最大风险是阶段 1 的接口设计不够前瞻性
  改进建议：
  • 阶段 1 必须产出一份「Skill Runtime Interface」设计文档，作为阶段 2/3 的契约
  • 在阶段 1 就引入 SkillLifecycleState 枚举（DRAFT → ACTIVE → DEPRECATED → ARCHIVED），为淘汰机制预埋
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ADR 输出
  Plan: VibeSOP Skill Ecosystem Evolution (v5.x Roadmap)
  Date: 2026-04-21
  Status: approved
  ADR:
    Context: >
      用户提出 6 个核心问题，揭示 VibeSOP 当前从「路由工具」
      向「智能技能操作系统」进化的关键 gap：
      技能发现、上下文推荐、评估淘汰、项目级隔离、
      快速插拔、沉淀分享。

    Decision: >
      采用「分层演进（Hybrid）」方案，分 3 个阶段交付：
      v5.0 解决作用域与插拔，v5.1 解决评估与分享，
      v5.2 解决推荐与发现。
      阶段 1 必须预埋评估数据接口和生命周期状态机。

    Consequences: >
      - v4.x 用户可通过配置平滑迁移
      - 需要新增 SkillRuntime、SkillMarket、SkillEvaluator 三个核心模块
      - 开发周期约 8-10 周（3 个阶段）
      - 阶段 1 的接口文档是后续阶段的关键依赖
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  下一步
  如果你想继续深入，我建议：
  1. 启动阶段 1 设计：我可以帮你产出 SkillRuntime 的接口设计文档（.vibe/plans/skill-runtime-v5.md）
  2. 先做最小验证：针对「项目级技能 + 快速禁用」两个功能，写一个 MVP PR 验证架构方向
  3. 参考社区实现：调研 Karpathy autoresearch / OpenHands skill system / Claude Code context 7 的实现细节

  你倾向哪个方向？

✨ 我觉得方案B挺好的，不过从您之前给我的思考来看，我觉得有一点你似乎没有给我答案，或者可能是我表述不够清楚，举个例子，假设用户提出 “请给我仔细深入阅读当前项目架构，深入分析其愿景、目标，对后续优化工作
提出指导意见”，此时，用户的意图包括了 “架构分析”，“代码评审”，“优化设计” 等一系列工作，对每个工作进行子 Agent 代理？或者串行使用不同技能？或者只选择某一个我们项目自带的技能，譬如 "评审“？这里的场景，
一方面决策过程看不到，另一方面，从我之前体验来看，我们似乎只会使用某一个技能，而且使用技能的理由，你也没有展示给我，我也没有选择同类技能的候选
• 用户指出了一个非常关键的产品体验问题。这涉及 VibeSOP 的核心路由决策透明度和技能组合能力。

  让我重新理解用户的问题：

  用户说："请给我仔细深入阅读当前项目架构，深入分析其愿景、目标，对后续优化工作提出指导意见"

  这个请求包含多个意图：

  1. 架构分析
  2. 代码评审
  3. 优化设计

  用户的问题是：

  1. VibeSOP 是怎么处理这种多意图请求的？是用子 Agent？串行技能？还是只选一个技能？
  2. 决策过程对用户不可见（黑盒）
  3. 体验上似乎只会用某一个技能
  4. 没有选择同类技能的候选展示
  5. 使用技能的理由没有展示

  这是一个关于 路由透明度 和 技能组合（Skill Composition） 的深层问题。

  当前 VibeSOP 的 7 层路由本质上是一个 "Winner Takes All"（先到先赢）的单技能路由系统。这就是问题的根源：

  • 对于多意图请求（如"分析+评审+设计"），当前系统只会路由到一个最匹配的技能
  • 没有技能组合/编排机制
  • 没有向用户展示"为什么选这个技能"
  • 没有展示"其他候选技能及分数"
  • 没有"拆分子任务 → 分配多个技能 → 聚合结果"的工作流

  这是一个架构级别的设计缺陷，不是简单的 bug fix。

  我应该：

  1. 承认这个问题
  2. 分析当前系统的局限性
  3. 提出技能组合 + 路由透明度的架构方案
  4. 讨论实现路径

  让我按照 Ralplan 的框架来组织，但保持对话式。

  核心概念：

  • Single-skill routing（当前）：Winner takes all
  • Multi-skill orchestration（需要）：任务分解 → 并行/串行执行 → 结果聚合
  • Routing transparency（需要）：展示决策过程、候选列表、置信度分数

  这实际上与方案 B（SkillOS）中的 SkillOrchestrator 模块直接相关。

  让我给出结构化的回答。
• 你指出了一个架构级的产品体验盲区。这个问题非常核心——它揭示了 VibeSOP 当前路由系统的根本局限。
  让我把问题拆开说清楚：
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  当前系统的真实行为（坦诚诊断）
  你的请求："仔细深入阅读当前项目架构，深入分析其愿景、目标，对后续优化工作提出指导意见"
  当前 UnifiedRouter 的处理逻辑：
  1. 7层路由匹配 → 最高置信度技能 wins
  2. 假设命中 "gstack/review"（置信度 0.87）
  3. 执行 review 技能
  4. 其他技能（analyze、optimize、architect）被丢弃
  5. 用户看到的：突然来了一个 review 风格的输出
  这就是你感到困惑的根源：
   你期望的                                                              当前系统给的
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   任务拆解：分析→评审→设计                                              只执行一个技能
   看到决策过程："我识别到 3 个意图，选择组合执行"                       黑盒，直接出结果
   候选技能展示："review (0.87) vs architect (0.82) vs analyze (0.79)"   无展示
   执行理由："因为请求包含 '深入分析' + '优化建议'，触发组合模式"        无解释
   串行/并行编排：先分析再评审再设计                                     单一技能单跳执行
  当前系统本质上是 Single-skill Router，不是 Task Orchestrator。
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  问题本质：三个缺失的架构层
  缺失层 1：意图分解（Intent Decomposition）
  # 当前
  query = "分析架构并提出优化建议"
  match = router.route(query)  # → 返回 1 个 SkillRoute

  # 需要的
  tasks = decomposer.decompose(query)
  # → [
  #   Task(intent="architectural_analysis", confidence=0.92),
  #   Task(intent="code_review", confidence=0.88),
  #   Task(intent="optimization_design", confidence=0.85)
  # ]
  缺失层 2：执行策略选择（Execution Strategy）
  # 组合模式决策
  strategy = orchestrator.select_strategy(tasks)
  # 选项：
  # - SEQUENTIAL: 分析 → 评审 → 设计（上游输出作为下游输入）
  # - PARALLEL: 分析+评审 同时执行 → 合并后交给设计
  # - SINGLE: 只执行最高置信度（当前行为，保留为退化模式）
  # - HYBRID: 分析串行，评审+设计并行
  缺失层 3：路由透明度（Routing Transparency）
  result = router.route(query, explain=True)
  # 用户看到的不是黑盒，而是：
  ┌─────────────────────────────────────────┐
  │ 路由决策报告                              │
  ├─────────────────────────────────────────┤
  │ 识别到 3 个子意图                          │
  │   • architectural_analysis  (0.92)      │
  │   • code_review            (0.88)       │
  │   • optimization_design    (0.85)       │
  │                                         │
  │ 执行策略: SEQUENTIAL                     │
  │   Step 1: architect 技能 (分析架构)       │
  │   Step 2: review 技能   (基于分析结果评审) │
  │   Step 3: optimize 技能 (基于评审设计优化)  │
  │                                         │
  │ [确认执行] [改为只分析] [查看候选技能]      │
  └─────────────────────────────────────────┘
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  为什么当前没做？（技术债分析）
  回顾之前看到的代码：
  # src/vibesop/core/routing/unified.py
  class UnifiedRouter(RouterStatsMixin):
      def route(self, query, candidates=None, context=None) -> RoutingResult:
          # 执行层按优先级顺序，first confident match wins
          ...
  设计时的隐式假设：
  • 一个用户请求 ≈ 一个技能
  • 技能之间是互斥的（review vs analyze vs optimize）
  • 用户不关心"怎么决策的"，只关心"结果对不对"
  这些假设在你的场景下全部失效。
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  方案：引入 Task Decomposer + Skill Orchestrator
  如果要解决你的问题，需要在方案 B（SkillOS）中加入两个新核心模块：
  模块 A：TaskDecomposer（意图分解器）
  class TaskDecomposer:
      def decompose(self, query: str, context: Context) -> list[SubTask]:
          """
          使用 LLM 或规则引擎将复合请求拆分为原子任务
          """
          # 方法1: LLM-based（准确但慢/贵）
          # 方法2: Keyword-based（快但粗）
          # 方法3: Hybrid（先用 keyword 快速分，不确定的用 LLM）

          # 输出示例：
          return [
              SubTask(intent="architectural_analysis",
                      keywords=["架构", "愿景", "目标"],
                      suggested_skill="superpowers-architect",
                      confidence=0.92),
              SubTask(intent="code_review",
                      keywords=["深入分析", "评审"],
                      suggested_skill="gstack-review",
                      confidence=0.88),
              SubTask(intent="optimization",
                      keywords=["优化", "改进", "指导意见"],
                      suggested_skill="superpowers-optimize",
                      confidence=0.85),
          ]
  模块 B：SkillOrchestrator（执行编排器）
  class SkillOrchestrator:
      def plan_execution(self, tasks: list[SubTask]) -> ExecutionPlan:
          """
          决定如何组合执行多个技能
          """
          # 依赖图分析
          # analyze → review → optimize （sequential，因为评审依赖分析结果）
          # 或者
          # analyze + review (parallel) → optimize (sequential)

          return ExecutionPlan(
              mode=ExecutionMode.SEQUENTIAL,
              steps=[
                  Step(skill="superpowers-architect",
                       input=original_query,
                       output_as="analysis_report"),
                  Step(skill="gstack-review",
                       input="$analysis_report + original_query",  # 上下文传递
                       output_as="review_notes"),
                  Step(skill="superpowers-optimize",
                       input="$review_notes",
                       output_as="final_recommendations")
              ],
              transparency_report=self._generate_report()
          )
  模块 C：RoutingTransparencyLayer（透明度层）
  @dataclass
  class RoutingTransparencyReport:
      original_query: str
      detected_intents: list[IntentDetection]
      candidate_skills: list[SkillCandidate]  # 所有候选，不只是 winner
      selected_strategy: ExecutionMode
      execution_plan: ExecutionPlan
      reasoning: str  # 自然语言解释"为什么这样决策"

      def to_markdown(self) -> str:
          ...
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  最小可行产品（MVP）设计
  不需要一次做完。可以先做一个两阶段交付：
  Phase 1：透明度先行（v5.0.x）
  不改变执行逻辑，只增加可见性：
  用户请求 → 当前 Single-skill 路由 → 但展示：
    1. "我识别到你可能想：分析(0.92) / 评审(0.88) / 优化(0.85)"
    2. "当前选择：review 技能（因为 '深入分析' 关键词匹配度最高）"
    3. "其他候选：architect (0.82), optimize (0.79)"
    4. "[重新选择技能] [组合执行（实验性）]"
  这解决你提出的"看不到决策过程"和"没有候选"的问题。
  Phase 2：组合执行（v5.1.x）
  引入真正的 TaskDecomposer：
  用户请求 → 分解为子任务 → 用户确认/编辑任务列表 → 编排执行
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  直接回答你的核心疑问
  ▌ "对每个工作进行子 Agent 代理？或者串行使用不同技能？或者只选择某一个我们项目自带的技能？"
  理想答案是：都应该支持，由系统根据请求复杂度自动选择策略。
   请求类型           策略           示例
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   单意图清晰请求     Single-skill   "帮我 review 这段代码"
   多意图有依赖关系   Sequential     "分析架构→评审问题→给出优化方案"
   多意图无依赖       Parallel       "同时 review 代码质量和安全性"
   模糊/开放请求      Interactive    "帮我改进这个项目" → 系统反问："侧重架构还是代码质量？"
  ▌ "决策过程看不到，使用技能的理由也没有展示"
  这需要 RoutingTransparencyLayer。当前系统没有这个概念。
  ▌ "似乎只会使用某一个技能"
  是的，当前系统的硬编码行为。route() 返回 RoutingResult（单结果），不是 List[RoutingResult] + ExecutionPlan。
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  建议的下一步
  如果你想解决这个问题，我建议分两步走：
  Option 1：先做透明度 MVP
  • 修改 route() 返回结构，增加 candidates 和 reasoning 字段
  • CLI 增加 --explain 或交互式模式展示决策过程
  • 工作量：1-2 天，立即改善体验
  Option 2：直接设计 SkillOrchestrator
  • 引入 TaskDecomposer + ExecutionPlan
  • 重写 route() 为 orchestrate()
  • 工作量：2-3 周，根本性解决
  你倾向哪个？还是两个一起做？

  另外，我想确认一个关键点：你觉得"用户确认执行计划"这个交互有必要吗？ 还是说系统应该自动编排，只给结果，但如果用户问"你怎么想的"再展示推理过程？这会直接影响产品形态。

✨ 我觉得从产品体验上，我们可以将 ”用户确认执行计划“ 这个作为可配置项，我们可以必须要用户确认执行，但是在 README 中说明清楚，用户可以关闭该选项以获取更顺畅的开发体验
• 用户确认了产品方向：

  1. 用户确认执行计划作为可配置项
  2. 默认必须用户确认（显式确认模式）
  3. 用户可以在配置中关闭（自动执行模式）
  4. README 中说明清楚

  这是一个产品决策，我应该：

  1. 确认这个决策
  2. 将其纳入 ADR
  3. 讨论具体的配置设计
  4. 给出下一步执行建议

  这个决策的关键影响：

  • 默认行为：安全、透明、用户可控
  • 可选行为：流畅、高效、适合高级用户
  • 需要配置系统支持：vibesop config set routing.confirmation_mode [always|never|ambiguous_only]

  让我结构化地回应，并把这个决策固化下来。
• Used EnterPlanMode
  Plan mode on
• 用户确认了产品决策：用户确认执行计划作为可配置项，默认必须确认，可关闭。

  现在我进入了 Plan Mode。我需要：

  1. 理解代码库中与路由、配置、CLI 相关的部分
  2. 设计实现方案
  3. 编写计划文件
  4. 调用 ExitPlanMode

  让我先探索代码库，了解：

  • 当前 route() 的返回结构
  • 配置系统如何工作
  • CLI 的交互模式
  • RoutingResult 的数据结构

  然后设计：

  1. RoutingResult 扩展：增加 candidates, reasoning, execution_plan
  2. 配置系统扩展：routing.confirmation_mode
  3. CLI 交互：展示决策报告 + 确认/重选/跳过
  4. 默认行为变更：route() → orchestrate()（或保持 route() 但增加 explain 模式）

  让我先探索代码。
⠹ Using Agent (Explore routing and config system)
  • subagent explore (ace01e5a1)
• Used Agent (Explore routing and config system)
  • subagent explore (ace01e5a1)
  • 17 more tool calls ...
  • Used Shell (echo "exiting")
  • Used ReadFile (/Users/huchen/.kimi/plans...ictor-black-bolt-daken.md)
  • Used Shell (cat > /Users/huchen/.kimi...AI triage costs | PLANEOF)
  • Used Shell (wc -l /Users/huchen/.kimi...ictor-black-bolt-daken.md)
• 我已经获得了关于 VibeSOP 路由和配置系统的详尽分析。现在我需要：

  1. 基于用户的决策（用户确认执行计划作为可配置项，默认必须确认，可关闭）
  2. 结合代码库现状
  3. 设计实现方案
  4. 编写计划文件
  5. 调用 ExitPlanMode

  让我先再快速查看几个关键文件来验证我的理解：

  • src/vibesop/core/models.py 中的 RoutingResult
  • src/vibesop/cli/main.py 的 route 命令
  • 当前配置文件结构

  然后设计一个具体的实现计划。

  核心要实现的功能：

  1. 路由透明度（Routing Transparency）：route() 返回详细的路由决策过程
  2. 用户确认模式（Confirmation Mode）：可配置的行为
  3. CLI 交互式展示：展示决策报告，让用户确认/重选/跳过

  让我看看配置文件的具体结构，了解如何添加新配置项。
• Used Shell (cd /Users/huchen/Projects...op/core/config/manager.py)
• Used Shell (cd /Users/huchen/Projects...nfig/manager.py | head -5)
• 用户确认了产品决策（用户确认执行计划作为可配置项，默认必须确认），我已经通过 explore agent 深入
  了解了代码库的路由和配置系统。

  现在我需要：

  1. 查看 DEFAULT_CONFIG 来了解配置结构
  2. 查看 CLI main.py 中 route 命令的具体实现
  3. 编写计划文件

  让我先看 DEFAULT_CONFIG 和 CLI 的 route 命令。
• Used ReadFile (src/vibesop/core/config/manager.py)
• Used ReadFile (src/vibesop/cli/main.py)
• 现在我对代码库有了很好的理解。让我设计一个具体的实现计划。

  用户确认的产品决策：

  1. 路由透明度：展示决策过程、候选技能、理由
  2. 用户确认模式：默认必须确认，可配置关闭
  3. 配置系统支持：routing.confirmation_mode

  需要修改的核心部分：

  1. 数据模型扩展 (src/vibesop/core/models.py)
    • LayerResult 增加 reason, duration_ms, diagnostics
    • RoutingResult 增加 layer_details: list[LayerDetail]
    • 新增 LayerDetail 模型
  2. 路由配置扩展 (src/vibesop/core/config/manager.py)
    • RoutingConfig 增加 confirmation_mode: str = "always" (always | never | ambiguous_only)
    • DEFAULT_CONFIG 同步更新
  3. 路由引擎增强 (src/vibesop/core/routing/unified.py)
    • _execute_layers() 收集所有层结果（不只是匹配的）
    • 每层方法填充 reason 和 diagnostics
    • _build_result() 包含 layer_details
  4. CLI 交互增强 (src/vibesop/cli/main.py)
    • route 命令增加 --yes / --no-confirm 选项
    • 当 confirmation_mode=always 时，展示决策报告并等待用户确认
    • 展示：原始查询、识别的意图、候选技能列表、选择理由、执行计划
    • 交互选项：确认 / 重选技能 / 跳过（退化到普通 Agent）
  5. 透明度渲染 (src/vibesop/cli/routing_report.py - 新文件)
    • 将 RoutingResult 渲染为漂亮的 Rich 决策树

  让我现在编写计划文件。

  实际上，我需要仔细考虑实现范围。用户的核心诉求是：

  • "决策过程看不到"
  • "只会使用某一个技能"
  • "使用技能的理由没有展示"
  • "没有选择同类技能的候选"

  这主要是一个路由透明度 + 用户确认的问题，而不是完整的 TaskDecomposer + SkillOrchestrator。

  所以计划应该聚焦在：

  1. 让路由决策可见
  2. 让用户有选择权
  3. 可配置确认模式

  多技能组合（TaskDecomposer）可以列为 Phase 2。
