import logging
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urljoin, urlparse
from dateutil import parser
from zoneinfo import ZoneInfo
import requests
import feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed

# Tiêu đề request chuẩn hóa
HEADERS_JSON = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 "
        "(Friend-Circle-Lite/1.0; +https://github.com/willow-god/Friend-Circle-Lite)"
    ),
    "X-Friend-Circle": "1.0"
}

HEADERS_XML = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 "
        "(Friend-Circle-Lite/1.0; +https://github.com/willow-god/Friend-Circle-Lite)"
    ),
    "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "X-Friend-Circle": "1.0"
}

timeout = (10, 15) # Thời gian chờ kết nối và đọc, ngăn requests nhận quá lâu

def format_published_time(time_str):
    """
    Định dạng thời gian xuất bản thành định dạng thống nhất YYYY-MM-DD HH:MM

    Tham số:
    time_str (str): Chuỗi thời gian đầu vào, có thể là nhiều định dạng.

    Trả về:
    str: Chuỗi thời gian đã định dạng, trả về chuỗi rỗng nếu phân tích thất bại.
    """
    # Thử phân tích tự động chuỗi thời gian đầu vào
    try:
        parsed_time = parser.parse(time_str, fuzzy=True)
    except (ValueError, parser.ParserError):
        # Định nghĩa các định dạng thời gian được hỗ trợ
        time_formats = [
            '%a, %d %b %Y %H:%M:%S %z',  # Mon, 11 Mar 2024 14:08:32 +0000
            '%a, %d %b %Y %H:%M:%S GMT',   # Wed, 19 Jun 2024 09:43:53 GMT
            '%Y-%m-%dT%H:%M:%S%z',         # 2024-03-11T14:08:32+00:00
            '%Y-%m-%dT%H:%M:%SZ',          # 2024-03-11T14:08:32Z
            '%Y-%m-%d %H:%M:%S',           # 2024-03-11 14:08:32
            '%Y-%m-%d'                     # 2024-03-11
        ]
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(time_str, fmt)
                break
            except ValueError:
                continue
        else:
            logging.warning(f"Không thể phân tích chuỗi thời gian: {time_str}")
            return ''

    # Xử lý chuyển đổi múi giờ
    if parsed_time.tzinfo is None:
        parsed_time = parsed_time.replace(tzinfo=timezone.utc)
    shanghai_time = parsed_time.astimezone(timezone(timedelta(hours=8)))
    return shanghai_time.strftime('%Y-%m-%d %H:%M')



def check_feed(friend, session):
    """
    Kiểm tra liên kết RSS hoặc Atom subscription của blog.

    Hàm này nhận một blog, thử nối '/atom.xml', '/rss2.xml' và '/feed' sau khi trích xuất, 
    và kiểm tra xem các liên kết này có thể truy cập được không.
    Ưu tiên Atom, nếu không thể truy cập được, trả về ['none', địa chỉ nguồn].

    Tham số:
    friend (dict): Từ điển chứa thông tin bạn bè.
    session (requests.Session): Đối tượng session dùng cho request.

    Trả về:
    list: Danh sách chứa loại và liên kết đã nối. Nếu liên kết atom có thể truy cập, trả về ['atom', atom_url];
            Nếu liên kết rss2 có thể truy cập, trả về ['rss2', rss_url];
            Nếu liên kết feed có thể truy cập, trả về ['feed', feed_url];
            Nếu không thể truy cập, trả về ['none', blog_url].
    """
    blog_url = friend.get("link", "")
    rsslink = friend.get("rss", "")
    
    possible_feeds = [
        ('atom', '/atom.xml'),
        ('rss', '/rss.xml'), # 2024-07-26 Thêm hỗ trợ nội dung /rss.xml
        ('rss2', '/rss2.xml'),
        ('rss3', '/rss.php'), # 2024-12-07 Thêm hỗ trợ nội dung /rss.php
        ('feed', '/feed'),
        ('feed2', '/feed.xml'), # 2024-07-26 Thêm hỗ trợ nội dung /feed.xml
        ('feed3', '/feed/'),
        ('index', '/index.xml') # 2024-07-25 Thêm hỗ trợ nội dung /index.xml
    ]

    for feed_type, path in possible_feeds:
        feed_url = rsslink if rsslink else blog_url + path
        try:
            response = session.get(feed_url, headers=HEADERS_XML, timeout=timeout)
            if response.status_code == 200:
                return [feed_url.split('/')[-1].split('.')[0], feed_url]
        except requests.RequestException:
            continue
    logging.warning(f"Không thể tìm thấy liên kết subscription: {friend}")
    return ['none', friend.get("link", "")]

