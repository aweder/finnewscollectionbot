# 福生无量天尊
from openai import OpenAI
import feedparser
import requests
from newspaper import Article
from datetime import datetime
import time
import pytz
import os
import re
from firecrawl import FirecrawlApp

# OpenAI API Key
openai_api_key = os.getenv("OPENAI_API_KEY")
# 从环境变量获取企业微信机器人 Webhook URL
wechat_webhook_url = os.getenv("WECHAT_WEBHOOK_URL")
if not wechat_webhook_url:
    raise ValueError("环境变量 WECHAT_WEBHOOK_URL 未设置，请在Github Actions中设置此变量！")

# Firecrawl API Key
firecrawl_api_key = "fc-b0cb6a0d8fd441a9b3f5cae5d55eff6c" #os.getenv("FIRECRAWL_API_KEY")
if not firecrawl_api_key:
    raise ValueError("环境变量 FIRECRAWL_API_KEY 未设置，请在Github Actions中设置此变量！")

# 初始化Firecrawl客户端
firecrawl_app = FirecrawlApp(api_key=firecrawl_api_key)

openai_client = OpenAI(api_key=openai_api_key, base_url="https://api.deepseek.com/v1")

# RSS源地址列表
rss_feeds = {
    "💲 华尔街见闻":{
        "华尔街见闻":"https://dedicated.wallstreetcn.com/rss.xml",      
    },
    "💻 36氪":{
        "36氪":"https://36kr.com/feed",   
        },
    "🇨🇳 中国经济": {
        "香港經濟日報":"https://www.hket.com/rss/china",
        "东方财富":"http://rss.eastmoney.com/rss_partener.xml",
        "百度股票焦点":"http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0",
        "中新网":"https://www.chinanews.com.cn/rss/finance.xml",
        "国家统计局-最新发布":"https://www.stats.gov.cn/sj/zxfb/rss.xml",
        "财富中文":"https://plink.anyfeeder.com/fortunechina",
        "经济日报" : "https://plink.anyfeeder.com/jingjiribao",
        "新财富" : "https://plink.anyfeeder.com/weixin/newfortune"

    },
      "🇺🇸 美国经济": {
        "华尔街日报 - 经济":"https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
        "华尔街日报 - 市场":"https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
        "MarketWatch美股": "https://www.marketwatch.com/rss/topstories",
        "ZeroHedge华尔街新闻": "https://feeds.feedburner.com/zerohedge/feed",
        "ETF Trends": "https://www.etftrends.com/feed/",
    },
    "🌍 世界经济": {
        "华尔街日报 - 经济":"https://feeds.content.dowjones.io/public/rss/socialeconomyfeed",
        "BBC全球经济": "http://feeds.bbci.co.uk/news/business/rss.xml",
    },
    "特色主题": {
        "雪球·今日话题": "https://xueqiu.com/hots/topic/rss",
        "德林社": "https://plink.anyfeeder.com/weixin/delinshe",
        "吴晓波频道": "https://plink.anyfeeder.com/weixin/wuxiaobo",
        "叶檀财经": "https://plink.anyfeeder.com/weixin/tancaijing",
        "21 世纪经济报道": "https://plink.anyfeeder.com/weixin/jjbd21",
        "中国日报-财经": "https://plink.anyfeeder.com/chinadaily/caijing",
    },

}

# 获取北京时间
def today_date():
    return datetime.now(pytz.timezone("Asia/Shanghai")).date()

