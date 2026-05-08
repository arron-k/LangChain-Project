# Progress Log

MVP 단계가 끝날 때마다 _무엇을 / 왜 / 어떻게 / 학습 포인트 / 다음 단계_ 를 기록합니다.

---

## 2026-05-07 — M1 ✅ 완료 — Hello LangGraph

### 1. 무엇을 만들었나

| 파일 | 역할 |
|---|---|
| `src/state.py` | `ResearchState(TypedDict)` — 그래프가 주고받는 상태 스키마 (`topic`, `message`) |
| `src/nodes/hello.py` | `hello_node(state) -> dict` — 입력 topic을 읽어 message를 채우는 결정적 노드 |
| `src/graph.py` | `StateGraph` 조립 → `compile()` → `Runnable` 반환. CLI 데모 포함 |
| `tests/test_state.py` | TypedDict의 키/타입 계약 검증 |
| `tests/test_graph.py` | 노드 단위 + 그래프 invoke 통합 검증 (4 테스트) |
| `CLAUDE.md` / `plan.md` / `progress.md` / `README.md` | 협업 규칙·로드맵·로그·개요 |

검증 결과: `pytest` 6/6 통과, `python -m src.graph "LangGraph"` → `Hello, LangGraph! topic=LangGraph` 출력.

### 2. 왜 이렇게 했나

- **LLM/외부 API를 의도적으로 배제**했습니다. M1은 "그래프가 어떻게 도는가"에 집중하는 단계라, LLM의 비결정성·네트워크·키 관리 같은 변수가 끼면 학습 신호가 흐려집니다. 결정적인 함수 하나로 시작해야 그래프 메커니즘이 또렷이 보입니다.
- **State를 `TypedDict`로 정의**한 이유는 LangGraph가 dict 기반 상태 머지를 채택했기 때문입니다. 노드는 "변경할 키만" 담은 dict를 반환하면, 프레임워크가 기존 state에 알아서 머지해줍니다.
- **TDD 빨강 → 초록** 사이클로 진행했습니다. 먼저 `from src.state import ResearchState` 같은 import만 적고 테스트를 돌려 `ModuleNotFoundError`(빨강) 를 확인 → 구현 → 6/6 통과(초록). 이게 TDD가 주는 첫 안전망입니다.

### 3. 어떻게 동작하나 — 코드 흐름

```
build_graph()
  └─ StateGraph(ResearchState)        # state 스키마 등록
       ├─ add_node("hello", hello_node)   # 노드 = (state) -> partial dict
       ├─ add_edge(START, "hello")        # 진입점
       └─ add_edge("hello", END)          # 종료
     .compile()  ──>  CompiledGraph (Runnable)

graph.invoke({"topic": "LangGraph", "message": ""})
  1. START → "hello" 노드 호출
  2. hello_node 가 {"message": "Hello, LangGraph! topic=LangGraph"} 반환
  3. LangGraph가 기존 state에 머지 (topic은 그대로, message만 갱신)
  4. "hello" → END
  5. 최종 state 반환
```

### 4. 학습 포인트 (이번 단계의 핵심)

1. **`StateGraph`는 "어떤 모양의 state를 주고받을지"를 먼저 선언**합니다. 그 모양이 `TypedDict`입니다. 이게 그래프 전체의 인터페이스 역할을 합니다.
2. **노드는 "변화분(partial state)"만 반환**합니다. `return {"message": ...}` 가 자동으로 머지됩니다. 전체 state를 다시 만들어 돌려줄 필요가 없습니다 — 이건 reducer 패턴과 같습니다.
3. **`compile()` 의 의미**: 그래프 정의(빌더) → 실제 실행 가능한 `Runnable` 변환. compile 후에는 `invoke / stream / batch` 같은 LangChain Runnable 인터페이스를 그대로 씁니다.
4. **`START`, `END`는 sentinel**: 진입/종료를 명시적으로 표시하는 특별 노드입니다. `set_entry_point("hello")` 대신 `add_edge(START, "hello")` 를 쓰는 최신 컨벤션을 채택했습니다.
5. **`invoke` vs `stream`**: 이번엔 `invoke`(최종 결과만)만 썼지만, M4에서 `stream`(노드별 중간 결과)을 다룹니다. 같은 그래프, 다른 호출 방식.
6. **TDD 첫 사이클**: 임포트만 적힌 테스트도 "이 모듈이 존재해야 한다"는 계약입니다. `ModuleNotFoundError`도 의미 있는 빨강입니다.

