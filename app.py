from __future__ import annotations

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from campaign_manager import assign_newsletters_to_segments
from content_generator import ContentGenerator, GenerationConfig, PERSONAS
from crm_hubspot import HubSpotCRM, HubSpotConfig, load_contacts_from_csv
from metrics_simulator import (
    append_performance_history,
    simulate_contact_outcomes,
    aggregate_from_contacts,
)
from performance_analyzer import PerformanceAnalyzer
from utils import DATA_DIR, OUTPUT_DIR, get_env, save_json

load_dotenv()

DEFAULT_TOPIC = "How AI is transforming workflow automation for small creative agencies"
CONTACTS_PATH = DATA_DIR / "mock_contacts.csv"
DEFAULT_LIVE_MODE = get_env("HUBSPOT_ACCESS_TOKEN") is not None

st.set_page_config(page_title="NovaMind AI Content Pipeline", layout="wide")
st.title("NovaMind AI Content Pipeline")
st.caption(
    "Generate an automation blog, create persona-based A/B newsletter variants, sync contacts to HubSpot, "
    "log campaign activity, and analyze performance."
)

if "pipeline_results" not in st.session_state:
    st.session_state.pipeline_results = None

with st.sidebar:
    st.header("Configuration")
    use_mock_openai = st.toggle(
        "Use mock content instead of OpenAI",
        value=get_env("OPENAI_API_KEY") is None,
    )
    live_hubspot = st.toggle(
        "Write to live HubSpot",
        value=DEFAULT_LIVE_MODE,
    )
    model_name = st.text_input("OpenAI model", value="gpt-4.1-mini")
    persona_property = st.text_input(
        "Optional HubSpot persona property internal name",
        value=get_env("HUBSPOT_PERSONA_PROPERTY", ""),
        help="Leave blank if you have not created a custom contact property in HubSpot.",
    )
    st.markdown("Add keys in `.env`: `OPENAI_API_KEY=` and `HUBSPOT_ACCESS_TOKEN=`.")
    if live_hubspot and not get_env("HUBSPOT_ACCESS_TOKEN"):
        st.error("Live HubSpot mode requires HUBSPOT_ACCESS_TOKEN in .env.")

st.subheader("Audience Segments")
for persona, profile in PERSONAS.items():
    st.write(f"**{persona}** — focus: {profile['focus']}")
    version_text = ", ".join(
        [f"{version}: {cfg['label']}" for version, cfg in profile["ab_versions"].items()]
    )
    st.caption(f"A/B test variants — {version_text}")

topic = st.text_input("Topic", value=DEFAULT_TOPIC)


def safe_divide(numerator, denominator):
    return numerator / denominator if denominator else 0


if st.button("Run pipeline", type="primary"):
    simulate_hubspot = not live_hubspot
    if live_hubspot and not get_env("HUBSPOT_ACCESS_TOKEN"):
        st.stop()

    with st.spinner("Generating content and campaign artifacts..."):
        generator = ContentGenerator(
            api_key=get_env("OPENAI_API_KEY"),
            config=GenerationConfig(model=model_name),
        )
        content = generator.generate_all(topic=topic, use_mock=use_mock_openai)
        save_json(content, OUTPUT_DIR / "generated_content.json")

        contacts = load_contacts_from_csv(CONTACTS_PATH)
        campaign = assign_newsletters_to_segments(
            contacts=contacts,
            newsletters=content["newsletters"],
            blog_title=content["blog"]["title"],
            simulate_only=simulate_hubspot,
        )

        contacts = simulate_contact_outcomes(contacts)

        hubspot = HubSpotCRM(
            HubSpotConfig(
                access_token=get_env("HUBSPOT_ACCESS_TOKEN"),
                simulate_only=simulate_hubspot,
                persona_property=persona_property or None,
                log_campaign_notes=True,
            )
        )
        contact_result = hubspot.upsert_contacts(contacts)
        log_result = hubspot.log_campaigns(
            campaign_rows=campaign["campaign_rows"],
            send_events=campaign["send_events"],
            email_to_contact_id=contact_result.get("email_to_contact_id", {}),
        )

        metrics_rows = aggregate_from_contacts(contacts)
        perf_path = append_performance_history(metrics_rows)

        analyzer = PerformanceAnalyzer(
            api_key=get_env("OPENAI_API_KEY"),
            model=model_name,
        )
        analysis_rows = analyzer.build_analysis(metrics_rows)
        summary = analyzer.summarize(metrics_rows, use_mock=use_mock_openai)
        next_topic = analyzer.suggest_next_topic(metrics_rows)
        report = analyzer.make_report(metrics_rows, summary, next_topic)

        report_path = OUTPUT_DIR / "performance_summary.md"
        report_path.write_text(report, encoding="utf-8")

        st.session_state.pipeline_results = {
            "content": content,
            "campaign": campaign,
            "contact_result": contact_result,
            "log_result": log_result,
            "metrics_rows": metrics_rows,
            "analysis_rows": analysis_rows,
            "summary": summary,
            "next_topic": next_topic,
            "perf_path": str(perf_path),
            "report_path": str(report_path),
            "live_hubspot": live_hubspot,
        }

    st.success("Pipeline run completed.")