# 爬取网页正文 (用于 AI 分析，但不展示) - 使用Firecrawl
def fetch_article_text(url, max_retries=3):
    """重构版文章内容抓取函数，解决404误判、速率限制和反爬机制问题"""
    
    # 定义需要重试的临时错误状态码
    RETRY_STATUS_CODES = {502, 503, 504, 520, 521, 522, 523, 524}
    # 定义永久错误状态码（移除404，因为可能是反爬机制）
    PERMANENT_ERROR_CODES = {400, 401, 410, 451}
    # 403和404可能是反爬，需要特殊处理
    ANTI_CRAWLER_CODES = {403, 404}
    
    # 针对不同网站的特殊请求头配置
    def get_site_specific_headers(url):
        """根据网站返回特定的请求头"""
        base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        if 'wallstreetcn.com' in url:
            base_headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://wallstreetcn.com/',
                'Origin': 'https://wallstreetcn.com'
            })
        elif '36kr.com' in url:
            base_headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://36kr.com/',
                'Origin': 'https://36kr.com'
            })
        elif 'eastmoney.com' in url:
            base_headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                'Referer': 'http://www.eastmoney.com/',
                'Origin': 'http://www.eastmoney.com'
            })
        elif 'hket.com' in url:
            base_headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://china.hket.com/',
                'Origin': 'https://china.hket.com'
            })
        else:
            base_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        return base_headers
    
    def smart_status_check(url):
        """智能状态检查，区分真实错误和反爬机制"""
        headers = get_site_specific_headers(url)
        session = requests.Session()
        
        try:
            # 先尝试HEAD请求
            response = session.head(url, timeout=15, allow_redirects=True, headers=headers)
            status_code = response.status_code
            
            # 如果HEAD请求返回405或其他错误，尝试GET请求
            if status_code in [405, 501] or status_code >= 500:
                response = session.get(url, timeout=15, headers=headers, stream=True)
                status_code = response.status_code
                response.close()
            
            return status_code
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 无法检查URL状态: {url}, 错误: {e}")
            return None
        finally:
            session.close()
    
    def is_error_page_content(text, url=""):
        """检查内容是否为错误页面"""
        if not text or len(text.strip()) < 50:
            return True
        
        # 更精确的错误页面检测
        error_indicators = [
            'page not found', '页面不存在', '页面未找到', '页面丢失',
            'internal server error', '服务器错误', '内部错误',
            'bad gateway', '网关错误',
            'service unavailable', '服务不可用',
            'gateway timeout', '网关超时',
            'access denied', '访问被拒绝', '权限不足',
            'forbidden', '禁止访问',
            '请完成下列验证后继续', '按住左边按钮拖动完成上方拼图',  # 36氪验证码页面
            'cloudflare', 'just a moment', 'checking your browser',  # Cloudflare保护页面
            '验证码', 'captcha', '人机验证', '安全验证',
            '403 forbidden', '404 not found', '500 internal server error',
            '网站维护中', 'under maintenance', 'temporarily unavailable'
        ]
        
        # 网站特定的错误检测
        site_specific_errors = {
            '36kr.com': ['请开启javascript', '需要验证', '滑动验证'],
            'wallstreetcn.com': ['登录后查看', '会员专享', '订阅用户'],
            'eastmoney.com': ['页面加载失败', '网络连接异常'],
            'hket.com': ['內容未找到', '文章不存在']
        }
        
        text_lower = text.lower()
        
        # 检查通用错误指示器
        error_count = sum(1 for indicator in error_indicators if indicator in text_lower)
        
        # 检查网站特定错误
        for domain, specific_errors in site_specific_errors.items():
            if domain in url:
                error_count += sum(1 for error in specific_errors if error in text_lower)
        
        # 检查内容质量
        if len(text.strip()) < 100 and any(keyword in text_lower for keyword in ['error', '错误', '失败', 'failed']):
            error_count += 1
        
        return error_count >= 2 or any(strong_indicator in text_lower for strong_indicator in [
            'page not found', '页面不存在', '请完成下列验证后继续', '403 forbidden', '404 not found'
        ])
    
    def handle_rate_limit_error(error_msg):
        """处理速率限制错误"""
        if 'rate limit' in error_msg.lower():
            # 从错误消息中提取等待时间
            import re
            wait_match = re.search(r'retry after (\d+)s', error_msg)
            if wait_match:
                wait_time = int(wait_match.group(1)) + 2  # 额外等待2秒
                print(f"⏳ Firecrawl速率限制，等待 {wait_time} 秒后重试")
                time.sleep(wait_time)
                return True
            else:
                print(f"⏳ Firecrawl速率限制，等待 15 秒后重试")
                time.sleep(15)
                return True
        return False
    
    # 智能状态检查（仅对可疑URL进行）
    status_code = None
    if any(domain in url for domain in ['wallstreetcn.com', '36kr.com', 'hket.com']):
        status_code = smart_status_check(url)
        if status_code and status_code in PERMANENT_ERROR_CODES:
            print(f"❌ URL返回永久错误状态码 {status_code}: {url}")
            return "（页面不存在或访问被拒绝）"
        elif status_code and status_code in ANTI_CRAWLER_CODES:
            print(f"⚠️ URL可能遇到反爬机制 (状态码 {status_code}): {url}，将尝试多种方法")
    
    # 开始重试循环
    firecrawl_failed = False
    for attempt in range(max_retries):
        if attempt > 0:
            wait_time = min(2 ** attempt, 10)  # 最大等待10秒
            print(f"🔄 第 {attempt + 1} 次重试 (等待 {wait_time} 秒): {url}")
            time.sleep(wait_time)
        
        # 尝试使用Firecrawl（如果之前没有遇到速率限制）
        if not firecrawl_failed:
            try:
                print(f"📰 正在使用Firecrawl爬取文章内容 (尝试 {attempt + 1}/{max_retries}): {url}")
                
                # 添加随机延迟避免速率限制
                if attempt > 0:
                    import random
                    delay = random.uniform(1, 3)
                    time.sleep(delay)
                
                # 根据网站优化Firecrawl配置
                firecrawl_config = {
                    'formats': ['markdown', 'html'],
                    'only_main_content': True,
                    'timeout': 45000,
                    'wait_for': 3000,
                }
                
                # 网站特定配置
                if 'wallstreetcn.com' in url:
                    firecrawl_config.update({
                        'include_tags': ['article', '.article-content', '.content', 'main', '.post-content'],
                        'exclude_tags': ['nav', 'footer', 'header', 'aside', 'script', 'style', '.ad', '.advertisement'],
                        'wait_for': 5000,
                        'actions': [{'type': 'wait', 'milliseconds': 2000}]
                    })
                elif '36kr.com' in url:
                    firecrawl_config.update({
                        'include_tags': ['article', '.article-wrapper', '.content', '.kr-rich-text-wrapper'],
                        'exclude_tags': ['nav', 'footer', 'header', 'aside', 'script', 'style', '.ad-container'],
                        'wait_for': 4000,
                        'actions': [{'type': 'wait', 'milliseconds': 3000}]
                    })
                elif 'eastmoney.com' in url:
                    firecrawl_config.update({
                        'include_tags': ['article', '.news-content', '.content', '#ContentBody'],
                        'exclude_tags': ['nav', 'footer', 'header', 'aside', 'script', 'style', '.ad'],
                        'wait_for': 3000
                    })
                elif 'hket.com' in url:
                    firecrawl_config.update({
                        'include_tags': ['article', '.article-content', '.content', '.post-content'],
                        'exclude_tags': ['nav', 'footer', 'header', 'aside', 'script', 'style', '.ad'],
                        'wait_for': 2000
                    })
                else:
                    firecrawl_config.update({
                        'include_tags': ['article', 'main', '.content', '.post-content', '.article-content'],
                        'exclude_tags': ['nav', 'footer', 'header', 'aside', 'script', 'style', '.ad']
                    })
                
                scrape_result = firecrawl_app.scrape(url, **firecrawl_config)
                
                if scrape_result and hasattr(scrape_result, 'markdown'):
                    text = scrape_result.markdown
                    
                    # 如果markdown内容为空，尝试使用HTML内容
                    if not text or len(text.strip()) < 50:
                        if hasattr(scrape_result, 'html') and scrape_result.html:
                            html_content = scrape_result.html
                            text = re.sub(r'<[^>]+>', '', html_content)
                            text = re.sub(r'\s+', ' ', text).strip()
                    
                    # 检查是否为错误页面内容
                    if is_error_page_content(text):
                        print(f"⚠️ Firecrawl获取到错误页面内容: {url}")
                        continue
                    
                    text = text[:1500] if text else ""
                    
                    if text and len(text.strip()) >= 50:
                        print(f"✅ Firecrawl成功获取文章内容，长度: {len(text)} 字符")
                        return text
                    else:
                        print(f"⚠️ Firecrawl获取的文章内容为空或过短: {url}")
                else:
                    print(f"⚠️ Firecrawl未返回有效内容: {url}")
                    
            except Exception as e:
                error_msg = str(e)
                
                # 处理速率限制
                if handle_rate_limit_error(error_msg):
                    continue  # 重试当前尝试
                
                # 处理其他错误
                if "rate limit" in error_msg.lower():
                    print(f"⚠️ Firecrawl遇到速率限制，切换到备用方案: {url}")
                    firecrawl_failed = True
                elif "404" in error_msg and "wallstreetcn.com" not in url:
                    print(f"❌ Firecrawl遇到404错误: {url}")
                    break  # 非华尔街见闻的404错误才跳出
                elif any(code in error_msg for code in ['502', '503', '504']):
                    print(f"⚠️ Firecrawl遇到临时服务器错误: {url}，错误: {e}")
                    continue  # 临时错误，继续重试
                else:
                    print(f"⚠️ Firecrawl爬取失败: {url}，错误: {e}")
                    firecrawl_failed = True
        
        # 使用增强的newspaper3k备用方案
        try:
            print(f"🔄 尝试增强newspaper3k备用方案 (尝试 {attempt + 1}/{max_retries}): {url}")
            
            # 创建会话保持连接
            session = requests.Session()
            headers = get_site_specific_headers(url)
            
            # 添加随机延迟
            import random
            delay = random.uniform(1, 3)
            time.sleep(delay)
            
            # 多步骤请求模拟真实用户行为
            try:
                # 第一步：访问主页建立会话
                if 'wallstreetcn.com' in url:
                    session.get('https://wallstreetcn.com/', headers=headers, timeout=10)
                elif '36kr.com' in url:
                    session.get('https://36kr.com/', headers=headers, timeout=10)
                elif 'eastmoney.com' in url:
                    session.get('http://www.eastmoney.com/', headers=headers, timeout=10)
                elif 'hket.com' in url:
                    session.get('https://china.hket.com/', headers=headers, timeout=10)
                
                time.sleep(random.uniform(0.5, 1.5))
            except:
                pass  # 忽略主页访问失败
            
            # 第二步：访问目标页面
            response = session.get(url, timeout=25, headers=headers, allow_redirects=True)
            
            # 检查HTTP状态码
            if response.status_code in PERMANENT_ERROR_CODES:
                print(f"❌ 备用方案遇到永久错误状态码 {response.status_code}: {url}")
                session.close()
                break
            elif response.status_code in RETRY_STATUS_CODES:
                print(f"⚠️ 备用方案遇到临时错误状态码 {response.status_code}: {url}")
                session.close()
                continue
            elif response.status_code in ANTI_CRAWLER_CODES:
                print(f"⚠️ 备用方案遇到反爬状态码 {response.status_code}: {url}，尝试解析内容")
                # 即使是403/404也尝试解析，可能是反爬但内容可用
            elif response.status_code != 200:
                print(f"⚠️ 备用方案遇到HTTP错误 {response.status_code}: {url}")
                session.close()
                continue
            
            # 使用newspaper3k解析
            article = Article(url)
            article.config.headers = headers
            article.config.request_timeout = 25
            article.config.browser_user_agent = headers['User-Agent']
            article.config.follow_meta_refresh = True
            article.config.fetch_images = False
            
            # 直接使用已获取的响应内容
            article.set_html(response.text)
            article.parse()
            
            text = article.text[:1500] if article.text else ""
            
            # 如果newspaper3k解析失败，尝试简单的HTML解析
            if not text or len(text.strip()) < 50:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 移除脚本和样式
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # 尝试提取主要内容
                content_selectors = [
                    'article', '.article-content', '.content', '.post-content',
                    '.entry-content', '.main-content', '#content', '.article-body',
                    '.news-content', '.text-content', '.article-text'
                ]
                
                for selector in content_selectors:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        text = content_elem.get_text(strip=True)[:1500]
                        if len(text.strip()) >= 50:
                            break
                
                # 如果还是没有内容，提取所有文本
                if not text or len(text.strip()) < 50:
                    text = soup.get_text(strip=True)[:1500]
            
            session.close()
            
            # 检查是否为错误页面内容
            if is_error_page_content(text, url):
                print(f"⚠️ 备用方案获取到错误页面内容: {url}")
                continue
            
            if text and len(text.strip()) >= 50:
                print(f"✅ 备用方案成功获取内容，长度: {len(text)} 字符")
                return text
            else:
                print(f"⚠️ 备用方案获取的内容为空或过短: {url}")
                
        except requests.exceptions.Timeout:
            print(f"⚠️ 备用方案请求超时: {url}")
            continue
        except requests.exceptions.RequestException as req_e:
            print(f"⚠️ 备用方案网络错误: {url}，错误: {req_e}")
            continue
        except Exception as backup_e:
            print(f"⚠️ 备用方案异常: {url}，错误: {backup_e}")
            continue
    
    print(f"❌ 所有尝试均失败，无法获取文章内容: {url}")
    return "（未能获取文章正文）"