### 5. 막힌 곳 / 결정

- `uv` 가 시스템에 없어서 brew로 설치했습니다 (사용자 승인된 패키지 매니저).
- Python 3.14는 너무 최신이라 일부 패키지 호환성 이슈 가능성이 있어 `requires-python = ">=3.11"` 로 고정했고, uv가 자동으로 3.11.15를 가져왔습니다.

### 6. 다음 단계 예고 — M2 선형 파이프라인

- `plan` (LLM이 sub-question 생성) → `search` (Tavily 호출) → `summarize` (LLM 요약) → `write` (LLM 보고서) 4-노드를 직선으로 연결.

---

## 2026-05-07 — M2 ✅ 완료 — 선형 파이프라인 (plan → search → summarize → write)

### 0. 제약과 그 영향

`ANTHROPIC_API_KEY`는 보유하지 않은 상태에서 진행했습니다. 이 제약이 설계를 한 단계 끌어올렸습니다 — **모든 LLM 호출을 `llm` 인자로 주입받게(DI)** 만들었고, 결과적으로 테스트가 결정적이고 빠르며 키 없이도 동작합니다. Tavily는 키가 있어 통합 smoke test 1건만 실제 호출, 나머지 단위 테스트는 `search_fn` 주입으로 mocking 했습니다.

### 1. 무엇을 만들었나

| 파일 | 역할 |
|---|---|
| `src/state.py` | state 확장: `sub_questions`, `search_results`(reducer), `summaries`(reducer), `final_report` |
| `src/llm.py` | `get_chat_model()` factory — Claude Sonnet 호출 지점을 한 곳으로 집중 |
| `src/tools/web_search.py` | `tavily_search(query)` — Tavily 응답을 `[{url, content}, ...]` 모양으로 정규화 |
| `src/nodes/plan.py` | 주제 → sub-question JSON 추출. JSON 깨지면 fallback 1개 |
| `src/nodes/search.py` | sub-question별 검색, `{question, hits}` 항목으로 누적 |
| `src/nodes/summarize.py` | 질문+증거 묶어 요약 1건씩 생성 |
| `src/nodes/write.py` | 요약·출처를 모아 마크다운 보고서 생성 |
| `src/graph.py` | 4-노드 선형 그래프 + `--fake` 데모 모드 |
| `tests/conftest.py` | `make_fake_llm(responses)` 헬퍼 (FakeListChatModel) |
| `tests/test_nodes.py` | 4개 노드 각각 단위 테스트 |
| `tests/test_graph.py` | E2E 그래프 invoke (전부 fake) |
| `tests/test_tavily_integration.py` | 실제 Tavily 호출 smoke test (skipif로 키 없으면 skip) |

검증: `pytest -q` **10/10 PASS**, `python -m src.graph --fake "LangGraph reflection patterns"` 실행 시 마크다운 보고서 + 9개 실제 URL 출력.

### 2. 왜 이렇게 했나 — 설계 의도

