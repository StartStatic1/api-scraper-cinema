import os
import re
import time
import requests
import urllib.parse
from flask import Flask, request, redirect, jsonify
from flask_cors import CORS
from rapidfuzz import fuzz

app = Flask(__name__)
CORS(app)

# ====== CONFIGURAÇÕES DO MESTRE ======
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]
UPLOADER_USER = "cinemega"
TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Bancos de dados em memória
catalogo_pessoal = [] # Itens do Archive
catalogo_m3u = {}     # Itens das Listas M3U

def limpar_string(texto):
    if not texto: return ""
    texto = re.sub(r'\[.*?\]|\(.*?\)', '', texto) # Remove [Dublado], (720p) etc
    texto = re.sub(r'[^a-zA-Z0-9\s]', '', texto.lower())
    return texto.strip()

def carregar_dados():
    global catalogo_pessoal, catalogo_m3u
    # 1. CARREGAR ARCHIVE.ORG
    try:
        url_arc = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_arc, timeout=20).json()
        catalogo_pessoal = r.get('response', {}).get('docs', [])
        print(f"✅ Archive: {len(catalogo_pessoal)} itens.")
    except: print("❌ Erro Archive")

    # 2. CARREGAR LISTAS M3U (O que te salva!)
    catalogo_m3u = {} # Limpa para atualizar
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, timeout=20).text
            nome = None
            for linha in r.splitlines():
                if linha.startswith("#EXTINF"):
                    # Extrai o nome após a última vírgula
                    nome_raw = linha.split(",")[-1]
                    nome = limpar_string(nome_raw)
                elif linha.startswith("http") and nome:
                    catalogo_m3u[nome] = linha
                    nome = None
            print(f"✅ Lista M3U Carregada: {url.split('/')[-1]}")
        except: print(f"❌ Erro na lista: {url}")

# Inicializa os dados
carregar_dados()

def buscar_archive(titulo_busca):
    t_limpo = limpar_string(titulo_busca)
    melhor_match = None
    score_alto = 0
    for item in catalogo_pessoal:
        titulo_item = limpar_string(item.get('title', ''))
        score = fuzz.token_set_ratio(t_limpo, titulo_item)
        if score > score_alto and score > 75:
            score_alto = score
            melhor_match = item
    
    if melhor_match:
        ident = melhor_match['identifier']
        try:
            meta = requests.get(f"https://archive.org/metadata/{ident}", timeout=10).json()
            for f in meta.get('files', []):
                if f['name'].lower().endswith(('.mp4', '.mkv', '.avi')):
                    return f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
        except: pass
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo: return jsonify({"erro": "Título vazio"}), 400

    titulo_busca = limpar_string(titulo)

    # 1. PRIORIDADE: SEU ACERVO RARO (Archive)
    link_archive = buscar_archive(titulo)
    if link_archive:
        return jsonify({"link_direto": link_archive, "fonte": "Archive Raro"})

    # 2. SEGUNDA OPÇÃO: LISTAS M3U (Onde estão os filmes comuns)
    # Procura por similaridade nas chaves do dicionário M3U
    melhor_m3u = None
    max_score = 0
    for nome_m3u in catalogo_m3u.keys():
        score = fuzz.ratio(titulo_busca, nome_m3u)
        if score > max_score and score > 80:
            max_score = score
            melhor_m3u = nome_m3u

    if melhor_m3u:
        return jsonify({"link_direto": catalogo_m3u[melhor_m3u], "fonte": "Lista IPTV/M3U"})

    return jsonify({"erro": "Não encontrado"}), 404

@app.route("/reload")
def reload():
    carregar_dados()
    return "Banco de dados sincronizado!"

if __name__ == "__main__":
    # Roda na porta 8000 para o Render ou local
    app.run(host="0.0.0.0", port=8000)
