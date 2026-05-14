"""
extract_info.py

파싱된 마크다운 텍스트에서 공고 핵심 정보를 JSON으로 추출한다.
문서에 없는 항목은 null로 반환하며, 절대 추측하지 않는다.
"""

import json
import requests

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "title":              {"type": ["string", "null"]},
        "category":           {
            "type": ["string", "null"],
            "enum": ["대외활동", "공모전", "인턴십", "장학금", "교육 프로그램", "기타", None],
        },
        "host":               {"type": ["string", "null"]},
        "deadline":           {"type": ["string", "null"]},
        "target":             {"type": ["string", "null"]},
        "qualifications":     {"type": ["string", "null"]},
        "benefits":           {"type": ["string", "null"]},
        "required_docs":      {"type": ["string", "null"]},
        "period":             {"type": ["string", "null"]},
        "location":           {"type": ["string", "null"]},
        "team_or_individual": {"type": ["string", "null"]},
        "special_notes":      {"type": ["string", "null"]},
    },
    "required": [
        "title", "category", "host", "deadline", "target",
        "qualifications", "benefits", "required_docs",
        "period", "location", "team_or_individual", "special_notes",
    ],
}

SYSTEM_PROMPT = (
    "아래 공고 텍스트에서 지정된 항목을 추출해 JSON으로만 반환하라. "
    "문서에 명시되지 않은 항목은 반드시 null로 반환하고 절대 추측하지 마라. "
    "JSON 이외의 텍스트는 출력하지 마라."
)


def extract_info(markdown_text: str, api_key: str) -> dict:
    """
    공고 마크다운 텍스트를 Solar LLM에 전달해 구조화된 JSON을 반환한다.

    Args:
        markdown_text: parse_document()의 반환값
        api_key:       Upstage API 키

    Returns:
        EXTRACT_SCHEMA에 정의된 필드를 포함한 딕셔너리
    """
    url = "https://api.upstage.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "solar-pro3",
        "temperature": 0.1,
        "max_tokens": 1000,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "opportunity_info",
                "schema": EXTRACT_SCHEMA,
            },
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": markdown_text},
        ],
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)
