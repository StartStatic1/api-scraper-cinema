import os
import re
import time
import json
import queue
import requests
import threading
import urllib.parse
import unicodedata
from rapidfuzz import fuzz
from flask import Flask, request, redirect, jsonify

# CORREÇÃO: __name__ com sublinhados duplos
app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================

LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]

# CORREÇÃO: Uploader correto para não dar 'archive: 0'
UPLOADER_USER = "cinemega" 
ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"
TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://archive.org/"
}

# CACHES
cache_tmdb, cache_busca, cache_archive, cache_debrid = {}, {}, {}, {}
catalogo_pessoal, catalogo_filmes = {}, {}

# =========================================================
# NORMALIZAÇÃO (CORRIGIDA)
# =========================================================

def limpar_texto(texto):
    if not texto: return ""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("utf-8").lower()
    # Limpa colchetes e parênteses corretamente
    texto = re.sub(r'\[[^\]]*\]', ' ', texto)
    texto = re.sub(r'\([^)]*\)', ' ', texto)
    
    lixo = ["dublado", "dual audio", "1080p", "720p", "4k", "bluray", "webdl", "torrent", "oficial"]
    for l in lixo: texto = texto.replace(l, " ")
    
    texto = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()

# =========================================================
# MATCH & BUSCA
# =========================================================

def melhor_match(busca, catalogo, minimo=80):
    melhor, score_final = None, 0
    for titulo in catalogo:
        score = fuzz.ratio(busca, titulo)
        if score > score_final:
            score_final = score
            melhor = titulo
    return melhor if score_final >= minimo else None

def buscar_archive(titulo):
    match = melhor_match(titulo, catalogo_pessoal)
    if not match: return None
    ident = catalogo_pessoal[match]
    
    if ident in cache_archive: return cache_archive[ident]
    try:
        r = requests.get(f"https://archive.org/metadata/{ident}", timeout=20).json()
        for f in r.get("files", []):
            if f.get("name", "").lower().endswith(('.mp4', '.mkv', '.avi')):
                link = f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
                cache_archive[ident] = link
                return link
    except: pass
    return None

def buscar_debrid(titulo, tmdb_id=""):
    try:
        termos = [titulo]
        if tmdb_id:
            tm = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}").json()
            if tm.get("imdb_id"): termos.insert(0, tm["imdb_id"])
        
        for t in termos:
            url = f"https://api.alldebrid.com/v4/magnets/instant?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(t)}"
            inst = requests.get(url, timeout=30).json()
            if inst.get("status") == "success" and inst["data"]["magnets"][0]["instant"]:
                h = inst["data"]["magnets"][0]["hash"]
                up = requests.get(f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote('magnet:?xt=urn:btih:'+h)}").json()
                mid = up["data"]["magnets"][0]["id"]
                time.sleep(2)
                st = requests.get(f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={mid}").json()
                link = st["data"]["magnets"][str(mid)]["links"][0]["link"]
                un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(link)}").json()
                return un["data"]["link"]
    except: pass
    return None

# =========================================================
# ENGINE MULTI-THREAD
# =========================================================

def motor_busca(titulo, tmdb_id=""):
    res_q = queue.Queue()
    
    # Prioridade Archive (Seu Acervo)
    def t_arc():
        link = buscar_archive(titulo)
        if link: res_q.put(link)
    
    # Failovers
    def t_deb():
        link = buscar_debrid(titulo, tmdb_id)
        if link: res_q.put(link)

    threads = [threading.Thread(target=t_arc), threading.Thread(target=t_deb)]
    for t in threads: t.start()
    
    start = time.time()
    while time.time() - start < 15:
        if not res_q.empty(): return res_q.get()
        time.sleep(0.5)
    return None

# =========================================================
# CARREGAMENTO INICIAL
# =========================================================

def carregar_tudo():
    global catalogo_pessoal, catalogo_filmes
    # Archive
    try:
        r = requests.get(f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000", timeout=30).json()
        catalogo_pessoal = {limpar_texto(d.get('title', d['identifier'])): d['identifier'] for d in r['response']['docs']}
        print(f"✅ Archive: {len(catalogo_pessoal)}")
    except: print("❌ Erro Archive")
    
    # M3U
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30).text
            nome = None
            for l in r.splitlines():
                if l.startswith("#EXTINF"): nome = limpar_texto(l.split(",")[-1])
                elif l.startswith("http") and nome:
                    if nome not in catalogo_filmes: catalogo_filmes[nome] = []
                    catalogo_filmes[nome].append(l); nome = None
        except: pass

carregar_tudo()

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "").strip()
    tmdb_id = request.args.get("id", "").strip()
    if not titulo: return jsonify({"erro": "vazio"}), 400
    
    link = motor_busca(limpar_texto(titulo), tmdb_id)
    if link: return redirect(link)
    
    if tmdb_id: return redirect(f"https://embed.su/embed/movie/{tmdb_id}")
    return jsonify({"erro": "nao encontrado"}), 404

@app.route("/")
def home():
    return jsonify({"status": "online", "archive": len(catalogo_pessoal), "m3u": len(catalogo_filmes)})

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=PORT, threaded=True)
