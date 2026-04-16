
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from utils import utc_now_iso

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


PERSONAS: dict[str, dict[str, Any]] = {
    "Agency Founder / Owner": {
        "focus": "efficiency, cost control, growth, reducing manual work",
        "tone": "direct, practical, business-focused",
        "cta": "Book a demo",
        "ab_versions": {
            "A": {
                "label": "ROI framing",
                "focus": "protecting margins, reducing hidden operational costs, improving capacity",
                "hook": "Many small agencies do not have a demand problem. They have a margin leak caused by manual workflow overhead.",
            },
            "B": {
                "label": "time-saving framing",
                "focus": "saving team time, speeding delivery, freeing founder attention",
                "hook": "If routine coordination eats hours every week, growth gets capped long before demand does.",
            },
        },
    },
    "Operations Manager": {
        "focus": "workflow standardization, tool integration, team coordination, process reliability",
        "tone": "clear, operational, systems-oriented",
        "cta": "See the workflow in action",
        "ab_versions": {
            "A": {
                "label": "process reliability framing",
                "focus": "reducing handoff errors, improving consistency, tightening review loops",
                "hook": "The real cost of manual workflows is not just time. It is inconsistency across repeated handoffs.",
            },
            "B": {
                "label": "speed and efficiency framing",
                "focus": "faster execution, fewer follow-ups, better throughput",
                "hook": "When teams spend too much time chasing status, speed drops before quality improves.",
            },
        },
    },
    "Marketing / Growth Lead": {
        "focus": "lead generation, campaign performance, content velocity, conversion",
        "tone": "growth-oriented, analytical, persuasive",
        "cta": "Explore growth use cases",
        "ab_versions": {
            "A": {
                "label": "content velocity framing",
                "focus": "faster production, more campaign volume, easier content repurposing",
                "hook": "Growth teams rarely run out of ideas first. They run out of production bandwidth.",
            },
            "B": {
                "label": "conversion optimization framing",
                "focus": "better testing, sharper messaging, improved engagement efficiency",
                "hook": "Automation matters most when it helps growth teams learn faster, not just produce faster.",
            },
        },
    },
}


@dataclass
class GenerationConfig:
    model: str = "gpt-4.1-mini"
    temperature: float = 0.6
    use_mock_if_no_api: bool = True


