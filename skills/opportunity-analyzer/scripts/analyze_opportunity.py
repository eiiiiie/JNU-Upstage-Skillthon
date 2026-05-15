"""
analyze_opportunity.py

공고 정보와 사용자 정보를 비교해 적합도 판단 결과를 생성한다.
판단 일관성을 위해 퓨샷 예시 2개를 시스템 프롬프트에 포함한다.
"""

import json
import re
from datetime import datetime, timezone, timedelta
import requests

ANALYSIS_SYSTEM = """
당신은 대학생 공고 적합도 분석 전문가다.
[공고 정보]와 [사용자 정보]를 비교해 아래 JSON 스키마로 판단 결과를 반환하라.
모든 출력은 반드시 한국어로 작성하라. 공고 원문이 외국어인 경우에도 분석 결과 전체를 한국어로 출력하라.

출력 JSON 스키마:
{
  "verdict": "바로 지원 가능 | 준비 후 지원 | 조건 확인 필요 | 비추천",
  "verdict_reason": "string — 아래 4가지 관점을 모두 포함",
  "summary_line": "string — 한 문장 요약",
  "fit_score": integer (1~10),
  "strengths": ["string"],
  "gaps": ["string"],
  "checklist": [{"item": "string", "priority": "필수 | 권장 | 선택", "description": "string — 준비 항목에 대한 구체적 설명"}],
  "tips": ["string"]
}

verdict_reason 필수 4가지 관점 (모두 빠짐없이 서술할 것):
1. 자격 요건 충족 여부 (문서에 명시된 조건 기준)
2. 사용자 관심/목표와의 부합도 (관심 유형 및 목표 항목 기준)
3. 일정·활동 가능 조건의 적합성 (활동 기간, 온/오프라인 방식 등)
4. 정보 부족 또는 불확실성 (미명시 조건, 추가 확인 필요 사항)
해당 정보가 부족한 관점도 그 사실을 명시하고 생략하지 마라.

판단 원칙:
- 공고 문서에 명시된 조건만 기준으로 삼는다. 외부 정보로 보완하지 않는다.
- 문서에 없거나 불명확한 조건은 추측하지 말고 "조건 확인 필요"로 처리한다.
- fit_score: 자격 미충족이 명확하면 4 이하, 핵심 조건 불명확이면 5~6 이하로 산정한다.

verdict 판정 기준:
- 바로 지원 가능: 명시된 모든 자격 요건 충족, 즉시 준비 가능
- 준비 후 지원: 1~2가지 부족하지만 준비하면 지원 가능
- 조건 확인 필요: 핵심 조건 불명확 또는 미명시 — 정보 부족의 보수적 처리
- 비추천: 자격 요건 미충족 명확 또는 상황과 현저히 불일치

절대 JSON 이외의 텍스트를 출력하지 마라.

--- 퓨샷 예시 시작 ---

예시 1 — 바로 지원 가능
입력:
  공고: 카카오 AI 해커톤 / 대학생 재학생 팀 2~4인 / 파이썬 우대 / 온라인 / 여름방학 3일
  사용자: 재학 2학년 / 포트폴리오 강화 목표 / 파이썬 가능 / 여름방학 가능
출력:
{
  "verdict": "바로 지원 가능",
  "verdict_reason": "① 재학 중 대학생 조건 충족, 파이썬 가능으로 우대 조건 해당. ② 포트폴리오 강화 목표와 공모전 성격·인턴 추천 혜택이 잘 맞음. ③ 온라인 진행이며 여름방학 기간과 겹쳐 참여 가능. ④ 팀원 확보 여부는 문서 외 사항으로 사용자 확인 필요.",
  "summary_line": "자격·일정·역량 모두 충족하며 포트폴리오 목표와 잘 맞는 공모전이다.",
  "fit_score": 9,
  "strengths": ["재학 요건 충족", "파이썬 역량으로 우대 조건 해당", "여름방학 일정 여유"],
  "gaps": ["팀원 구성 필요 (2~4인 팀 참가)"],
  "checklist": [
    {"item": "팀원 모집 (1~3명)", "priority": "필수", "description": "공고의 팀 구성 요건을 충족할 수 있도록 함께 참여할 팀원을 확보"},
    {"item": "아이디어 기획서 초안 작성 (A4 3매)", "priority": "필수", "description": "제출 요구사항에 맞춰 핵심 문제 정의와 해결 아이디어를 문서화"},
    {"item": "머신러닝 관련 아이디어 구체화", "priority": "권장", "description": "포트폴리오 강화 목표와 연결될 수 있도록 구현 방향과 차별점을 정리"}
  ],
  "tips": [
    "인턴 추천 혜택이 있으므로 기획서에 실현 가능성과 기술 스택을 명확히 기술하면 유리하다.",
    "온라인 해커톤이므로 협업 툴(Notion, GitHub)을 팀과 사전에 맞춰두면 좋다."
  ]
}

예시 2 — 조건 확인 필요
입력:
  공고: 환경부 글로벌 청년 서포터즈 / '활동에 열정 있는 청년' / 오프라인 서울 / 4개월
  사용자: 재학 3학년 / 스펙·네트워크 목표 / 2학기 수업 있음, 주말 가능
출력:
{
  "verdict": "조건 확인 필요",
  "verdict_reason": "① '활동에 열정 있는 청년'으로만 명시돼 나이·학년 등 구체적 자격 불명확. ② 스펙·네트워크 목표와 서포터즈 성격은 잘 맞음. ③ 4개월 오프라인(서울) 활동과 2학기 수업 일정 충돌 가능 — 주중 참여 가능 여부 확인 필요. ④ 모집 대상 null로 핵심 자격 미명시 — 지원 전 주최 기관에 직접 확인 권장.",
  "summary_line": "목표와는 잘 맞지만 자격 요건과 주중 일정 충돌 가능성을 먼저 확인해야 한다.",
  "fit_score": 5,
  "strengths": ["스펙·네트워크 목표와 부합", "개인 지원으로 팀 구성 불필요"],
  "gaps": ["모집 대상 불명확 — 나이·학년 제한 여부 확인 필요", "주중 오프라인 활동과 2학기 수업 충돌 가능"],
  "checklist": [
    {"item": "환경부 담당자에게 자격 요건 확인", "priority": "필수", "description": "모집 대상이 불명확하므로 나이·학년 제한 여부를 지원 전 직접 확인"},
    {"item": "주중 오프라인 일정 가능 여부 확인", "priority": "필수", "description": "4개월 오프라인 활동과 2학기 수업 일정 충돌 여부를 사전에 점검"},
    {"item": "자기소개서 초안 작성 (확인 후 진행)", "priority": "권장", "description": "자격 및 일정 확인 완료 후 공고 요구사항에 맞춰 초안 준비"}
  ],
  "tips": [
    "자격 확인 전에 지원서 작성 시간을 투자하기보다 담당자 문의를 먼저 하는 것이 효율적이다.",
    "환경 관련 경험이 없더라도 관심과 참여 의지를 구체적 사례로 서술하면 보완 가능하다."
  ]
}

--- 퓨샷 예시 끝 ---
"""

