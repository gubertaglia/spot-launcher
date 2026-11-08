"""Translate short text through MyMemory outside the GTK thread."""
from functools import lru_cache
from html import unescape
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# Shared by command parsing and service validation.
LANGUAGE_ALIASES = {
    alias: code
    for code, names in {
        'pt': 'português|portugues|portuguese|portugais',
        'en': 'inglês|ingles|english|inglés|anglais',
        'es': 'espanhol|español|espanol|spanish|espagnol',
        'fr': 'francês|frances|français|francais|french|francés',
        'ru': 'russo|russian|ruso|russe',
        'de': 'alemão|alemao|german|alemán|aleman|allemand',
        'it': 'italiano|italian|italien',
        'ja': 'japonês|japones|japanese|japonés|japonais',
        'zh': 'chinês|chines|chinese|chino|chinois|mandarim|mandarin',
        'ko': 'coreano|korean|coréen',
        'ar': 'árabe|arabe|arabic',
        'hi': 'hindi',
        'uk': 'ucraniano|ukrainian|ukrainien',
        'el': 'grego|greek|griego|grec',
        'he': 'hebraico|hebrew|hebreo|hébreu',
        'tr': 'turco|turkish|turc',
        'nl': 'holandês|holandes|neerlandês|neerlandes|dutch|néerlandais',
        'pl': 'polonês|polones|polish|polaco|polonais',
        'sv': 'sueco|swedish|suédois',
        'da': 'dinamarquês|dinamarques|danish|danés|danois',
        'no': 'norueguês|noruegues|norwegian|noruego|norvégien',
        'fi': 'finlandês|finlandes|finnish|finés|finnois',
        'cs': 'tcheco|checo|czech|tchèque',
        'ro': 'romeno|romanian|rumano|roumain',
        'hu': 'húngaro|hungaro|hungarian|hongrois',
        'id': 'indonésio|indonesio|indonesian|indonésien',
        'vi': 'vietnamita|vietnamese|vietnamien',
        'th': 'tailandês|tailandes|thai|thaï',
    }.items()
    for alias in (code, *names.split('|'))
}


@lru_cache(maxsize=64)
def translate(text, source, target):
    if source not in LANGUAGE_ALIASES.values() or target not in LANGUAGE_ALIASES.values():
        raise ValueError('Unsupported translation language')
    if not text.strip() or len(text.encode('utf-8')) > 500:
        raise ValueError('Translation requires 1–500 UTF-8 bytes')
    if source == target:
        return text
    url = 'https://api.mymemory.translated.net/get?' + urlencode({
        'q': text, 'langpair': source + '|' + target,
    })
    request = Request(url, headers={'User-Agent': 'SpotLauncher/1.7 (translation)'})
    with urlopen(request, timeout=5) as response:
        data = json.loads(response.read(2_000_000))
    if not isinstance(data, dict):
        raise ValueError('Invalid translation response')
    if str(data.get('responseStatus')) != '200' or data.get('quotaFinished'):
        raise ValueError('Translation service unavailable or quota exceeded')
    response_data = data.get('responseData')
    if not isinstance(response_data, dict):
        raise ValueError('Invalid translation response')
    result = response_data.get('translatedText')
    if not isinstance(result, str):
        raise ValueError('Missing translation')
    result = unescape(result).strip()
    if not result:
        raise ValueError('Missing translation')
    return result
