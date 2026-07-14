// Kimi-Gated Fix — 动态工作流模板
// pipeline: Design(核对精确 diff) → KimiReview(改动前 kimi 复审) → Apply(仅 APPROVE 落盘) → Verify(build)
//
// 用法:
//   1) 改下方 PROJECT CONFIG 几行
//   2) 用 Workflow 工具调用, args = { bugContext: "...", items: [{key,file,why,proposedOld,proposedNew}] }
//   3) proposedOld 必须是文件里的精确原文(含缩进)

export const meta = {
  name: 'kimi-gated-fix',
  description: '定点修复: Design->Kimi 改动前复审->仅 APPROVE 才 Apply->build 验证',
  phases: [
    { title: 'Design', detail: '逐项 Read 核对精确 diff(只读)' },
    { title: 'KimiReview', detail: '改动应用前 kimi 独立复审每处' },
    { title: 'Apply', detail: '仅 kimi APPROVE 才 Edit 落盘' },
    { title: 'Verify', detail: 'build / 类型检查' },
  ],
}

// ================== PROJECT CONFIG (按项目改这几行) ==================
const REPO = '/Users/huchen/Projects/<repo>'
const KIMI = '/Users/huchen/.kimi-code/bin/kimi'
const BUILD_CMD = 'npm run build'   // 类型检查/构建命令
const TEST_CMD = null               // 定向测试命令或 null(避开已知 hang 的整包测试)
// ===================================================================

const DESIGN_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    key: { type: 'string' }, file: { type: 'string' },
    oldString: { type: 'string' }, newString: { type: 'string' },
    verifiedInFile: { type: 'boolean' }, notes: { type: 'string' },
  },
  required: ['key', 'file', 'oldString', 'newString', 'verifiedInFile'],
}
const KIMI_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    key: { type: 'string' }, file: { type: 'string' }, oldString: { type: 'string' },
    approved: { type: 'boolean' }, kimiRan: { type: 'boolean' },
    finalNewString: { type: 'string' }, verdict: { type: 'string' },
    concerns: { type: 'array', items: { type: 'string' } },
  },
  required: ['key', 'file', 'oldString', 'approved', 'kimiRan', 'finalNewString'],
}
const APPLY_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    key: { type: 'string' }, file: { type: 'string' }, applied: { type: 'boolean' },
    kimiApproved: { type: 'boolean' }, kimiRan: { type: 'boolean' },
    kimiVerdict: { type: 'string' }, note: { type: 'string' },
  },
  required: ['key', 'file', 'applied', 'kimiApproved', 'note'],
}
const BUILD_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    buildOk: { type: 'boolean' }, output: { type: 'string' },
    errorLines: { type: 'array', items: { type: 'string' } },
  },
  required: ['buildOk', 'output'],
}

const bugContext = (args && args.bugContext) || '(在此描述 bug 根因)'
const items = Array.isArray(args && args.items) ? args.items : []

if (items.length === 0) {
  log('args.items 为空 — 请传 [{key,file,why,proposedOld,proposedNew}]')
  return { applied: [], build: null }
}

function designPrompt(item) {
  return [
    '核对一处定点修复的精确 diff(只读,不要改文件)。',
    '仓库根: ' + REPO,
    '== bug 背景 ==', bugContext,
    '== 本次改动 ==',
    'key: ' + item.key + '   文件: ' + item.file,
    '目的: ' + item.why,
    '== 拟替换旧代码(proposedOld) ==', item.proposedOld,
    '== 拟替换新代码(proposedNew) ==', item.proposedNew,
    '步骤: Read ' + item.file + ' 相应区域 → 判断 proposedOld 是否逐字存在(空格/缩进/换行一致)。',
    '完全一致: oldString=proposedOld, verifiedInFile=true。缩进微差: oldString 用真实原文并对齐, notes 写明。',
    '找不到: verifiedInFile=false。newString 沿用 proposedNew(或对齐缩进)。',
  ].join('\n')
}

function kimiReviewPrompt(design) {
  const fileBody = [
    '复审以下代码改动,判断是否 (a) 正确修复根因 (b) 无回归 (c) 最小清晰。',
    '文件: ' + design.file,
    '【旧代码】', design.oldString,
    '【新代码】', design.newString,
    '第一行写 APPROVE 或 REJECT;随后理由;若建议修改给出完整新代码块。',
  ].join('\n')
  return [
    '你是 kimi 复审协调员。改动应用前调 kimi 独立复审。',
    '== bug 背景 ==', bugContext,
    '== 待复审 == key:' + design.key + ' 文件:' + design.file,
    '旧代码:', design.oldString, '新代码:', design.newString,
    '步骤:',
    '1. 用 Write 工具把下面 ===P=== 与 ===E=== 之间的文字写入 /tmp/kimi_' + design.key + '.md:',
    '===P===', fileBody, '===E===',
    '2. Bash 运行: ' + KIMI + ' -p "$(< /tmp/kimi_' + design.key + '.md)" --output-format text',
    '3. 解析第一行 APPROVE/REJECT。',
    '返回: approved(仅 APPROVE 为 true), kimiRan(调用成功), finalNewString(kimi 给更好代码则采用,否则沿用新代码), verdict, concerns, 回填 key/file/oldString。',
    'REJECT 或调用失败 → approved=false, verdict/concerns 写明。',
  ].join('\n')
}

function applyPrompt(review) {
  return [
    '按 kimi 复审结论应用(或跳过)一处改动。',
    'key:' + review.key + ' 文件:' + review.file + '(仓库根 ' + REPO + ')',
    'kimi: approved=' + review.approved + ' kimiRan=' + review.kimiRan,
    '== 要替换旧代码(oldString) ==', review.oldString,
    '== 最终新代码(finalNewString) ==', review.finalNewString,
    '规则: 仅 approved===true 才应用(先 Read 再 Edit 把 oldString 精确替换为 finalNewString)。',
    'approved!==true 不改文件, applied=false。Edit 不匹配也 applied=false。回填 kimiApproved/kimiRan/kimiVerdict。',
  ].join('\n')
}

phase('Design')
log('对 ' + items.length + ' 处改动逐条走 Design -> Kimi 复审 -> Apply')

const applied = await pipeline(
  items,
  (item) => agent(designPrompt(item), { schema: DESIGN_SCHEMA, phase: 'Design', label: 'design:' + item.key }),
  (design) => agent(kimiReviewPrompt(design), { schema: KIMI_SCHEMA, phase: 'KimiReview', label: 'kimi:' + design.key, effort: 'high' }),
  (review) => agent(applyPrompt(review), { schema: APPLY_SCHEMA, phase: 'Apply', label: 'apply:' + review.key }),
)

phase('Verify')
const testLine = TEST_CMD ? '\n再运行定向测试(跳过整包): ' + TEST_CMD : ''
const build = await agent(
  [
    '运行构建验证改动不破坏编译。仓库根: ' + REPO,
    '运行: cd ' + REPO + ' && ' + BUILD_CMD + testLine,
    '捕获 stdout+stderr。返回 {buildOk: 退出码为0, output: 末尾摘要, errorLines: 报错行}。',
    '注意: 不要跑整包 npm test(可能含 hang 的测试)。',
  ].join('\n'),
  { schema: BUILD_SCHEMA, phase: 'Verify', label: 'build' },
)

return { applied: applied.filter(Boolean), build }
