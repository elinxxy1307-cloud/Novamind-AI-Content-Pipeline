from __future__ import annotations

from typing import Any

from utils import utc_now_iso

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


class PerformanceAnalyzer:
    def __init__(self, api_key: str | None = None, model: str = "gpt-4.1-mini") -> None:
        self.client = OpenAI(api_key=api_key) if api_key and OpenAI else None
        self.model = model

    @staticmethod
    def _safe_div(numerator: float, denominator: float) -> float:
        if denominator == 0:
            return 0.0
        return numerator / denominator

    @staticmethod
    def _pct_uplift(base: float, challenger: float) -> float:
        if base == 0:
            return 0.0
        return (challenger - base) / base

    def build_analysis(self, metrics_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Build a segment-level A/B analysis table with:
        - funnel-derived metrics
        - uplift
        - winner selection
        - next-step experiment recommendation
        """
        grouped: dict[str, dict[str, dict[str, Any]]] = {}

        for row in metrics_rows:
            segment = row["persona_segment"]
            version = row["version"]
            grouped.setdefault(segment, {})[version] = row

        analysis_rows: list[dict[str, Any]] = []

        for segment, versions in grouped.items():
            if "A" not in versions or "B" not in versions:
                continue

            a = versions["A"]
            b = versions["B"]

            a_open = float(a["open_rate"])
            a_click = float(a["click_rate"])
            a_conv = float(a["conversion_rate"])
            a_unsub = float(a["unsubscribe_rate"])

            b_open = float(b["open_rate"])
            b_click = float(b["click_rate"])
            b_conv = float(b["conversion_rate"])
            b_unsub = float(b["unsubscribe_rate"])

            a_click_given_open = self._safe_div(a_click, a_open)
            b_click_given_open = self._safe_div(b_click, b_open)

            a_conv_given_click = self._safe_div(a_conv, a_click)
            b_conv_given_click = self._safe_div(b_conv, b_click)

            open_uplift_b_vs_a = self._pct_uplift(a_open, b_open)
            click_uplift_b_vs_a = self._pct_uplift(a_click, b_click)
            conv_uplift_b_vs_a = self._pct_uplift(a_conv, b_conv)
            unsub_uplift_b_vs_a = self._pct_uplift(a_unsub, b_unsub)

            # Decision rule:
            # primary metric = conversion_rate
            # secondary metric = click_rate
            # guardrail = unsubscribe_rate
            if b_conv > a_conv and b_click >= a_click and b_unsub <= a_unsub:
                winner = "B"
                primary_reason = "B wins on conversion and does not worsen unsubscribe."
                next_experiment = "Keep B body framing; test subject-line variants to recover opens if needed."
            elif a_conv > b_conv and a_click >= b_click and a_unsub <= b_unsub:
                winner = "A"
                primary_reason = "A wins on conversion and does not worsen unsubscribe."
                next_experiment = "Keep A body framing; test shorter CTA and subject-line variants to improve opens."
            elif a_open > b_open and b_click > a_click:
                winner = "Mixed"
                primary_reason = "A wins top-funnel opens, while B wins deeper engagement."
                next_experiment = "Run a split test: A-style subject line with B-style body copy."
            elif b_open > a_open and a_click > b_click:
                winner = "Mixed"
                primary_reason = "B wins top-funnel opens, while A wins deeper engagement."
                next_experiment = "Run a split test: B-style subject line with A-style body copy."
            else:
                winner = "No clear winner"
                primary_reason = "Results are directionally mixed across the funnel."
                next_experiment = "Reduce test scope and isolate one variable next round (subject line or body framing)."

            analysis_rows.append(
                {
                    "persona_segment": segment,
                    "winner_version": winner,
                    "primary_reason": primary_reason,
                    "next_experiment": next_experiment,
                    "A_open_rate": a_open,
                    "B_open_rate": b_open,
                    "A_click_rate": a_click,
                    "B_click_rate": b_click,
                    "A_conversion_rate": a_conv,
                    "B_conversion_rate": b_conv,
                    "A_unsubscribe_rate": a_unsub,
                    "B_unsubscribe_rate": b_unsub,
                    "A_click_given_open": a_click_given_open,
                    "B_click_given_open": b_click_given_open,
                    "A_conversion_given_click": a_conv_given_click,
                    "B_conversion_given_click": b_conv_given_click,
                    "open_uplift_B_vs_A": open_uplift_b_vs_a,
                    "click_uplift_B_vs_A": click_uplift_b_vs_a,
                    "conversion_uplift_B_vs_A": conv_uplift_b_vs_a,
                    "unsubscribe_uplift_B_vs_A": unsub_uplift_b_vs_a,
                }
            )

        return analysis_rows

    def summarize(self, metrics_rows: list[dict[str, Any]], use_mock: bool = False) -> str:
        analysis_rows = self.build_analysis(metrics_rows)

        if use_mock or self.client is None:
            return self._mock_summary(analysis_rows)

        prompt = (
            "You are a growth analyst. Based on the structured A/B analysis below, "
            "write a concise analytical summary. Do not invent metrics. "
            "For each segment, state the winner or tradeoff and explain the funnel implication. "
            "Then give 2 next-step experimental recommendations.\n\n"
            f"Analysis rows: {analysis_rows}"
        )
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            temperature=0.3,
        )
        return response.output_text.strip()

    def _mock_summary(self, analysis_rows: list[dict[str, Any]]) -> str:
        lines: list[str] = []

        for row in analysis_rows:
            seg = row["persona_segment"]
            winner = row["winner_version"]

            if winner in {"A", "B"}:
                lines.append(
                    f"For {seg}, version {winner} is the preferred variant because it performed better on the primary decision metric (conversion rate) without creating a worse unsubscribe tradeoff."
                )
            else:
                lines.append(
                    f"For {seg}, there is no clean single winner: one version performs better at the top of the funnel while the other is stronger post-open, so the next round should split subject-line and body-copy testing."
                )

            lines.append(
                f"In funnel terms, click-through-after-open was "
                f"{row['A_click_given_open']:.1%} for A vs. {row['B_click_given_open']:.1%} for B, "
                f"and conversion-after-click was {row['A_conversion_given_click']:.1%} for A vs. {row['B_conversion_given_click']:.1%} for B."
            )

        lines.append(
            "Across segments, the important pattern is not just which version gets opened more, but which version converts more efficiently after the open. That distinction should drive the next round of content decisions."
        )

        next_steps = []
        for row in analysis_rows:
            next_steps.append(f"{row['persona_segment']}: {row['next_experiment']}")
        lines.append("Next steps: " + " ".join(next_steps))

        return " ".join(lines)

    def suggest_next_topic(self, metrics_rows: list[dict[str, Any]]) -> str:
        analysis_rows = self.build_analysis(metrics_rows)
        if not analysis_rows:
            return "How small agencies can use AI to improve campaign execution and workflow efficiency"

        # Choose next topic based on the segment with the strongest winning conversion rate
        scored = []
        for row in analysis_rows:
            best_conv = max(row["A_conversion_rate"], row["B_conversion_rate"])
            scored.append((best_conv, row["persona_segment"]))

        scored.sort(reverse=True)
        top_segment = scored[0][1]

        if top_segment == "Marketing / Growth Lead":
            return "How small agencies can build a repeatable content experimentation system with AI"
        if top_segment == "Operations Manager":
            return "How agencies can automate recurring workflows without losing review control"
        return "How agency founders can use AI automation to reduce manual overhead and improve delivery capacity"

    def make_report(
        self,
        metrics_rows: list[dict[str, Any]],
        summary: str,
        next_topic: str,
    ) -> str:
        analysis_rows = self.build_analysis(metrics_rows)

        lines = [
            "# Performance Summary",
            "",
            f"Generated at: {utc_now_iso()}",
            "",
            "## Raw A/B Segment Metrics",
        ]

        for row in metrics_rows:
            lines.append(
                f"- {row['persona_segment']} | version={row['version']} ({row['version_label']}): "
                f"open_rate={row['open_rate']:.1%}, click_rate={row['click_rate']:.1%}, "
                f"unsubscribe_rate={row['unsubscribe_rate']:.1%}, conversion_rate={row['conversion_rate']:.1%}"
            )

        lines += ["", "## Analytical Decision Table"]

        for row in analysis_rows:
            lines.append(
                f"- {row['persona_segment']}: winner={row['winner_version']}; "
                f"open_uplift_B_vs_A={row['open_uplift_B_vs_A']:.1%}, "
                f"click_uplift_B_vs_A={row['click_uplift_B_vs_A']:.1%}, "
                f"conversion_uplift_B_vs_A={row['conversion_uplift_B_vs_A']:.1%}, "
                f"A_click_given_open={row['A_click_given_open']:.1%}, "
                f"B_click_given_open={row['B_click_given_open']:.1%}, "
                f"A_conversion_given_click={row['A_conversion_given_click']:.1%}, "
                f"B_conversion_given_click={row['B_conversion_given_click']:.1%}. "
                f"Reason: {row['primary_reason']} "
                f"Next test: {row['next_experiment']}"
            )

        lines += ["", "## AI Summary", summary, "", "## Suggested Next Topic", next_topic, ""]
        return "\n".join(lines)
