# OpenCode Configuration Research

**Date:** 2026-03-06  
**Purpose:** Research effective agent configurations and plugins for ko2-tools project

---

## Web Search Status

**Issue:** Web search was returning empty results.

**Root cause:** Two separate issues:

1. **Built-in `websearch` tool** - requires `OPENCODE_ENABLE_EXA=true` environment variable (uses Exa AI, no API key needed)
   ```bash
   OPENCODE_ENABLE_EXA=1 opencode
   ```

2. **`web-search-prime_web_search_prime` MCP tool** - from external MCP server, not the built-in tool

**Current MCP servers:**
- `fetch` - URL fetching only
- `mcp-registry` - MCP server discovery
- `meta-prompting` - Meta-prompting
- `sequential-thinking` - Sequential thinking

**Note:** The `web-search-prime_web_search_prime` tool referenced in old experiment files is from an external MCP server that was configured in past experiments but is no longer active.

---

## Effective Agent Types (Proven Patterns)

Based on analysis of installed plugins and agent configurations across multiple marketplaces.

### 1. Architect Agents (Highly Effective)

**Found in:**
- `sc-system-architect.md` (superclaude)
- `sc-frontend-architect.md` (superclaude)
- `sc-backend-architect.md` (superclaude)
- `sc-devops-architect.md` (superclaude)
- `code-architect.md` (feature-dev)

**Pattern:**
> Senior software architect who designs feature architectures by analyzing existing codebase patterns and conventions, then providing comprehensive implementation blueprints with specific files to create/modify, component designs, data flows, and build sequences.

**Why effective:**
- Analyzes existing patterns BEFORE proposing solutions
- Makes decisive architectural choices (not multiple options)
- Provides specific file paths, function names, concrete steps
- Clear output structure

**Output structure:**
1. Patterns & Conventions Found (with file:line references)
2. Architecture Decision (with rationale and trade-offs)
3. Component Design (file path, responsibilities, dependencies, interfaces)
4. Implementation Map (specific files to create/modify)
5. Data Flow (complete flow from entry to output)
6. Build Sequence (phased implementation steps)
7. Critical Details (error handling, state management, testing, performance, security)

**Use for:**
- ARCH-001: Split ko2.py into modules
- ARCH-002: Extract shared service layer
- ARCH-006: Reorganize source tree for multiple frontends

---

### 2. Reviewer/Quality Agents (Highly Effective)

**Found in:**
- `code-reviewer.md` (cc-handbook)
- `sc-quality-engineer.md` (superclaude)
- `sc-root-cause-analyst.md` (superclaude)
- `chris.md` (custom adversarial researcher)

**Pattern:**
> Provides systematic analysis without modifying code - only analyzes and provides structured feedback.