- **노드의 시그니처를 `(state, llm=None) → dict` / `(state, search_fn=None) → dict`** 로 잡았습니다. 운영 코드는 None일 때 기본 구현을 lazy-import하고, 테스트는 fake를 주입합니다. LangGraph의 `partial(node, llm=...)` 으로 그래프 빌더에서 한 번에 주입.
- **`Annotated[list, operator.add]` reducer**를 `search_results`/`summaries`에 적용했습니다. M3에서 reflection 루프가 도입되면 같은 노드가 여러 번 실행되며 결과가 자연스럽게 누적됩니다 — M2에서 미리 깔아둔 토대.
- **`sub_questions`는 reducer 없음** = 매번 덮어씀. M3에서 plan을 다시 부를 일이 없으니 의도된 비대칭.
- **JSON 파싱 실패 시 fallback** — 실제 LLM은 가끔 코드펜스를 두르거나 prefix를 답니다. `re.search(r"\{.*\}", text, re.DOTALL)` 로 추출하고 실패해도 그래프가 죽지 않게.

### 3. 데이터 흐름 (실제 실행 기준)

```
invoke({topic: "LangGraph reflection patterns", ...empty})
   │
   ▼ plan_node
state.sub_questions = ["What is it?", "Why is it useful?", "How is it used?"]
   │
   ▼ search_node  (sub_questions 순회 → tavily_search 호출)
state.search_results += [
  {question: "What is it?", hits: [{url, content}, ...]},
  {question: "Why is it useful?", hits: [...]},
  {question: "How is it used?", hits: [...]},
]
   │
   ▼ summarize_node  (각 entry → LLM 1회 호출)
state.summaries += ["Summary 1...", "Summary 2...", "Summary 3..."]
   │
   ▼ write_node  (summaries + URL 정리 → LLM 1회 호출)
state.final_report = "# Demo Report\n..."
   │
   ▼ END
```

### 4. 학습 포인트 (이번 단계의 핵심)

1. **Reducer (`Annotated[list, operator.add]`)**: 노드가 `{"search_results": [item1, item2]}` 를 반환하면, 프레임워크가 기존 리스트에 append합니다. reducer 없으면 덮어쓰기. 이 둘의 선택이 그래프의 의미를 결정합니다.
2. **노드 = 순수 함수 + 선택적 의존성 주입**: 노드를 클래스로 만들 필요 없이 `(state, llm=None) -> dict` 함수로 충분합니다. `functools.partial`로 그래프 빌드 시 의존성을 묶습니다. 테스트에서는 다른 partial로 묶고, 운영에서는 기본값 사용.
3. **LLM mocking — `FakeListChatModel`**: LangChain은 미리 답변 리스트를 받아 순서대로 돌려주는 fake 모델을 제공합니다. 이걸로 `plan`, `summarize 1`, `summarize 2`, `write` 호출 순서까지 테스트할 수 있습니다.
4. **외부 도구 래퍼는 정규화 책임**: Tavily 원본 응답은 dict이며 키가 다양합니다. `tavily_search`가 `{url, content}`로 깎아서 노드는 도구 변경에 영향받지 않게.
5. **Integration vs Unit 분리**: 실제 네트워크 호출이 필요한 테스트는 `@pytest.mark.skipif`로 키 없으면 skip. 단위 테스트는 항상 결정적·오프라인.
6. **그래프는 단순할수록 좋다**: M2는 일부러 분기/루프 없이 직선입니다. 이 구조에서 reducer/DI/mocking 패턴을 충분히 익혀야 M3 reflection 루프를 자신있게 추가할 수 있습니다.

### 5. 막힌 곳 / 결정

- 사용자가 `ANTHROPIC_API_KEY`라며 `tvly-` 키를 주셔서 → Tavily 키로 인식하고 그렇게 사용. Anthropic 키는 추후 보강.
- `--fake` 모드를 추가해 키 없는 환경에서도 그래프 전 구간을 시연 가능. 학습 자료로 유용.
- LangGraph 0.x 최신에서 `set_entry_point` 대신 `add_edge(START, ...)` 가 권장되어 그 방식 채택.

### 6. 다음 단계 예고 — M3 Reflection 루프

- `reflect` 노드 추가 + `add_conditional_edges` 로 분기 → 정보 부족 시 search 재호출

---

