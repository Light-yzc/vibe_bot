# tool_use_loop

description: Decide when to call tools and how to continue after tool results.

## When to use
- A task needs state updates or external data
- The agent must perform multiple steps

## Guidance
- Answer directly when no tool is needed.
- Use tools for real state changes or state reads.
- After a tool result, continue naturally instead of dumping raw data.

## Do
- Use the smallest tool call needed.
- Mention success clearly after a state update.

## Avoid
- Pretending a tool-backed change happened without calling a tool.
- Repeating the same read tool over and over.

## Examples
- 先更新关系状态，再告诉用户称呼已经改好了。
