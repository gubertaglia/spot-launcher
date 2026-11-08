from datetime import datetime
from functools import lru_cache
from pathlib import Path
import json
import locale
import os
import re
import math
import time
from typing import Dict, List, Optional
import urllib.parse
import urllib.request
import zoneinfo

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib
from src import LANGUAGE, VERSION, _, regional_date_format
from src.storage import write_json
from src.search import normalize_text
from src.search_commands import command_query

# Mapeamento limpo e automático: sem listas gigantescas manuais

CURRENCY_ALIASES = {
    "dolar": "USD",
    "dolares": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "$": "USD",
    "real": "BRL",
    "reais": "BRL",
    "r$": "BRL",
    "euro": "EUR",
    "euros": "EUR",
    "€": "EUR",
    "libra": "GBP",
    "libras": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "£": "GBP",
    "iene": "JPY",
    "ienes": "JPY",
    "yen": "JPY",
    "yenes": "JPY",
    "yens": "JPY",
    "livre": "GBP",
    "livres": "GBP",
    "reales": "BRL",
    "reals": "BRL",
    "reaux": "BRL",
    "¥": "JPY",
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
}


# Common unit names across the supported languages. Other unit expressions
# (including compound symbols) are handled by Pint.
UNIT_ALIASES = {
    alias: symbol for symbol, aliases in {
        "degC": "c celsius °c degc", "degF": "f fahrenheit °f degf",
        "kelvin": "k kelvin",
        "m": "metro metros metre metres",
        "km": "quilometro quilometros kilometro kilometros kilometre kilometres",
        "cm": "centimetro centimetros centimetre centimetres",
        "mm": "milimetro milimetros millimetre millimetres",
        "mi": "milha milhas milla millas mille milles",
        "ft": "pe pes pie pies pied pieds",
        "inch": "polegada polegadas pulgada pulgadas pouce pouces",
        "g": "grama gramas gramo gramos gramme grammes",
        "kg": "quilograma quilogramas quilo quilos kilogramo kilogramos kilogramme kilogrammes",
        "lb": "libra libras livre livres",
        "l": "litro litros litre litres",
        "ml": "mililitro mililitros millilitre millilitres",
        "s": "segundo segundos seconde secondes",
        "min": "minuto minutos",
        "h": "hora horas heure heures",
        "day": "dia dias jour jours",
    }.items() for alias in aliases.split()
}
CONVERSION_QUERY = re.compile(
    r"^([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))\s*([a-z$€£¥°/]+)\s+(?:em|para|to|in|en|a|vers)\s+([a-z$€£¥°/]+)$"
)


_PLACE = r"\s+(?:em|no|na|nos|nas|de|do|da|dos|das|in|en|a|au|aux|du)\s+(?P<place>[^?]{2,}?)\s*\??$"
WEATHER_QUERY = re.compile(
    r"^¿?(?:(?:what(?:['’]s| is) the|como esta (?:o|el)|quel|que)\s+)?"
    r"(?:clima|temperatura|weather(?: like)?|wheater|wheather|temperature|meteo|temps(?: fait-il)?|tiempo(?: hace)?|pronostico)"
    + _PLACE
)
TIME_QUERY = re.compile(
    r"^¿?(?:(?:que|quelle|what)\s+)?(?:hora(?: es)?|horas(?: sao)?|horario|tempo|fuso|"
    r"heure(?: est-il)?|time(?: is it)?)" + _PLACE
)


@lru_cache(maxsize=1)
def country_capitals():
    data = Path(__file__).resolve().parents[1] / "data/countries/capitals.json"
    with data.open(encoding="utf-8") as stream:
        return {
            normalize_text(name): (code, capital)
            for code, capital, *names in json.load(stream)
            for name in names
        }



