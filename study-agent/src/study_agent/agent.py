from __future__ import annotations

import json
import os
from typing import Any

from .calendar import list_events
from .db import Store
from .github import repository_summary
from .system_clock import system_time


BASE_INSTRUCTIONS = """
你是一个通用的学习、知识管理与项目规划 Agent。当前 Topic 决定本次对话的专业上下文。

目标：帮助用户学习任何课程或主题，把知识转化为理解、练习、作品、项目和可验证成果。对于技术与职业 Topic，进一步连接真实工业场景与简历证据。

规则：
1. 每日只安排 2-4 项任务，总时长不得超过用户可用时间的 80%。
2. 每天至少一个可验证产出：代码、测试、架构图、指标、实验结论或文档。
3. 课程是输入，掌握与可验证输出是结果。根据当前 Topic 选择笔记、练习、实验、作品或项目；不要把主题强行改写成某个预设领域。
4. 不能虚构完成情况、指标、用户量或简历经历。未知数字写成 [待测]。
5. 调用工具读取真实状态，并用 create_task、complete_task、record_evidence 更新长期记忆。
6. GitHub 和 Calendar 工具只读。你不能自行创建日历事件；只能提出建议，由用户在 CLI 确认。
7. 回答默认用中文；涉及求职项目时，简历 bullet 同时给英文。
8. 技术讨论要包含 trade-off、失败模式、可观测指标和验证方法；非技术主题则给相应的练习与检验方法。

今日计划输出必须包含：今日目标、任务与时间、完成标准、阻塞时的最小替代方案、一道复习或自测问题。
晚间复盘必须包含：实际进展、证据、未完成项如何处理、次日最重要任务；仅在求职 Topic 中、且有真实证据时给英文简历 bullet。
"""

INSIGHTS_INSTRUCTIONS = """
你是一个跨 Topic 的通用学习分析师。根据提供的真实本地数据生成学习洞察。
不要虚构完成情况、项目、指标或经验。信息不足时明确写“尚无证据”。
重点把课程知识转化成真正掌握、可验证产出和适合当前 Topic 的项目；技术 Topic 进一步连接工业界能力与作品集证据。

只返回一个合法 JSON object，不要 Markdown code fence，不要额外文字。结构必须是：
{
  "overview": "2-4 句总体判断",
  "strengths": ["有证据支持的优势"],
  "gaps": [{"topic": "知识缺口", "why": "为何重要", "evidence": "从数据看到的依据"}],
  "meaningful_questions": [
    {
      "question": "用户问过或应该反复练习的有价值问题",
      "why_it_matters": "学习、实践或职业价值",
      "missing_concept": "尚未掌握的核心概念",
      "review_prompt": "下次用于自测的问题"
    }
  ],
  "next_learning": [
    {"priority": 1, "topic": "下一主题", "why": "选择理由", "next_action": "30-120 分钟可执行动作", "done_when": "完成标准"}
  ],
  "industry_projects": [
    {
      "name": "项目名",
      "industrial_use": "真实公司为何需要",
      "architecture": ["组件或数据流"],
      "milestones": ["递进里程碑"],
      "metrics": ["需要测量的指标"],
      "resume_evidence": "最终可写简历的真实证据；未知数字使用 [待测]"
    }
  ]
}

约束：
1. meaningful_questions 选择 3-8 个真正能暴露理解深度的问题，不要机械复制闲聊。
2. next_learning 最多 5 项，按依赖关系和用户目标排序。
3. industry_projects 给 2-4 个适合当前 Topic 的真实项目；技术项目应能在个人环境中做出并体现 production trade-off。
4. 技术项目必须涉及可靠性、可观测性、成本/延迟、安全或部署中的至少两类；非技术项目使用该领域相应的质量指标。
5. 默认中文；resume_evidence 使用英文。
"""


def insights_payload(store: Store) -> dict[str, Any]:
    profile = store.profile() or {}
    context: dict[str, Any] = {
        "system_time": system_time(),
        "profile": profile,
        "topics": store.topics(),
        "tasks": store.tasks(limit=100),
        "checkins": store.checkins(limit=30),
        "evidence": store.evidence(limit=50),
        "conversation_history": store.recent_messages(limit=200),
    }
    repo = profile.get("github_repo")
    if repo:
        try:
            context["github"] = repository_summary(repo)
        except (RuntimeError, ValueError, OSError) as exc:
            context["github"] = {"unavailable": str(exc)}
    return {
        "instructions": INSIGHTS_INSTRUCTIONS,
        "input": json.dumps(context, ensure_ascii=False, indent=2),
    }


