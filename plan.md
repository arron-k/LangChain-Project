# Plan — LangGraph 리서치 에이전트

## 목표

주제(topic)를 입력받아 → 웹 검색 → 부족한 정보 재검색(reflection 루프) → 마크다운 보고서를 작성하는 자율 리서치 에이전트.

## MVP 단계 로드맵

| 단계 | Day | 이름 | 핵심 산출물 | 검증 |
|---|---|---|---|---|
| M1 | Day 1 | Hello LangGraph | 단일 노드 그래프, state pass-through | `pytest` + `python -m src.graph` ✅ |
| M2 | Day 2 | 선형 파이프라인 | plan → search → summarize → write | 주제 입력 → 거친 보고서 생성 ✅ |
| M3 | Day 3 | Reflection 루프 | conditional edge + iteration cap(3) | 루프 동작 단위 테스트 ✅ |
| M4 | Day 4 | 영속성 / 스트리밍 | SqliteSaver, `stream_mode`, interrupt | thread_id 재개, 노드별 스트림 ✅ |
| M5 | Day 5 | UI/마무리 | Streamlit, README, 데모, 그래프 시각화 | 전체 5단계 학습 완료 ✅ |

각 단계는 "동작하는 가장 작은 시스템"이며, 직전 단계의 코드 위에 쌓는다.

---

## M1 (Day 1) — Hello LangGraph  ⬅ 현재

### 목표
LangGraph의 가장 작은 실행 단위(State + Node + Edge + compile)를 직접 구성하고 실행해본다. LLM/외부 API 의존성 없이 그래프 메커니즘 자체에 집중한다.

### 산출물
- `src/state.py` — `ResearchState(TypedDict)` 최소형 (`topic`, `message`)
- `src/nodes/hello.py` — `hello_node(state) -> dict` (결정적 동작, LLM 호출 없음)
- `src/graph.py` — `StateGraph` 조립 + `__main__` 데모
- `tests/test_state.py`, `tests/test_graph.py`

### Definition of Done
- [ ] `uv run pytest -q` 전부 통과
- [ ] `uv run python -m src.graph "LangGraph"` 실행 시 `Hello, LangGraph! topic=LangGraph` 출력
- [ ] `progress.md` 에 M1 회고 섹션 작성

---

## M2 (Day 2) — 선형 파이프라인 ⬅ 현재

### 목표
실제 LLM과 웹 검색을 그래프에 연결한다. 분기/루프 없이 직선으로 흐르는 4-노드 파이프라인.

### 제약
- **`ANTHROPIC_API_KEY` 미보유** — 모든 LLM 호출은 추상화(`get_chat_model()` factory)를 통하고, 테스트는 fake model로 진행. 실제 LLM E2E는 키 추가 시 별도 검증.
- `TAVILY_API_KEY` 보유 — Tavily 단위 테스트는 mock, 통합 smoke test 1회만 실제 호출.

### 노드 설계
1. `plan_node` — 주제를 sub-question 3~5개로 분해 (LLM, JSON 출력)
2. `search_node` — sub-question별 Tavily 검색 (top_k=3)
3. `summarize_node` — 검색 결과를 출처 포함 요약 (LLM)
4. `write_node` — 마크다운 보고서 작성 (LLM)

### State 확장
- `sub_questions: list[str]`
- `search_results: Annotated[list[dict], operator.add]` — 누적 머지
- `summaries: Annotated[list[str], operator.add]`
- `final_report: str`

### 모듈 구조
```
src/
├── llm.py              # get_chat_model() factory (DI 가능)
├── tools/web_search.py # Tavily 래퍼 (search(query) -> list[dict])
└── nodes/
    ├── plan.py
    ├── search.py
    ├── summarize.py
    └── write.py
```

### Definition of Done
- [ ] `uv run pytest -q` 전부 통과 (LLM/Tavily 모두 mock)
- [ ] Tavily 통합 smoke test 1건 통과 (`-m integration` 마커)
- [ ] M1의 `hello` 노드 제거, M2 그래프로 교체
- [ ] `progress.md` M2 회고 작성

---

## M3 (Day 3) — Reflection 루프 ✅

- `reflect_node`: summaries 평가 → `{"sufficient": bool, "gaps": [...]}` JSON
- `search_node`가 `iteration` 카운터 증가
- `summarize_node`는 새 search_results만 처리 (`already = len(summaries)`)
- `add_conditional_edges("reflect", router, {"search": ..., "write": ...})` — 부족하고 iter<3이면 `search`로 회귀, 아니면 `write`
- 테스트: 1회 만족 / 1회 보강 후 만족 / cap에서 강제 종료 3가지 시나리오 모두 검증

## M4 (Day 4) — 영속성 / 스트리밍 ✅

- `build_graph(checkpointer=, interrupt_before=)` 인자 추가 — 컴파일 시점에 주입
- `MemorySaver` (테스트) / `SqliteSaver` (운영) — 같은 `BaseCheckpointSaver` 인터페이스
- `config = {"configurable": {"thread_id": "..."}}` 로 thread 식별
- `graph.stream(state, config, stream_mode="updates")` — 노드별 실시간 청크
- `interrupt_before=["write"]` + `graph.invoke(None, config)` 로 재개 (HITL)
- Streamlit UI에 thread_id 입력, "Resume Existing Thread" 탭, interrupt 토글 추가

## M5 (Day 5) — UI / 마무리 ✅

- Streamlit UI 정비 (영속성·스트리밍·HITL·그래프 다이어그램 사이드바)
- `scripts/show_graph.py` — Mermaid/ASCII 그래프 출력
- README 정비 (스택, 디렉토리 구조, 시나리오, LangSmith 셋업, 트러블슈팅)
- 학습 단계 요약 표 + 확장 트랙 제안

---

## 변경 이력

- 2026-05-07 — 초기 plan 작성, M1 진행 시작
