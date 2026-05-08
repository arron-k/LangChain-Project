from langchain_core.language_models.fake_chat_models import FakeListChatModel


def make_fake_llm(responses: list[str]) -> FakeListChatModel:
    return FakeListChatModel(responses=responses)