# 添加 User-Agent 头
def fetch_feed_with_headers(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    return feedparser.parse(url, request_headers=headers)


# 自动重试获取 RSS
def fetch_feed_with_retry(url, retries=3, delay=5):
    for i in range(retries):
        try:
            feed = fetch_feed_with_headers(url)
            if feed and hasattr(feed, 'entries') and len(feed.entries) > 0:
                return feed
        except Exception as e:
            print(f"⚠️ 第 {i+1} 次请求 {url} 失败: {e}")
            time.sleep(delay)
    print(f"❌ 跳过 {url}, 尝试 {retries} 次后仍失败。")
    return None

# 获取RSS内容（爬取正文但不展示）
def fetch_rss_articles(rss_feeds, max_articles=10):
    news_data = {}
    analysis_text = ""  # 用于AI分析的正文内容

    for category, sources in rss_feeds.items():
        category_content = ""
        for source, url in sources.items():
            print(f"📡 正在获取 {source} 的 RSS 源: {url}")
            feed = fetch_feed_with_retry(url)
            if not feed:
                print(f"⚠️ 无法获取 {source} 的 RSS 数据")
                continue
            print(f"✅ {source} RSS 获取成功，共 {len(feed.entries)} 条新闻")

            articles = []  # 每个source都需要重新初始化列表
            for entry in feed.entries[:5]:
                title = entry.get('title', '无标题')
                link = entry.get('link', '') or entry.get('guid', '')
                if not link:
                    print(f"⚠️ {source} 的新闻 '{title}' 没有链接，跳过")
                    continue

                # 爬取正文用于分析（不展示）
                article_text = fetch_article_text(link)
                analysis_text += f"【{title}】\n{article_text}\n\n"

                print(f"🔹 {source} - {title} 获取成功")
                articles.append(f"- [{title}]({link})")

            if articles:
                category_content += f"### {source}\n" + "\n".join(articles) + "\n\n"

        news_data[category] = category_content

    return news_data, analysis_text

# AI 生成内容摘要（基于爬取的正文）
def summarize(text):
    completion = openai_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": """
             你是一名专业的财经新闻分析师，请根据以下新闻内容，按照以下步骤完成任务：
             1. 提取新闻中涉及的主要行业和主题，找出近1天涨幅最高的3个行业或主题，以及近3天涨幅较高且此前2周表现平淡的3个行业/主题。（如新闻未提供具体涨幅，请结合描述和市场情绪推测热点）
             2. 针对每个热点，输出：
                - 催化剂：分析近期上涨的可能原因（政策、数据、事件、情绪等）。
                - 复盘：梳理过去3个月该行业/主题的核心逻辑、关键动态与阶段性走势。
                - 展望：判断该热点是短期炒作还是有持续行情潜力。
             3. 将以上分析整合为一篇1500字以内的财经热点摘要，逻辑清晰、重点突出，适合专业投资者阅读。
             """},
            {"role": "user", "content": text}
        ]
    )
    return completion.choices[0].message.content.strip()

# 发送企业微信机器人推送（支持4096字符限制的智能分割）
def send_to_wechat(title, content):
    """发送企业微信消息，自动处理4096字符限制
    
    Args:
        title: 消息标题
        content: 消息内容
    
    Returns:
        bool: 是否全部发送成功
    """
    
    def smart_split_message(message, max_length=3900):  # 留更多余量给序号标识
        """智能分割消息，优先在段落和句子边界分割"""
        if len(message) <= max_length:
            return [message]
        
        chunks = []
        current_chunk = ""
        
        # 按段落分割（双换行）
        paragraphs = message.split('\n\n')
        
        for paragraph in paragraphs:
            # 如果单个段落就超过限制，需要进一步分割
            if len(paragraph) > max_length:
                # 按句子分割
                sentences = re.split(r'([。！？\n])', paragraph)
                temp_paragraph = ""
                
                for i in range(0, len(sentences), 2):
                    sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else "")
                    
                    if len(current_chunk + temp_paragraph + sentence) > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        if temp_paragraph:
                            chunks.append(temp_paragraph.strip())
                            temp_paragraph = ""
                        
                        # 如果单个句子还是太长，强制分割
                        if len(sentence) > max_length:
                            while len(sentence) > max_length:
                                chunks.append(sentence[:max_length].strip())
                                sentence = sentence[max_length:]
                            if sentence.strip():
                                temp_paragraph = sentence
                        else:
                            temp_paragraph = sentence
                    else:
                        temp_paragraph += sentence
                
                if temp_paragraph:
                    if len(current_chunk + "\n\n" + temp_paragraph) > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = temp_paragraph
                        else:
                            chunks.append(temp_paragraph.strip())
                    else:
                        current_chunk += ("\n\n" if current_chunk else "") + temp_paragraph
            else:
                # 检查是否可以添加到当前块
                test_chunk = current_chunk + ("\n\n" if current_chunk else "") + paragraph
                if len(test_chunk) > max_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = paragraph
                else:
                    current_chunk = test_chunk
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def send_single_message(message_content, part_info=""):
        """发送单条消息"""
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": message_content
            }
        }
        
        try:
            response = requests.post(wechat_webhook_url, json=data, timeout=15)
            if response.ok:
                result = response.json()
                if result.get("errcode") == 0:
                    print(f"✅ 企业微信推送成功{part_info}")
                    return True
                else:
                    print(f"❌ 企业微信推送失败{part_info}: {result.get('errmsg', '未知错误')}")
                    return False
            else:
                print(f"❌ 企业微信推送失败{part_info}，HTTP状态码: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 企业微信推送异常{part_info}: {e}")
            return False
    
    # 构建完整消息
    full_message = f"**{title}**\n\n{content}"
    
    # 检查是否需要分割（企业微信严格限制4096字符）
    if len(full_message) < 4096:
        return send_single_message(full_message)
    
    print(f"📝 消息长度 {len(full_message)} 字符，超过4096限制，开始智能分割")
    
    # 分割消息
    message_chunks = smart_split_message(full_message)
    total_chunks = len(message_chunks)
    
    print(f"📋 消息已分割为 {total_chunks} 部分")
    
    success_count = 0
    
    for i, chunk in enumerate(message_chunks, 1):
        # 添加序号标识
        if total_chunks > 1:
            part_indicator = f"\n\n---\n📄 **第 {i}/{total_chunks} 部分**"
            if i == 1:
                # 第一部分保持原标题
                message_with_indicator = chunk + part_indicator
            else:
                # 后续部分添加续篇标识
                continuation_title = f"**{title}（续 {i}/{total_chunks}）**\n\n"
                chunk_content = chunk.replace(f"**{title}**\n\n", "")
                message_with_indicator = continuation_title + chunk_content + part_indicator
        else:
            message_with_indicator = chunk
        
        # 确保最终消息不超过4096字符
        if len(message_with_indicator) >= 4096:
            # 如果添加标识后超长，需要进一步截断内容
            available_length = 4095 - len(part_indicator) - (len(continuation_title) if total_chunks > 1 and i > 1 else 0)
            if i == 1:
                available_length -= len(f"**{title}**\n\n")
            
            if available_length > 100:  # 确保有足够内容
                if i == 1:
                    truncated_content = chunk[:available_length] + "..."
                    message_with_indicator = truncated_content + part_indicator
                else:
                    truncated_content = chunk_content[:available_length] + "..."
                    message_with_indicator = continuation_title + truncated_content + part_indicator
            else:
                print(f"⚠️ 第 {i} 部分内容过长，无法添加完整标识")
                message_with_indicator = chunk[:4095]
        
        # 发送消息
        part_info = f" (第 {i}/{total_chunks} 部分)" if total_chunks > 1 else ""
        success = send_single_message(message_with_indicator, part_info)
        
        if success:
            success_count += 1
        else:
            print(f"⚠️ 第 {i} 部分发送失败，继续发送后续部分")
        
        # 在消息之间添加延迟避免频率限制
        if i < total_chunks:
            delay_time = 2 if total_chunks <= 3 else 3  # 根据分割数量调整延迟
            print(f"⏳ 等待 {delay_time} 秒后发送下一部分...")
            time.sleep(delay_time)
    
    # 发送结果统计
    if success_count == total_chunks:
        print(f"🎉 所有 {total_chunks} 部分消息发送成功")
        return True
    else:
        print(f"⚠️ {total_chunks} 部分消息中有 {total_chunks - success_count} 部分发送失败")
        return False


if __name__ == "__main__":
    today_str = today_date().strftime("%Y-%m-%d")

    # 每个网站获取最多 5 篇文章
    articles_data, analysis_text = fetch_rss_articles(rss_feeds, max_articles=5)
    
    # AI生成摘要
    summary = summarize(analysis_text)

    # 生成仅展示标题和链接的最终消息
    final_summary = f"📅 **{today_str} 财经新闻摘要**\n\n✍️ **今日分析总结：**\n{summary}\n\n---\n\n"
    for category, content in articles_data.items():
        if content.strip():
            final_summary += f"## {category}\n{content}\n\n"

    # 推送到企业微信机器人
    send_to_wechat(title=f"📌 {today_str} 财经新闻摘要", content=final_summary)
