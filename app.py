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
from flask import Flask, request, redirect, jsonify, make_response

app = Flask(__name__)

# ====== CONFIGURAÇÕES DO MESTRE ======
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]
UPLOADER_USER = "rafaela_andrea_ferrada_flores"
ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"
TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

catalogo_pessoal = {}
catalogo_filmes = {}

def limpar_texto(texto):
    if not texto: return ""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("utf-8").lower()
    t = re.sub(r'\[.*?\]|\(.*?\)', ' ', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', ' ', t)
    return " ".join(t.split()).strip()

def carregar_dados():
    global catalogo_pessoal, catalogo_filmes
    # Archive
    try:
        url = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url, timeout=30).json()
        catalogo_pessoal = {limpar_texto(doc.get('title', doc['identifier'])): doc['identifier'] for doc in r.get('response', {}).get('docs', [])}
    except: pass
    # M3U
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, timeout=30).text
            nome = None
            for linha in r.splitlines():
                if linha.startswith("#EXTINF"): nome = limpar_texto(linha.split(",")[-1])
                elif linha.startswith("http") and nome:
                    if nome not in catalogo_filmes: catalogo_filmes[nome] = []
                    catalogo_filmes[nome].append(linha); nome = None
        except: pass

carregar_dados()

def buscar_archive(titulo):
    melhor_t = None; melhor_score = 0
    for t in catalogo_pessoal:
        score = fuzz.ratio(titulo, t)
        if score > melhor_score: melhor_score = score; melhor_t = t
    if melhor_score < 80: return None
    ident = catalogo_pessoal[melhor_t]
    try:
        meta = requests.get(f"https://archive.org/metadata/{ident}").json()
        for f in meta.get('files', []):
            if f.get('name', '').lower().endswith(('.mp4', '.mkv')):
                return f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
    except: pass
    return None

def buscar_debrid(titulo, tmdb_id=""):
    try:
        termos = [titulo]
        if tmdb_id:
            tm = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}").json()
            if tm.get("imdb_id"): termos.insert(0, tm["imdb_id"])
        for t in termos:
            inst = requests.get(f"https://api.alldebrid.com/v4/magnets/instant?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(t)}").json()
            if inst.get("status") == "success" and inst["data"]["magnets"][0]["instant"]:
                mag = f"magnet:?xt=urn:btih:{inst['data']['magnets'][0]['hash']}"
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
    if not titulo: return "Vazio", 400
    t_limpo = limpar_texto(titulo)
    
    # 1. Archive | 2. Debrid | 3. M3U
    link = buscar_archive(t_limpo)
    if not link: link = buscar_debrid(t_limpo, tmdb_id)
    if not link:
        for t in catalogo_filmes:
            if fuzz.ratio(t_limpo, t) > 85: link = catalogo_filmes[t][0]; break

    if link: return redirect(link)
    if tmdb_id: return redirect(f"https://embed.su/embed/movie/{tmdb_id}")
    return "Não encontrado", 404

@app.route("/")
def home(): return jsonify({"archive": len(catalogo_pessoal), "m3u": len(catalogo_filmes)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