def parse_feed(url, session, count=5, blog_url=''):
    """
    Phân tích feed Atom hoặc RSS2 và trả về từ điển chứa tên website, tác giả, liên kết gốc và nội dung chi tiết của mỗi bài viết.

    Hàm này nhận một địa chỉ feed (atom.xml hoặc rss2.xml), phân tích dữ liệu trong đó và trả về một cấu trúc từ điển,
    bao gồm tên website, tác giả, liên kết gốc và nội dung chi tiết của mỗi bài viết.

    Tham số:
    url (str): URL của feed Atom hoặc RSS2.
    session (requests.Session): Đối tượng session dùng cho request.
    count (int): Số bài viết tối đa cần lấy. Nếu nhỏ hơn thì lấy tất cả, nếu số bài viết lớn hơn thì chỉ lấy count bài viết đầu tiên.

    Trả về:
    dict: Từ điển chứa tên website, tác giả, liên kết gốc và nội dung chi tiết của mỗi bài viết.
    """
    try:
        response = session.get(url, headers=HEADERS_XML, timeout=timeout)
        response.encoding = response.apparent_encoding or 'utf-8'
        feed = feedparser.parse(response.text)
        
        result = {
            'website_name': feed.feed.title if 'title' in feed.feed else '', # type: ignore
            'author': feed.feed.author if 'author' in feed.feed else '', # type: ignore
            'link': feed.feed.link if 'link' in feed.feed else '', # type: ignore
            'articles': []
        }
        
        for _ , entry in enumerate(feed.entries):
            
            if 'published' in entry:
                published = format_published_time(entry.published)
            elif 'updated' in entry:
                published = format_published_time(entry.updated)
                # Xuất thông tin cảnh báo
                logging.warning(f"Bài viết {entry.title} không chứa thời gian xuất bản, đã sử dụng thời gian cập nhật {published}")
            else:
                published = ''
                logging.warning(f"Bài viết {entry.title} không chứa bất kỳ thông tin thời gian nào, vui lòng kiểm tra bài gốc, đặt thành thời gian mặc định")
            
            # Xử lý lỗi có thể có trong liên kết, ví dụ như ip hoặc localhost
            article_link = replace_non_domain(entry.link, blog_url) if 'link' in entry else '' # type: ignore
            
            article = {
                'title': entry.title if 'title' in entry else '',
                'author': result['author'],
                'link': article_link,
                'published': published,
                'summary': entry.summary if 'summary' in entry else '',
                'content': entry.content[0].value if 'content' in entry and entry.content else entry.description if 'description' in entry else ''
            }
            result['articles'].append(article)
        
        # Sắp xếp bài viết theo thời gian và chỉ lấy count bài viết đầu tiên
        result['articles'] = sorted(result['articles'], key=lambda x: datetime.strptime(x['published'], '%Y-%m-%d %H:%M'), reverse=True)
        if count < len(result['articles']):
            result['articles'] = result['articles'][:count]
        
        return result
    except Exception as e:
        logging.error(f"Không thể phân tích địa chỉ FEED: {url}, vui lòng tự kiểm tra nguyên nhân!")
        return {
            'website_name': '',
            'author': '',
            'link': '',
            'articles': []
        }

def replace_non_domain(link: str, blog_url: str) -> str:
    """
    Chưa triển khai
    Phát hiện và thay thế phần tên miền không bình thường trong chuỗi (như địa chỉ IP hoặc localhost), thay thế bằng blog_url.
    Sau khi thay thế bắt buộc sử dụng https, và xem xét blog_url có dấu gạch chéo ở cuối không.

    :param link: Chuỗi địa chỉ gốc
    :param blog_url: Địa chỉ blog thay thế
    :return: Chuỗi địa chỉ sau khi thay thế
    """
    
    # Trích xuất phần đường dẫn trong link, không cần giao thức và tên miền
    # path = re.sub(r'^https?://[^/]+', '', link)
    # print(path)
    
    try:
        parsed = urlparse(link)
        if 'localhost' in parsed.netloc or re.match(r'^\d{1,3}(\.\d{1,3}){3}$', parsed.netloc):  # Địa chỉ IP hoặc localhost
            # Trích xuất path + query
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            return urljoin(blog_url.rstrip('/') + '/', path.lstrip('/'))
        else:
            return link  # Tên miền hợp lệ thì trả về liên kết gốc
    except Exception as e:
        logging.warning(f"Lỗi khi thay thế liên kết: {link}, error: {e}")
        return link

