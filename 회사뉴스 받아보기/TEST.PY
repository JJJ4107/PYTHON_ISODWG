import requests

company = "두산에너빌러티"
query = "주식회사 " + company + " 뉴스"
url = f"https://www.google.com/search?q={query}&tbm=nws"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

res = requests.get(url, headers=headers, timeout=5)

# HTML 파일로 저장
with open("google_news_result.html", "w", encoding="utf-8") as f:
    f.write(res.text)

print("✅ 구글 뉴스 결과가 google_news_result.html 파일로 저장되었습니다.")
