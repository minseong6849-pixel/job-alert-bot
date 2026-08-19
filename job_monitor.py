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
import time
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
    """신한투자증권 채용공고 목록 (정적 HTML -> requests로 충분)"""
    url = "https://recruit.shinhansec.com/recruit/list.do"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    jobs = []
    for a in soup.select("a"):
        text = a.get_text(strip=True)
        if not text:
            continue
        if ("D-" in text or "마감" in text) and ("경력" in text or "신입" in text or "인턴" in text or "기타" in text):
            jobs.append({"title": text, "url": url})

    return jobs


def fetch_hantu_securities():
    """한국투자증권 채용공고 목록 (Vue.js 렌더링 -> Selenium으로 브라우저 렌더링 후 파싱)"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By

    url = "https://recruit.truefriend.com/announcementList"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")

    driver = webdriver.Chrome(options=options)
    jobs = []
    try:
        driver.get(url)
        # Vue가 데이터를 채울 시간을 줌
        time.sleep(3)

        # 공고 카드/행 요소를 찾음 (사이트 구조가 바뀌면 이 선택자도 바뀔 수 있음)
        elements = driver.find_elements(By.CSS_SELECTOR, "li, tr, .anno-item, [class*='anno']")
        for el in elements:
            text = el.text.strip()
            if not text:
                continue
            # 채용공고 항목으로 보이는 텍스트만 필터링 (마감일/D-day 패턴 포함)
            if ("D-" in text or "마감" in text) and len(text) < 200:
                # 같은 텍스트가 여러 컨테이너에서 중복으로 잡히는 걸 방지
                if not any(text in j["title"] or j["title"] in text for j in jobs):
                    jobs.append({"title": text.replace("\n", " "), "url": url})
    finally:
        driver.quit()

    return jobs


# 미래에셋증권은 robots.txt로 자동 접근을 차단하고 있어 크롤링 대상에서 제외함


COMPANIES = {
    "신한투자증권": fetch_shinhan_securities,
    "한국투자증권": fetch_hantu_securities,
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