def process_friend(friend, session, count, specific_RSS=[]):
    """
    Xử lý thông tin blog của một người bạn.

    Tham số:
    friend (list): Danh sách chứa thông tin bạn bè [name, blog_url, avatar].
    session (requests.Session): Đối tượng session dùng cho request.
    count (int): Số bài viết tối đa cho mỗi blog.
    specific_RSS (list): Danh sách từ điển chứa nguồn RSS cụ thể [{name, url}]

    Trả về:
    dict: Từ điển chứa thông tin blog của bạn bè.
    """
    name = friend.get("name", "")
    blog_url = friend.get("link", "")
    avatar = friend.get("avatar", "")
    
    # Nếu specific_RSS có name tương ứng, trả về trực tiếp feed_url
    if specific_RSS is None:
        specific_RSS = []
    rss_feed = next((rss['url'] for rss in specific_RSS if rss['name'] == name), None)
    if rss_feed:
        feed_url = rss_feed
        feed_type = 'specific'
        logging.info(f"Blog \"{name}\" \" {blog_url} \" là nguồn RSS cụ thể \" {feed_url} \"")
    else:
        feed_type, feed_url = check_feed(friend, session)
        logging.info(f"Loại feed của blog \"{name}\" \" {blog_url} \" là \"{feed_type}\", địa chỉ feed là \" {feed_url} \"")

    if feed_type != 'none':
        feed_info = parse_feed(feed_url, session, count, blog_url)
        articles = [
            {
                'title': article['title'],
                'created': article['published'],
                'link': article['link'],
                'author': name,
                'avatar': avatar
            }
            for article in feed_info['articles']
        ]
        
        for article in articles:
            logging.info(f"{name} đã xuất bản bài viết mới: {article['title']}, thời gian: {article['created']}, liên kết: {article['link']}")
        
        return {
            'name': name,
            'status': 'active',
            'articles': articles
        }
    else:
        logging.warning(f"Blog {blog_url} của {name} không thể truy cập")
        return {
            'name': name,
            'status': 'error',
            'articles': []
        }

def fetch_and_process_data(json_url, specific_RSS=[], count=5):
    """
    Đọc dữ liệu JSON và xử lý thông tin subscription, trả về dữ liệu thống kê và thông tin bài viết.

    Tham số:
    json_url (str): URL của file JSON chứa thông tin bạn bè.
    count (int): Số bài viết tối đa cho mỗi blog.
    specific_RSS (list): Danh sách từ điển chứa nguồn RSS cụ thể [{name, url}]

    Trả về:
    dict: Từ điển chứa dữ liệu thống kê và thông tin bài viết.
    """
    session = requests.Session()
    
    try:
        response = session.get(json_url, headers=HEADERS_JSON, timeout=timeout)
        friends_data = response.json()
    except Exception as e:
        logging.error(f"Không thể lấy liên kết: {json_url} :{e}", exc_info=True)
        return None

    # Chỉ lấy bạn bè từ con có id_name = "cf-links"
    for category in friends_data['friends']:
        if category['id_name'] == "cf-links":
            friends_data = category['link_list']
            break

    total_friends = len(friends_data) # không phải friends_data['friends']
    active_friends = 0
    error_friends = 0
    total_articles = 0
    article_data = []
    error_friends_info = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_friend = {
            executor.submit(process_friend, friend, session, count, specific_RSS): friend
            for friend in friends_data # không phải friends_data['friends']
        }
        
        for future in as_completed(future_to_friend):
            friend = future_to_friend[future]
            try:
                result = future.result()
                if result['status'] == 'active':
                    active_friends += 1
                    article_data.extend(result['articles'])
                    total_articles += len(result['articles'])
                else:
                    error_friends += 1
                    error_friends_info.append(friend)
            except Exception as e:
                logging.error(f"Lỗi khi xử lý {friend}: {e}", exc_info=True)
                error_friends += 1
                error_friends_info.append(friend)

    result = {
        'statistical_data': {
            'friends_num': total_friends,
            'active_num': active_friends,
            'error_num': error_friends,
            'article_num': total_articles,
            'last_updated_time': datetime.now(ZoneInfo("Asia/Shanghai")).strftime('%Y-%m-%d %H:%M:%S')
        },
        'article_data': article_data
    }
    
    logging.info(f"Đã hoàn thành xử lý dữ liệu, tổng cộng có {total_friends} bạn bè, trong đó {active_friends} blog có thể truy cập, {error_friends} blog không thể truy cập")

    return result, error_friends_info