## 2026-05-07 — M3 ✅ 완료 — Reflection 루프 (순환 그래프 등장)

### 1. 무엇을 만들었나

| 파일 | 변경/추가 |
|---|---|
| `src/state.py` | `iteration: int`, `sufficient: bool`, `reflection: str` 추가 |
| `src/nodes/reflect.py` | **신규** — summaries 평가, `{"sufficient", "gaps"}` JSON 파싱 |
| `src/nodes/search.py` | `iteration` 카운터 +1 추가 |
| `src/nodes/summarize.py` | 누적된 search_results 중 **아직 요약되지 않은 항목만** 처리하도록 수정 (중요) |
| `src/graph.py` | `reflect` 노드 + `add_conditional_edges("reflect", router, {...})` 추가, `MAX_ITERATIONS=3` |
| `tests/test_reflect.py` | 신규 — reflect 노드 단위 테스트 3건 |
| `tests/test_loop.py` | 신규 — 루프 시나리오 2건 (1회 보강 후 종료 / cap 도달) |

검증: `pytest -q` **15/15 PASS**, `python -m src.graph --fake "..."` 정상 출력 (1 iter sufficient).

### 2. 왜 이렇게 했나 — 설계 의도

- **`add_conditional_edges`** 가 LangGraph에서 분기/루프를 만드는 유일한 메커니즘입니다. 라우터 함수 `_route_after_reflect(state) -> str` 가 다음 노드 이름을 반환하면, mapping dict (`{"search": "search", "write": "write"}`) 로 실제 노드를 찾아갑니다.
- **종료 조건은 두 가지**: (1) `sufficient=True` 또는 (2) `iteration >= MAX_ITERATIONS`. 두 번째가 없으면 LLM이 영원히 "부족"을 외칠 때 무한 루프. **반드시 cap을 넣는다**가 reflection 패턴의 철칙.
- **요약은 "새 항목만"** — search/summarize에 둘 다 reducer를 쓰면 search_results는 누적됩니다. 그러면 매 라운드 summarize가 이미 요약한 것까지 다시 LLM에 보내 비용·시간이 폭증하고, 출력 길이도 어긋납니다. `pending = search_results[len(summaries):]` 한 줄로 해결.
- **`sub_questions` 는 reducer 없음 = 매번 덮어씀**: reflect가 새 gap 질문을 만들면 다음 search는 그것만 검색합니다. 의도된 설계입니다.

### 3. 그래프 토폴로지 (M2 → M3 변화)

```
M2 (선형):
START → plan → search → summarize → write → END

M3 (분기/루프):
START → plan → search → summarize → reflect ─┬─ sufficient or iter≥3 → write → END
                  ▲                          │
                  └──────────── search ──────┘  (insufficient & iter<3)
```

### 4. 데이터 흐름 (cap 시나리오 예시)

```
초기:        iteration=0, sufficient=False
plan:        sub_questions=[q1]
search 1:    iteration=1, search_results=[{q1, hits}]
summarize 1: summaries=[s1]                          (already=0, slice [q1])
reflect 1:   sufficient=False, sub_questions=[gap1]  → route: 1<3 → search
search 2:    iteration=2, search_results=[..., {gap1, hits}]
summarize 2: summaries=[s1, s2]                      (already=1, slice [gap1])
reflect 2:   sufficient=False, sub_questions=[gap2]  → route: 2<3 → search
search 3:    iteration=3, search_results=[..., {gap2, hits}]
summarize 3: summaries=[s1, s2, s3]                  (already=2, slice [gap2])
reflect 3:   sufficient=False, sub_questions=[gap3]  → route: 3>=3 → write
write:       final_report 작성 → END
```

### 5. 학습 포인트 (이번 단계의 핵심)

