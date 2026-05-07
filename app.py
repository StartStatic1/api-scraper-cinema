import os
import re
import time
import json
import requests
import urllib.parse
import unicodedata
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# ====== CONFIGURAÇÕES DO MESTRE ======
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]
UPLOADER_USER = "cinemega"
ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"
TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

catalogo_pessoal = {}
catalogo_filmes = {}

def limpar_texto(texto):
    if not texto: return ""
    # Normaliza mas MANTÉM NÚMEROS (Importante para Lenda de Hei 2)
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("utf-8").lower()
    texto = re.sub(r'\[.*?\]|\(.*?\)', ' ', texto)
    # Remove apenas palavras que atrapalham, mas não números de sequência
    lixo = ["dublado", "dual", "1080p", "720p", "4k", "bluray", "webdl", "torrent", "completo"]
    for l in lixo: texto = texto.replace(l, " ")
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', texto).strip()

def carregar_dados():
    global catalogo_pessoal, catalogo_filmes
    try:
        url = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url, timeout=30).json()
        docs = r.get('response', {}).get('docs', [])
        catalogo_pessoal = {limpar_texto(doc.get('title', doc['identifier'])): doc['identifier'] for doc in docs if 'identifier' in doc}
        print(f"✅ Archive Carregado")
    except: print("❌ Erro Archive")
    
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, timeout=30).text
            nome = None
            for linha in r.splitlines():
                if linha.startswith("#EXTINF"): nome = limpar_texto(linha.split(",")[-1])
                elif linha.startswith("http") and nome:
                    if nome not in catalogo_filmes: catalogo_filmes[nome] = []
                    catalogo_filmes[nome].append(linha)
                    nome = None
        except: pass

carregar_dados()

def buscar_archive(titulo_limpo):
    melhor_t = None; melhor_score = 0
    for t in catalogo_pessoal:
        score = fuzz.token_sort_ratio(titulo_limpo, t) # Melhor para sequências
        if score > melhor_score: melhor_score = score; melhor_t = t
    if melhor_score < 80: return None # Score mais alto para não confundir Hei 1 com Hei 2
    ident = catalogo_pessoal[melhor_t]
    try:
        meta = requests.get(f"https://archive.org/metadata/{ident}", timeout=10).json()
        for f in meta.get('files', []):
            if f['name'].lower().endswith('.mp4'):
                return f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
    except: pass
    return None

def processar_alldebrid(tmdb_id):
    if not tmdb_id: return None
    try:
        # Busca ID IMDB exato para não errar o filme
        tm = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}").json()
        imdb_id = tm.get("imdb_id")
        if not imdb_id: return None

        url = f"https://torrentio.strem.fun/stream/movie/{imdb_id}.json"
        streams = requests.get(url, timeout=10).json().get("streams", [])
        for s in streams:
            h = s.get("infoHash")
            if not h: continue
            mag = f"magnet:?xt=urn:btih:{h}"
            chk = requests.get(f"https://api.alldebrid.com/v4/magnets/instant?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(mag)}").json()
            if chk.get("status") == "success" and chk["data"]["magnets"][0]["instant"]:
                up = requests.get(f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(mag)}").json()
                m_id = up["data"]["magnets"][0]["id"]
                st = requests.get(f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={m_id}").json()
                link = st["data"]["magnets"][str(m_id)]["links"][0]["link"]
                un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(link)}").json()
                return un["data"]["link"]
    except: pass
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    modo_json = request.args.get("modo") == "json"
    
    if not titulo: return "Vazio", 400
    t_limpo = limpar_texto(titulo)
    link = None

    # 1. ARCHIVE (Prioridade 1)
    link = buscar_archive(t_limpo)
    
    # 2. ALLDEBRID VIA IMDB_ID (Prioridade 2 - Anti-Erro de Sequência)
    if not link and tmdb_id:
        link = processar_alldebrid(tmdb_id)
        
    # 3. M3U
    if not link:
        for t in catalogo_filmes:
            if fuzz.ratio(t_limpo, t) > 85:
                link = catalogo_filmes[t][0]
                break

    if link:
        if modo_json: return jsonify({"link_direto": link})
        return redirect(link)
    
    return jsonify({"erro": "nao encontrado"}), 404

@app.route("/")
def home():
    return jsonify({"archive": len(catalogo_pessoal), "m3u": len(catalogo_filmes), "status": "online"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