results = st.session_state.pipeline_results

if results is not None:
    content = results["content"]
    campaign = results["campaign"]
    contact_result = results["contact_result"]
    log_result = results["log_result"]
    metrics_rows = results["metrics_rows"]
    analysis_rows = results["analysis_rows"]
    summary = results["summary"]
    next_topic = results["next_topic"]
    perf_path = results["perf_path"]
    report_path = results["report_path"]
    saved_live_hubspot = results["live_hubspot"]

    left, right = st.columns([1.15, 1])

    with left:
        st.subheader("Blog Outline")
        st.json(content["blog"]["outline"])

        st.subheader("Blog Draft")
        st.write(content["blog"]["content"])

    with right:
        st.subheader("Newsletter Variants")
        for newsletter in content["newsletters"]:
            label = (
                f"{newsletter['persona']} | version {newsletter['version']} "
                f"({newsletter['version_label']})"
            )
            with st.expander(label, expanded=False):
                st.write(f"**Subject:** {newsletter['subject']}")
                st.write(f"**Preview text:** {newsletter['preview_text']}")
                st.write(newsletter["body"])
                st.write(f"**CTA:** {newsletter['cta']}")

    st.subheader("CRM Distribution Summary")
    st.write(f"Contacts created or updated: {contact_result['created_or_updated']}")
    st.write(f"Campaign rows logged: {log_result['logged_rows']}")
    st.write(f"HubSpot mode used in last run: {'live' if saved_live_hubspot else 'simulated'}")
    if log_result.get("note_results"):
        st.write(f"Campaign notes created or simulated: {len(log_result['note_results'])}")
    st.dataframe(pd.DataFrame(campaign["send_events"]), use_container_width=True)

    st.subheader("HubSpot Contact Upsert Results")
    st.dataframe(pd.DataFrame(contact_result["results"]), use_container_width=True)

    st.subheader("Raw Performance Metrics")
    metrics_df = pd.DataFrame(metrics_rows)
    st.dataframe(metrics_df, use_container_width=True)

    if not metrics_df.empty:
        st.subheader("Metric Comparison Chart")

        chart_df = (
            metrics_df
            .groupby(["persona_segment", "version"], as_index=False)
            .agg({
                "sent_count": "sum",
                "opens": "sum",
                "clicks": "sum",
                "conversions": "sum",
            })
        )

        chart_df["open_rate"] = chart_df.apply(
            lambda r: safe_divide(r["opens"], r["sent_count"]), axis=1
        )
        chart_df["click_rate"] = chart_df.apply(
            lambda r: safe_divide(r["clicks"], r["sent_count"]), axis=1
        )
        chart_df["conversion_rate"] = chart_df.apply(
            lambda r: safe_divide(r["conversions"], r["sent_count"]), axis=1
        )
        chart_df["segment_version"] = (
            chart_df["persona_segment"] + " | " + chart_df["version"]
        )

        metric_choice = st.selectbox(
            "Choose metric to compare",
            ["open_rate", "click_rate", "conversion_rate"],
            index=0,
            key="metric_choice",
        )
        st.bar_chart(chart_df.set_index("segment_version")[[metric_choice]])

        st.subheader("Funnel View")

        funnel_df = (
            metrics_df
            .groupby(["persona_segment", "version"], as_index=False)
            .agg({
                "sent_count": "sum",
                "opens": "sum",
                "clicks": "sum",
                "conversions": "sum",
            })
        )
        funnel_df["segment_version"] = (
            funnel_df["persona_segment"] + " | " + funnel_df["version"]
        )

        selected = st.selectbox(
            "Choose segment/version",
            sorted(funnel_df["segment_version"].unique()),
            key="funnel_segment_version",
        )
        row = funnel_df[funnel_df["segment_version"] == selected].iloc[0]

        funnel_counts = pd.DataFrame({
            "stage": ["Sent", "Opened", "Clicked", "Converted"],
            "count": [
                row["sent_count"],
                row["opens"],
                row["clicks"],
                row["conversions"],
            ],
        })
        funnel_counts["stage"] = pd.Categorical(
            funnel_counts["stage"],
            categories=["Sent", "Opened", "Clicked", "Converted"],
            ordered=True,
        )
        funnel_counts = funnel_counts.sort_values("stage")

        st.bar_chart(funnel_counts.set_index("stage"))

        st.subheader("Funnel Derived Metrics")

        funnel_analysis = metrics_df.copy()

        if "open_rate" not in funnel_analysis.columns:
            funnel_analysis["open_rate"] = funnel_analysis.apply(
                lambda r: safe_divide(r.get("opens", 0), r.get("sent_count", 0)),
                axis=1,
            )
        if "click_rate" not in funnel_analysis.columns:
            funnel_analysis["click_rate"] = funnel_analysis.apply(
                lambda r: safe_divide(r.get("clicks", 0), r.get("sent_count", 0)),
                axis=1,
            )
        if "conversion_rate" not in funnel_analysis.columns:
            funnel_analysis["conversion_rate"] = funnel_analysis.apply(
                lambda r: safe_divide(r.get("conversions", 0), r.get("sent_count", 0)),
                axis=1,
            )
        if "unsubscribe_rate" not in funnel_analysis.columns:
            funnel_analysis["unsubscribe_rate"] = 0

        funnel_analysis["click_given_open"] = funnel_analysis.apply(
            lambda r: safe_divide(r.get("clicks", 0), r.get("opens", 0)),
            axis=1,
        )
        funnel_analysis["conversion_given_click"] = funnel_analysis.apply(
            lambda r: safe_divide(r.get("conversions", 0), r.get("clicks", 0)),
            axis=1,
        )

        preferred_cols = [
            "campaign_id",
            "newsletter_id",
            "persona_segment",
            "version",
            "sent_count",
            "opens",
            "clicks",
            "conversions",
            "open_rate",
            "click_rate",
            "conversion_rate",
            "click_given_open",
            "conversion_given_click",
            "unsubscribe_rate",
        ]
        display_cols = [col for col in preferred_cols if col in funnel_analysis.columns]
        st.dataframe(funnel_analysis[display_cols], use_container_width=True)

        st.subheader("Analytical Decision Table")
        analysis_df = pd.DataFrame(analysis_rows)

        preferred_analysis_cols = [
            "persona_segment",
            "winner_version",
            "primary_reason",
            "open_uplift_B_vs_A",
            "click_uplift_B_vs_A",
            "conversion_uplift_B_vs_A",
            "A_click_given_open",
            "B_click_given_open",
            "A_conversion_given_click",
            "B_conversion_given_click",
            "next_experiment",
        ]

        if not analysis_df.empty:
            analysis_display_cols = [
                col for col in preferred_analysis_cols if col in analysis_df.columns
            ]
            if analysis_display_cols:
                st.dataframe(analysis_df[analysis_display_cols], use_container_width=True)
            else:
                st.dataframe(analysis_df, use_container_width=True)
        else:
            st.info("No analytical decision table could be generated from the current metrics.")

        st.subheader("AI Performance Summary")
        st.write(summary)
        st.write(f"**Suggested next topic:** {next_topic}")

        st.subheader("Artifacts")
        st.write(f"Generated content saved to: `{OUTPUT_DIR / 'generated_content.json'}`")
        st.write(f"Campaign log saved to: `{OUTPUT_DIR / 'campaign_log.csv'}`")
        st.write(f"Performance history saved to: `{perf_path}`")
        st.write(f"Performance summary saved to: `{report_path}`")
    else:
        st.warning("The pipeline ran, but no metrics were returned.")