# 항목5: response_format에 사용할 JSON 스키마 (기존 출력 필드 그대로)
_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["바로 지원 가능", "준비 후 지원", "조건 확인 필요", "비추천"],
        },
        "verdict_reason": {"type": "string"},
        "summary_line":   {"type": "string"},
        "fit_score":      {"type": "integer"},
        "strengths":      {"type": "array", "items": {"type": "string"}},
        "gaps":           {"type": "array", "items": {"type": "string"}},
        "checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item":        {"type": "string"},
                    "priority":    {
                        "type": "string",
                        "enum": ["필수", "권장", "선택"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["item", "priority", "description"],
                "additionalProperties": False,
            },
        },
        "tips": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict", "verdict_reason", "summary_line",
        "fit_score", "strengths", "gaps", "checklist", "tips",
    ],
    "additionalProperties": False,
}

_VALID_VERDICTS = {"바로 지원 가능", "준비 후 지원", "조건 확인 필요", "비추천"}
_VALID_PRIORITIES = {"필수", "권장", "선택"}

# KST = UTC+9
_KST = timezone(timedelta(hours=9))


# ── 항목 2·3: deadline 판단 헬퍼 ────────────────────────────────────────────

def _parse_deadline(deadline_str: str) -> datetime | None:
    """
    deadline 문자열에서 날짜(+시각)를 파싱한다.
    인식 불가능한 형식이면 None을 반환하고 예외를 터뜨리지 않는다.
    지원 패턴: YYYY.MM.DD, YYYY-MM-DD, YYYY/MM/DD (시각 선택적)
    """
    if not deadline_str or not isinstance(deadline_str, str):
        return None

    # 날짜+시각 패턴: 2025.07.15 18:00, 2025-07-15 23:59 등
    patterns = [
        r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})",
        r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})",
    ]
    for pat in patterns:
        m = re.search(pat, deadline_str)
        if m:
            groups = m.groups()
            try:
                if len(groups) == 5:
                    year, month, day, hour, minute = (int(g) for g in groups)
                    return datetime(year, month, day, hour, minute, tzinfo=_KST)
                else:
                    year, month, day = (int(g) for g in groups)
                    # 날짜만 있을 때는 당일 23:59를 마감으로 간주
                    return datetime(year, month, day, 23, 59, tzinfo=_KST)
            except ValueError:
                return None
    return None


