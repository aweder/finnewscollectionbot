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
firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
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
    """增强版文章内容抓取函数，包含完整的错误处理和重试机制"""
    
    # 定义需要重试的临时错误状态码
    RETRY_STATUS_CODES = {502, 503, 504, 520, 521, 522, 523, 524}
    # 定义永久错误状态码
    PERMANENT_ERROR_CODES = {400, 401, 403, 404, 410, 451}
    
    def check_http_status(url):
        """检查URL的HTTP状态码"""
        try:
            response = requests.head(url, timeout=10, allow_redirects=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            return response.status_code
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 无法检查URL状态: {url}, 错误: {e}")
            return None
    
    def is_error_page_content(text):
        """检查内容是否为错误页面"""
        if not text or len(text.strip()) < 50:
            return True
        
        error_indicators = [
            '404', 'not found', 'page not found', '页面不存在', '页面未找到',
            '500', 'internal server error', '服务器错误', '内部错误',
            '502', 'bad gateway', '网关错误',
            '503', 'service unavailable', '服务不可用',
            '504', 'gateway timeout', '网关超时',
            'access denied', '访问被拒绝', '权限不足',
            'forbidden', '禁止访问'
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in error_indicators)
    
    # 首先检查URL的HTTP状态码
    status_code = check_http_status(url)
    if status_code:
        if status_code in PERMANENT_ERROR_CODES:
            print(f"❌ URL返回永久错误状态码 {status_code}: {url}")
            return "（页面不存在或访问被拒绝）"
        elif status_code in RETRY_STATUS_CODES:
            print(f"⚠️ URL返回临时错误状态码 {status_code}: {url}，将进行重试")
        elif status_code >= 400:
            print(f"⚠️ URL返回错误状态码 {status_code}: {url}")
    
    # 开始重试循环
    for attempt in range(max_retries):
        if attempt > 0:
            wait_time = 2 ** attempt  # 指数退避
            print(f"🔄 第 {attempt + 1} 次重试 (等待 {wait_time} 秒): {url}")
            time.sleep(wait_time)
        
        # 尝试使用Firecrawl
        try:
            print(f"📰 正在使用Firecrawl爬取文章内容 (尝试 {attempt + 1}/{max_retries}): {url}")
            
            scrape_result = firecrawl_app.scrape(
                url, 
                formats=['markdown', 'html'],
                only_main_content=True,
                include_tags=['title', 'article', 'main', 'content'],
                exclude_tags=['nav', 'footer', 'header', 'aside', 'script', 'style'],
                timeout=30000,
            )
            
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
            if "404" in error_msg or "not found" in error_msg.lower():
                print(f"❌ Firecrawl遇到404错误: {url}")
                break  # 404错误不需要重试
            elif any(code in error_msg for code in ['502', '503', '504']):
                print(f"⚠️ Firecrawl遇到临时服务器错误: {url}，错误: {e}")
                continue  # 临时错误，继续重试
            else:
                print(f"❌ Firecrawl爬取失败: {url}，错误: {e}")
        
        # 如果Firecrawl失败，尝试newspaper3k备用方案
        try:
            print(f"🔄 尝试newspaper3k备用方案 (尝试 {attempt + 1}/{max_retries}): {url}")
            
            # 先检查URL状态
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            # 检查HTTP状态码
            if response.status_code in PERMANENT_ERROR_CODES:
                print(f"❌ 备用方案遇到永久错误状态码 {response.status_code}: {url}")
                break
            elif response.status_code in RETRY_STATUS_CODES:
                print(f"⚠️ 备用方案遇到临时错误状态码 {response.status_code}: {url}")
                continue
            elif response.status_code != 200:
                print(f"⚠️ 备用方案遇到HTTP错误 {response.status_code}: {url}")
                continue
            
            article = Article(url)
            article.config.headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            article.config.request_timeout = 15
            
            article.download()
            article.parse()
            
            text = article.text[:1500]
            
            # 检查是否为错误页面内容
            if is_error_page_content(text):
                print(f"⚠️ 备用方案获取到错误页面内容: {url}")
                continue
            
            if text and len(text.strip()) >= 50:
                print(f"✅ 备用方案成功获取内容，长度: {len(text)} 字符")
                return text
            else:
                print(f"⚠️ 备用方案获取的内容为空或过短: {url}")
                
        except requests.exceptions.HTTPError as http_e:
            if "404" in str(http_e):
                print(f"❌ 备用方案遇到404错误: {url}")
                break
            else:
                print(f"⚠️ 备用方案HTTP错误: {url}，错误: {http_e}")
        except Exception as backup_e:
            print(f"⚠️ 备用方案异常: {url}，错误: {backup_e}")
    
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

# 发送企业微信机器人推送
def send_to_wechat(title, content):
    # 企业微信机器人消息格式
    message = f"**{title}**\n\n{content}"
    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": message
        }
    }
    
    try:
        response = requests.post(wechat_webhook_url, json=data, timeout=10)
        if response.ok:
            result = response.json()
            if result.get("errcode") == 0:
                print("✅ 企业微信推送成功")
            else:
                print(f"❌ 企业微信推送失败: {result.get('errmsg', '未知错误')}")
        else:
            print(f"❌ 企业微信推送失败，HTTP状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 企业微信推送异常: {e}")


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
