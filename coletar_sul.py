#!/usr/bin/env python3
"""
coletar_sul.py — puxa elevações de PR, SC e RS do OpenStreetMap e do Wikidata
e grava dados/mapeados_sul.json.

Essa é a CAMADA MAPEADA do catálogo: nome, altitude e coordenada, e mais nada.
Não inventa trilha, água nem pernoite — esses campos só existem em
dados/morros_sul.json, que é curadoria manual e continua sendo a fonte da verdade.

O coletor nunca sobrescreve um morro que já tem ficha: se o nome bate e o ponto
está a menos de 1 km de um registro curado, ele é descartado como duplicata.

Uso:
    python3 coletar_sul.py                  # OSM + Wikidata
    python3 coletar_sul.py --altitude       # + preenche altitude faltante (Open-Elevation)
    python3 coletar_sul.py --municipios     # + município via Nominatim (LENTO, 1 req/s)
    python3 coletar_sul.py --so-osm         # pula o Wikidata

Requer: pip install requests
"""

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Falta a lib requests. Rode: pip install requests")

RAIZ = Path(__file__).parent
CURADO = RAIZ / "dados" / "morros_sul.json"
SAIDA = RAIZ / "dados" / "mapeados_sul.json"

OVERPASS_ESPELHOS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]
WIKIDATA = "https://query.wikidata.org/sparql"
OPEN_ELEVATION = "https://api.open-elevation.com/api/v1/lookup"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"

# Nominatim e Wikidata exigem User-Agent identificável. Ponha seu contato.
UA = "acima-de-300/1.0 (catalogo de elevacoes do sul; contato: seu-email@exemplo.com)"

# O acervo guarda de 300 m para cima; o site é que abre em 500 m.
# Coletar a partir de 300 mantém a faixa baixa disponível pelo filtro de piso.
ALTITUDE_MINIMA = 300
ALTITUDE_TETO = 2000  # nada no Sul passa disso; acima é erro de digitação no OSM

CONSULTA_OSM = """
[out:json][timeout:600];
area["ISO3166-2"="BR-PR"]->.pr;
area["ISO3166-2"="BR-SC"]->.sc;
area["ISO3166-2"="BR-RS"]->.rs;
(
  node["natural"~"^(peak|hill|volcano)$"](area.pr);
  node["natural"~"^(peak|hill|volcano)$"](area.sc);
  node["natural"~"^(peak|hill|volcano)$"](area.rs);
);
out body;
"""

# Caixa que cobre PR + SC + RS com folga
CONSULTA_WIKIDATA = """
SELECT ?item ?nome ?coord ?ele WHERE {
  SERVICE wikibase:box {
    ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:cornerSouthWest "Point(-58.2 -34.0)"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point(-47.8 -22.4)"^^geo:wktLiteral .
  }
  ?item wdt:P31/wdt:P279* ?classe .
  VALUES ?classe { wd:Q8502 wd:Q54050 wd:Q207326 }
  OPTIONAL { ?item wdt:P2044 ?ele . }
  ?item rdfs:label ?nome . FILTER(LANG(?nome) = "pt")
}
"""

PREFIXOS_TIPO = {
    "pico": "pico", "morro": "morro", "cerro": "cerro", "monte": "monte",
    "montanha": "montanha", "pedra": "pedra", "serra": "serra",
    "cume": "pico", "alto": "morro", "coxilha": "morro", "cerrito": "cerro",
}


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def chave_nome(nome):
    """Normaliza para comparação: 'Pico Paraná' e 'Parana' viram a mesma chave."""
    limpo = sem_acento(nome).lower()
    limpo = re.sub(r"[^a-z0-9 ]", " ", limpo)
    partes = limpo.split()
    if partes and partes[0] in PREFIXOS_TIPO:
        partes = partes[1:]
    if partes and partes[0] in ("do", "da", "de", "dos", "das"):
        partes = partes[1:]
    return " ".join(partes)


def distancia_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def inferir_tipo(nome):
    partes = sem_acento(nome).lower().split()
    if partes and partes[0] in PREFIXOS_TIPO:
        return PREFIXOS_TIPO[partes[0]]
    for parte in partes:
        if parte in PREFIXOS_TIPO:
            return PREFIXOS_TIPO[parte]
    return "morro"


def parse_altitude(valor):
    """OSM guarda ele como texto e às vezes vem sujo: '1.877 m', '1877m', '1877,5'."""
    if valor is None:
        return None
    texto = str(valor).strip().lower().replace("m", "").replace(" ", "")
    if re.match(r"^\d{1,3}\.\d{3}$", texto):      # 1.877 = separador de milhar
        texto = texto.replace(".", "")
    texto = texto.replace(",", ".")
    try:
        alt = float(texto)
    except ValueError:
        return None
    return alt if 0 < alt < ALTITUDE_TETO else None