class ToolsEngine:

    def __init__(self):
        cache_base = GLib.get_user_cache_dir()
        self.cache_dir = os.path.join(cache_base, "spot-launcher")
        self.rates_file = os.path.join(self.cache_dir, "currency_rates.json")
        # Older caches contain Portuguese place names.
        geo_filename = "geocache.json" if LANGUAGE == "pt" else f"geocache-{LANGUAGE}.json"
        self.geo_cache_file = os.path.join(self.cache_dir, geo_filename)
        self.clipboard_file = os.path.join(self.cache_dir, "clipboard.json")

        self._rates: Dict[str, float] = {}
        self._geo_cache: Dict[str, dict] = {}
        self._weather_cache = {}
        self._weather_attempts = {}

        self._rates_timestamp = 0.0
        self._last_rates_attempt = None
        self._ureg = None
        self._pint_loaded = False
        # Nenhum acesso à rede ou carregamento de Pint no construtor.
        self._load_geo_cache()
        self._read_rates_cache()

    @staticmethod
    def supports_query(query):
        clean = normalize_text(command_query(query) or query)
        return bool(
            TIME_QUERY.match(clean)
            or WEATHER_QUERY.match(clean)
            or CONVERSION_QUERY.fullmatch(clean)
        )

    def search(self, query):
        """Executado exclusivamente no worker de ferramentas."""
        match = CONVERSION_QUERY.fullmatch(normalize_text(command_query(query) or query))
        if match:
            # Currency names can overlap with units of mass (e.g. "libra").
            currencies = CURRENCY_ALIASES.values()
            def is_currency(token):
                code = CURRENCY_ALIASES.get(token, token.upper())
                return code in currencies or code in self._rates

            if all(is_currency(token) for token in match.groups()[1:]):
                return self.convert_currency(query)
            if any(token in UNIT_ALIASES for token in match.groups()[1:]):
                return self.convert_units(query)
            return self.convert_units(query) or self.convert_currency(query)
        return self.check_weather(query) or self.check_timezone(query)

    def _unit_registry(self):
        if not self._pint_loaded:
            self._pint_loaded = True
            try:
                import pint
                self._ureg = pint.UnitRegistry()
            except ImportError:
                pass
        return self._ureg

    def check_weather(self, query: str) -> Optional[dict]:
        match = WEATHER_QUERY.match(normalize_text(command_query(query) or query))
        if not match:
            return None
        target = match.group("place").strip()
        if len(target) < 2:
            return None
        now = time.monotonic()
        cached = self._weather_cache.get(target)
        if cached and now - cached[0] < 600:
            return cached[1]
        last_attempt = self._weather_attempts.get(target)
        if last_attempt is None or now - last_attempt >= 60:
            self._weather_attempts[target] = now
            try:
                geo = self._geo_cache.get(self._geo_key(target))
                # Caches de versões anteriores contêm apenas o fuso.
                if not geo or "latitude" not in geo or "longitude" not in geo:
                    geo = self._fetch_geocoding(target)
                if geo:
                    params = urllib.parse.urlencode({
                        "latitude": geo["latitude"], "longitude": geo["longitude"],
                        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,wind_speed_10m",
                        "timezone": "auto", "temperature_unit": "celsius",
                        "wind_speed_unit": "kmh",
                    })
                    request = urllib.request.Request(
                        "https://api.open-meteo.com/v1/forecast?" + params,
                        headers={"User-Agent": f"SpotLauncher/{VERSION}"},
                    )
                    with urllib.request.urlopen(request, timeout=3) as response:
                        current = json.loads(response.read().decode())["current"]
                    temperature, feels, humidity, wind = (
                        float(current[key]) for key in (
                            "temperature_2m", "apparent_temperature",
                            "relative_humidity_2m", "wind_speed_10m",
                        )
                    )
                    if not all(math.isfinite(value) for value in (temperature, feels, humidity, wind)):
                        raise ValueError("Dados de clima inválidos")
                    condition, icon = self._weather_condition(current["weather_code"], current["is_day"])
                    title = _("{temperature} °C em {place} — {condition}").format(
                        temperature=locale.format_string("%g", temperature),
                        place=geo["display"], condition=condition,
                    )
                    result = {
                        "title": title,
                        "sub": _("Sensação: {feels} °C · Umidade: {humidity}% · Vento: {wind} km/h · "
                                 "Open-Meteo · {time} (hora local)").format(
                            feels=locale.format_string("%g", feels),
                            humidity=locale.format_string("%g", humidity),
                            wind=locale.format_string("%g", wind),
                            time=datetime.fromisoformat(current["time"]).strftime(regional_date_format() + " %H:%M"),
                        ),
                        "icon": icon, "copy": title,
                    }
                    self._weather_cache[target] = (now, result)
                    return result
            except (OSError, ValueError, TypeError, KeyError) as exc:
                print(f"[Clima] Consulta indisponível: {exc}")
        if cached:
            return {**cached[1], "sub": cached[1]["sub"] + " · " + _("Desatualizado; falha ao atualizar")}
        return {
            "title": _("Clima indisponível para '%s'") % target.title(),
            "sub": _("Verifique a cidade pesquisada e sua conexão"),
            "icon": "dialog-warning-symbolic", "copy": None,
        }

    @staticmethod
    def _weather_condition(code, is_day):
        if code == 0:
            return (_("Céu limpo"), "weather-clear-symbolic" if is_day else "weather-clear-night-symbolic")
        if code in (1, 2):
            return (_("Parcialmente nublado"), "weather-few-clouds-symbolic")
        if code == 3:
            return (_("Nublado"), "weather-overcast-symbolic")
        if code in (45, 48):
            return (_("Nevoeiro"), "weather-fog-symbolic")
        if code in (51, 53, 55, 56, 57):
            return (_("Garoa"), "weather-showers-scattered-symbolic")
        if code in (61, 63, 65, 66, 67, 80, 81, 82):
            return (_("Chuva"), "weather-showers-symbolic")
        if code in (71, 73, 75, 77, 85, 86):
            return (_("Neve"), "weather-snow-symbolic")
        if code in (95, 96, 99):
            return (_("Tempestade"), "weather-storm-symbolic")
        return (_("Condições indisponíveis"), "weather-overcast-symbolic")

    # ==========================================================
    # 1. MOTOR DE FUSOS GLOBAIS (Geocoding Aberto OpenStreetMap / Open-Meteo)
    # ==========================================================
    def check_timezone(self, query: str) -> Optional[dict]:
        clean = normalize_text(command_query(query) or query)
        match = TIME_QUERY.match(clean)
        if not match:
            return None

        target = match.group("place").strip()
        if len(target) < 2:
            return None

        # 1. Tenta carregar do cache offline local (0 ms)
        geo_data = self._geo_cache.get(self._geo_key(target))

        # 2. Se não estiver no cache, consulta a base global em tempo real
        if not geo_data:
            geo_data = self._fetch_geocoding(target)

        if geo_data:
            tz_name = geo_data["tz"]
            display_name = geo_data["display"]
            try:
                tz = zoneinfo.ZoneInfo(tz_name)
                now = datetime.now(tz)
                time_str = now.strftime("%H:%M")
                date_str = now.strftime(regional_date_format())
                return {
                    "title": _("São {time} em {place}").format(time=time_str, place=display_name),
                    "sub": _("Data: {date} (Fuso Oficial: {zone})").format(date=date_str, zone=tz_name),
                    "icon": "preferences-system-time-symbolic",
                    "copy": time_str,
                }
            except Exception:
                pass

        # Uma falha de rede também pode impedir a resolução da localização.
        return {
            "title": _("Localização indisponível para '%s'") % target.title(),
            "sub": _(
                "Verifique a localização pesquisada e sua conexão"
            ),
            "icon": "dialog-warning-symbolic",
            "copy": None,
        }

    @staticmethod
    def _geo_key(place_name):
        country = country_capitals().get(place_name)
        return f"capital:{country[0]}" if country else place_name

    def _fetch_geocoding(self, place_name: str) -> Optional[dict]:
        """Consulta qualquer cidade, país ou estado do planeta Terra sem listas manuais."""
        try:
            capital = country_capitals().get(place_name)
            params = {"name": place_name, "count": 1, "language": LANGUAGE}
            if capital:
                params.update(countryCode=capital[0], name=capital[1])
            url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(
                url, headers={"User-Agent": f"SpotLauncher/{VERSION}"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode())
                results = data.get("results")
                if results:
                    item = results[0]
                    tz_name = item.get("timezone")
                    name = item.get("name")
                    country = item.get("country", "")
                    admin1 = item.get("admin1", "")

                    if not tz_name:
                        return None

                    if capital and item.get("country_code") != capital[0]:
                        return None
                    display = name
                    if not capital and admin1 and admin1 != name:
                        display += f", {admin1}"
                    if country and country != name:
                        display += f" ({country})"

                    if capital:
                        display = _("{name} ({country}, capital)").format(name=name, country=country)

                    geo_entry = {"tz": tz_name, "display": display}
                    if "latitude" in item and "longitude" in item:
                        geo_entry.update(latitude=item["latitude"], longitude=item["longitude"])
                    self._geo_cache[self._geo_key(place_name)] = geo_entry
                    self._save_geo_cache()
                    return geo_entry
        except Exception as e:
            print(f"[Geocoding] Erro na consulta de '{place_name}': {e}")
        return None

    def _load_geo_cache(self):
        if os.path.exists(self.geo_cache_file):
            try:
                with open(self.geo_cache_file, "r") as f:
                    data = json.load(f)
                    self._geo_cache = {
                        key: value for key, value in data.items()
                        if isinstance(value, dict)
                        and isinstance(value.get("tz"), str)
                        and isinstance(value.get("display"), str)
                    }
            except Exception:
                pass

    def _save_geo_cache(self):
        try:
            write_json(self.geo_cache_file, self._geo_cache)
        except Exception:
            pass

    # ==========================================================
    # 2. MOTOR DE MOEDAS E CRIPTO (Catálogo Dinâmico Coinbase)
    # ==========================================================
    def convert_currency(self, query: str) -> Optional[dict]:
        clean = normalize_text(command_query(query) or query)
        match = CONVERSION_QUERY.fullmatch(clean)
        if not match:
            return None

        val_str, curr_from, curr_to = match.groups()
        try:
            val = float(val_str.replace(",", "."))
        except ValueError:
            return None

        if not math.isfinite(val):
            return None

        c_from = CURRENCY_ALIASES.get(curr_from, curr_from.upper())
        c_to = CURRENCY_ALIASES.get(curr_to, curr_to.upper())

        self._load_rates()

        # Só converte se ambas forem moedas REAIS presentes no mercado
        if c_from in self._rates and c_to in self._rates:
            val_in_usd = val / self._rates[c_from]
            res = val_in_usd * self._rates[c_to]

            fmt_res = locale.format_string("%.2f" if res >= 0.01 else "%.6f", res, grouping=True)
            sub = _("{value} {source} para {target} — Coinbase, {updated}").format(
                value=locale.str(val), source=c_from, target=c_to,
                updated=datetime.fromtimestamp(self._rates_timestamp).strftime(regional_date_format() + " %H:%M"),
            )
            if time.time() - self._rates_timestamp > 3600:
                sub = _("{quote} (desatualizada)").format(quote=sub)
            return {
                "title": f"= {fmt_res} {c_to}",
                "sub": sub,
                "icon": "help-about-symbolic",
                "copy": f"{res:.2f}",
            }

        return {"title": _("Cotação indisponível"),
                "sub": _("Não foi possível obter uma cotação para essas moedas"),
                "icon": "dialog-warning-symbolic", "copy": None}

    @staticmethod
    def _validated_rates(rates):
        converted = {str(k): float(v) for k, v in rates.items()}
        if not converted or any(not math.isfinite(v) or v <= 0 for v in converted.values()):
            raise ValueError("Cotações inválidas")
        return converted

    def _read_rates_cache(self):
        try:
            with open(self.rates_file, encoding="utf-8") as stream:
                data = json.load(stream)
            # Cache antigo sem timestamp deve ser atualizado, não tratado como recente.
            rates = data.get("rates", data)
            timestamp = float(data.get("fetched_at", 0))
            if not math.isfinite(timestamp) or timestamp > time.time():
                timestamp = 0
            self._rates = self._validated_rates(rates)
            self._rates_timestamp = timestamp
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def _load_rates(self):
        now = time.time()
        if self._rates and 0 <= now - self._rates_timestamp < 3600:
            return
        # Evita repetir uma falha de rede a cada tecla.
        if self._last_rates_attempt is not None and time.monotonic() - self._last_rates_attempt < 60:
            return
        self._last_rates_attempt = time.monotonic()
        try:
            req = urllib.request.Request(
                "https://api.coinbase.com/v2/exchange-rates?currency=USD",
                headers={"User-Agent": f"SpotLauncher/{VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
            rates = self._validated_rates(data["data"]["rates"])
            self._rates = rates
            self._rates_timestamp = time.time()
            write_json(self.rates_file, {"fetched_at": self._rates_timestamp, "rates": rates})
        except Exception as exc:
            print(f"[Coinbase] Cotação indisponível; preservando cache: {exc}")

    # ==========================================================
    # 3. MOTOR CIENTÍFICO DE UNIDADES (Via Pint)
    # ==========================================================
    def convert_units(self, query: str) -> Optional[dict]:
        clean = normalize_text(command_query(query) or query)
        match = CONVERSION_QUERY.fullmatch(clean)
        if not match:
            return None

        val_str, u_from, u_to = match.groups()
        try:
            val = float(val_str.replace(",", "."))
        except ValueError:
            return None

        if not math.isfinite(val):
            return None

        u_a = UNIT_ALIASES.get(u_from, u_from)
        u_b = UNIT_ALIASES.get(u_to, u_to)

        # O registro é carregado sob demanda na thread de ferramentas.
        ureg = self._unit_registry()
        if ureg:
            try:
                quantity = ureg.Quantity(val, u_a)
                converted = quantity.to(u_b)
                res_num = converted.magnitude
                if not math.isfinite(res_num):
                    return None
                formatted_val = (
                    locale.format_string("%.2f", res_num, grouping=True)
                    if isinstance(res_num, float) and not res_num.is_integer()
                    else f"{int(res_num)}"
                )
                return {
                    "title": f"= {formatted_val} {u_to}",
                    "sub": _("{value} {source} convertido para {target} (Sistema Universal)").format(
                        value=locale.str(val), source=u_from, target=u_to,
                    ),
                    "icon": "emblem-synchronizing-symbolic",
                    "copy": f"{res_num}",
                }
            except Exception:
                pass

        return None

    # ==========================================================
    # 4. HISTÓRICO DA ÁREA DE TRANSFERÊNCIA
    # ==========================================================
    def record_clipboard(self, text: str):
        if not text or len(text.strip()) == 0:
            return
        items = self.get_clipboard_history()
        if items and items[0] == text:
            return
        if text in items:
            items.remove(text)
        items.insert(0, text)
        items = items[:15]
        try:
            write_json(self.clipboard_file, items)
        except Exception:
            pass

    def get_clipboard_history(self) -> List[str]:
        if os.path.exists(self.clipboard_file):
            try:
                with open(self.clipboard_file, "r") as f:
                    data = json.load(f)
                    return [item for item in data if isinstance(item, str)][:15] if isinstance(data, list) else []
            except Exception:
                return []
        return []
