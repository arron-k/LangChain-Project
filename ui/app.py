import os
import sqlite3
import sys
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.ab_compare import PRESETS, judge_pair, run_one  # noqa: E402
from src.cache import SearchCache  # noqa: E402
from src.exporters import markdown_to_docx_bytes, markdown_to_pdf_bytes  # noqa: E402
from src.feedback import FeedbackStore  # noqa: E402
from src.graph import _fake_llm, build_graph  # noqa: E402
from src.i18n import t  # noqa: E402
from src.judge import JudgeStore, judge_report  # noqa: E402
from src.multi_agent import build_multi_agent_graph  # noqa: E402
from src.llm import available_providers, langsmith_status, secrets_status  # noqa: E402
from src.persistence import delete_thread, thread_summaries  # noqa: E402
from src.state import empty_state  # noqa: E402
from src.thread_meta import ThreadMeta  # noqa: E402
from src.usage import UsageStore  # noqa: E402

DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "checkpoints.sqlite")))
CACHE_PATH = Path(os.getenv("CACHE_DB", str(ROOT / "search_cache.sqlite")))
USAGE_PATH = Path(os.getenv("USAGE_DB", str(ROOT / "usage.sqlite")))
META_PATH = Path(os.getenv("META_DB", str(ROOT / "thread_meta.sqlite")))
FEEDBACK_PATH = Path(os.getenv("FEEDBACK_DB", str(ROOT / "feedback.sqlite")))
JUDGE_PATH = Path(os.getenv("JUDGE_DB", str(ROOT / "judge.sqlite")))


@st.cache_resource
def get_saver() -> SqliteSaver:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    return SqliteSaver(conn)


@st.cache_resource
def get_search_cache() -> SearchCache:
    return SearchCache(str(CACHE_PATH), ttl_seconds=24 * 3600)


@st.cache_resource
def get_usage_store() -> UsageStore:
    return UsageStore(str(USAGE_PATH))


@st.cache_resource
def get_thread_meta() -> ThreadMeta:
    return ThreadMeta(str(META_PATH))


@st.cache_resource
def get_feedback_store() -> FeedbackStore:
    return FeedbackStore(str(FEEDBACK_PATH))


@st.cache_resource
def get_judge_store() -> JudgeStore:
    return JudgeStore(str(JUDGE_PATH))


saver = get_saver()
search_cache = get_search_cache()
usage_store = get_usage_store()
meta = get_thread_meta()
feedback_store = get_feedback_store()
judge_store = get_judge_store()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = uuid.uuid4().hex[:8]
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = "ko"


def L(key: str) -> str:
    return t(key, st.session_state.ui_lang)


st.set_page_config(page_title="Research Agent", layout="wide")
st.title(L("title"))
st.caption(L("caption"))