def estado_por_coordenada(lat, lon):
    if lat > -26.72:
        return "PR"
    if lat > -29.38:
        return "SC"
    return "RS"


def gerar_id(nome, estado, usados):
    base = re.sub(r"[^a-z0-9]+", "-", sem_acento(nome).lower()).strip("-")
    base = f"{estado.lower()}-{base}"[:60]
    candidato, n = base, 2
    while candidato in usados:
        candidato = f"{base}-{n}"
        n += 1
    usados.add(candidato)
    return candidato


# ---------------------------------------------------------------- coleta

def buscar_osm():
    print("OpenStreetMap: consultando Overpass (pode levar 2-5 min)...")
    dados = None
    for espelho in OVERPASS_ESPELHOS:
        try:
            print(f"  tentando {espelho}")
            resposta = requests.post(espelho, data={"data": CONSULTA_OSM},
                                     timeout=700, headers={"User-Agent": UA})
            resposta.raise_for_status()
            dados = resposta.json()
            break
        except Exception as erro:
            print(f"  falhou: {erro}")
    if dados is None:
        print("  todos os espelhos falharam; seguindo sem OSM")
        return []

    elementos = dados.get("elements", [])
    print(f"  {len(elementos)} nós retornados")

    registros = []
    for elemento in elementos:
        tags = elemento.get("tags", {})
        nome = (tags.get("name") or "").strip()
        lat, lon = elemento.get("lat"), elemento.get("lon")
        if not nome or lat is None or lon is None:
            continue
        registros.append({
            "nome": nome,
            "altitude": parse_altitude(tags.get("ele")),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "estado": estado_por_coordenada(lat, lon),
            "tipo": inferir_tipo(nome),
            "fontes": ["OpenStreetMap"],
        })
    print(f"  {len(registros)} com nome próprio")
    return registros