def sort_articles_by_time(data):
    """
    Sắp xếp dữ liệu bài viết theo thời gian

    Tham số:
    data (dict): Từ điển chứa thông tin bài viết

    Trả về:
    dict: Từ điển thông tin bài viết đã sắp xếp theo thời gian
    """
    # Đảm bảo mỗi phần tử có thời gian
    for article in data['article_data']:
        if article['created'] == '' or article['created'] == None:
            article['created'] = '2024-01-01 00:00'
            # Xuất thông tin cảnh báo
            logging.warning(f"Bài viết {article['title']} không chứa thông tin thời gian, đã đặt thành thời gian mặc định 2024-01-01 00:00")
    
    if 'article_data' in data:
        sorted_articles = sorted(
            data['article_data'],
            key=lambda x: datetime.strptime(x['created'], '%Y-%m-%d %H:%M'),
            reverse=True
        )
        data['article_data'] = sorted_articles
    return data

def marge_data_from_json_url(data, marge_json_url):
    """
    Lấy dữ liệu từ file JSON khác và hợp nhất vào dữ liệu gốc.

    Tham số:
    data (dict): Từ điển chứa thông tin bài viết
    marge_json_url (str): URL của file JSON chứa thông tin bài viết khác.

    Trả về:
    dict: Từ điển thông tin bài viết sau khi hợp nhất, đã xử lý trùng lặp
    """
    try:
        response = requests.get(marge_json_url, headers=HEADERS_JSON, timeout=timeout)
        marge_data = response.json()
    except Exception as e:
        logging.error(f"Không thể lấy liên kết: {marge_json_url}, vấn đề gặp phải là: {e}", exc_info=True)
        return data
    
    if 'article_data' in marge_data:
        logging.info(f"Bắt đầu hợp nhất dữ liệu, dữ liệu gốc có {len(data['article_data'])} bài viết, dữ liệu bên thứ ba có {len(marge_data['article_data'])} bài viết")
        data['article_data'].extend(marge_data['article_data'])
        data['article_data'] = list({v['link']:v for v in data['article_data']}.values())
        logging.info(f"Đã hoàn thành hợp nhất dữ liệu, hiện có {len(data['article_data'])} bài viết")
    return data

import requests

def marge_errors_from_json_url(errors, marge_json_url):
    """
    Lấy thông tin lỗi từ file JSON mạng khác và duyệt, xóa trong errors,
    thông tin liên kết bạn bè không tồn tại trong marge_errors.

    Tham số:
    errors (list): Danh sách chứa thông tin lỗi
    marge_json_url (str): URL của file JSON chứa thông tin lỗi khác.

    Trả về:
    list: Danh sách thông tin lỗi sau khi hợp nhất
    """
    try:
        response = requests.get(marge_json_url, timeout=10)  # Đặt thời gian chờ request
        marge_errors = response.json()
    except Exception as e:
        logging.error(f"Không thể lấy liên kết: {marge_json_url}, vấn đề gặp phải là: {e}", exc_info=True)
        return errors

    # Trích xuất URL từ marge_errors
    marge_urls = {item[1] for item in marge_errors}

    # Sử dụng bộ lọc giữ lại URL trong errors xuất hiện trong marge_errors
    filtered_errors = [error for error in errors if error[1] in marge_urls]

    logging.info(f"Đã hoàn thành hợp nhất thông tin lỗi, sau khi hợp nhất có {len(filtered_errors)} bạn bè")
    return filtered_errors

def deal_with_large_data(result):
    """
    Xử lý dữ liệu bài viết, giữ lại 150 bài đầu tiên và sự xuất hiện của tác giả trong các bài viết tiếp theo.
    
    Tham số:
    result (dict): Từ điển chứa dữ liệu thống kê và dữ liệu bài viết.
    
    Trả về:
    dict: Dữ liệu sau khi xử lý, chỉ chứa các bài viết cần thiết.
    """
    result = sort_articles_by_time(result)
    article_data = result.get("article_data", [])

    # Kiểm tra số lượng bài viết có lớn hơn 150 không
    max_articles = 150
    if len(article_data) > max_articles:
        logging.info("Dữ liệu lớn, bắt đầu xử lý...")
        # Lấy tập hợp tác giả của max_articles bài viết đầu tiên
        top_authors = {article["author"] for article in article_data[:max_articles]}

        # Lọc từ bài viết thứ {max_articles + 1}, chỉ giữ lại bài viết của tác giả xuất hiện trong max_articles bài đầu tiên
        filtered_articles = article_data[:max_articles] + [
            article for article in article_data[max_articles:]
            if article["author"] in top_authors
        ]

        # Cập nhật article_data trong kết quả
        result["article_data"] = filtered_articles
        # Cập nhật dữ liệu thống kê trong kết quả
        result["statistical_data"]["article_num"] = len(filtered_articles)
        logging.info(f"Đã hoàn thành xử lý dữ liệu, giữ lại {len(filtered_articles)} bài viết")

    return result
