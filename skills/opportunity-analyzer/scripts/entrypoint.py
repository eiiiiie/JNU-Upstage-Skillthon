"""
entrypoint.py

사용자 정보 수집 및 분석 흐름의 진입점 역할을 하는 얇은 레이어.
- 이미 있는 사용자 정보는 다시 묻지 않는다.
- 필수 정보가 비어 있으면 보완 가능하다.
- 정보가 일부 부족해도 전체 분석은 진행된다.

핵심 분석 함수(analyze_opportunity, rank_opportunities)는 그대로 유지된다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_env() -> None:
    """
    스크립트와 같은 디렉터리(또는 상위 디렉터리)의 .env 파일을 읽어
    환경변수로 등록한다. 이미 설정된 값은 덮어쓰지 않는다.
    """
    script_dir = Path(__file__).resolve().parent
    for candidate in (script_dir / ".env", script_dir.parent / ".env"):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
            break


_load_env()

from parse_document import parse_documents
from extract_info import extract_info, check_is_opportunity, check_document_quality
from analyze_opportunity import analyze_opportunity
from rank_opportunities import rank_opportunities

# 필수 항목과 질문 문구 정의
_REQUIRED_FIELDS: list[tuple[str, str]] = [
    ("학년",  "학년을 입력하세요 (예: 1학년, 2학년): "),
    ("학적",  "학적 상태를 입력하세요 (재학/휴학/졸업예정): "),
    ("목표",  "활동 목표를 입력하세요 (예: 포트폴리오 강화, 스펙, 네트워크 등, 쉼표 구분): "),
]


def collect_user_info(user_info: dict | None = None) -> dict:
    """
    사용자 정보 딕셔너리를 받아 필수 항목이 비어 있으면 CLI로 보완한다.
    이미 채워진 항목은 묻지 않는다.
    정보가 일부 부족해도 분석은 진행할 수 있도록 빈 문자열을 허용한다.

    Args:
        user_info: 기존에 수집된 사용자 정보 딕셔너리 (없으면 빈 딕셔너리로 시작)

    Returns:
        보완된 사용자 정보 딕셔너리
    """
    if user_info is None:
        user_info = {}

    for key, prompt in _REQUIRED_FIELDS:
        existing = user_info.get(key)
        if existing is not None and str(existing).strip():
            continue

        try:
            value = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            value = ""

        if not value:
            print(f"  ※ '{key}' 정보가 없어도 분석은 진행됩니다.")
            continue

        if key == "목표":
            user_info[key] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            user_info[key] = value

    return user_info


def format_result_as_markdown(
    opp_info: dict,
    analysis: dict,
    warnings: list[str] | None = None,
) -> str:
    """
    단일 공고의 추출 결과(opp_info)와 분석 결과(analysis)를
    skill.md §5-1 템플릿에 따라 Markdown 문자열로 조합한다.

    Args:
        opp_info:  extract_info() 반환값
        analysis:  analyze_opportunity() 반환값
        warnings:  표시할 경고 문자열 목록 (공고 형식 아님, 문서 품질 등)

    Returns:
        Markdown 형식의 분석 결과 문자열
    """
    lines: list[str] = []

    # 마감 임박/완료 긴급 안내 (결과 상단)
    deadline_warning = analysis.get("deadline_warning")
    if deadline_warning == "마감 임박":
        lines.append(
            "🚨 **긴급 안내: 마감이 24시간 이내로 임박했습니다."
            " 즉시 준비 가능한 항목을 먼저 확인하세요.**\n"
        )
    elif deadline_warning == "마감 완료":
        lines.append(
            "⚠️ **참고용 분석: 마감이 이미 지난 공고입니다."
            " 아래 분석은 참고용으로만 활용하세요.**\n"
        )

    # 외부에서 전달된 경고 (공고 형식 아님, 문서 품질 낮음 등)
    if warnings:
        for w in warnings:
            lines.append(f"{w}\n")

    # 제목
    title = opp_info.get("title") or "공고"
    lines.append(f"### {title} 분석 결과\n")

    # 기본 정보 표
    lines.append("#### 기본 정보\n")
    lines.append("| 항목 | 내용 |")
    lines.append("|---|---|")
    lines.append(f"| 카테고리 | {opp_info.get('category') or '명시되지 않음'} |")
    lines.append(f"| 주최 | {opp_info.get('host') or '명시되지 않음'} |")
    lines.append(f"| 마감일 | {opp_info.get('deadline') or '명시되지 않음'} |")
    lines.append(f"| 활동 기간 | {opp_info.get('period') or '명시되지 않음'} |")
    lines.append("")

    # 적합도 요약 표
    lines.append("#### 적합도 요약\n")
    lines.append("| 항목 | 내용 |")
    lines.append("|---|---|")
    lines.append(f"| 지원 판단 | {analysis.get('verdict', '')} |")
    lines.append(f"| 목표 부합도 | {analysis.get('fit_score', '')}/10 |")
    lines.append(f"| 한줄 요약 | {analysis.get('summary_line', '')} |")
    lines.append("")

    # 판단 근거
    verdict_reason = analysis.get("verdict_reason", "")
    if verdict_reason:
        lines.append("#### 판단 근거\n")
        reason_lines = [ln.strip() for ln in verdict_reason.splitlines() if ln.strip()]
        if len(reason_lines) > 1:
            for rl in reason_lines:
                lines.append(f"- {rl}")
        else:
            lines.append(f"- {verdict_reason}")
        lines.append("")

    # 강점 및 보완점 표
    strengths = analysis.get("strengths", [])
    gaps = analysis.get("gaps", [])
    if strengths or gaps:
        lines.append("#### 강점 및 보완점\n")
        lines.append("| 구분 | 내용 |")
        lines.append("|---|---|")
        strengths_str = " / ".join(strengths) if strengths else "해당 사항 없음"
        gaps_str = " / ".join(gaps) if gaps else "해당 사항 없음"
        lines.append(f"| 유리한 점 | {strengths_str} |")
        lines.append(f"| 부족한 점 | {gaps_str} |")
        lines.append("")

    # 준비 체크리스트 표
    checklist = analysis.get("checklist", [])
    if checklist:
        lines.append("#### 준비 체크리스트\n")
        lines.append("| 우선순위 | 준비 항목 | 설명 |")
        lines.append("|---|---|---|")
        for entry in checklist:
            lines.append(
                f"| {entry.get('priority', '')} "
                f"| {entry.get('item', '')} "
                f"| {entry.get('description', '')} |"
            )
        lines.append("")

    # 공고 특화 조언
    tips = analysis.get("tips", [])
    if tips:
        lines.append("#### 공고 특화 조언(tips)\n")
        for tip in tips:
            lines.append(f"- {tip}")
        lines.append("")

    return "\n".join(lines)


def format_ranking_as_markdown(ranking: dict) -> str:
    """
    rank_opportunities() 반환값을 skill.md §5-1의 우선순위 요약 표 형식으로
    Markdown 문자열로 변환한다.

    Args:
        ranking: rank_opportunities() 반환값

    Returns:
        Markdown 형식의 우선순위 요약 문자열.
        ranked가 없거나 단일 공고이면 빈 문자열 반환.
    """
    ranked = ranking.get("ranked", [])
    if len(ranked) < 2:
        return ""

    lines: list[str] = []
    lines.append("### 우선순위 요약\n")
    lines.append("| 순위 | 공고명 | 지원 판단 | 목표 부합도 | 한줄 요약 |")
    lines.append("|---|---|---|---|---|")

    for entry in ranked:
        rank = entry.get("rank", "")
        label = entry.get("label", "")
        verdict = entry.get("verdict", "")
        fit = entry.get("fit_score", "")
        summary = entry.get("summary_line", "")
        dw = entry.get("deadline_warning")
        if dw == "마감 완료":
            label = f"{label} ⚠️마감완료"
        elif dw == "마감 임박":
            label = f"{label} 🚨마감임박"
        lines.append(f"| {rank} | {label} | {verdict} | {fit}/10 | {summary} |")

    lines.append("")

    comparison = ranking.get("comparison")
    if comparison:
        lines.append(f"> {comparison}")
        lines.append("")

    return "\n".join(lines)


def run_analysis(
    opp_infos: list[dict],
    user_info: dict,
    api_key: str,
    labels: list[str] | None = None,
) -> dict:
    """
    공고 분석 전체 흐름을 실행하는 진입점.
    단일 공고는 기존 analyze_opportunity 결과를 그대로 반환한다.
    복수 공고는 rank_opportunities 결과를 추가로 반환한다.

    Args:
        opp_infos: extract_info() 반환값의 리스트
        user_info: collect_user_info()로 보완된 사용자 정보
        api_key:   Upstage API 키
        labels:    각 공고 레이블 (없으면 자동 부여)

    Returns:
        {
          "analyses": [분석결과, ...],
          "ranking":  rank_opportunities 결과  # 복수 공고일 때만 포함
        }
    """
    analyses = []
    for opp_info in opp_infos:
        result = analyze_opportunity(opp_info, user_info, api_key)
        analyses.append(result)

    output: dict = {"analyses": analyses}

    if len(analyses) > 1:
        output["ranking"] = rank_opportunities(analyses, labels=labels)

    return output


def run_pipeline(
    file_paths: list[str],
    api_key: str,
    user_info: dict | None = None,
) -> str:
    """
    파일 경로 목록을 받아 parse → extract → analyze → rank → Markdown 출력까지
    전체 흐름을 실행하고 결과 문자열을 반환한다.

    Args:
        file_paths: 공고 파일 경로 리스트 (PDF 또는 이미지)
        api_key:    Upstage API 키
        user_info:  사용자 정보 딕셔너리 (None이면 CLI로 수집)

    Returns:
        Markdown 형식의 분석 결과 문자열
    """
    # Step 1. 사용자 정보 수집 (이미 있는 항목은 묻지 않음)
    user_info = collect_user_info(user_info)

    # Step 2. parse: 파일 → 마크다운 텍스트
    parsed_map = parse_documents(file_paths, api_key)
    if not parsed_map:
        return "⚠️ 파싱 가능한 문서가 없습니다. 입력 파일 경로와 형식을 확인해 주세요."

    # Step 3. extract + 공고 여부 확인 + 문서 품질 확인
    opp_infos: list[dict] = []
    labels: list[str] = []
    all_warnings: dict[str, list[str]] = {}

    for path, markdown_text in parsed_map.items():
        label = os.path.basename(path)
        opp_info = extract_info(markdown_text, api_key)

        # 공고 문서 여부 판단
        is_opp, opp_warning = check_is_opportunity(opp_info)
        if not is_opp:
            print(f"[{label}] {opp_warning} — 건너뜀")
            continue

        # 문서 품질 판단
        warnings: list[str] = []
        is_low, quality_warning = check_document_quality(opp_info)
        if is_low and quality_warning:
            warnings.append(quality_warning)

        opp_infos.append(opp_info)
        labels.append(label)
        all_warnings[label] = warnings

    if not opp_infos:
        return "⚠️ 분석 가능한 공고 문서가 없습니다. 공고 PDF 또는 이미지를 다시 확인해 주세요."

    # Step 4. analyze + rank
    result = run_analysis(opp_infos, user_info, api_key, labels=labels)
    analyses = result["analyses"]

    # Step 5. format output
    output_parts: list[str] = []

    for i, (opp_info, analysis) in enumerate(zip(opp_infos, analyses)):
        label = labels[i]
        warnings = all_warnings.get(label, [])
        md = format_result_as_markdown(opp_info, analysis, warnings=warnings)
        output_parts.append(md)

    if "ranking" in result:
        ranking_md = format_ranking_as_markdown(result["ranking"])
        if ranking_md:
            output_parts.append(ranking_md)

    return "\n---\n".join(output_parts)


def main() -> None:
    """
    CLI 진입점.
    사용법: python entrypoint.py <파일경로1> [파일경로2 ...] [--api-key <KEY>]
    API 키는 --api-key 옵션 또는 UPSTAGE_API_KEY 환경변수로도 설정 가능하다.
    """
    args = sys.argv[1:]

    api_key = os.environ.get("UPSTAGE_API_KEY", "")
    file_paths: list[str] = []

    i = 0
    while i < len(args):
        if args[i] in ("--api-key", "-k") and i + 1 < len(args):
            api_key = args[i + 1]
            i += 2
        else:
            file_paths.append(args[i])
            i += 1

    if not api_key:
        print(
            "❌ API 키가 없습니다. --api-key 옵션 또는"
            " UPSTAGE_API_KEY 환경변수로 설정하세요."
        )
        sys.exit(1)

    if not file_paths:
        print("❌ 분석할 파일 경로를 하나 이상 입력하세요.")
        print("사용법: python entrypoint.py <파일1> [파일2 ...] --api-key <KEY>")
        sys.exit(1)

    # 파일 존재 여부 사전 확인
    missing = [p for p in file_paths if not os.path.isfile(p)]
    if missing:
        for m in missing:
            print(f"❌ 파일을 찾을 수 없습니다: {m}")
        sys.exit(1)

    output = run_pipeline(file_paths, api_key)
    print(output)


if __name__ == "__main__":
    main()