"""
parse_document.py

Upstage Document Parse API를 호출해 공고 파일을 마크다운 텍스트로 변환한다.
지원 형식: PDF, 이미지(PNG/JPG), 스캔 문서
"""

import time
import requests


def parse_document(file_path: str, api_key: str) -> str:
    """
    공고 파일을 Document Parse API로 읽어 마크다운 텍스트를 반환한다.

    Args:
        file_path: 로컬 파일 경로 (PDF 또는 이미지)
        api_key:   Upstage API 키

    Returns:
        마크다운 형식의 문서 텍스트

    Raises:
        ValueError: 파싱 결과가 비어 있을 때
        requests.HTTPError: API 오류 응답 시
    """
    url = "https://api.upstage.ai/v1/document-digitization"
    headers = {"Authorization": f"Bearer {api_key}"}

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        with open(file_path, "rb") as f:
            response = requests.post(
                url,
                headers=headers,
                files={"document": f},
                data={
                    "model": "document-parse",
                    "ocr": "auto",
                    "output_formats": '["markdown"]',
                },
            )

        if response.status_code == 429:
            if attempt < max_retries:
                time.sleep(1)
                continue
            response.raise_for_status()

        response.raise_for_status()
        break

    markdown = response.json().get("content", {}).get("markdown", "")
    if not markdown.strip():
        raise ValueError(f"공고 내용을 인식하지 못했습니다: {file_path}")

    return markdown


def parse_documents(file_paths: list[str], api_key: str) -> dict[str, str]:
    """
    복수 파일을 순차 처리해 {파일명: 마크다운} 딕셔너리를 반환한다.
    파싱에 실패한 파일은 건너뛰고 오류를 출력한다.
    """
    results = {}
    total = len(file_paths)

    for i, path in enumerate(file_paths, start=1):
        print(f"파싱 중 ({i}/{total}): {path}")
        try:
            results[path] = parse_document(path, api_key)
        except (ValueError, requests.HTTPError) as e:
            print(f"  ⚠️ 건너뜀 — {e}")

    return results