1. **`add_conditional_edges(node, router, mapping)`** — LangGraph의 분기/루프 메커니즘. router는 state 보고 다음 노드 이름을 문자열로 반환. mapping은 그 문자열 → 실제 노드 이름. 두 번째와 세 번째 인자가 같은 의미의 문자열일 때도 mapping을 명시하면 의도가 분명해집니다.
2. **루프 종료 조건 = 의도 + 안전망** — "충분하다" 같은 LLM 판단에 의존하면 무한 루프 위험. 반드시 별도의 hard cap (`iteration >= N`)을 함께 두기.
3. **Reducer는 양날의 검** — `Annotated[list, operator.add]` 가 누적을 자동화하지만, 그걸 다시 처리하는 노드는 "이미 처리한 부분"을 알아야 합니다. M3에서 summarize 버그가 그 함정이었고, `len(summaries)` 로 동기화해 해결.
4. **카운터를 어디서 증가시킬까** — `iteration`을 reflect에서 올릴 수도 있지만 search에서 올렸습니다. "search 진입 = 한 번의 리서치 라운드 시작"이라는 의미가 가장 자연스러워서. cap 비교는 reflect 라우터에서.
5. **`FakeListChatModel`로 비결정 LLM을 결정 시뮬레이션** — 루프 테스트에서 "이번엔 부족, 다음엔 충분" 같은 시나리오를 응답 리스트로 정확히 재현했습니다. 같은 패턴으로 회귀 테스트를 계속 쌓을 수 있습니다.
6. **버그 → 수정 사이클이 TDD의 진짜 가치** — 처음 cap 테스트가 `2 == 3` 으로 실패했고, 그게 summarize의 누적 처리 버그를 드러냈습니다. 테스트가 없었다면 실 LLM에서 토큰 낭비로 발견했을 문제.

### 6. 막힌 곳 / 결정

- 처음 구현에서 summarize가 모든 search_results를 매번 재요약 → fake LLM 응답 시퀀스가 어긋나 두 루프 테스트 실패. `pending = search_results[len(summaries):]` 슬라이싱으로 해결.
- LangGraph 기본 `recursion_limit=25` 는 MAX_ITERATIONS=3 시나리오에선 여유.
- LangSmith trace 시각화는 `LANGSMITH_API_KEY` 가 있을 때만 의미 있음 → 추후 추가.

### 7. 다음 단계 예고 — M4 영속성 / 스트리밍

- `SqliteSaver` checkpointer + `graph.stream` + `interrupt_before` (HITL)

---

## 2026-05-07 — M4 ✅ 완료 — 영속성 / 스트리밍 / HITL interrupt

### 1. 무엇을 만들었나

| 파일 | 변경/추가 |
|---|---|
| `src/graph.py` | `build_graph(checkpointer=None, interrupt_before=None)` 인자 추가 — 컴파일 시 주입 |
| `tests/test_persistence.py` | **신규** — 4 테스트: 상태 저장 / 스레드 격리 / interrupt+resume / 스트리밍 청크 |
| `ui/app.py` | thread_id 입력, "Resume Existing Thread" 탭, interrupt 토글, `graph.stream` 으로 노드 타임라인, `SqliteSaver` 연결 |
| `pyproject.toml` | `langgraph-checkpoint-sqlite` 추가 |

검증: `pytest -q` **19/19 PASS**, Streamlit UI 영속성 + interrupt 동작.

### 2. 왜 이렇게 했나 — 설계 의도

