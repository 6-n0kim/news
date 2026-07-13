# llm_chain.py
#
# LangChain 기반 뉴스 분석 파이프라인.
#   1) 뉴스를 10개씩 청크로 나누어 각각 자유 형식으로 분석 (map)
#   2) 청크별 분석을 하나의 자유 형식 텍스트로 종합 (reduce)
#   3) 자유 형식 텍스트를 구조화된 스키마로 후처리 파싱
#   4) 파싱 결과를 기존 이모지 템플릿 텍스트로 렌더링

import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.exceptions import OutputParserException

from app.rss_runner import RssItem

load_dotenv()

CHUNK_SIZE = 10
NVIDIA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
MAX_BODY_CHARS = 800

# 시스템 프롬프트: 모델에게 역할과 분석 맥락을 별도로 부여한다.
SYSTEM_PROMPT = (
    "당신은 20년 이상 한국 주식시장을 분석해 온 매크로/섹터 애널리스트입니다.\n"
    "당신의 역할은 그날 수집된 뉴스 흐름을 바탕으로 다음 거래일 코스피·코스닥 시장에 "
    "미칠 영향을 냉정하고 근거 있게 분석하는 것입니다.\n"
    "과장된 표현이나 근거 없는 추측은 피하고, 실제 투자자가 참고할 수 있는 수준의 "
    "통찰을 제공하세요."
)


def get_chat_model(max_tokens: int = 4096, reasoning_budget: int = 4096) -> ChatOpenAI:
    """NVIDIA NIM(OpenAI 호환)을 가리키는 LangChain ChatOpenAI 인스턴스 반환."""
    return ChatOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.environ["NVIDIA_API_KEY"],
        model=NVIDIA_MODEL,
        temperature=0.0,
        top_p=0.95,
        max_tokens=max_tokens,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": reasoning_budget,
        },
    )


# --- 구조화 스키마 (자유 형식 분석 결과를 이 형태로 후처리 파싱한다) ---

class Issue(BaseModel):
    title: str = Field(description="이슈/뉴스 제목 요약")
    impact_level: str = Field(description="시장 영향도. '상', '중', '하' 중 하나")
    direction: str = Field(description="예상 방향성. '긍정적', '부정적', '중립' 중 하나")


class Sector(BaseModel):
    name: str = Field(description="섹터 또는 테마명")
    direction: str = Field(description="예상 방향. '강세', '약세', '변동성 확대' 중 하나")
    related_stocks: str = Field(description="관련 종목이나 ETF 이름 목록 (쉼표로 구분)")
    strategy: str = Field(description="투자 대응 방법 요약")


class MarketAnalysis(BaseModel):
    market_summary: str = Field(description="내일 시장 심리에 대한 종합 요약")
    issues: List[Issue] = Field(description="핵심 이슈 목록 (2~4개)")
    sectors: List[Sector] = Field(description="섹터 및 종목별 영향 목록 (2~4개)")
    final_strategy: str = Field(description="내일 장 전략 한 줄 요약")


def _chunk_items(items: List[RssItem], size: int = CHUNK_SIZE) -> List[List[RssItem]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _format_news_block(chunk: List[RssItem], offset: int) -> str:
    lines = []
    for i, it in enumerate(chunk, start=offset + 1):
        body = (it.summary or it.content_html or "").strip()
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + "...(생략)"
        lines.append(f"[{i}] 제목: {it.title}")
        if it.published:
            lines.append(f"    게시일: {it.published}")
        if body:
            lines.append(f"    내용: {body}")
    return "\n".join(lines)


# --- 1) 청크 단위 자유 형식 분석 (map) ---

_CHUNK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human",
     "아래는 오늘 수집된 뉴스 중 {chunk_index}/{chunk_total}번째 묶음입니다.\n"
     "각 뉴스를 훑어보고, 다음 거래일 한국 주식시장에 영향을 줄 만한 내용이 있다면 "
     "자유로운 문장으로 서술하세요.\n"
     "글머리 기호나 표 같은 형식에 얽매이지 말고, 어떤 이슈가 왜 중요한지와 관련 "
     "섹터·종목을 자연스럽게 설명하세요. 영향이 없는 단순 뉴스는 간단히 언급하거나 "
     "생략해도 됩니다.\n\n"
     "[뉴스 목록]\n{news_block}"),
])


def _analyze_chunk(chat: ChatOpenAI, chunk: List[RssItem], chunk_index: int, chunk_total: int, offset: int) -> str:
    news_block = _format_news_block(chunk, offset)
    messages = _CHUNK_PROMPT.format_messages(
        chunk_index=chunk_index, chunk_total=chunk_total, news_block=news_block,
    )
    return chat.invoke(messages).content


# --- 2) 청크별 분석 종합 (reduce) ---

_SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human",
     "아래는 오늘 수집된 전체 뉴스를 {chunk_total}개 묶음으로 나누어 각각 분석한 "
     "결과입니다.\n"
     "이 분석들을 종합하여 내일 한국 주식시장에 대한 하나의 통합된 분석을 자유 형식 "
     "문장으로 작성하세요.\n"
     "다음 네 가지 내용이 모두 포함되도록 서술하되, 형식은 자유입니다:\n"
     "- 시장 전반 심리 요약\n"
     "- 핵심 이슈들 (각 이슈의 시장 영향도와 예상 방향성 포함)\n"
     "- 영향받는 섹터/종목과 투자 대응 전략\n"
     "- 내일 장 전략 한 줄 요약\n\n"
     "[묶음별 분석 결과]\n{combined_summaries}"),
])