def buscar_wikidata():
    print("Wikidata: consultando SPARQL...")
    try:
        resposta = requests.get(WIKIDATA, timeout=180,
                                params={"query": CONSULTA_WIKIDATA, "format": "json"},
                                headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
        resposta.raise_for_status()
        linhas = resposta.json()["results"]["bindings"]
    except Exception as erro:
        print(f"  falhou: {erro}; seguindo sem Wikidata")
        return []

    print(f"  {len(linhas)} resultados")
    registros = []
    for linha in linhas:
        nome = linha["nome"]["value"].strip()
        ponto = linha["coord"]["value"]          # "Point(-48.81 -25.24)"
        casado = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", ponto)
        if not nome or not casado:
            continue
        lon, lat = float(casado.group(1)), float(casado.group(2))
        registros.append({
            "nome": nome,
            "altitude": parse_altitude(linha.get("ele", {}).get("value")),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "estado": estado_por_coordenada(lat, lon),
            "tipo": inferir_tipo(nome),
            "fontes": ["Wikidata"],
        })
    return registros


# ---------------------------------------------------------------- enriquecimento

def preencher_altitude(registros, lote=100):
    faltando = [r for r in registros if r["altitude"] is None]
    if not faltando:
        return
    print(f"Open-Elevation: buscando altitude de {len(faltando)} pontos...")
    for inicio in range(0, len(faltando), lote):
        grupo = faltando[inicio:inicio + lote]
        payload = {"locations": [{"latitude": r["lat"], "longitude": r["lon"]} for r in grupo]}
        try:
            resposta = requests.post(OPEN_ELEVATION, json=payload, timeout=180,
                                     headers={"User-Agent": UA})
            resposta.raise_for_status()
            for registro, resultado in zip(grupo, resposta.json()["results"]):
                altitude = float(resultado["elevation"])
                if 0 < altitude < ALTITUDE_TETO:
                    registro["altitude"] = altitude
                    registro["fontes"].append("Open-Elevation")
        except Exception as erro:
            print(f"  lote {inicio} falhou: {erro}")
        print(f"  {min(inicio + lote, len(faltando))}/{len(faltando)}")
        time.sleep(1)


def preencher_municipios(registros):
    """Nominatim aceita 1 requisição por segundo. Com milhares de pontos, isso leva horas."""
    print(f"Nominatim: buscando município de {len(registros)} pontos (1/s)...")
    cache = {}
    for indice, registro in enumerate(registros, 1):
        chave = (round(registro["lat"], 2), round(registro["lon"], 2))
        if chave in cache:
            registro["municipios"] = cache[chave]
            continue
        try:
            resposta = requests.get(NOMINATIM, timeout=30, headers={"User-Agent": UA},
                                    params={"lat": registro["lat"], "lon": registro["lon"],
                                            "format": "json", "zoom": 10})
            endereco = resposta.json().get("address", {})
            municipio = (endereco.get("city") or endereco.get("town")
                         or endereco.get("municipality") or endereco.get("village"))
            registro["municipios"] = [municipio] if municipio else []
            cache[chave] = registro["municipios"]
        except Exception:
            registro["municipios"] = []
        if indice % 100 == 0:
            print(f"  {indice}/{len(registros)}")
        time.sleep(1.1)


# ---------------------------------------------------------------- junção

def mesclar(listas):
    """Junta OSM + Wikidata, colapsando pontos com mesmo nome a menos de 1 km."""
    juntos = []
    for lista in listas:
        for novo in lista:
            achou = None
            chave = chave_nome(novo["nome"])
            for existente in juntos:
                if chave_nome(existente["nome"]) != chave:
                    continue
                if distancia_km(novo["lat"], novo["lon"],
                                existente["lat"], existente["lon"]) < 1.0:
                    achou = existente
                    break
            if achou:
                for fonte in novo["fontes"]:
                    if fonte not in achou["fontes"]:
                        achou["fontes"].append(fonte)
                if achou["altitude"] is None:
                    achou["altitude"] = novo["altitude"]
            else:
                juntos.append(novo)
    return juntos


def tirar_curados(registros):
    """Remove o que já tem ficha manual, para não duplicar nem sobrescrever."""
    if not CURADO.exists():
        print(f"AVISO: {CURADO} não encontrado; nada foi descartado")
        return registros
    curados = json.loads(CURADO.read_text(encoding="utf-8"))["morros"]
    indice = [(chave_nome(m["nome"]), m["lat"], m["lon"]) for m in curados]

    sobrou, descartados = [], 0
    for registro in registros:
        chave = chave_nome(registro["nome"])
        colide = any(chave == k and distancia_km(registro["lat"], registro["lon"], la, lo) < 1.0
                     for k, la, lo in indice)
        if colide:
            descartados += 1
        else:
            sobrou.append(registro)
    print(f"{descartados} descartados por já terem ficha curada")
    return sobrou


def main():
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--altitude", action="store_true",
                            help="preenche altitude faltante via Open-Elevation")
    analisador.add_argument("--municipios", action="store_true",
                            help="preenche município via Nominatim (muito lento)")
    analisador.add_argument("--so-osm", action="store_true", help="pula o Wikidata")
    analisador.add_argument("--piso", type=int, default=ALTITUDE_MINIMA,
                            help=f"altitude mínima coletada em metros (padrão {ALTITUDE_MINIMA})")
    argumentos = analisador.parse_args()

    fontes = [buscar_osm()]
    if not argumentos.so_osm:
        fontes.append(buscar_wikidata())

    registros = mesclar(fontes)
    print(f"{len(registros)} pontos únicos depois da mesclagem")

    if argumentos.altitude:
        preencher_altitude(registros)

    antes = len(registros)
    piso = argumentos.piso
    registros = [r for r in registros
                 if r["altitude"] is not None and piso <= r["altitude"] < ALTITUDE_TETO]
    print(f"{len(registros)} acima de {piso} m "
          f"({antes - len(registros)} fora do corte ou sem altitude)")

    registros = tirar_curados(registros)

    for registro in registros:
        registro.setdefault("municipios", [])
    if argumentos.municipios:
        preencher_municipios(registros)

    usados = set()
    for registro in registros:
        registro["id"] = gerar_id(registro["nome"], registro["estado"], usados)
        registro["altitude"] = round(registro["altitude"])
        registro["ficha"] = False
        registro["regiao"] = ""
        registro["confianca"] = "mapeado"

    registros.sort(key=lambda r: -r["altitude"])

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({
        "metadata": {
            "data_coleta": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(registros),
            "camada": "mapeada",
            "sources": ["OpenStreetMap"] + ([] if argumentos.so_osm else ["Wikidata"])
                       + (["Open-Elevation"] if argumentos.altitude else [])
                       + (["Nominatim"] if argumentos.municipios else []),
            "filtro_minimo": f"{argumentos.piso}m",
            "aviso": "Só nome, altitude e coordenada. Sem trilha, água ou pernoite conferidos.",
        },
        "mapeados": registros,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nGravado em {SAIDA}")
    acima500 = sum(1 for r in registros if r["altitude"] >= 500)
    print(f"  {acima500} acima de 500 m (o que o site mostra por padrão)")
    por_estado = {}
    for registro in registros:
        por_estado[registro["estado"]] = por_estado.get(registro["estado"], 0) + 1
    for estado, quantidade in sorted(por_estado.items()):
        print(f"  {estado}: {quantidade}")
    print("\nAgora rode:  python3 build.py")


if __name__ == "__main__":
    main()
