# nvidia_llm.py

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def get_client() -> OpenAI:
    """NVIDIA NIM 클라이언트 반환 (싱글턴 패턴)"""
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.environ["NVIDIA_API_KEY"],
    )

def analyze_news(prompt: str, reasoning_budget: int = 4096) -> str:
    """
    주식에 영향이 있을 뉴스를 수집 후 요약
    """
    client = get_client()
    completion = client.chat.completions.create(
        model="nvidia/nemotron-3-ultra-550b-a55b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,      # 분석 작업에는 더 낮은 temperature 권장
        top_p=0.95,
        max_tokens=4096,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": reasoning_budget,
        },
        stream=True,
    )

    result = []
    for chunk in completion:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            result.append(delta.content)
    
    return "".join(result)