def direct_chat_payload(
    store: Store,
    message: str,
    conversation: list[dict[str, Any]] | None = None,
    topic_name: str = "General",
) -> dict[str, Any]:
    """Build a Responses API payload for ChatGPT-plan inference.

    Sign in with ChatGPT currently supports text inference but not the Agents SDK
    tool loop, so we provide the same verified local context up front. External
    integrations are best-effort: a missing GitHub token or Calendar permission
    must not prevent ordinary coaching conversations.
    """
    profile = store.profile() or {}
    context: dict[str, Any] = {
        "system_time": system_time(),
        "active_topic": topic_name,
        "profile": profile,
        "open_tasks": [
            task
            for task in store.tasks(limit=30)
            if task["status"] in {"planned", "doing"}
        ],
        "recent_checkins": store.checkins(limit=7),
        "recent_evidence": store.evidence(limit=20),
    }
    repo = profile.get("github_repo")
    if repo:
        try:
            context["github"] = repository_summary(repo)
        except (RuntimeError, ValueError, OSError) as exc:
            context["github"] = {"unavailable": str(exc)}
    try:
        context["calendar"] = list_events(7)
    except (RuntimeError, ValueError, OSError) as exc:
        context["calendar"] = {"unavailable": str(exc)}

    instructions = (
        BASE_INSTRUCTIONS
        + "\n你正在通过 Continue with ChatGPT 的安全文字推理通道运行。"
        + "本次不能直接调用数据库写工具；不得声称已经创建、完成或修改任务。"
        + "如果用户需要写操作，清楚列出建议变更，并请用户确认后在应用的 API-key 模式执行。"
        + "\n\n以下是只读的本地真实上下文：\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )
    input_messages = [
        {"role": item["role"], "content": item["content"]}
        for item in (conversation or [])[-30:]
        if item.get("role") in {"user", "assistant"}
    ]
    input_messages.append({"role": "user", "content": message})
    return {"instructions": instructions, "input": input_messages}


def build_agent(store: Store):
    try:
        from agents import Agent, function_tool
    except ImportError as exc:
        raise RuntimeError(
            "Missing openai-agents. Run: python -m pip install -e ."
        ) from exc

    @function_tool
    def get_profile() -> str:
        """Return the learner profile and course progress."""
        return json.dumps(store.profile(), ensure_ascii=False)

    @function_tool
    def get_open_tasks() -> str:
        """Return planned and active learning tasks."""
        tasks = store.tasks(limit=30)
        return json.dumps(
            [task for task in tasks if task["status"] in {"planned", "doing"}],
            ensure_ascii=False,
        )

    @function_tool
    def get_recent_checkins() -> str:
        """Return recent morning, evening, and weekly check-ins."""
        return json.dumps(store.checkins(limit=7), ensure_ascii=False)

    @function_tool
    def get_evidence() -> str:
        """Return recent verified project and learning evidence."""
        return json.dumps(store.evidence(limit=20), ensure_ascii=False)

    @function_tool
    def get_system_time() -> str:
        """Read the Mac's current local date, time, timezone, and UTC offset."""
        return json.dumps(system_time(), ensure_ascii=False)

    @function_tool
    def create_task(
        title: str, details: str, estimate_minutes: int, due_date: str = ""
    ) -> str:
        """Create one concrete learning task. due_date uses YYYY-MM-DD or empty."""
        task_id = store.add_task(
            title, details, estimate_minutes, due_date or None
        )
        return f"Created task {task_id}"

    @function_tool
    def complete_task(task_id: int) -> str:
        """Mark a task complete only after the user reports it complete."""
        return "Task completed" if store.set_task_status(task_id, "done") else "Task not found"

    @function_tool
    def record_evidence(
        kind: str, value: str, note: str = "", task_id: int = 0
    ) -> str:
        """Record a commit, URL, benchmark, screenshot, test result, or design document."""
        evidence_id = store.add_evidence(task_id or None, kind, value, note)
        return f"Recorded evidence {evidence_id}"

    @function_tool
    def get_github_summary() -> str:
        """Read recent commits, open PRs, and issues from the configured GitHub repository."""
        profile = store.profile() or {}
        repo = profile.get("github_repo")
        if not repo:
            return "No GitHub repository configured."
        return json.dumps(repository_summary(repo), ensure_ascii=False)

    @function_tool
    def get_calendar_events(days: int = 7) -> str:
        """Read macOS Calendar events for the next 1-30 days."""
        return json.dumps(list_events(days), ensure_ascii=False)

    return Agent(
        name="General Study Agent",
        instructions=BASE_INSTRUCTIONS,
        model=os.getenv("OPENAI_MODEL", "gpt-6-astra"),
        tools=[
            get_profile,
            get_open_tasks,
            get_recent_checkins,
            get_evidence,
            get_system_time,
            create_task,
            complete_task,
            record_evidence,
            get_github_summary,
            get_calendar_events,
        ],
    )


async def run_agent(
    store: Store,
    message: str,
    conversation: list[dict[str, Any]] | None = None,
    topic_name: str = "General",
) -> str:
    try:
        from agents import Runner
    except ImportError as exc:
        raise RuntimeError(
            "Missing openai-agents. Run: python -m pip install -e ."
        ) from exc
    agent = build_agent(store)
    context: dict[str, Any] = {
        "system_time": system_time(),
        "active_topic": topic_name,
        "profile": store.profile(),
        "open_tasks": [
            task
            for task in store.tasks(limit=20)
            if task["status"] in {"planned", "doing"}
        ],
        "recent_checkins": store.checkins(limit=3),
        "recent_evidence": store.evidence(limit=8),
        "conversation": conversation or [],
    }
    prompt = (
        "以下是本地数据库中的真实上下文：\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\n\n用户请求：\n"
        + message
    )
    result = await Runner.run(agent, prompt, max_turns=12)
    return str(result.final_output)

