"""Read RocoMusic's public catalog and MIDI downloads without login cookies."""

from html.parser import HTMLParser
import re
import time
from urllib.parse import urlencode, urljoin, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from uuid import UUID

ORIGIN = 'https://rocomusic.cn'
STORAGE_HOST = 'c9b792ad002485adae47482f4dba6a72.r2.cloudflarestorage.com'


def score_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('无效的在线曲谱编号') from exc


class SameSiteRedirect(HTTPRedirectHandler):
    def __init__(self, allow_storage=False):
        super().__init__()
        self.allowed_hosts = {'rocomusic.cn'} | ({STORAGE_HOST} if allow_storage else set())

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != 'https' or urlsplit(newurl).netloc not in self.allowed_hosts:
            raise ValueError('下载重定向到非洛克乐谱站点，已中止')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(path, stop, limit=4 * 1024 * 1024, *, allow_storage=False):
    if stop.is_set():
        raise ValueError('已取消在线请求')
    if not path.startswith('/') or path.startswith('//'):
        raise ValueError('无效的在线曲谱路径')
    request = Request(ORIGIN + path, headers={'User-Agent': 'RocoPlayer/0.1 (public-score-client)'})
    start = time.monotonic()
    try:
        with build_opener(SameSiteRedirect(allow_storage)).open(request, timeout=8) as response:
            chunks, size = [], 0
            while True:
                if stop.is_set():
                    raise ValueError('已取消在线请求')
                if time.monotonic() - start > 30:
                    raise ValueError('网站响应超时，请重试')
                chunk = response.read(64 * 1024)
                if not chunk:
                    return b''.join(chunks)
                size += len(chunk)
                if size > limit:
                    raise ValueError('在线文件超过大小限制')
                chunks.append(chunk)
    except HTTPError as exc:
        raise ValueError(f'网站返回 HTTP {exc.code}，请稍后重试或在网站确认下载权限') from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError('无法连接洛克乐谱，请检查网络后重试') from exc


class Page(HTMLParser):
    """Extract visible text/links only; never evaluate remote scripts or markup."""
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.texts = {}
        self.stack = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.links.append(attrs.get('href', ''))
        if tag in ('img', 'input', 'br', 'meta', 'link', 'hr', 'source', 'wbr'):
            return
        labels = attrs.get('class', '').split()
        if tag == 'h1':
            labels.append('heading')
        self.stack.append((tag, labels, []))

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            return
        _, labels, parts = self.stack.pop()
        value = ' '.join(''.join(parts).split())
        for label in labels:
            self.texts.setdefault(label, value)

    def handle_data(self, data):
        if any(tag in ('script', 'style') for tag, _, _ in self.stack):
            return
        for _, _, parts in self.stack:
            parts.append(data)


def catalog(query, page, stop):
    query = str(query).strip()
    if len(query) > 100 or type(page) is not int or not 1 <= page <= 10000:
        raise ValueError('搜索词或页码无效')
    html = fetch('/library?' + urlencode({'q': query, 'page': page}), stop).decode('utf-8')
    if 'library-search' not in html:
        raise ValueError('网站页面格式已变化或访问受限，请在网站查看')
    items = []
    for fragment in re.findall(r'<article\b[^>]*class="score-card"[^>]*>(.*?)</article>', html, re.S):
        card = Page(fragment)
        link = next((link for link in card.links if link.startswith('/scores/')), None)
        if not link or not card.texts.get('score-title'):
            raise ValueError('无法识别在线曲谱卡片，请在网站查看')
        identity = score_id(urlsplit(link).path.split('/')[-1])
        items.append({'id': identity, 'title': card.texts['score-title'],
                      'subtitle': card.texts.get('score-subtitle', ''),
                      'author': card.texts.get('byline', ''),
                      'format': card.texts.get('format-chip', ''),
                      'url': ORIGIN + '/scores/' + identity})
    parsed = Page(html)
    if not items and 'score-title' in html:
        raise ValueError('网站曲谱列表格式已变化，请在网站查看')
    more = any(urlsplit(link).path == '/library' and
               parse_qs(urlsplit(link).query).get('page') == [str(page + 1)] for link in parsed.links)
    return {'query': query, 'page': page, 'items': items, 'has_next': more}


def download(identity, stop):
    identity = score_id(identity)
    detail = Page(fetch('/scores/' + identity, stop).decode('utf-8'))
    prefix = f'/api/scores/{identity}/file'
    link = next((link for link in detail.links if urlsplit(link).path == prefix
                 and parse_qs(urlsplit(link).query).get('download') == ['1']), None)
    if not link or urlsplit(link).netloc or not detail.texts.get('heading'):
        raise ValueError('该曲谱暂无可下载 MIDI，或网站格式已变化')
    data = fetch(link, stop, limit=8 * 1024 * 1024, allow_storage=True)
    if not data.startswith(b'MThd'):
        raise ValueError('下载内容不是 MIDI，未写入谱库')
    return data, detail.texts['heading'], urljoin(ORIGIN, link)