- **Checkpointer는 컴파일 시점에 주입**: `builder.compile(checkpointer=saver)`. 그래프 빌더는 그대로 두고 컴파일 옵션만 다르게 하면 같은 토폴로지를 영속/비영속으로 동시에 굴릴 수 있습니다.
- **`MemorySaver` (테스트) vs `SqliteSaver` (UI)**: 둘 다 `BaseCheckpointSaver` 인터페이스라 코드 변경 없이 교체. 테스트는 빠르고 결정적인 메모리, 운영은 디스크 기반 sqlite.
- **`thread_id`는 config의 `configurable`에 들어간다**: `config = {"configurable": {"thread_id": "abc"}}`. 같은 thread_id면 이어서, 다른 id면 격리. 멀티 사용자/세션 자연 지원.
- **`interrupt_before=["write"]` + `invoke(None, config)`**: write 진입 직전에 그래프가 **얼어붙고** 상태가 체크포인트에 저장됩니다. 다음 호출 때 입력으로 `None`을 주면 "거기서 이어서 돌려" 라는 의미가 되어 write 노드부터 재개.
- **스트리밍은 `stream_mode`** 로 의미가 갈림:
  - `updates` — 노드가 반환한 변화분만 (가장 가독성 ↑, UI 타임라인에 적합)
  - `values` — 매 단계의 전체 state 스냅샷
  - `messages` — LLM 토큰 단위 (M5에서 시도 가능)

### 3. interrupt → resume 흐름 (HITL)

```
1차 호출:  graph.invoke({...}, config={thread_id: "t1"})
            ┌─ plan → search → summarize → reflect 까지 실행
            └─ "write" 직전에 STOP — 상태가 sqlite에 저장됨
            반환 state.final_report == ""

(사용자가 UI에서 검토)

2차 호출:  graph.invoke(None, config={thread_id: "t1"})
            ┌─ 체크포인터에서 마지막 상태 로드
            └─ "write" 부터 재개 → END
            반환 state.final_report 채워짐
```

### 4. 학습 포인트

1. **Checkpointer = thread_id 별 상태 저장소**. 그래프 한 번 정의하면 무수한 동시 thread를 같은 그래프로 처리 가능 (마치 Redux store별 사용자처럼).
2. **`graph.invoke(None, config)` 의 의미**: "새 입력 없이, 저장된 곳에서 이어 돌려." interrupt 상태를 풀고 다음 노드로 넘기는 표준 관용구.
3. **`interrupt_before` vs `interrupt_after`**: 둘 다 가능. 보고서 검토는 before-write가 자연. 도구 호출 승인 같은 케이스는 after-tool 패턴.
4. **`graph.get_state(config)` 로 외부에서 현재 상태/다음 노드 조회**: UI의 "Resume Existing Thread" 탭이 이걸 사용. `snap.next` 가 비어있으면 종료, 비어있지 않으면 거기서 멈춰있다는 뜻.
5. **스트리밍은 progress UI 의 핵심**: `stream_mode="updates"` 청크는 `{"노드명": 변화분 dict}` 형태. UI에서 이걸 그대로 타임라인 카드로 그릴 수 있습니다.
6. **테스트에서 Memory, 운영에서 Sqlite** 패턴은 LangChain 전반의 컨벤션 (대부분의 abstraction이 인메모리/디스크 두 구현을 제공).

### 5. 막힌 곳 / 결정

- `SqliteSaver.from_conn_string(...)` 은 **컨텍스트 매니저** 라 Streamlit 리런마다 닫히면 곤란 → `sqlite3.connect(..., check_same_thread=False)` + `SqliteSaver(conn)` 를 `@st.cache_resource` 로 감싸 한 번만 만들고 재사용.
- LangGraph의 기본 `recursion_limit=25` 가 reflection 루프를 충분히 수용 (M3 테스트와 동일).
- LangSmith trace는 키가 들어오면 자동 활성화되도록 환경변수만 채워두고 실제 연동은 사용자가 API 키 추가 시 검증.

### 6. 다음 단계 예고 — M5 마무리

- README 정비, 그래프 시각화, LangSmith 가이드, 확장 트랙

---

## 2026-05-07 — M5 ✅ 완료 — UI · 시각화 · 문서 마무리

### 1. 무엇을 만들었나

| 파일 | 변경/추가 |
|---|---|
| `README.md` | 빠른 시작·스택·실행 모드 표·디렉토리 구조·시나리오·LangSmith 가이드·트러블슈팅 정비 |
| `scripts/show_graph.py` | **신규** — `graph.get_graph().draw_mermaid()` 와 ASCII 출력 |
| `ui/app.py` | 사이드바에 Mermaid 그래프 다이어그램 expander 추가 |
| `plan.md` / `progress.md` | M5 ✅ 표시 + 회고 |