class ContentGenerator:
    def __init__(self, api_key: str | None, config: GenerationConfig | None = None) -> None:
        self.config = config or GenerationConfig()
        self.client = OpenAI(api_key=api_key) if api_key and OpenAI else None

    def _call_model(self, system_prompt: str, user_prompt: str) -> str:
        if self.client is None:
            if self.config.use_mock_if_no_api:
                raise RuntimeError("OpenAI client unavailable; mock generation should be handled upstream.")
            raise RuntimeError("OPENAI_API_KEY not configured.")

        response = self.client.responses.create(
            model=self.config.model,
            temperature=self.config.temperature,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = getattr(response, "output_text", "") or ""
        if not text.strip():
            raise RuntimeError("OpenAI returned an empty response. Check your API key, model name, and billing/quota.")
        return text.strip()

    def _parse_json_response(self, raw: str) -> dict[str, Any]:
        cleaned = raw.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("Parsed JSON is not an object.")
            return parsed
        except Exception:
            pass

        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            candidate = match.group(0)
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict):
                raise ValueError("Parsed JSON is not an object.")
            return parsed

        raise ValueError(f"Model did not return valid JSON. Raw output:\n{raw}")

    def generate_all(self, topic: str, use_mock: bool = False) -> dict[str, Any]:
        if use_mock or self.client is None:
            return self._generate_mock(topic)

        outline_data = self.generate_outline(topic)
        blog_draft = self.generate_blog(outline_data["title"], outline_data["outline"])

        newsletters: list[dict[str, str]] = []
        for persona, profile in PERSONAS.items():
            for version, version_profile in profile["ab_versions"].items():
                newsletters.append(
                    self.generate_newsletter(
                        persona=persona,
                        base_profile=profile,
                        version=version,
                        version_profile=version_profile,
                        blog_draft=blog_draft,
                    )
                )

        return {
            "topic": topic,
            "generated_at": utc_now_iso(),
            "blog": {
                "title": outline_data["title"],
                "outline": outline_data["outline"],
                "content": blog_draft,
            },
            "newsletters": newsletters,
        }

    def generate_outline(self, topic: str) -> dict[str, Any]:
        system_prompt = (
            "You are a B2B content strategist for a startup serving small creative agencies. "
            "Return only valid JSON. Do not include markdown fences or extra commentary."
        )
        user_prompt = f"""
Given the topic below, generate:
1. A compelling blog title
2. A structured outline with 4-6 sections

Topic: {topic}

Requirements:
- Audience: small creative agencies and decision makers
- Focus on automation trends, workflow efficiency, growth, and productivity
- Each section should include a short description
- Make the angle specific enough to support newsletter testing later

Return JSON in this shape:
{{
  "title": "...",
  "outline": [{{"section": "...", "description": "..."}}]
}}
""".strip()
        raw = self._call_model(system_prompt, user_prompt)
        return self._parse_json_response(raw)

    def generate_blog(self, title: str, outline: list[dict[str, str]]) -> str:
        system_prompt = "You are a startup content writer producing concise, useful B2B blog posts."
        user_prompt = f"""
Using the title and outline below, write a 400-600 word blog post.

Title: {title}
Outline: {json.dumps(outline, ensure_ascii=False)}

Requirements:
- Audience: small creative agencies
- Tone: practical, clear, insight-driven
- Include a strong hook in the first paragraph
- Include a problem statement, why it matters, how automation helps, one example, and a clear takeaway
- Emphasize business impact, operating leverage, and workflow tradeoffs
- Avoid hype and vague claims
""".strip()
        return self._call_model(system_prompt, user_prompt).strip()

    def generate_newsletter(
        self,
        persona: str,
        base_profile: dict[str, Any],
        version: str,
        version_profile: dict[str, str],
        blog_draft: str,
    ) -> dict[str, str]:
        system_prompt = "You write concise B2B newsletters. Return only valid JSON. Do not include markdown fences or extra commentary."
        user_prompt = f"""
Write a short newsletter version of the blog below for this audience.

Persona: {persona}
General focus: {base_profile['focus']}
Tone: {base_profile['tone']}
CTA: {base_profile['cta']}
A/B version: {version}
Version label: {version_profile['label']}
Version focus: {version_profile['focus']}
Suggested opening hook: {version_profile['hook']}

Blog:
{blog_draft}

Requirements:
- 120-180 words
- Include subject, preview_text, body, and cta
- Keep the same core message as the blog, but reframe it for this persona and version
- Make the difference between version A and version B meaningful
- Use a strong first sentence and a clear CTA

Return JSON:
{{
  "persona": "{persona}",
  "version": "{version}",
  "version_label": "{version_profile['label']}",
  "subject": "...",
  "preview_text": "...",
  "body": "...",
  "cta": "{base_profile['cta']}"
}}
""".strip()
        raw = self._call_model(system_prompt, user_prompt)
        parsed = self._parse_json_response(raw)
        parsed["persona"] = persona
        parsed["version"] = version
        parsed["version_label"] = version_profile["label"]
        parsed["cta"] = parsed.get("cta") or base_profile["cta"]
        return parsed

    def _generate_mock(self, topic: str) -> dict[str, Any]:
        title = "How AI Is Transforming Workflow Automation for Small Creative Agencies"
        outline = [
            {"section": "Why manual work compounds quickly", "description": "Small teams lose time when repetitive coordination tasks stay manual."},
            {"section": "What automation now handles well", "description": "Modern AI tools can draft content, route tasks, and summarize client communication."},
            {"section": "Where agencies feel the impact first", "description": "The earliest gains usually show up in turnaround time, consistency, and team focus."},
            {"section": "A practical rollout model", "description": "Start with one repeated workflow, then expand once the process is measurable."},
            {"section": "What to watch as you scale", "description": "Leaders still need review loops, metrics, and role clarity to avoid low-quality automation."},
        ]
        blog = (
            "Small creative agencies usually do not break because they lack ideas. They break when too much routine work accumulates across too few people. "
            "Approvals, status checks, client follow-ups, task routing, and repurposing content across channels all create hidden operating drag. "
            "That drag slows delivery, makes output less consistent, and reduces the time available for high-value client work.\n\n"
            "That is why workflow automation matters now. The point is not to replace judgment. The point is to reduce repetitive coordination so teams can spend more attention on strategy, creative quality, and client communication. "
            "AI tools can now help draft first-pass copy, summarize meetings, classify inbound requests, generate channel variants from one source asset, and trigger downstream tasks once specific inputs are available.\n\n"
            "For smaller agencies, the first wins are usually operational. Turnaround time improves. Fewer tasks get stuck between handoffs. Managers spend less time chasing updates. Output becomes more repeatable because more of the workflow is structured. Over time, those improvements matter because they expand delivery capacity without requiring the team to add headcount at the same pace.\n\n"
            "A practical rollout should start narrow. One useful example is automating the path from a weekly blog draft to persona-specific newsletter versions, campaign logging, and follow-up analysis. The value is not just speed. It is that the workflow becomes measurable. A team can compare subject line performance, click-through rates, and conversion patterns by audience instead of treating content production as one untracked block of work.\n\n"
            "The common mistake is assuming automation creates value on its own. It does not. Teams still need review rules, content standards, and clear success metrics. But with those in place, automation creates leverage. For small creative agencies, that leverage shows up as tighter operations, better content throughput, and more room for growth without adding avoidable process overhead."
        )
        newsletters = [
            {
                "persona": "Agency Founder / Owner",
                "version": "A",
                "version_label": "ROI framing",
                "subject": "Where AI automation protects margin inside a small agency",
                "preview_text": "Manual workflow overhead often shows up as hidden cost before it shows up as obvious inefficiency.",
                "body": "Many small agencies do not have a demand problem. They have a margin leak caused by manual coordination work. When approvals, handoffs, and follow-ups stay manual, delivery slows and team capacity gets consumed by low-leverage work. AI automation helps by reducing that drag across repeated workflows such as content repurposing, task routing, and recurring updates. The payoff is not abstract. It shows up in better operating leverage, more consistent delivery, and more room to take on revenue-generating work without expanding headcount at the same pace.",
                "cta": "Book a demo",
            },
            {
                "persona": "Agency Founder / Owner",
                "version": "B",
                "version_label": "time-saving framing",
                "subject": "How founders can get hours back from repeat agency workflows",
                "preview_text": "If routine coordination keeps stealing time, growth gets capped before demand does.",
                "body": "If repeat workflows keep eating hours every week, founders stay trapped in coordination instead of growth. AI automation can remove part of that burden by handling first-pass drafting, summarizing meetings, and moving tasks forward once specific inputs are ready. The gain is not just speed. It is founder attention. Teams respond faster, spend less time chasing updates, and create more room for strategic work. A practical place to start is one measurable workflow, such as turning a weekly blog into segmented newsletters and tracking performance by audience.",
                "cta": "Book a demo",
            },
            {
                "persona": "Operations Manager",
                "version": "A",
                "version_label": "process reliability framing",
                "subject": "Why cleaner workflow handoffs matter more than teams think",
                "preview_text": "Manual steps usually fail first at the handoff, not at the strategy layer.",
                "body": "The real cost of manual workflows is not just time. It is inconsistency across repeated handoffs. When task ownership, approvals, and recurring updates stay loose, operational teams spend too much time fixing preventable issues. Automation helps tighten that system. AI can standardize repeated outputs, route tasks based on inputs, and support more reliable review loops. The result is better process control, more consistent execution, and less firefighting across the week.",
                "cta": "See the workflow in action",
            },
            {
                "persona": "Operations Manager",
                "version": "B",
                "version_label": "speed and efficiency framing",
                "subject": "How operations teams can reduce follow-up drag with automation",
                "preview_text": "When teams spend too much time chasing status, execution speed drops fast.",
                "body": "When operations teams spend too much time following up, throughput gets capped by coordination overhead. AI automation can help remove that friction by summarizing updates, triggering next-step tasks, and reducing manual follow-up across repeated workflows. The result is a faster operating rhythm without giving up visibility. Start with one measurable workflow, define review points clearly, and compare output speed and error rates over time.",
                "cta": "See the workflow in action",
            },
            {
                "persona": "Marketing / Growth Lead",
                "version": "A",
                "version_label": "content velocity framing",
                "subject": "How automation increases content output without stretching the team",
                "preview_text": "Growth teams usually hit bandwidth limits before idea limits.",
                "body": "Growth teams rarely run out of ideas first. They run out of production bandwidth. Automation helps by turning one source asset into multiple channel-specific outputs, reducing manual repetition, and making campaign execution more scalable. That improves content velocity while preserving time for strategy, testing, and higher-value analysis. For smaller teams, that can create meaningful leverage without increasing process overhead.",
                "cta": "Explore growth use cases",
            },
            {
                "persona": "Marketing / Growth Lead",
                "version": "B",
                "version_label": "conversion optimization framing",
                "subject": "Automation matters most when it helps growth teams learn faster",
                "preview_text": "Faster production only matters when it also improves testing and conversion learning.",
                "body": "Automation creates the most value for growth teams when it improves learning speed, not just content speed. AI can help generate testable variants, tighten feedback loops, and reduce the manual work required to move from one asset to multiple campaign experiments. That makes it easier to compare subject lines, audience response, and conversion signals by segment. For lean teams, that means faster optimization with less execution drag.",
                "cta": "Explore growth use cases",
            },
        ]
        return {
            "topic": topic,
            "generated_at": utc_now_iso(),
            "blog": {"title": title, "outline": outline, "content": blog},
            "newsletters": newsletters,
        }