**Why effective:**
- Non-destructive (read-only analysis)
- Structured output format
- Clear boundaries (won't auto-fix)
- Specific feedback categories

**Example: code-reviewer.md**
```yaml
tools: SlashCommand, Bash(git *), Read, Search, Ls, Grep, Glob
```
- Invokes `/review` command
- Returns output as-is
- Does NOT modify or fix code
- Provides structured code review feedback

**Example: chris.md (Adversarial Researcher)**
- Actively tries to DISPROVE technical claims
- Finds edge cases, caveats, exceptions
- Output: SAFE / NEEDS CAVEATS / FALSE verdict
- Research quality hierarchy: CVEs > Official docs > RFCs > Production war stories

**Use for:**
- Post-implementation review of P0 changes
- TEST-002: Validate _detect_channels implementation
- PROT-002: Verify device_info() implementation approach

---

### 3. Research/Discovery Agents (Highly Effective)

**Found in:**
- `scout.md` (custom ecosystem discovery specialist)
- `sc-deep-research-agent.md` (superclaude)
- `sc-repo-index.md` (superclaude)

**Pattern:**
> Searches across ecosystem sources to find existing solutions before building from scratch.

**Why effective:**
- Prevents reinventing the wheel
- Provides fit scoring (High/Medium/Low)
- Complexity assessment (Simple/Moderate/Complex)
- Build vs. Buy recommendation

**Example: scout.md**
```yaml
tools: WebSearch, WebFetch, Read, Grep, Glob
```
- Searches: GitHub repos, marketplaces, community collections
- Analyzes: Functional fit, quality indicators, complexity, integration effort
- Presents: Top 3-5 matches ranked by relevance with pros/cons

**Use for:**
- Finding existing solutions before implementing new features
- DATA-001: Research existing sample database patterns
- EMU-001: Find emulator documentation patterns

---

### 4. Configuration/Workflow Agents (Highly Effective)

**Found in:**
- `kim.md` (custom configuration specialist)
- `sc-python-expert.md` (superclaude)
- `sc-refactoring-expert.md` (superclaude)

**Pattern:**
> Systematic task execution with verification loops and lessons-learned logging.

**Why effective:**
- Delegation model (you provide task, agent executes with validation)
- Success criteria framework
- Lessons-learned logging for future reference
- Quality checkpoints before completion

**Example: kim.md**
```yaml
tools: Read, Write, Edit, Bash, Glob, Grep, TodoWrite, WebFetch, WebSearch
model: sonnet
```

**Systematic workflow:**
1. Understand Task (parse, identify deliverables, assess complexity)
2. Verify Feasibility (check competency, tools, permissions, boundaries)
3. Research (if needed - check working knowledge, lessons learned, official docs)
4. Plan Approach (break into steps, identify file operations, plan validation)
5. Execute with Validation (perform operations, validate each step, track changes)
6. Verify Success (quality checklist, no side effects, documentation updated)
7. Report Results (structured format with metrics)

**Constitutional checkpoints:**
- ✓ Scope: Stayed within delegated task boundaries?
- ✓ Quality: Files syntactically valid and functional?
- ✓ Boundaries: Avoided modifying project content (only configs)?
- ✓ Impact: Can quantify result (tokens saved, features added)?
- ✓ Documentation: Logged lessons learned?

**Use for:**
- Creating detailed implementation plans for backlog items
- Writing findings and documentation
- Systematic configuration changes

---

### 5. Planner Agents (Moderately Effective)

**Found in:**
- `project-planner.md` (meta-cc-marketplace)
- `phase-planner-executor.md` (meta-cc-marketplace)

**Pattern:**
> Analyzes project documentation and status to generate development plans with TDD iterations.

**Why moderately effective:**
- Good for structured planning
- Can be overkill for simple tasks
- Best for complex, multi-iteration projects

**Example: project-planner.md**
```yaml
description: Analyzes project documentation and status to generate development plans with TDD iterations
```
- Input: docs, state
- Output: plan with iterations
- Constraints: |code(i)| ≤ 500, |test(i)| ≤ 500
- Structure: objectives, stages, acceptance_criteria, dependencies

**Limitation:** Most planner agents don't have write tools by design.

---

## Plugin Recommendations

### Installed Marketplaces

| Marketplace | Description | Notable Content |
|------------|-------------|-----------------|
| **anthropic-agent-skills** | Official Anthropic skills | docx, pptx, xlsx, pdf, mcp-builder, skill-creator |
| **superclaude** | Comprehensive agent collection | 24 agents (architects, researchers, quality) |
| **cc-handbook** | Claude Code handbook | code-reviewer, git worktree integration |
| **claude-code-plugins** | Community plugins | feature-dev, code-architect |
| **superpowers-dev** | Development workflows | brainstorming, debugging, TDD, code review |
| **every-marketplace** | Meta-marketplace | compound-engineering, architecture patterns |

### Highly Praised Plugins

#### 1. SuperClaude (sc@superclaude)
**Agents included:**
- `sc-system-architect` - System architecture design
- `sc-frontend-architect` - Frontend patterns and components
- `sc-backend-architect` - Backend services and APIs
- `sc-devops-architect` - Infrastructure and deployment
- `sc-quality-engineer` - Quality assurance and testing
- `sc-deep-research-agent` - Autonomous web research
- `sc-python-expert` - Python best practices
- `sc-refactoring-expert` - Code refactoring patterns
- `sc-performance-engineer` - Performance optimization
- `sc-root-cause-analyst` - Debugging and root cause analysis
- `sc-requirements-analyst` - Requirements gathering
- `sc-business-panel-experts` - Business domain expertise
- `sc-learning-guide` - Educational content creation
- `sc-pm-agent` - Product management
- `sc-socratic-mentor` - Teaching and mentoring

**Installation:**
```bash
/plugin marketplace add superclaude
/plugin install sc@superclaude
```

#### 2. CC-Handbook (handbook@cc-handbook)
**Features:**
- Code reviewer agent
- Git worktree workflows
- Development best practices

**Already installed**

#### 3. Anthropic Agent Skills (anthropic-agent-skills)
**Skills included:**
- Document creation: docx, pptx, xlsx, pdf
- MCP builder
- Skill creator
- Web app testing
- Frontend design
- Brand guidelines

**Installation:**
```bash
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
/plugin install example-skills@anthropic-agent-skills
```

---

## Recommended Configuration for ko2-tools

### Essential Agents to Keep

1. **Chris** (adversarial researcher)
   - File: `~/.claude/agents/chris.md`
   - Use: P0 item validation, protocol verification
   - Why: Actively disproves claims, finds edge cases

2. **Scout** (ecosystem discovery)
   - File: `~/.claude/agents/scout.md`
   - Use: Finding existing solutions before building
   - Why: Prevents reinventing, provides fit scoring

3. **Kim** (configuration specialist)
   - File: `~/.claude/agents/kim.md`
   - Use: Plan writing, systematic execution
   - Why: Has write tools, validation loops, lessons learned

### Agents to Add/Install

#### For Architecture Work (P0: ARCH-001, ARCH-002)

**Option A: Use superclaude**
```bash
/plugin install sc@superclaude
# Use: sc-system-architect
```

**Option B: Use existing code-architect**
```bash
# Already in claude-code-plugins
# Use: code-architect
```

**Why:** Architect agents analyze existing patterns before proposing solutions, make decisive choices, provide specific file paths and implementation steps.

#### For Quality/Testing (P1: TEST-001 through TEST-004)

**Use: chris** (adversarial researcher)
- Validate test coverage claims
- Find edge cases in _detect_channels
- Verify error recovery paths

#### For Protocol Discovery (P0-P1: PROT-001 through PROT-006)

**Use: sc-deep-research-agent** (from superclaude)
```bash
/plugin install sc@superclaude
# Use: sc-deep-research-agent
```

**Why:** Autonomous web research with evidence synthesis.

#### For TUI Work (P0-P2: TUI-001 through TUI-015)

**Use: sc-frontend-architect** (from superclaude)
```bash
# After installing superclaude
# Use: sc-frontend-architect
```

**Why:** Frontend patterns, component design, UI architecture.

---

## Plan Agent: Writing Findings & Detailed Plans

### Problem
Most planner agents don't have write tools by design - they only analyze and plan.

### Solution Options

#### Option 1: Enhance Planner with Write Tools (Not Recommended)
Create new agent with write capabilities:
```yaml
---
name: project-planner-enhanced
description: Analyzes project documentation and creates detailed implementation plans with write capabilities
tools: Read, Write, Edit, Glob, Grep, LS, WebSearch, WebFetch
model: sonnet
---
```

**Drawbacks:**
- Duplicates Kim's functionality
- Another agent to maintain
- Unclear boundaries between planner and executor

#### Option 2: Use Kim for Plan Writing (Recommended)
**Kim already has:**
- Read, Write, Edit tools
- Systematic execution workflow
- Validation loops
- Lessons-learned logging
- Success criteria framework

**Workflow:**
```
User → "Kim, analyze BACKLOG.md P0 items and create detailed implementation plans for ARCH-001 and ARCH-002"

Kim executes:
1. Read BACKLOG.md (understand requirements)
2. Analyze ko2.py structure (assess current state)
3. Create plans/ARCH-001-implementation-plan.md (write output)
4. Create plans/ARCH-002-service-layer-plan.md (write output)
5. Verify success (quality checklist)
6. Report results with metrics
```

**Why recommended:**
- Kim already designed for this workflow
- Has write tools and validation
- Logs lessons learned
- No new agent needed

#### Option 3: Hybrid Approach (For Complex Planning)
1. Use planner agent for analysis (read-only)
2. Delegate to Kim for writing the plan
3. Use architect agent for design decisions

**Workflow:**
```
User → planner: "Analyze ARCH-001 requirements"
Planner → outputs analysis (no files written)
User → kim: "Write detailed implementation plan based on planner's analysis"
Kim → writes plans/ARCH-001.md
User → architect: "Review and refine the plan"
Architect → provides refinements
```

### Recommendation
**Use Kim for plan writing** - she has the tools, workflow, and validation already built in.

---

## Agent Selection Matrix for Backlog

| Backlog Item | Recommended Agent | Why |
|-------------|-------------------|-----|
| ARCH-001: Split ko2.py | sc-system-architect or code-architect | Analyzes patterns, provides specific file structure |
| ARCH-002: Service layer | sc-backend-architect | Backend service design patterns |
| ARCH-003: Class renaming | kim | Configuration specialist with write tools |
| ARCH-004: Refactor commands | sc-refactoring-expert | Refactoring patterns |
| TEST-001: Squash fix verification | chris | Adversarial validation |
| TEST-002: Channel detection tests | chris | Find edge cases |
| TEST-003: Error recovery tests | sc-quality-engineer | Quality assurance |
| PROT-001: Playback protocol | sc-deep-research-agent | Autonomous research |
| PROT-002: device_info() | chris | Verify implementation approach |
| TUI-001: Enter in popups | sc-frontend-architect | UI patterns |
| TUI-004: Sorting | sc-frontend-architect | Table/UI patterns |
| DATA-001: Sample database | scout | Find existing solutions |
| EMU-001: Emulator docs | kim | Write documentation |
| META-001: Git cleanup | kim | Configuration and workflow |

---

## Installation Commands

### Install Recommended Agents

```bash
# 1. Install superclaude marketplace (24 agents)
/plugin marketplace add superclaude
/plugin install sc@superclaude

# 2. Verify current agents are working
ls ~/.claude/agents/
# Should see: chris.md, scout.md, kim.md

# 3. Test agent availability
# In Claude Code:
/delegate sc-system-architect "Analyze ko2.py structure"
```

### List Available Agents

```bash
# After installation, available agents:
# From superclaude:
sc-system-architect
sc-frontend-architect
sc-backend-architect
sc-devops-architect
sc-quality-engineer
sc-deep-research-agent
sc-python-expert
sc-refactoring-expert
sc-performance-engineer
sc-root-cause-analyst
sc-requirements-analyst
sc-business-panel-experts
sc-learning-guide
sc-pm-agent
sc-socratic-mentor

# From custom:
chris
scout
kim
```

---

## Usage Patterns

### Pattern 1: Architecture Work
```bash
# Step 1: Analyze existing patterns
/delegate sc-system-architect "Analyze ko2.py and design module split plan"

# Step 2: Write the plan
/delegate kim "Create detailed implementation plan for ARCH-001 based on architect's analysis"

# Step 3: Validate approach
/delegate chris "Verify that the proposed split won't break existing functionality"
```

### Pattern 2: Protocol Discovery
```bash
# Step 1: Research existing implementations
/delegate scout "Find existing EP-133 protocol documentation"

# Step 2: Deep dive research
/delegate sc-deep-research-agent "Research MIDI SysEx protocol patterns for playback implementation"

# Step 3: Write findings
/delegate kim "Document protocol findings in PROTOCOL.md"
```

### Pattern 3: Quality Assurance
```bash
# Step 1: Validate test coverage
/delegate chris "Verify that _detect_channels tests cover edge cases"

# Step 2: Design tests
/delegate sc-quality-engineer "Design test suite for upload error recovery"

# Step 3: Write tests
# (Main Claude does implementation)
```

### Pattern 4: TUI Development
```bash
# Step 1: Design UI patterns
/delegate sc-frontend-architect "Design TUI sorting interface with constraints"

# Step 2: Write implementation plan
/delegate kim "Create implementation plan for TUI-004 sorting feature"

# Step 3: Validate UX
/delegate chris "Verify that sorting constraints prevent data corruption"
```

---

## Lessons Learned

### What Works Well
1. **Specialized agents** with narrow focus (architect, reviewer, researcher)
2. **Clear boundaries** (read-only vs. write-capable)
3. **Systematic workflows** with validation (Kim's approach)
4. **Adversarial validation** (Chris's approach)
5. **Ecosystem discovery** before building (Scout's approach)

### What Doesn't Work Well
1. **Generic agents** trying to do everything
2. **Planner agents without write tools** (creates handoff friction)
3. **Agents that auto-fix** (better to provide structured feedback)
4. **Multiple options instead of decisive choices** (architects should decide)

### Key Insights
1. **Separation of concerns:** Analysis → Planning → Execution should use different agents
2. **Write capability is special:** Only give to agents that need it (Kim, not planners)
3. **Validation loops are critical:** Kim's success checklist prevents errors
4. **Lessons learned are valuable:** Kim's logging improves future sessions
5. **Adversarial stance is powerful:** Chris's skepticism finds real issues

---

## Next Steps

1. **Install superclaude marketplace:**
   ```bash
   /plugin marketplace add superclaude
   /plugin install sc@superclaude
   ```

2. **Use Kim for plan writing:**
   ```bash
   /delegate kim "Create detailed implementation plans for P0 backlog items ARCH-001 and ARCH-002"
   ```

3. **Use architects for design:**
   ```bash
   /delegate sc-system-architect "Design module structure for ko2.py split"
   ```

4. **Use Chris for validation:**
   ```bash
   /delegate chris "Verify that proposed architecture changes won't break existing functionality"
   ```

---

## References

### Agent Files (Your Custom)
- `~/.claude/agents/chris.md` - Adversarial researcher
- `~/.claude/agents/scout.md` - Ecosystem discovery
- `~/.claude/agents/kim.md` - Configuration specialist

### Marketplaces
- `~/.claude/plugins/marketplaces/superclaude/` - 24 agents
- `~/.claude/plugins/marketplaces/cc-handbook/` - Code reviewer
- `~/.claude/plugins/marketplaces/anthropic-agent-skills/` - Official skills

### Documentation
- `~/.claude/knowledge/plugins-agents-reference.md` - Installation reference
- `~/.claude/CLAUDE.md` - Global conventions
- `https://opencode.ai` - OpenCode documentation
- `https://github.com/anthropics/skills` - Official skills repository
