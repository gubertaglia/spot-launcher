"""Read Wiktionary definitions outside the GTK thread."""
from html.parser import HTMLParser
import json
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class Definitions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.capture_depth = None
        self.parts = []
        self.term = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        parent = self.stack[-1] if self.stack else {}
        blocked = (parent.get('blocked', False) or tag in ('style', 'script', 'sup')
                   or attributes.get('aria-hidden') == 'true' or 'hidden' in attributes
                   or bool(set(attributes.get('class', '').split()) & {'references', 'reference', 'toc'})
                   or (self.capture_depth is not None and tag in ('ol', 'ul', 'dl')))
        if tag == 'br' and self.capture_depth is not None and not blocked:
            self.parts.append(' ')
        if tag in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            return
        self.stack.append({'tag': tag, 'blocked': blocked, 'numbered': False})
        if tag == 'dt':
            self.term = []
        candidate = ((tag == 'li' and parent.get('tag') == 'ol')
                     or (tag == 'dd' and parent.get('tag') == 'dl' and parent.get('numbered')))
        if candidate and not blocked and self.capture_depth is None:
            self.capture_depth = len(self.stack)
            self.parts = []

    def handle_data(self, text):
        if not self.stack or self.stack[-1]['blocked']:
            return
        if self.capture_depth is not None:
            self.parts.append(text)
        elif any(frame['tag'] == 'dt' for frame in self.stack):
            self.term.append(text)

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1)
                      if self.stack[i]['tag'] == tag), None)
        if index is None:
            return
        if tag == 'dt':
            for frame in reversed(self.stack[:index]):
                if frame['tag'] == 'dl':
                    frame['numbered'] = ''.join(self.term).strip()[:1].isdigit()
                    break
        if self.capture_depth is not None and index < self.capture_depth:
            text = ' '.join(''.join(self.parts).split())
            if text and text not in self.items:
                self.items.append(text)
            self.capture_depth = None
        del self.stack[index:]


def lookup(word, search_url):
    host = urlsplit(search_url).netloc

    def fetch(parameters):
        url = 'https://' + host + '/w/api.php?' + urlencode({
            'format': 'json', 'formatversion': 2, **parameters,
        })
        request = Request(url, headers={'User-Agent': 'SpotLauncher/1.7 (dictionary lookup)'})
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read(2_000_000))

    def definitions(term):
        data = fetch({'action': 'parse', 'page': term, 'prop': 'text', 'redirects': 1})
        parser = Definitions()
        parser.feed(data.get('parse', {}).get('text', ''))
        return data, parser.items[:8]

    data, items = definitions(word)
    if data.get('error', {}).get('code') != 'missingtitle':
        return items
    if word != word.lower():
        data, items = definitions(word.lower())
        if data.get('error', {}).get('code') != 'missingtitle':
            return items
    search = fetch({'action': 'query', 'list': 'search', 'srsearch': word,
                    'srinfo': 'suggestion', 'srlimit': 1, 'srprop': ''})
    suggestion = search.get('query', {}).get('searchinfo', {}).get('suggestion')
    if suggestion and suggestion.casefold() != word.casefold():
        _, items = definitions(suggestion)
        return [suggestion + ' — ' + text for text in items]
    return []