def _synthesize(chat: ChatOpenAI, chunk_summaries: List[str]) -> str:
    combined = "\n\n".join(
        f"--- 묶음 {i} 분석 ---\n{s}" for i, s in enumerate(chunk_summaries, start=1)
    )
    messages = _SYNTHESIS_PROMPT.format_messages(
        chunk_total=len(chunk_summaries), combined_summaries=combined,
    )
    return chat.invoke(messages).content


# --- 3) 자유 형식 텍스트 -> 구조화 스키마 후처리 파싱 ---

_PARSER = PydanticOutputParser(pydantic_object=MarketAnalysis)

_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 자유 형식의 시장 분석 텍스트를 정해진 스키마의 구조화된 데이터로 정확히 "
     "옮겨 적는 데이터 추출기입니다. 텍스트에 없는 내용을 추측하거나 지어내지 마세요."),
    ("human",
     "아래 자유 형식 분석 텍스트를 스키마에 맞게 구조화하세요.\n\n"
     "[자유 형식 분석]\n{freeform_text}\n\n{format_instructions}"),
])

_RETRY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "당신은 잘못된 JSON 출력을 스키마에 맞게 고치는 교정기입니다."),
    ("human",
     "아래 출력은 스키마 파싱에 실패했습니다.\n\n[이전 출력]\n{previous_output}\n\n"
     "[파싱 오류]\n{error}\n\n{format_instructions}\n\n"
     "위 오류를 반영하여 스키마에 맞는 JSON만 다시 출력하세요."),
])


def _extract_structured(chat: ChatOpenAI, freeform_text: str) -> MarketAnalysis:
    format_instructions = _PARSER.get_format_instructions()
    messages = _EXTRACTION_PROMPT.format_messages(
        freeform_text=freeform_text, format_instructions=format_instructions,
    )
    raw = chat.invoke(messages).content
    try:
        return _PARSER.parse(raw)
    except OutputParserException as exc:
        # 스키마 불일치 시 오류 내용을 알려주고 한 번 더 교정 요청 (post-processing 재시도)
        retry_messages = _RETRY_PROMPT.format_messages(
            previous_output=raw, error=str(exc), format_instructions=format_instructions,
        )
        fixed = chat.invoke(retry_messages).content
        return _PARSER.parse(fixed)


# --- 4) 구조화 결과 -> 기존 이모지 템플릿 렌더링 ---

_IMPACT_EMOJI = {"상": "🟢", "중": "🟡", "하": "🔴"}
_DIRECTION_EMOJI = {"긍정적": "🟢", "부정적": "🔴", "중립": "🟡"}
_SECTOR_EMOJI = {"강세": "🟢", "약세": "🔴", "변동성 확대": "🟡"}
_NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def _with_emoji(value: str, table: dict) -> str:
    for key, emoji in table.items():
        if key in value:
            return f"{value}{emoji}"
    return f"{value}⚪"


def render_template(analysis: MarketAnalysis) -> str:
    lines = [
        "[시장 요약 진단]",
        f"내용: {analysis.market_summary}",
        "",
        "-" * 50,
        "[핵심 이슈 분석]",
    ]
    for i, issue in enumerate(analysis.issues, start=1):
        lines.append(f"이슈 {i}: {issue.title}")
        lines.append(f"- 시장 영향도: {_with_emoji(issue.impact_level, _IMPACT_EMOJI)}")
        lines.append(f"- 예상 방향성: {_with_emoji(issue.direction, _DIRECTION_EMOJI)}")
        lines.append("")

    lines.append("-" * 50)
    lines.append("[섹터 및 종목별 영향]")
    for i, sector in enumerate(analysis.sectors, start=1):
        marker = _NUMBER_EMOJIS[i - 1] if i <= len(_NUMBER_EMOJIS) else f"{i}."
        lines.append(f"{marker} {sector.name}")
        lines.append(f"- 예상 방향: {_with_emoji(sector.direction, _SECTOR_EMOJI)}")
        lines.append(f"- 관련 종목군: {sector.related_stocks}")
        lines.append(f"- 투자 대응: {sector.strategy}")
        lines.append("")

    lines.append("-" * 50)
    lines.append("[내일 장 전략 한 줄 요약]")
    lines.append(f"전략: {analysis.final_strategy}")

    return "\n".join(lines)


def run_pipeline(items: List[RssItem]) -> str:
    """
    뉴스 목록을 청크 단위로 분석(map) -> 종합(reduce) -> 구조화 파싱 ->
    템플릿 렌더링까지 수행하고 최종 텔레그램용 텍스트를 반환한다.
    """
    chat = get_chat_model()
    chunks = _chunk_items(items)
    chunk_total = len(chunks)

    chunk_summaries = []
    offset = 0
    for idx, chunk in enumerate(chunks, start=1):
        chunk_summaries.append(_analyze_chunk(chat, chunk, idx, chunk_total, offset))
        offset += len(chunk)

    freeform_result = (
        chunk_summaries[0] if chunk_total == 1 else _synthesize(chat, chunk_summaries)
    )

    analysis = _extract_structured(chat, freeform_result)
    return render_template(analysis)
