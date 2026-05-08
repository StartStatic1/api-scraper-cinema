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

UPLOADER_EMAIL = "rafflores17@gmail.com"
ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"

catalogo_pessoal = {}
catalogo_filmes = {}

def limpar_texto(texto):
    if not texto: return ""
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
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_EMAIL})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, headers=headers, timeout=20).json()
        items = r.get('response', {}).get('docs', [])
        for doc in items:
            id_ia = doc.get('identifier')
            titulo_xml = doc.get('title', id_ia)
            if id_ia:
                catalogo_pessoal[limpar_texto(titulo_xml)] = id_ia
                catalogo_pessoal[limpar_texto(id_ia)] = id_ia
        print(f"✅ Acervo Pessoal OK")
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
                    if ultimo_nome not in catalogo_filmes: catalogo_filmes[ultimo_nome] = []
                    catalogo_filmes[ultimo_nome].append(l)
                    ultimo_nome = None
            print(f"✅ Lista M3U OK")
        except: pass

carregar_acervo_pessoal()
carregar_m3u()

def obter_link_direto_ia(identifier):
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        arquivos = r.get("files", [])
        for f in arquivos:
            nome = f.get("name", "").lower()
            fmt = f.get("format", "").lower()
            if nome.endswith('.mp4') and ("h.264" in fmt or "h264" in fmt):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
        for f in arquivos:
            nome = f.get("name", "").lower()
            if nome.endswith(('.mp4', '.mkv')):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
    except: pass
    return None

def buscar_alldebrid_reforcado(titulo, tmdb_id=None):
    """Tenta YTS e depois Torrentio (Stremio) para garantir o play"""
    magnets = []
    
    # Fonte 1: YTS
    try:
        url_yts = f"https://yts.mx/api/v2/list_movies.json?query_term={urllib.parse.quote(titulo)}&limit=1"
        r_yts = requests.get(url_yts, timeout=5).json()
        if r_yts.get("data", {}).get("movies"):
            magnets.append(f"magnet:?xt=urn:btih:{r_yts['data']['movies'][0]['torrents'][0]['hash']}")
    except: pass

    # Fonte 2: Torrentio (Se tiver o ID do TMDB, a chance de erro é zero)
    if not magnets and tmdb_id:
        try:
            # Busca ID do IMDB via TMDB
            tm = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key=c90fb79a2f7d756a49bee848bce5f413").json()
            imdb_id = tm.get("imdb_id")
            if imdb_id:
                r_tor = requests.get(f"https://torrentio.strem.fun/stream/movie/{imdb_id}.json", timeout=5).json()
                for s in r_tor.get("streams", []):
                    if "infoHash" in s:
                        magnets.append(f"magnet:?xt=urn:btih:{s['infoHash']}")
                        break
        except: pass

    for mag in magnets:
        try:
            # Manda pro AllDebrid
            url_up = f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(mag)}"
            r_up = requests.get(url_up, timeout=5).json()
            if r_up.get("status") == "success":
                m_id = r_up["data"]["magnets"][0]["id"]
                time.sleep(2.5) # Aguarda processamento
                r_st = requests.get(f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={m_id}").json()
                links = r_st.get("data", {}).get("magnets", {}).get(str(m_id), {}).get("links", [])
                if links:
                    r_un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(links[0]['link'])}").json()
                    if r_un.get("status") == "success":
                        return r_un["data"]["link"]
        except: continue
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    if not titulo: return "Título vazio", 400
    
    t_busca = limpar_texto(titulo)
    link = None
    
    # 1. SEU ACERVO (Archive.org)
    if t_busca in catalogo_pessoal:
        link = obter_link_direto_ia(catalogo_pessoal[t_busca])
    
    if not link:
        for n_ia, i_ia in catalogo_pessoal.items():
            if t_busca in n_ia or n_ia in t_busca:
                link = obter_link_direto_ia(i_ia)
                if link: break

    # 2. ALLDEBRID REFORÇADO (Tenta YTS + Torrentio)
    if not link:
        link = buscar_alldebrid_reforcado(t_busca, tmdb_id)

    # 3. FAILOVER M3U (Última opção para evitar Max Connection do Zerohop)
    if not link and t_busca in catalogo_filmes:
        link = catalogo_filmes[t_busca][0]

    if link:
        res = make_response(redirect(link))
        res.headers['Access-Control-Allow-Origin'] = '*'
        return res
    
    if tmdb_id:
        return redirect(f"https://vidsrc.to/embed/movie/{tmdb_id}")
    return "Não encontrado.", 404

@app.route("/atualizar")
def atualizar():
    carregar_acervo_pessoal(); carregar_m3u()
    return jsonify({"status": "sucesso", "ia": len(catalogo_pessoal), "m3u": len(catalogo_filmes)})

@app.route("/")
def index():
    return f"🚀 Cine Mega PRO | IA: {len(catalogo_pessoal)} | M3U: {len(catalogo_filmes)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
