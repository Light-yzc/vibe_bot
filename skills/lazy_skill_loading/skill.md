# lazy_skill_loading

description: Load only relevant skill sections on demand instead of loading full skill files.

## When to use
- User asks about architecture or prompt organization
- The agent needs extra behavior guidance for a specific topic

## Guidance
- Start from the skill catalog summary.
- Load only Guidance, Do, and Avoid by default.
- Load Examples only if wording help is truly needed.

## Do
- Use load_skill_section with targeted sections.
- Reuse loaded guidance in the current task.

## Avoid
- Loading full skill files by default.
- Loading unrelated skills just in case.

## Examples
- 先加载 relationship_rules 的 Guidance 和 Avoid，不要直接整篇全拿。