검증: `pytest -q` **19/19 PASS**, `uv run python scripts/show_graph.py` Mermaid 출력 정상.

### 2. 학습 포인트

1. **`graph.get_graph().draw_mermaid()`** — 컴파일된 그래프 토폴로지를 Mermaid 문법으로 직접 추출. 문서·UI에 그대로 임베드 가능.
2. **conditional edge는 `-.->` 점선** 으로 표시됨 (Mermaid 출력에서 reflect→search/write 가 점선) — 분기와 일반 엣지를 시각적으로 구분.
3. **README는 "다섯 단계의 결과물" 인덱스** — 미래의 자기·동료가 한 번에 진입할 수 있는 단일 페이지. 우리 프로젝트의 학습용 가치는 여기에 응축됩니다.

---

## 🎓 전체 여정 회고 — 5단계로 본 LangGraph

이 프로젝트는 LangGraph를 작은 단위부터 누적으로 쌓아 올리며 학습했습니다. 단계별 핵심 키워드:

| 단계 | 한 줄 정의 | 새로 배운 LangGraph 개념 |
|---|---|---|
| **M1** | "그래프란 무엇인가" | `StateGraph`, `TypedDict`, 노드 = 변화분 dict 반환, `START/END`, `compile()` |
| **M2** | "선형 파이프라인 + 외부 도구" | `Annotated[list, operator.add]` reducer, 노드 DI 패턴, `FakeListChatModel`, 도구 래퍼 정규화 |
| **M3** | "분기와 루프, 그리고 종료 조건" | `add_conditional_edges`, 라우터 함수, hard cap, reducer 누적 처리 함정 |
| **M4** | "상태가 디스크에 산다" | `checkpointer`, `thread_id` config, `interrupt_before`, `graph.invoke(None, ...)`, `stream_mode` |
| **M5** | "사용자에게 보여주기" | `graph.get_graph().draw_mermaid()`, Streamlit 통합, README/문서로 응결 |

### TDD가 실제로 잡아낸 것
- **M3 cap 테스트 `2 == 3` 실패** → summarize가 누적 search_results를 매번 재요약하는 버그 발견 → `pending = search_results[len(summaries):]` 슬라이싱으로 해결. 실 LLM이었으면 토큰 낭비로만 보였을 문제를 fake LLM의 결정성이 즉시 드러냈습니다.

### 의도적으로 안 한 것 (그리고 이유)
- **모든 노드를 클래스로 만들기** — 함수 + DI 로 충분. 클래스는 상태가 노드 자체에 있을 때만 가치.
- **광범위한 try/except** — 노드는 순수 함수에 가까울수록 좋음. 외부 경계(LLM 응답 파싱)에서만 fallback.
- **추상 도구 인터페이스** — Tavily 외 검색이 들어올 때 만들면 충분. 지금은 `SearchFn = Callable[[str], list[dict]]` 한 줄로 끝.

### 다음에 시도하면 좋을 확장
- **Multi-agent (Supervisor)** — researcher / critic / writer 분리. 같은 `StateGraph` 위에 노드만 늘리면 됨.
- **RAG hybrid** — 사내 문서 retriever를 search 노드와 병렬 호출 (`Send` API).
- **평가 자동화** — LangSmith Datasets + LLM-as-judge 로 보고서 품질 회귀 테스트.
- **`stream_mode="messages"`** — LLM 토큰 단위 스트리밍. 실 Anthropic 키가 들어오는 순간 UI에 즉시 반영 가능.
- **배포** — LangGraph Cloud 또는 FastAPI + Docker 로 외부 서비스화.

이 코드베이스는 위 모든 확장의 출발점으로 충분히 깨끗합니다.
