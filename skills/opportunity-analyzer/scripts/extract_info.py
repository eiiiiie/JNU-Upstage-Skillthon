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
        "required_docs":      {
            "oneOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"},
            ]
        },
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
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "아래 공고 텍스트에서 지정된 항목을 추출해 JSON으로만 반환하라. "
    "문서에 명시되지 않은 항목은 반드시 null로 반환하고 절대 추측하지 마라. "
    "required_docs는 제출 서류 목록을 배열(array)로 반환하라. 서류가 여러 개면 각각 개별 항목으로 분리하고, 명시되지 않으면 null로 반환하라. "
    "공고가 외국어로 작성된 경우에도 추출된 모든 문자열 값은 반드시 한국어로 번역해 반환하라. "
    "JSON 이외의 텍스트는 출력하지 마라."
)

_FALLBACK = {
    "title": None, "category": None, "host": None, "deadline": None,
    "target": None, "qualifications": None, "benefits": None,
    "required_docs": None, "period": None, "location": None,
    "team_or_individual": None, "special_notes": None,
}

_VALID_CATEGORIES = {"대외활동", "공모전", "인턴십", "장학금", "교육 프로그램", "기타"}

# 공고 문서 여부 판단에 필수적인 핵심 필드
_CORE_FIELDS = ("title", "host", "deadline", "qualifications")

# 문서 품질 경고 기준: 전체 12개 필드 중 null 비율
_QUALITY_WARN_THRESHOLD = 0.75  # 75% 이상 null이면 품질 낮음으로 판단


def _normalize(result: dict) -> dict:
    """파싱 성공 후 필드별 정합성을 최소 보정한다."""
    for key, default in _FALLBACK.items():
        if key not in result:
            result[key] = default

    if result.get("category") not in _VALID_CATEGORIES:
        result["category"] = None

    rd = result.get("required_docs")
    if isinstance(rd, str):
        result["required_docs"] = [rd]
    elif isinstance(rd, list):
        if not all(isinstance(item, str) for item in rd):
            result["required_docs"] = None

    return result


def check_is_opportunity(opp_info: dict) -> tuple[bool, str | None]:
    """
    추출 결과를 바탕으로 공고 문서 여부를 판단한다.
    핵심 필드(title, host, deadline, qualifications)가 모두 null이면
    공고 문서가 아닐 수 있음을 안내한다.

    Returns:
        (is_opportunity: bool, warning_message: str | None)
        공고로 판단되면 (True, None), 아니면 (False, 안내 문자열)
    """
    null_core = sum(1 for f in _CORE_FIELDS if not opp_info.get(f))
    if null_core == len(_CORE_FIELDS):
        return (
            False,
            "⚠️ 업로드된 문서가 공고 문서가 아닐 수 있습니다. "
            "공고 PDF 또는 공고 이미지를 다시 업로드해 주세요.",
        )
    return True, None


def check_document_quality(opp_info: dict) -> tuple[bool, str | None]:
    """
    추출 결과를 바탕으로 문서 품질을 판단한다.
    전체 필드 중 null 비율이 임계값 이상이면 품질 낮음 경고를 반환한다.

    Returns:
        (is_low_quality: bool, warning_message: str | None)
        품질 낮으면 (True, 경고 문자열), 아니면 (False, None)
    """
    total = len(_FALLBACK)
    null_count = sum(1 for f in _FALLBACK if not opp_info.get(f))
    if null_count / total >= _QUALITY_WARN_THRESHOLD:
        return (
            True,
            "⚠️ 문서에서 인식된 정보가 적습니다. 스캔 품질이 낮거나 텍스트 추출이 제한된 문서일 수 있습니다. "
            "분석 결과의 정확도가 낮을 수 있으며, 공고 원문을 직접 확인하시기 바랍니다.",
        )
    return False, None


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
                "strict": True,
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
    try:
        result = json.loads(content)
        if not isinstance(result, dict):
            return dict(_FALLBACK)
        return _normalize(result)
    except (json.JSONDecodeError, KeyError):
        return dict(_FALLBACK)