with st.sidebar:
    st.header(L("settings"))

    st.session_state.ui_lang = st.radio(
        L("ui_lang"),
        options=["ko", "en"],
        format_func=lambda x: {"ko": "🇰🇷 한국어", "en": "🇬🇧 English"}[x],
        horizontal=True,
        index=["ko", "en"].index(st.session_state.ui_lang),
    )

    has_google = bool(os.getenv("GOOGLE_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_tavily = bool(os.getenv("TAVILY_API_KEY"))
    has_any_llm = has_google or has_anthropic

    providers = available_providers()
    if providers:
        st.write(f"LLM: {' → '.join(providers)} (with fallback)")
    else:
        st.write("LLM: ❌ (fake LLM only)")
    st.write(f"TAVILY: {'✅' if has_tavily else '❌'}")

    with st.expander("🔐 Secrets (masked)"):
        for k, info in secrets_status().items():
            mark = "✅" if info["set"] else "❌"
            value = info["masked"] or "(not set)"
            st.text(f"{mark} {k}: {value}")

    ls = langsmith_status()
    if ls["enabled"]:
        st.markdown(f"📈 LangSmith: ✅ [{ls['project']}]({ls['url']})")
    elif ls["has_key"]:
        st.caption("📈 LangSmith key 있음 — `LANGSMITH_TRACING=true` 추가 필요")
    else:
        st.caption("📈 LangSmith: 비활성")

    use_fake = st.toggle(L("use_fake_llm"), value=not has_any_llm)
    interrupt = st.toggle(L("interrupt_before_write"), value=False)
    compact_mode = st.toggle(L("compact_mode"), value=False)

    st.markdown("---")
    st.subheader(L("report_options"))
    language = st.radio(
        L("language"),
        options=["en", "ko"],
        format_func=lambda x: {"en": "🇬🇧 English", "ko": "🇰🇷 한국어"}[x],
        horizontal=True,
        index=1,
    )
    report_style = st.selectbox(L("style"), options=["concise", "detailed", "academic", "blog"], index=0)
    report_length = st.selectbox(L("length"), options=["short", "medium", "long"], index=1)

    st.markdown("---")
    st.subheader(L("graph_options"))
    num_questions = st.slider(L("sub_questions"), 1, 6, 3)
    max_iterations = st.slider(L("max_iterations"), 1, 5, 3)
    rerank = st.toggle(L("rerank"), value=False)
    min_hit_score = st.slider(L("min_hit_score"), 0.0, 1.0, 0.0, step=0.05)
    use_critic = st.toggle(L("use_critic"), value=False, help=L("use_critic_help"))
    extract_top = st.toggle(L("extract_top"), value=False, help=L("extract_top_help"))
    use_lessons = st.toggle(L("use_lessons"), value=False, help=L("use_lessons_help"))
    stream_tokens = st.toggle(L("stream_tokens"), value=False, help=L("stream_tokens_help"))
    use_search_cache = st.toggle(L("use_search_cache"), value=True, help=L("use_search_cache_help"))
    auto_judge = st.toggle(L("auto_judge"), value=False, help=L("auto_judge_help"))
    self_rag = st.toggle(L("self_rag"), value=False, help=L("self_rag_help"))
    multi_agent = st.toggle(L("multi_agent"), value=False, help=L("multi_agent_help"))
    domain_dedup = st.toggle(L("domain_dedup"), value=False, help=L("domain_dedup_help"))
    max_per_domain = st.slider(L("max_per_domain"), 1, 5, 2) if domain_dedup else 2
    freshness_on = st.toggle(L("freshness"), value=False, help=L("freshness_help"))
    freshness_days = st.slider(L("freshness_days"), 30, 1825, 365, step=30) if freshness_on else 0
    per_agent_models = st.toggle(L("per_agent_models"), value=False, help=L("per_agent_models_help"))
    llm_supervisor = st.toggle(L("llm_supervisor"), value=False, help=L("llm_supervisor_help"))
    self_correct_writer = st.toggle(L("self_correct_writer"), value=False, help=L("self_correct_writer_help"))
    cross_reference_check = st.toggle(L("cross_reference"), value=False, help=L("cross_reference_help"))
    vision_enabled = st.toggle(L("vision"), value=False, help=L("vision_help"))
    reflexion_enabled = st.toggle(L("reflexion"), value=False, help=L("reflexion_help"))

    st.markdown("---")
    st.subheader(L("search_filters"))
    include_domains_raw = st.text_input(L("include_domains"), placeholder="github.com, arxiv.org")
    exclude_domains_raw = st.text_input(L("exclude_domains"), placeholder="reddit.com")
    time_range = st.selectbox(
        L("time_range"),
        options=["", "day", "week", "month", "year"],
        index=0,
        format_func=lambda x: {"": "Any/전체", "day": "Past day", "week": "Past week", "month": "Past month", "year": "Past year"}[x],
    )
    include_domains = [d.strip() for d in include_domains_raw.split(",") if d.strip()]
    exclude_domains = [d.strip() for d in exclude_domains_raw.split(",") if d.strip()]

    st.markdown("---")
    st.subheader(L("thread"))

    summaries_list = thread_summaries(
        build_graph(llm=_fake_llm(), checkpointer=saver),
        saver,
    )
    all_meta = meta.all()

    search_q = st.text_input(L("search_threads"), placeholder="topic / tag / id")

    def _matches(s, meta_row, q):
        if not q:
            return True
        q = q.lower()
        haystack = " ".join([
            (s.get("topic") or ""),
            (meta_row.get("display_name") or ""),
            ",".join(meta_row.get("tags") or []),
            s["thread_id"],
        ]).lower()
        return q in haystack

    filtered = [s for s in summaries_list if _matches(s, all_meta.get(s["thread_id"], {}), search_q)]
    favs = [s for s in filtered if all_meta.get(s["thread_id"], {}).get("favorite")]
    others = [s for s in filtered if not all_meta.get(s["thread_id"], {}).get("favorite")]
    ordered = favs + others

    if ordered:
        def _label(s):
            md = all_meta.get(s["thread_id"], {})
            star = "⭐" if md.get("favorite") else "  "
            mark = "✅" if s["sufficient"] else ("⏸" if s["next"] else "⚠️")
            name = md.get("display_name") or (s.get("topic") or "(empty)")
            return f"{star} {mark} {name[:30]} — {s['thread_id']}"

        options = ["(current)"] + [_label(s) for s in ordered]
        id_by_label = {_label(s): s["thread_id"] for s in ordered}
        picked = st.selectbox(
            f"Recent ({len(ordered)})",
            options=options,
            index=0,
            key="thread_picker",
        )
        if picked != "(current)":
            new_id = id_by_label[picked]
            if new_id != st.session_state.thread_id:
                st.session_state.thread_id = new_id
                st.rerun()
    elif search_q:
        st.caption(L("no_match"))

    st.text_input("thread_id", key="thread_id")
    if st.button(L("new_thread")):
        st.session_state.thread_id = uuid.uuid4().hex[:8]
        st.rerun()

    with st.expander(L("manage_threads")):
        cur_meta = meta.get(st.session_state.thread_id)
        new_name = st.text_input(L("rename"), value=cur_meta["display_name"], key="meta_name")
        new_tags = st.text_input(L("tags"), value=", ".join(cur_meta["tags"]), key="meta_tags")
        is_fav = st.checkbox(L("favorite"), value=cur_meta["favorite"], key="meta_fav")
        if st.button(L("save")):
            tags_list = [tg.strip() for tg in new_tags.split(",") if tg.strip()]
            meta.upsert(st.session_state.thread_id, display_name=new_name, tags=tags_list, favorite=is_fav)
            st.success("Saved")
            st.rerun()

    st.markdown("---")
    st.subheader(L("ops"))
    with st.expander("📊 Usage today"):
        usage = usage_store.stats(since_seconds=86400)
        st.metric("LLM calls (24h)", usage["total_calls"])
        st.metric("Successful", usage["successful_calls"])
        if usage["by_combo"]:
            st.dataframe(usage["by_combo"], use_container_width=True, hide_index=True)
        else:
            st.caption("No calls yet today.")

    with st.expander(f"🎯 {L('judge_avg_7d')}"):
        js = judge_store.stats(since_seconds=7 * 86400)
        if js["count"] == 0:
            st.caption("No evaluations yet.")
        else:
            st.metric(L("judge_overall"), f"{js['overall']:.2f}", help=f"n={js['count']}")
            cols = st.columns(2)
            cols[0].metric(L("judge_accuracy"), f"{js['accuracy']:.2f}")
            cols[1].metric(L("judge_citations"), f"{js['citations']:.2f}")
            cols2 = st.columns(2)
            cols2[0].metric(L("judge_structure"), f"{js['structure']:.2f}")
            cols2[1].metric(L("judge_readability"), f"{js['readability']:.2f}")
            st.metric(L("judge_length"), f"{js['length_fit']:.2f}")

    with st.expander("💬 Feedback stats"):
        fs = feedback_store.stats()
        st.metric("Total", fs["total"])
        c1, c2 = st.columns(2)
        c1.metric("👍", fs["positive"])
        c2.metric("👎", fs["negative"])

    with st.expander("🗄 Search cache"):
        cstats = search_cache.stats()
        st.metric("Cached entries", cstats["count"])
        st.metric("Live (within TTL)", cstats["live"])
        if st.button("🧹 Clear cache"):
            search_cache.clear()
            st.success("Cache cleared")
            st.rerun()

    with st.expander("🧹 " + L("manage_threads") + " (delete)"):
        if st.button(L("delete_current")):
            ok = delete_thread(saver, st.session_state.thread_id)
            meta.delete(st.session_state.thread_id)
            if ok:
                st.session_state.thread_id = uuid.uuid4().hex[:8]
                st.success("Deleted")
                st.rerun()
            else:
                st.warning("No state to delete.")
        if st.button(L("delete_all"), type="secondary"):
            n = 0
            for s in summaries_list:
                if delete_thread(saver, s["thread_id"]):
                    meta.delete(s["thread_id"])
                    n += 1
            st.success(f"Deleted {n} threads.")
            st.rerun()

    st.markdown("---")
    with st.expander("📐 Graph"):
        if multi_agent:
            st.markdown(
                """```mermaid
graph TD
    START --> supervisor
    supervisor --> researcher
    supervisor --> critic
    supervisor --> writer
    researcher --> supervisor
    critic --> supervisor
    writer --> END
```"""
            )
        else:
            st.markdown(
                """```mermaid
graph TD
    START --> plan
    plan --> search
    search --> summarize
    summarize --> reflect
    reflect -.->|insufficient & iter<cap| search
    reflect -.->|sufficient or iter>=cap| write
    write --> END
```"""
            )


def make_graph():
    if multi_agent:
        return build_multi_agent_graph(
            llm=_fake_llm() if use_fake else None,
            checkpointer=saver,
            interrupt_before=["writer"] if interrupt else None,
            search_cache=search_cache if use_search_cache else None,
            per_agent_models=per_agent_models and not use_fake,
        )
    return build_graph(
        llm=_fake_llm() if use_fake else None,
        checkpointer=saver,
        interrupt_before=["write"] if interrupt else None,
        use_critic=use_critic,
        search_cache=search_cache if use_search_cache else None,
    )


config = {"configurable": {"thread_id": st.session_state.thread_id}}


def make_state(topic: str, follow_up: str = "") -> dict:
    return empty_state(
        topic,
        language=language,
        num_questions=num_questions,
        max_iterations=max_iterations,
        report_style=report_style,
        report_length=report_length,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        time_range=time_range,
        rerank=rerank,
        min_hit_score=min_hit_score,
        use_critic=use_critic,
        extract_top=extract_top,
        use_lessons=use_lessons,
        self_rag=self_rag,
        multi_agent=multi_agent,
        domain_dedup=domain_dedup,
        max_per_domain=max_per_domain,
        freshness_max_age_days=freshness_days,
        per_agent_models=per_agent_models,
        llm_supervisor=llm_supervisor,
        self_correct_writer=self_correct_writer,
        cross_reference_check=cross_reference_check,
        vision_enabled=vision_enabled,
        reflexion_enabled=reflexion_enabled,
        follow_up=follow_up,
    )


def _safe_filename(s: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_ " else "_" for c in s).strip()
    return (keep[:60] or "report").replace(" ", "-")


def render_state(out: dict):
    if compact_mode:
        col_l = col_r = st.container()
    else:
        col_l, col_r = st.columns([2, 1])

    with col_l:
        report = out.get("final_report") or ""
        st.subheader(L("final_report"))
        if report:
            topic = out.get("topic", "report")
            fname = _safe_filename(topic)
            cols = st.columns(3)
            cols[0].download_button(
                L("download_md"),
                data=report.encode("utf-8"),
                file_name=f"{fname}.md",
                mime="text/markdown",
                use_container_width=True,
            )
            try:
                cols[1].download_button(
                    L("download_pdf"),
                    data=markdown_to_pdf_bytes(report),
                    file_name=f"{fname}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                cols[1].caption(f"PDF err: {e}")
            try:
                cols[2].download_button(
                    L("download_docx"),
                    data=markdown_to_docx_bytes(report),
                    file_name=f"{fname}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as e:
                cols[2].caption(f"DOCX err: {e}")
            st.markdown(report)
        else:
            st.markdown("_(not yet written)_")

    with col_r:
        st.subheader(L("run_summary"))
        st.metric(L("iterations"), out.get("iteration", 0))
        st.metric(L("sufficient"), "Yes" if out.get("sufficient") else "No")
        st.metric(L("search_batches"), len(out.get("search_results", [])))
        st.metric(L("summaries"), len(out.get("summaries", [])))

    st.subheader(L("sources"))
    seen = set()
    for entry in out.get("search_results", []):
        for h in entry.get("hits", []):
            url = h.get("url", "")
            if url and url not in seen:
                seen.add(url)
                badge = _freshness_badge(h.get("published_date") or "")
                st.markdown(f"- {badge} [{url}]({url})")

    if out.get("final_report"):
        st.subheader(L("judge_panel"))
        latest_score = judge_store.latest_for(st.session_state.thread_id)

        if latest_score:
            cols = st.columns(6)
            cols[0].metric(L("judge_overall"), f"{latest_score['overall']:.1f}")
            cols[1].metric(L("judge_accuracy"), f"{latest_score['accuracy']:.1f}")
            cols[2].metric(L("judge_citations"), f"{latest_score['citations']:.1f}")
            cols[3].metric(L("judge_structure"), f"{latest_score['structure']:.1f}")
            cols[4].metric(L("judge_readability"), f"{latest_score['readability']:.1f}")
            cols[5].metric(L("judge_length"), f"{latest_score['length_fit']:.1f}")
            if latest_score.get("comment"):
                st.caption(f"💭 {latest_score['comment']}")

        if st.button(L("evaluate_now"), key=f"judge-{st.session_state.thread_id}"):
            with st.spinner(L("judge_running")):
                score = judge_report(
                    out.get("topic", ""),
                    out["final_report"],
                    language=out.get("language", "en"),
                )
            if score is None:
                st.warning(L("judge_failed"))
            else:
                judge_store.submit(
                    thread_id=st.session_state.thread_id,
                    score=score,
                    topic=out.get("topic", ""),
                )
                st.rerun()

        st.subheader(L("feedback"))
        existing = feedback_store.latest_for(st.session_state.thread_id)
        if existing:
            mark = "👍" if existing["rating"] > 0 else "👎"
            st.caption(f"{mark}  {existing.get('comment') or '(no comment)'}")
        with st.form(f"feedback-{st.session_state.thread_id}", clear_on_submit=True):
            st.write(L("feedback_q"))
            cols = st.columns([1, 1, 6])
            up = cols[0].form_submit_button("👍")
            down = cols[1].form_submit_button("👎")
            comment = st.text_area(L("feedback_comment"), height=80, label_visibility="collapsed")
            if up or down:
                rating = 1 if up else -1
                feedback_store.submit(
                    thread_id=st.session_state.thread_id,
                    rating=rating,
                    comment=comment,
                    topic=out.get("topic", ""),
                )
                st.success(L("feedback_thanks"))

    image_findings = out.get("image_findings") or []
    if image_findings:
        st.subheader(L("image_findings"))
        for f in image_findings[:5]:
            cols = st.columns([1, 3])
            with cols[0]:
                try:
                    st.image(f.get("url", ""), width="stretch")
                except Exception:
                    st.caption(f.get("url", ""))
            with cols[1]:
                st.caption(f.get("question", ""))
                st.markdown(f.get("description", ""))

    rmemo = out.get("reflexion_memo") or {}
    if rmemo and (rmemo.get("strategy_for_next_time") or rmemo.get("what_worked")):
        st.subheader(L("reflexion_memo"))
        rcols = st.columns(3)
        with rcols[0]:
            st.markdown(f"**✅ {L('what_worked')}**")
            for s in rmemo.get("what_worked", [])[:3]:
                st.markdown(f"- {s}")
        with rcols[1]:
            st.markdown(f"**🔧 {L('what_to_improve')}**")
            for s in rmemo.get("what_to_improve", [])[:3]:
                st.markdown(f"- {s}")
        with rcols[2]:
            st.markdown(f"**🎯 {L('strategy_next')}**")
            st.caption(rmemo.get("strategy_for_next_time", ""))

    cv = out.get("claim_verification") or {}
    if cv and cv.get("claims"):
        st.subheader(L("verification_panel"))
        if cv.get("summary"):
            st.caption(cv["summary"])
        rows = []
        confidences = []
        for c in cv["claims"]:
            risk = c.get("risk", "ok")
            badge = {"ok": "🟢", "single-source": "🟡", "unsupported": "🔴", "conflicting": "⚠️"}.get(risk, "📄")
            conf = float(c.get("confidence", 5.0))
            confidences.append(conf)
            rows.append({
                L("claim"): c.get("text", ""),
                L("supported_by"): ", ".join(f"[{n}]" for n in (c.get("supported_by") or [])) or "—",
                L("risk"): f"{badge} {risk}",
                L("confidence"): f"{conf:.1f}",
            })
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        st.metric(L("avg_confidence"), f"{avg_conf:.1f} / 10")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander(L("reflection_trace")):
        st.code(out.get("reflection", ""), language="json")
    with st.expander(L("raw_state")):
        _safe_json_render(out, expanded=True)


def _freshness_badge(published_date: str) -> str:
    if not published_date:
        return "📄"
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - dt).days
        year = dt.strftime("%Y")
    except Exception:
        return "📄"
    if age_days <= 90:
        return f"🟢 {year}"
    if age_days <= 365:
        return f"🟡 {year}"
    if age_days <= 365 * 3:
        return f"🟠 {year}"
    return f"⚠️ {year}"


def _safe_json_render(value, expanded: bool = False) -> None:
    if isinstance(value, dict) and value:
        try:
            st.json(value, expanded=expanded)
            return
        except Exception:
            pass
    if isinstance(value, dict) and not value:
        st.caption("_(no state changes)_")
        return
    st.code(repr(value), language="python")


def _explain_error(e: Exception) -> str:
    msg = str(e)
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        return "⏳ LLM 무료 한도 초과. 잠시 후 또는 다른 프로바이더 키 추가."
    if "TAVILY" in msg.upper():
        return "🔍 Tavily 검색 오류. TAVILY_API_KEY 확인."
    if "API_KEY" in msg or "authentication" in msg.lower():
        return "🔑 API 키 문제. .env 확인 후 재시작."
    if "timeout" in msg.lower():
        return f"⏱ 호출 타임아웃 ({os.getenv('LLM_TIMEOUT','60')}s)."
    return f"❌ {msg[:200]}"


def stream_run(initial):
    graph = make_graph()
    timeline = st.container()
    token_placeholder = None
    accumulated = ""
    if stream_tokens:
        st.markdown("### ⌨️ Live tokens (write)")
        token_placeholder = st.empty()

    with st.status("Running graph...", expanded=True) as status:
        try:
            if stream_tokens:
                for mode_name, payload in graph.stream(
                    initial, config=config, stream_mode=["updates", "messages"]
                ):
                    if mode_name == "updates":
                        for node, update in payload.items():
                            with timeline:
                                st.markdown(f"### 🟢 `{node}`")
                                _safe_json_render(update)
                    elif mode_name == "messages":
                        msg, m = payload
                        if m.get("langgraph_node") == "write":
                            from src.llm import to_text
                            chunk_text = to_text(getattr(msg, "content", ""))
                            if chunk_text:
                                accumulated += chunk_text
                                if token_placeholder is not None:
                                    token_placeholder.markdown(accumulated)
            else:
                for chunk in graph.stream(initial, config=config, stream_mode="updates"):
                    for node, update in chunk.items():
                        with timeline:
                            st.markdown(f"### 🟢 `{node}`")
                            _safe_json_render(update)
            status.update(label="✅ Step complete", state="complete")
        except Exception as e:
            status.update(label="❌ Failed", state="error")
            st.error(_explain_error(e))
            with st.expander("🐛 Full trace"):
                st.exception(e)
    try:
        final = graph.get_state(config).values or {}
    except Exception:
        return {}

    if auto_judge and final.get("final_report"):
        try:
            with st.spinner(L("judge_running")):
                score = judge_report(
                    final.get("topic", ""),
                    final["final_report"],
                    language=final.get("language", "en"),
                )
            if score is not None:
                judge_store.submit(
                    thread_id=st.session_state.thread_id,
                    score=score,
                    topic=final.get("topic", ""),
                )
        except Exception:
            pass
    return final


tab_run, tab_resume, tab_ab = st.tabs([L("tab_run"), L("tab_resume"), L("tab_ab")])

with tab_run:
    topic = st.text_input(L("research_topic"), value="LangGraph reflection patterns")
    col1, col2 = st.columns(2)
    if col1.button(L("run"), type="primary", use_container_width=True):
        if topic.strip():
            out = stream_run(make_state(topic))
            render_state(out)
    if col2.button(L("resume"), use_container_width=True):
        out = stream_run(None)
        render_state(out)

with tab_resume:
    st.write(f"{L('loading_state')} `{st.session_state.thread_id}`")
    try:
        snap = make_graph().get_state(config)
        if snap.values:
            st.success(f"{L('found_state')} {list(snap.next) or '(end)'}")
            render_state(snap.values)

            st.markdown("---")
            st.subheader(L("continuation"))
            follow_up_text = st.text_input(L("follow_up_q"), key="follow_up_input")
            if st.button(L("continue_research"), use_container_width=True):
                if follow_up_text.strip():
                    cur = snap.values
                    new_questions = (cur.get("sub_questions") or []) + [follow_up_text]
                    update = {
                        "sub_questions": new_questions,
                        "sufficient": False,
                        "follow_up": follow_up_text,
                        "language": language,
                        "report_style": report_style,
                        "report_length": report_length,
                        "max_iterations": max_iterations,
                    }
                    graph = make_graph()
                    graph.update_state(config, update, as_node="plan")
                    out = stream_run(None)
                    render_state(out)
        else:
            st.info(L("no_state"))
    except Exception as e:
        st.warning(f"Could not load: {e}")


with tab_ab:
    st.caption(
        "두 옵션 조합을 같은 토픽으로 동시에 실행하고 LLM-judge가 승자를 선언합니다."
    )
    ab_topic = st.text_input(L("ab_topic"), value="LangGraph reflection patterns", key="ab_topic_input")

    preset_keys = list(PRESETS.keys())
    col_a, col_b = st.columns(2)
    with col_a:
        preset_a = st.selectbox(
            L("ab_preset_a"),
            options=preset_keys,
            index=0,
            format_func=lambda k: PRESETS[k]["label"],
            key="preset_a",
        )
        st.caption(PRESETS[preset_a]["description"])
    with col_b:
        preset_b = st.selectbox(
            L("ab_preset_b"),
            options=preset_keys,
            index=min(4, len(preset_keys) - 1),
            format_func=lambda k: PRESETS[k]["label"],
            key="preset_b",
        )
        st.caption(PRESETS[preset_b]["description"])

    if st.button(L("ab_run"), type="primary", use_container_width=True):
        if ab_topic.strip() and not use_fake:
            shared = dict(
                checkpointer=saver,
                search_cache=search_cache if use_search_cache else None,
            )

            with st.status(L("ab_running_a"), expanded=False):
                try:
                    state_a = run_one(
                        ab_topic,
                        {**PRESETS[preset_a]["options"], "language": language},
                        **shared,
                    )
                except Exception as e:
                    st.error(_explain_error(e))
                    state_a = {}

            with st.status(L("ab_running_b"), expanded=False):
                try:
                    state_b = run_one(
                        ab_topic,
                        {**PRESETS[preset_b]["options"], "language": language},
                        **shared,
                    )
                except Exception as e:
                    st.error(_explain_error(e))
                    state_b = {}

            with st.spinner(L("ab_judging")):
                verdict = judge_pair(ab_topic, state_a, state_b, language=language)

            winner = verdict["winner"]
            winner_label = (
                "🅰️ A" if winner == "A" else "🅱️ B" if winner == "B" else f"🤝 {L('ab_tie')}"
            )
            top1, top2, top3 = st.columns(3)
            top1.metric(L("ab_winner"), winner_label)
            top2.metric(
                f"A {L('judge_overall')}",
                f"{verdict['score_a']['overall']:.1f}" if verdict["score_a"] else "—",
            )
            top3.metric(
                f"B {L('judge_overall')}",
                f"{verdict['score_b']['overall']:.1f}" if verdict["score_b"] else "—",
            )
            st.caption(f"{L('ab_diff')}: {verdict['diff']:+.2f}")

            ca, cb = st.columns(2)
            with ca:
                st.markdown(f"#### 🅰️ {PRESETS[preset_a]['label']}")
                if verdict["score_a"]:
                    s = verdict["score_a"]
                    st.write(
                        f"Acc {s['accuracy']:.1f} · Cite {s['citations']:.1f} · "
                        f"Struct {s['structure']:.1f} · Read {s['readability']:.1f} · "
                        f"Length {s['length_fit']:.1f}"
                    )
                    st.caption(s.get("comment", ""))
                with st.expander("📄 Report A"):
                    st.markdown(state_a.get("final_report", "_(empty)_"))
            with cb:
                st.markdown(f"#### 🅱️ {PRESETS[preset_b]['label']}")
                if verdict["score_b"]:
                    s = verdict["score_b"]
                    st.write(
                        f"Acc {s['accuracy']:.1f} · Cite {s['citations']:.1f} · "
                        f"Struct {s['structure']:.1f} · Read {s['readability']:.1f} · "
                        f"Length {s['length_fit']:.1f}"
                    )
                    st.caption(s.get("comment", ""))
                with st.expander("📄 Report B"):
                    st.markdown(state_b.get("final_report", "_(empty)_"))
        elif use_fake:
            st.warning("A/B 비교는 실 LLM 모드에서만 동작합니다 (사이드바 'Use fake LLM' 끄세요).")
