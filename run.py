import logging
import json
import sys
import os

from friend_circle_lite.get_info import (
    fetch_and_process_data,
    marge_data_from_json_url,
    marge_errors_from_json_url,
    deal_with_large_data
)
from friend_circle_lite.get_conf import load_config
from rss_subscribe.push_article_update import (
    get_latest_articles_from_link,
    extract_emails_from_issues
)
from push_rss_update.send_email import send_emails

# ========== Cài đặt logging ==========
logging.basicConfig(
    level=logging.INFO,
    format='😋 %(levelname)s: %(message)s'
)

# ========== Tải cấu hình ==========
config = load_config("./conf.yaml")

# ========== Module crawler ==========
if config["spider_settings"]["enable"]:
    logging.info("✅ Crawler đã được kích hoạt")

    json_url = config['spider_settings']['json_url']
    article_count = config['spider_settings']['article_count']
    specific_rss = config['specific_RSS']

    logging.info(f"📥 Đang lấy dữ liệu từ {json_url}, mỗi blog lấy {article_count} bài viết")
    result, lost_friends = fetch_and_process_data(
        json_url=json_url,
        specific_RSS=specific_rss,
        count=article_count
    ) # type: ignore

    if config["spider_settings"]["merge_result"]["enable"]:
        merge_url = config['spider_settings']["merge_result"]['merge_json_url']
        logging.info(f"🔀 Tính năng merge đã bật, lấy dữ liệu từ {merge_url}")

        result = marge_data_from_json_url(result, f"{merge_url}/all.json")
        lost_friends = marge_errors_from_json_url(lost_friends, f"{merge_url}/errors.json")

    article_count = len(result.get("article_data", []))
    logging.info(f"📦 Đã lấy xong dữ liệu, có {article_count} bạn bè có hoạt động, đang xử lý dữ liệu")

    result = deal_with_large_data(result)

    with open("all.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(lost_friends, f, ensure_ascii=False, indent=2)

# ========== Chuẩn bị gửi email ==========
SMTP_isReady = False

sender_email = ""
server = ""
port = 0
use_tls = False
password = ""

if config["email_push"]["enable"] or config["rss_subscribe"]["enable"]:
    logging.info("📨 Tính năng push đã được kích hoạt, đang chuẩn bị...")

    smtp_conf = config["smtp"]
    sender_email = smtp_conf["email"]
    server = smtp_conf["server"]
    port = smtp_conf["port"]
    use_tls = smtp_conf["use_tls"]
    password = os.getenv("SMTP_PWD")

    logging.info(f"📡 SMTP server: {server}:{port}")
    if not password or not sender_email or not server or not port:
        logging.error("❌ Biến môi trường SMTP_PWD chưa được thiết lập, không thể gửi email")
    else:
        logging.info(f"🔐 Mật khẩu(phần): {password[:3]}*****")
        SMTP_isReady = True

# ========== Gửi email (chưa triển khai) ==========
if config["email_push"]["enable"] and SMTP_isReady:
    logging.info("📧 Gửi email đã được kích hoạt")
    logging.info("⚠️ Xin lỗi, tính năng gửi email hiện chưa được triển khai")

# ========== Push RSS subscription ==========
if config["rss_subscribe"]["enable"] and SMTP_isReady:
    logging.info("📰 Push RSS subscription đã được kích hoạt")

    # Lấy thông tin GitHub repository
    fcl_repo = os.getenv('FCL_REPO') # Repository built-in
    if fcl_repo:
        github_username, github_repo = fcl_repo.split('/')
    else:
        github_username = str(config["rss_subscribe"]["github_username"]).strip()
        github_repo = str(config["rss_subscribe"]["github_repo"]).strip()

    logging.info(f"👤 GitHub username: {github_username}")
    logging.info(f"📁 GitHub repository: {github_repo}")

    your_blog_url = config["rss_subscribe"]["your_blog_url"]
    email_template = config["rss_subscribe"]["email_template"]
    website_title = config["rss_subscribe"]["website_info"]["title"]

    latest_articles = get_latest_articles_from_link(
        url=your_blog_url,
        count=5,
        last_articles_path="./rss_subscribe/last_articles.json" # Lưu bài viết lần trước
    )

    if not latest_articles:
        logging.info("📭 Không có bài viết mới, không cần push")
    else:
        logging.info(f"🆕 Bài viết mới nhất nhận được: {latest_articles}")

        github_api_url = (
            f"https://api.github.com/repos/{github_username}/{github_repo}/issues"
            f"?state=closed&label=subscribed&per_page=200"
        )
        logging.info(f"🔎 Đang lấy email subscription từ GitHub: {github_api_url}")
        email_list = extract_emails_from_issues(github_api_url)

        if not email_list:
            logging.info("⚠️ Không có email subscription, vui lòng kiểm tra định dạng hoặc có người subscribe không")
            sys.exit(0)

        logging.info(f"📬 Nhận được danh sách email: {email_list}")

        for article in latest_articles:
            template_data = {
                "title": article["title"],
                "summary": article["summary"],
                "published": article["published"],
                "link": article["link"],
                "website_title": website_title,
                "github_issue_url": (
                    f"https://github.com/{github_username}/{github_repo}"
                    "/issues?q=is%3Aissue+is%3Aclosed"
                ),
            }

            send_emails(
                emails=email_list["emails"],
                sender_email=sender_email,
                smtp_server=server,
                port=port,
                password=password,
                subject=f"{website_title} のBài viết mới nhất: {article['title']}",
                body=(
                    f"📄 Tiêu đề bài viết: {article['title']}\n"
                    f"🔗 Liên kết: {article['link']}\n"
                    f"📝 Giới thiệu: {article['summary']}\n"
                    f"🕒 Thời gian xuất bản: {article['published']}"
                ),
                template_path=email_template,
                template_data=template_data,
                use_tls=use_tls
            )
