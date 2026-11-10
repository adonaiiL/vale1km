"""Vale1Km: constantes do domínio, compartilhadas por todos os scripts."""

NOME = "Vale1Km"

# Centro do domínio: ponto médio entre Blumenau e Pomerode (SC)
CENTRO = (-26.83, -49.12)  # (lat, lon)

# Quantos domínios o WRF usa (um só número para mudar):
#   2 = d01 de 5 km como "ponte" (não é plotado) + d02 de 1 km, que é o produto. Recomendado: o ICON tem ~13 km,
#       e alimentar 1 km direto com ele (razão 13:1) piora o resultado.
#   1 = um único domínio de 1 km alimentado direto pelo ICON (mais barato e menos preciso).
N_DOM = 2

D01 = dict(dx=5000, e_we=102, e_sn=102)                     # 101 x 101 células (505 km)
D02 = dict(dx=1000, e_we=96, e_sn=76, i0=42, j0=44, razao=5)  # 95 x 75 células (95 x 75 km), centrado em D01
D_UNICO = dict(dx=1000, e_we=141, e_sn=121)                 # 140 x 120 km, direto do ICON (N_DOM = 1)
NIVEIS_VERT = 60

DOMINIOS = [D01, D02] if N_DOM == 2 else [D_UNICO]
FINO = "d%02d" % len(DOMINIOS)  # sufixo do domínio de 1 km nos arquivos do WRF (d02 ou d01)
TRUELAT = (-24.0, -30.0)

# Recorte do ICON em lat/lon (graus): lon_min, lon_max, lat_min, lat_max
RECORTE = (-58.0, -40.0, -34.0, -19.0)

PONTOS = {
    "A": ("Adonai", -26.91468, -49.07622),
    "F": ("Fabrício", -26.760251, -49.184348),
    "K": ("Kelvin", -26.675419, -49.184906),
    "Ko": ("Komprão", -26.706956, -49.162766),
}

# Municípios destacados (código IBGE)
MUNICIPIOS = {"4202404": "Blumenau", "4213203": "Pomerode"}
# Sede de cada município (lat, lon): rótulo no mapa e conferência dos limites baixados
# Onde escrever o nome de cada município no mapa (lat, lon), longe dos pontos A, F, K e Ko; ajuste à vontade
ROTULOS_MUN = {"4202404": (-26.985, -49.085), "4213203": (-26.700, -49.100)}
SEDES = {"4202404": (-26.9194, -49.0661), "4213203": (-26.7406, -49.1769)}

# UH 2-5 km, hemisfério Sul: rotação ciclônica é negativa
UH_LIMIAR = -100.0  # m²/s², ajustado para 1 km

PASSO_CONTORNO_S = 10800  # condições de contorno a cada 3 h
SPINUP_PADRAO_H = 6
