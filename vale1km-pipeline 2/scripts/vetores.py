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


def municipios(cache, caixa):
    """{codigo IBGE: [anéis]} do Blumenau, Pomerode e vizinhos que tocam a caixa (lon0, lon1, lat0, lat1)."""
    if os.path.exists(cache):
        try:
            out = json.load(open(cache, encoding="utf-8"))
            if all(c in out for c in D.MUNICIPIOS):
                print(f"Limites municipais: {len(out)} municípios do cache")
                return out
        except Exception:
            pass
    out = {}
    try:
        lista = json.loads(_get(f"{IBGE}/v1/localidades/estados/42/municipios"))
        alvo = {_norm(n) for n in VIZINHOS}
        ids = {str(m["id"]): m["nome"] for m in lista if _norm(m["nome"]) in alvo}
        for cod in D.MUNICIPIOS:
            ids.setdefault(cod, D.MUNICIPIOS[cod])
        print(f"Limites municipais: baixando {len(ids)} municípios do IBGE")
        for cod, nome in ids.items():
            q = "maxima" if cod in D.MUNICIPIOS else "intermediaria"
            try:
                gj = json.loads(_get(f"{IBGE}/v3/malhas/municipios/{cod}?formato=application/vnd.geo+json&qualidade={q}"))
                an = _geom_de(gj)
                if an and _toca(an, caixa):
                    out[cod] = an
            except Exception as e:
                print(f"  aviso: {nome} ({cod}) falhou: {e}")
    except Exception as e:
        print(f"AVISO: lista de municípios do IBGE falhou ({e})")
    if not all(c in out for c in D.MUNICIPIOS):
        print("Limites municipais: tentando a malha do estado inteiro")
        try:
            gj = json.loads(_get(f"{IBGE}/v3/malhas/estados/42?formato=application/vnd.geo+json&intrarregiao=municipio&qualidade=intermediaria", timeout=180))
            for f in gj.get("features", []):
                cod = str(f.get("properties", {}).get("codarea", ""))
                an = _aneis(f.get("geometry"))
                if an and _toca(an, caixa):
                    out[cod] = an
        except Exception as e:
            print(f"AVISO: malha do estado falhou ({e})")
    if all(c in out for c in D.MUNICIPIOS):
        json.dump(out, open(cache, "w", encoding="utf-8"))
        print(f"Limites municipais: {len(out)} municípios (Blumenau e Pomerode ok)")
    else:
        print("AVISO: SEM limites de Blumenau e Pomerode; os mapas sairão sem eles")
    return out


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
        q = ('[out:json][timeout:120];way["highway"~"^(motorway|trunk|primary|secondary)$"]'
             f'({caixa[2]},{caixa[0]},{caixa[3]},{caixa[1]});out geom;')
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
