# Project: LangGraph 리서치 에이전트

LangChain + LangGraph 오케스트레이션 학습용 신규 프로젝트입니다. 사용자가 입력한 주제에 대해 자율적으로 웹 검색·요약·반성(reflection)·보고서 작성을 수행하는 리서치 에이전트를 단계적으로(M1~M5) 구축합니다.

## 개발 원칙

- **TDD 필수**: 모든 기능은 *실패하는 테스트 작성 → 구현 → 통과 → 리팩터링* 순으로 진행한다. 단계마다 `uv run pytest -q` 로 반드시 검증한다. 검증을 건너뛰고 다음 단계로 넘어가지 않는다.
- **코멘트 최소화**: 코드 안에 불필요한 주석을 달지 않는다. 네이밍과 구조로 의도를 드러낸다. WHY가 비자명할 때만 짧게 한 줄 남긴다. 무엇(What)을 하는지 설명하는 주석은 금지.
- **MVP 단계별 개발**: 기능을 단계(M1, M2, …)로 쪼개 점진적으로 쌓는다. 한 단계는 항상 "동작하는 가장 작은 시스템"이어야 한다. 단계 완료 후에는 사용자가 학습할 수 있도록 `progress.md`에 *무엇을 / 왜 / 어떻게* 만들었는지 상세히 기록한다.

## 검증 기준

각 MVP 단계는 다음 두 가지가 모두 성공해야 "완료"로 간주한다.

1. `uv run pytest -q` 전부 통과
2. 그래프 실제 실행 (CLI 또는 데모 스크립트)이 의도한 출력을 낸다
3. (선택) `LANGSMITH_TRACING=true` 환경에서 LangSmith trace가 잡히는지 확인

## 문서 동기화 규칙

단계 완료 시 다음 두 문서를 함께 갱신한다.

- `plan.md` — 다음 단계 정의 / 변경된 설계 반영
- `progress.md` — 완료 회고 (학습 노트)

## 스택 (확정)

- Python 3.11+, 패키지 매니저 **uv**
- `langgraph`, `langchain`, `langchain-anthropic` (Codex Sonnet 4.6)
- 검색(M2~) `langchain-tavily`, 영속성(M4) SqliteSaver
- 테스트 `pytest`, `pytest-asyncio`

## 디렉토리 컨벤션

```
src/
  state.py           # ResearchState (TypedDict)
  graph.py           # StateGraph 조립 + compile
  nodes/             # 노드 함수 (1 노드 = 1 파일)
  tools/             # 외부 도구 래퍼 (M2~)
  prompts/           # 프롬프트 템플릿 (M2~)
tests/               # pytest 단위/통합 테스트
```

