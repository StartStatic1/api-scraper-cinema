import os
import re
import requests
import urllib.parse
import unicodedata
import time
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

catalogo_pessoal = {}
catalogo_filmes = {}

def limpar_texto(texto):
    t = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8')
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado|completo|filmes|filme)', '', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_acervo_pessoal():
    global catalogo_pessoal
    catalogo_pessoal = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, headers=headers, timeout=20).json()
        items = r.get('response', {}).get('docs', [])
        for doc in items:
            id_ia = doc.get('identifier')
            titulo = doc.get('title', id_ia)
            if id_ia:
                catalogo_pessoal[limpar_texto(titulo)] = id_ia
        print("✅ Acervo Pessoal OK")
    except: print("❌ Erro Archive.org")

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {} 
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, stream=True, timeout=60)
            ultimo_nome = None 
            for linha in r.iter_lines():
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                if l.startswith("#EXTINF"):
                    ultimo_nome = limpar_texto(l.split(",")[-1])
                elif l.startswith("http") and ultimo_nome:
                    if ultimo_nome not in catalogo_filmes:
                        catalogo_filmes[ultimo_nome] = []
                    catalogo_filmes[ultimo_nome].append(l)
                    ultimo_nome = None
        except: pass

carregar_acervo_pessoal()
carregar_m3u()

def obter_link_direto_ia(identifier):
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        for f in r.get("files", []):
            if f.get("name", "").lower().endswith('.mp4'):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
    except: pass
    return None

def testar_link(url):
    try:
        r = requests.get(url, headers={'User-Agent': 'VLC/3.0.16'}, stream=True, timeout=3)
        return r.status_code in [200, 206, 301, 302]
    except: return False

def buscar_alldebrid_pro(titulo, id_tmdb=""):
    if not ALLDEBRID_API: return None
    try:
        termos = [titulo]
        if id_tmdb:
            # Puxa o ID do IMDB para busca infalível
            tm = requests.get(f"https://api.themoviedb.org/3/movie/{id_tmdb}?api_key={TMDB_API_KEY}").json()
            if tm.get("original_title"): termos.append(tm["original_title"])
            if tm.get("imdb_id"): termos.append(tm["imdb_id"])

        for t in termos:
            # Busca torrent
            yts = requests.get(f"https://yts.mx/api/v2/list_movies.json?query_term={urllib.parse.quote(t)}&limit=1").json()
            if yts.get("data", {}).get("movies"):
                mag = f"magnet:?xt=urn:btih:{yts['data']['movies'][0]['torrents'][0]['hash']}"
                # Sobe pro AllDebrid
                up = requests.get(f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(mag)}").json()
                if up.get("status") == "success":
                    m_id = up["data"]["magnets"][0]["id"]
                    time.sleep(3.5) # Tempo para processar filme antigo
                    st = requests.get(f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={m_id}").json()
                    links = st.get("data", {}).get("magnets", {}).get(str(m_id), {}).get("links", [])
                    if links:
                        un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(links[0]['link'])}").json()
                        return un.get("data", {}).get("link")
        return None
    except: return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    if not titulo: return "Título vazio", 400
    
    t_busca = limpar_texto(titulo)
    link = None
    
    # 1. ACERVO IA
    if t_busca in catalogo_pessoal: link = obter_link_direto_ia(catalogo_pessoal[t_busca])
    
    # 2. ALLDEBRID (AGORA COMO PRIORIDADE ANTES DA M3U)
    if not link: link = buscar_alldebrid_pro(t_busca, tmdb_id)

    # 3. M3U FAILOVER
    if not link and t_busca in catalogo_filmes:
        for l in catalogo_filmes[t_busca]:
            if testar_link(l): link = l; break
        if not link: link = catalogo_filmes[t_busca][0]

    if link:
        res = make_response(redirect(link))
        res.headers['Access-Control-Allow-Origin'] = '*'
        return res
    
    # 4. ÚLTIMA OPÇÃO (O PLAYER RUIM COM PROPAGANDA)
    if tmdb_id: return redirect(f"https://vidsrc.to/embed/movie/{tmdb_id}")
    return "404", 404

@app.route("/atualizar")
def atualizar():
    carregar_acervo_pessoal(); carregar_m3u()
    return jsonify({"status": "ok"})

@app.route("/")
def index():
    return f"🚀 Sniper PRO Ativo | IA: {len(catalogo_pessoal)} | M3U: {len(catalogo_filmes)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
