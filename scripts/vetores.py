"""Vale1Km: limites municipais (IBGE) e rodovias (OpenStreetMap) para mapas e sondagens.

Falhas de rede não derrubam a rodada, mas são avisadas no log. O resultado fica em cache (dados/vetores).
"""
import json
import os
import time
import unicodedata
import urllib.parse
import urllib.request

import dominio as D

IBGE = "https://servicodados.ibge.gov.br/api"
VIZINHOS = ["Blumenau", "Pomerode", "Gaspar", "Indaial", "Timbo", "Rio dos Cedros", "Benedito Novo", "Doutor Pedrinho",
            "Botuvera", "Brusque", "Guabiruba", "Luiz Alves", "Ilhota", "Massaranduba", "Jaragua do Sul", "Schroeder",
            "Apiuna", "Ascurra", "Rodeio", "Itaja", "Navegantes", "Camboriu", "Joinville", "Corupa", "Guaramirim"]
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://lz4.overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]


def _get(url, dados=None, tent=3, timeout=90):
    erro = None
    for i in range(tent):
        try:
            req = urllib.request.Request(url, data=dados, headers={"User-Agent": "vale1km/1.0 (previsao meteorologica)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            erro = e
            time.sleep(3 * (i + 1))
    raise erro


def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").strip()


def _aneis(geom):
    if not geom:
        return []
    if geom["type"] == "Polygon":
        polis = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polis = geom["coordinates"]
    else:
        return []
    return [[(p[0], p[1]) for p in anel] for poli in polis for anel in poli]


def _geom_de(gj):
    """Extrai os anéis de um GeoJSON (FeatureCollection, Feature ou Geometry)."""
    if gj.get("type") == "FeatureCollection":
        return [a for f in gj.get("features", []) for a in _aneis(f.get("geometry"))]
    if gj.get("type") == "Feature":
        return _aneis(gj.get("geometry"))
    return _aneis(gj)


def _toca(aneis, caixa):
    pts = [p for a in aneis for p in a]
    if not pts:
        return False
    lo = [p[0] for p in pts]; la = [p[1] for p in pts]
    return not (max(lo) < caixa[0] or min(lo) > caixa[1] or max(la) < caixa[2] or min(la) > caixa[3])


GEODATA = ["https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-42-mun.json",
           "https://raw.githubusercontent.com/tbrugz/geodata-br/main/geojson/geojs-42-mun.json"]


def _codigo(props, nome_osm=""):
    """Código IBGE a partir das propriedades; cai para o nome quando só ele existe."""
    cod = str(props.get("id") or props.get("codarea") or props.get("CD_MUN") or props.get("IBGE:GEOCODIGO")
              or props.get("ref:IBGE") or "")
    nome = _norm(props.get("name") or props.get("nome") or nome_osm or "")
    for c, n in D.MUNICIPIOS.items():
        if cod == c or (nome and nome == _norm(n)):
            return c
    return cod or ("nome:" + nome)


def _fonte_geodata(caixa):
    """Limites de todos os municípios de SC no repositório geodata-br (GitHub); alcançável das máquinas do Actions."""
    for url in GEODATA:
        try:
            gj = json.loads(_get(url, tent=2, timeout=60))
        except Exception as e:
            print(f"  aviso: geodata-br {url.split('/')[5]} falhou: {str(e)[:100]}")
            continue
        out = {}
        for f in gj.get("features", []):
            an = _aneis(f.get("geometry"))
            if an and _toca(an, caixa):
                out[_codigo(f.get("properties", {}))] = an
        if out:
            return out
    return {}


def _fonte_overpass(caixa):
    """Limites administrativos (nível 8 = município) do OpenStreetMap."""
    q = ('[out:json][timeout:120];relation["boundary"="administrative"]["admin_level"="8"]'
         f'({caixa[2]},{caixa[0]},{caixa[3]},{caixa[1]});out geom;')
    dados = urllib.parse.urlencode({"data": q}).encode()
    for url in OVERPASS:
        try:
            els = json.loads(_get(url, dados, tent=1, timeout=150))["elements"]
        except Exception as e:
            print(f"  aviso: Overpass (limites) {url} falhou: {str(e)[:100]}")
            continue
        out = {}
        for el in els:
            if el.get("type") != "relation":
                continue
            tags = el.get("tags", {})
            aneis = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in el.get("members", [])
                     if m.get("type") == "way" and m.get("geometry") and m.get("role") in ("outer", "inner", "")]
            if aneis and _toca(aneis, caixa):
                out[_codigo(tags)] = aneis
        if out:
            return out
    return {}


def _fonte_ibge(caixa):
    """IBGE (costuma não responder às máquinas do GitHub; fica por último, com tempo curto)."""
    out = {}
    try:
        for cod, nome in D.MUNICIPIOS.items():
            gj = json.loads(_get(f"{IBGE}/v3/malhas/municipios/{cod}?formato=application/vnd.geo+json&qualidade=maxima", tent=1, timeout=25))
            an = _geom_de(gj)
            if an:
                out[cod] = an
    except Exception as e:
        print(f"  aviso: IBGE falhou: {str(e)[:100]}")
    return out


def _sede_ok(out):
    """Blumenau e Pomerode: a sede precisa cair dentro da caixa dos limites baixados (descarta dados trocados ou errados)."""
    for cod in D.MUNICIPIOS:
        if cod not in out:
            return False
        la, lo = D.SEDES[cod]
        pts = [p for a in out[cod] for p in a]
        if not (min(p[0] for p in pts) <= lo <= max(p[0] for p in pts) and min(p[1] for p in pts) <= la <= max(p[1] for p in pts)):
            print(f"  aviso: a sede de {D.MUNICIPIOS[cod]} não cai nos limites recebidos; descartando esta fonte")
            return False
    return True


def municipios(cache, caixa):
    """{código IBGE: [anéis]} de Blumenau, Pomerode e vizinhos que tocam a caixa (lon0, lon1, lat0, lat1)."""
    if os.path.exists(cache):
        try:
            out = json.load(open(cache, encoding="utf-8"))
            if _sede_ok(out):
                print(f"Limites municipais: {len(out)} municípios do cache")
                return out
        except Exception:
            pass
    melhor = {}
    for nome, fonte in (("OpenStreetMap", _fonte_overpass), ("geodata-br", _fonte_geodata), ("IBGE", _fonte_ibge)):
        print(f"Limites municipais: tentando {nome}")
        out = fonte(caixa)
        print(f"  {nome}: {len(out)} municípios; destaques: {[c for c in D.MUNICIPIOS if c in out]}")
        if _sede_ok(out):
            json.dump(out, open(cache, "w", encoding="utf-8"))
            return out
        if len(out) > len(melhor):
            melhor = out
    print("AVISO: nenhuma fonte trouxe limites confiáveis de Blumenau e Pomerode" if melhor else
          "AVISO: SEM limites municipais em nenhuma das três fontes; os mapas sairão sem eles")
    return melhor


def rodovias(cache, caixa):
    """Lista de (ref, [(lon, lat), ...], classe) das rodovias principais na caixa."""
    els = None
    if os.path.exists(cache):
        try:
            els = json.load(open(cache, encoding="utf-8"))
            print(f"Rodovias: {len(els)} trechos do cache")
        except Exception:
            els = None
    if els is None:
        bb = f"({caixa[2]},{caixa[0]},{caixa[3]},{caixa[1]})"
        q = ('[out:json][timeout:120];(' + f'way["highway"~"^(motorway|trunk|primary)$"]{bb};'
             + f'way["highway"="secondary"]["ref"~"^(BR|SC)-"]{bb};' + ');out geom;')
        dados = urllib.parse.urlencode({"data": q}).encode()
        for rodada in range(2):
            for url in OVERPASS:
                try:
                    els = json.loads(_get(url, dados, tent=1, timeout=150))["elements"]
                    print(f"Rodovias: {len(els)} trechos de {url}")
                    break
                except Exception as e:
                    print(f"  aviso: Overpass {url} falhou: {str(e)[:120]}")
            if els is not None:
                break
            time.sleep(20)
        if els is None:
            print("AVISO: SEM rodovias (Overpass indisponível); os mapas sairão sem elas")
            return []
        json.dump(els, open(cache, "w", encoding="utf-8"))
    out = []
    for e in els:
        g = e.get("geometry")
        if g:
            t = e.get("tags", {})
            out.append((t.get("ref", ""), [(p["lon"], p["lat"]) for p in g], t.get("highway", "primary")))
    return out
