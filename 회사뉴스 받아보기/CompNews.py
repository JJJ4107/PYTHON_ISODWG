import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
import smtplib
from datetime import datetime
import time

# [1] 메일플러그 계정 정보
EMAIL_ADDRESS = "JJ@ACEPLANT.CO.KR"
EMAIL_PASSWORD = "#JANG4107"
RECEIVER = "JJ@ACEPLANT.CO.KR"

# [2] 견적회사 리스트 불러오기
def load_company_list(filename="견적회사.TXT"):
    try:
        with open(filename, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("❌ 견적회사.TXT 파일이 없습니다.")
        return []

# [3] 네이버 뉴스 수집 함수
def get_naver_news(company):
    query = "주식회사 " + company
    url = f"https://search.naver.com/search.naver?where=news&query={query}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("div.news_area")[:3]
        result = ""
        for item in items:
            title_tag = item.select_one("a.news_tit")
            if title_tag:
                title = title_tag["title"]
                link = title_tag["href"]
                result += f"- {title}\n  {link}\n"
        return result if result else None  # 뉴스가 없는 경우 None 반환
    except Exception as e:
        return f"- 뉴스 수집 실패: {str(e)}\n"

# [4] 전체 뉴스 수집
def collect_all_news(companies):
    today = datetime.now().strftime("%Y-%m-%d")
    report = f"[{today} 견적회사 뉴스 요약]\n\n"
    count = 0
    for company in companies:
        news = get_naver_news(company)
        if news:
            report += f"📌 {company}\n{news}\n"
            count += 1
        time.sleep(1.0)
    if count == 0:
        report += "※ 관련 뉴스가 발견된 회사가 없습니다.\n"
    return report

# [5] 이메일 전송
def send_email(subject, body, sender, password, receiver):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    try:
        with smtplib.SMTP_SSL("smtp.mailplug.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
        print("✅ 이메일 전송 완료.")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# [6] 메인 실행
if __name__ == "__main__":
    companies = load_company_list()
    if companies:
        news_body = collect_all_news(companies)

        # 결과 콘솔 출력
        print("\n📬 이메일 내용 미리보기:")
        print(news_body)

        send_email(
            subject="[매일뉴스] 견적회사 동향 보고",
            body=news_body,
            sender=EMAIL_ADDRESS,
            password=EMAIL_PASSWORD,
            receiver=RECEIVER
        )

