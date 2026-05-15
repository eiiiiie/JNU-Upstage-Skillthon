"""
rank_opportunities.py

복수 공고 분석 결과를 받아 우선순위를 정렬하고 비교 요약을 반환한다.
단일 공고 처리 흐름(analyze_opportunity)은 변경하지 않는다.
"""

from __future__ import annotations

# verdict 우선순위 점수 (높을수록 우선)
_VERDICT_SCORE = {
    "바로 지원 가능": 3,
    "준비 후 지원":   2,
    "조건 확인 필요": 1,
    "비추천":         0,
}

# gaps 수가 적을수록 준비 부담이 낮음 → 점수 높게
def _prep_burden_score(result: dict) -> float:
    """gaps 수 기반 준비 부담 역점수 (낮을수록 좋음 → 역수로 변환)."""
    gaps = result.get("gaps", [])
    count = len(gaps) if isinstance(gaps, list) else 0
    return 1.0 / (1.0 + count)


# deadline_warning이 없으면 일정 적합 → 가산점 없음(0)
# "마감 임박"이면 소폭 감점, "마감 완료"이면 큰 감점
def _schedule_penalty(result: dict) -> float:
    warning = result.get("deadline_warning")
    if warning == "마감 완료":
        return -2.0
    if warning == "마감 임박":
        return -0.5
    return 0.0


def _composite_score(result: dict) -> float:
    """
    기존 분석 결과 필드만 사용해 복합 점수를 산출한다.
    구성: fit_score(정규화) + verdict 점수 + 준비 부담 역점수 + 일정 패널티
    """
    fit = result.get("fit_score", 5)
    if not isinstance(fit, (int, float)):
        fit = 5
    fit_norm = fit / 10.0  # 0~1로 정규화

    verdict_s = _VERDICT_SCORE.get(result.get("verdict", ""), 0) / 3.0  # 0~1

    burden   = _prep_burden_score(result)   # 0~1
    penalty  = _schedule_penalty(result)    # 음수 또는 0

    # 가중치: fit_score 중심, verdict 보조, 준비 부담 소폭 반영
    return fit_norm * 0.6 + verdict_s * 0.3 + burden * 0.1 + penalty


def rank_opportunities(
    analyses: list[dict],
    labels: list[str] | None = None,
) -> dict:
    """
    복수 공고 분석 결과를 우선순위 순으로 정렬해 비교 요약을 반환한다.
    단일 공고(len==1)도 입력 가능하지만, 추가 요약은 붙지 않는다.

    Args:
        analyses: analyze_opportunity() 반환값의 리스트
        labels:   각 공고를 구분하는 레이블 리스트 (없으면 "공고1", "공고2" … 자동 부여)

    Returns:
        {
          "ranked": [
            {
              "rank":          int,          # 1위부터 시작
              "label":         str,          # 공고 식별 레이블
              "verdict":       str,
              "fit_score":     int,
              "summary_line":  str,
              "deadline_warning": str | None,  # 없으면 키 자체 미포함
              "composite_score": float,      # 내부 정렬 점수 (참고용)
            },
            ...
          ],
          "top_pick":    str,   # 1순위 레이블
          "comparison":  str,   # 한 줄 비교 요약
        }
        단일 공고인 경우 "ranked" 리스트만 반환하고 "top_pick"/"comparison" 생략.
    """
    if not analyses:
        return {"ranked": []}

    # 레이블 보정
    if labels is None or len(labels) != len(analyses):
        labels = [f"공고{i + 1}" for i in range(len(analyses))]

    # 점수 계산 후 정렬 (내림차순)
    scored = []
    for label, result in zip(labels, analyses):
        scored.append({
            "label":   label,
            "result":  result,
            "score":   _composite_score(result),
        })
    scored.sort(key=lambda x: x["score"], reverse=True)

    # ranked 리스트 구성
    ranked = []
    for rank, item in enumerate(scored, start=1):
        r = item["result"]
        entry = {
            "rank":           rank,
            "label":          item["label"],
            "verdict":        r.get("verdict", ""),
            "fit_score":      r.get("fit_score", 5),
            "summary_line":   r.get("summary_line", ""),
            "composite_score": round(item["score"], 4),
        }
        if "deadline_warning" in r:
            entry["deadline_warning"] = r["deadline_warning"]
        ranked.append(entry)

    # 단일 공고는 추가 요약 없이 반환
    if len(ranked) == 1:
        return {"ranked": ranked}

    # 복수 공고: top_pick + 한 줄 비교 요약 추가
    top = ranked[0]
    top_pick = top["label"]

    # 비교 요약: 상위 2개까지 대비 서술
    second = ranked[1] if len(ranked) > 1 else None
    if second:
        comparison = (
            f"{top_pick}(fit {top['fit_score']}, {top['verdict']})이 "
            f"{second['label']}(fit {second['fit_score']}, {second['verdict']})보다 "
            f"우선 추천됩니다."
        )
    else:
        comparison = f"{top_pick}이 가장 높은 적합도를 보입니다."

    return {
        "ranked":     ranked,
        "top_pick":   top_pick,
        "comparison": comparison,
    }