def _deadline_flags(deadline_str: str | None) -> dict:
    """
    deadline 문자열을 받아 마감 관련 플래그 딕셔너리를 반환한다.
    반환 키:
      - deadline_parsed (bool): 파싱 성공 여부
      - is_expired      (bool | None): 마감 지났으면 True, 아니면 False, 파싱 실패면 None
      - is_urgent       (bool | None): 24시간 이내면 True, 아니면 False, 파싱 실패면 None
    """
    if not deadline_str:
        return {"deadline_parsed": False, "is_expired": None, "is_urgent": None}

    dt = _parse_deadline(deadline_str)
    if dt is None:
        return {"deadline_parsed": False, "is_expired": None, "is_urgent": None}

    now = datetime.now(tz=_KST)
    delta = dt - now
    is_expired = delta.total_seconds() < 0
    is_urgent  = (not is_expired) and (delta.total_seconds() <= 86400)  # 24h

    return {
        "deadline_parsed": True,
        "is_expired": is_expired,
        "is_urgent": is_urgent,
    }


# ── 기존 _normalize_result (유지) ───────────────────────────────────────────

def _normalize_result(result: dict) -> dict:
    """파싱 성공 후 출력 필드별 정합성을 최소 보정한다."""
    if result.get("verdict") not in _VALID_VERDICTS:
        result["verdict"] = "조건 확인 필요"

    score = result.get("fit_score")
    if isinstance(score, (int, float)):
        result["fit_score"] = max(1, min(10, int(score)))
    else:
        result["fit_score"] = 5

    for field in ("strengths", "gaps", "tips"):
        if not isinstance(result.get(field), list):
            result[field] = []

    if not isinstance(result.get("checklist"), list):
        result["checklist"] = []
    else:
        cleaned = []
        for entry in result["checklist"]:
            if not isinstance(entry, dict):
                continue
            item = entry.get("item", "")
            if not isinstance(item, str):
                item = ""
            if not item.strip():
                continue
            priority = entry.get("priority", "")
            if priority not in _VALID_PRIORITIES:
                priority = "권장"
            description = entry.get("description", "")
            if not isinstance(description, str):
                description = ""
            cleaned.append({"item": item, "priority": priority, "description": description})
        result["checklist"] = cleaned

    if not isinstance(result.get("verdict_reason"), str):
        result["verdict_reason"] = "판단 근거를 확인할 수 없습니다. 공고 원문을 재확인해 주세요."
    if not isinstance(result.get("summary_line"), str):
        result["summary_line"] = "요약 정보를 확인할 수 없습니다."

    return result


# ── 메인 함수 ────────────────────────────────────────────────────────────────

def analyze_opportunity(opp_info: dict, user_info: dict, api_key: str) -> dict:
    """
    공고 정보와 사용자 정보를 Solar LLM에 전달해 적합도 판단 결과를 반환한다.

    Args:
        opp_info:  extract_info()의 반환값
        user_info: 사용자 정보 딕셔너리
                   예: {"학년": "2학년", "학적": "재학", "목표": ["포트폴리오 강화"], ...}
        api_key:   Upstage API 키

    Returns:
        ANALYSIS_SYSTEM 스키마에 정의된 판단 결과 딕셔너리.
        deadline 정보가 있을 경우 아래 필드가 추가될 수 있다:
          - deadline_warning (str): "마감 임박" | "마감 완료"  (해당하는 경우에만)
    """
    url = "https://api.upstage.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if not isinstance(opp_info, dict):
        opp_info = {}
    if not isinstance(user_info, dict):
        user_info = {}

    user_content = (
        f"[공고 정보]\n{json.dumps(opp_info, ensure_ascii=False, indent=2)}\n\n"
        f"[사용자 정보]\n{json.dumps(user_info, ensure_ascii=False, indent=2)}"
    )

    # 항목5: response_format으로 구조화 출력 강제 (기존 후처리는 보조 안전장치로 유지)
    payload = {
        "model": "solar-pro3",
        "temperature": 0.3,
        "max_tokens": 1500,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "opportunity_analysis",
                "strict": True,
                "schema": _ANALYSIS_SCHEMA,
            },
        },
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]
    try:
        result = json.loads(raw)
        result = _normalize_result(result)
    except (json.JSONDecodeError, KeyError):
        result = {
            "verdict": "조건 확인 필요",
            "verdict_reason": "분석 결과 파싱에 실패했습니다. 공고 원문을 재확인하거나 다시 시도해 주세요.",
            "summary_line": "결과를 불러올 수 없습니다.",
            "fit_score": 5,
            "strengths": [],
            "gaps": [],
            "checklist": [],
            "tips": [],
        }

    # 항목 2·3: deadline 플래그를 기존 결과에 덧붙임
    flags = _deadline_flags(opp_info.get("deadline"))
    if flags["is_expired"] is True:
        result["deadline_warning"] = "마감 완료"
    elif flags["is_urgent"] is True:
        result["deadline_warning"] = "마감 임박"
    # 해당 없으면 필드 미추가 (기존 구조 그대로)

    return result
