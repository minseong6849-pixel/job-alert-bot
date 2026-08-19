"""
증권사 채용공고 모니터링 -> 텔레그램 알림 봇

동작 방식:
1. 등록된 회사의 채용 페이지를 크롤링해서 현재 공고 목록(제목)을 가져옴
2. 이전 실행 때 저장해둔 목록(seen_jobs.json)과 비교
3. 새로 생긴 공고가 있으면 텔레그램으로 알림 전송
4. 최신 목록을 다시 저장

사용법:
    export TELEGRAM_BOT_TOKEN="8870881294:AAHdPxs5mqeidFi-7npx0REPgfSu0VVaFnE"
    export TELEGRAM_CHAT_ID="7840587132"
    python job_monitor.py
"""

import json
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

SEEN_JOBS_FILE = Path(__file__).parent / "seen_jobs.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# 회사별 크롤러
# 각 함수는 {"title": 공고제목, "url": 상세링크} 딕셔너리의 리스트를 반환해야 함
# ---------------------------------------------------------------------------

def fetch_shinhan_securities():
    """신한투자증권 채용공고 목록"""
    url = "https://recruit.shinhansec.com/recruit/list.do"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    jobs = []
    # 채용공고 목록은 <a> 태그들로 구성되어 있고, 텍스트 안에 마감일(D-N 또는 "마감")이 포함됨
    for a in soup.select("a"):
        text = a.get_text(strip=True)
        if not text:
            continue
        # 채용공고 항목만 필터링: 마감일 표시가 포함된 것들
        if ("D-" in text or "마감" in text) and ("경력" in text or "신입" in text or "인턴" in text or "기타" in text):
            jobs.append({"title": text, "url": url})

    return jobs


# 여기에 다른 회사 크롤러를 추가할 수 있음
# 예: fetch_hantu_securities(), fetch_mirae_asset() 등
# 한국투자증권(recruit.truefriend.com)은 Vue.js로 렌더링되어
# requests만으로는 목록을 가져올 수 없음 -> Selenium/Playwright 필요
# 미래에셋증권은 채용 사이트가 robots.txt로 자동 접근을 차단하고 있어 제외함


COMPANIES = {
    "신한투자증권": fetch_shinhan_securities,
}


# ---------------------------------------------------------------------------
# 저장된 공고 목록 관리
# ---------------------------------------------------------------------------

def load_seen_jobs():
    if SEEN_JOBS_FILE.exists():
        with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen_jobs(data):
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 텔레그램 알림
# ---------------------------------------------------------------------------

def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[경고] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        print(text)
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        api_url,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": False},
        timeout=10,
    )
    if not resp.ok:
        print(f"[에러] 텔레그램 전송 실패: {resp.status_code} {resp.text}")


# ---------------------------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------------------------

def main():
    seen = load_seen_jobs()
    any_new = False

    for company, fetch_fn in COMPANIES.items():
        try:
            current_jobs = fetch_fn()
        except Exception as e:
            print(f"[에러] {company} 크롤링 실패: {e}")
            continue

        prev_titles = set(seen.get(company, []))
        current_titles = {job["title"] for job in current_jobs}
        new_titles = current_titles - prev_titles

        if new_titles:
            any_new = True
            for job in current_jobs:
                if job["title"] in new_titles:
                    message = f"🔔 [{company}] 새 채용공고\n\n{job['title']}\n\n{job['url']}"
                    send_telegram_message(message)
                    print(f"알림 전송: {job['title']}")

        seen[company] = list(current_titles)

    if not any_new:
        print("새로운 공고 없음.")

    save_seen_jobs(seen)


if __name__ == "__main__":
    main()
