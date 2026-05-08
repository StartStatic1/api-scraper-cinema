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
# CHAVE CORRIGIDA: h minúsculo para autenticação real 💎
ALLDEBRID_API = "hGt5I30bMYFLdhzDKZ06" 

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
    try:
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_EMAIL})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, timeout=20).json()
        for doc in r.get('response', {}).get('docs', []):
            id_ia = doc.get('identifier')
            if id_ia:
                catalogo_pessoal[limpar_texto(doc.get('title', id_ia))] = id_ia
                catalogo_pessoal[limpar_texto(id_ia)] = id_ia
        print("✅ Acervo Archive Sincronizado")
    except: print("❌ Falha Archive")

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
            print(f"✅ Listas M3U prontas")
        except: pass

carregar_acervo_pessoal()
carregar_m3u()

def buscar_alldebrid_vip(titulo, tmdb_id=None):
    """Tenta Torrentio (IMDB) e YTS. Aguarda o link ficar pronto."""
    magnets = []
    
    # 1. TORRENTIO (O melhor para AllDebrid)
    if tmdb_id:
        try:
            tm = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key=c90fb79a2f7d756a49bee848bce5f413").json()
            imdb_id = tm.get("imdb_id")
            if imdb_id:
                r_tor = requests.get(f"https://torrentio.strem.fun/stream/movie/{imdb_id}.json", timeout=10).json()
                for s in r_tor.get("streams", []):
                    if "infoHash" in s:
                        magnets.append(f"magnet:?xt=urn:btih:{s['infoHash']}")
                        break
        except: pass

    # 2. YTS
    if not magnets:
        try:
            r_yts = requests.get(f"https://yts.mx/api/v2/list_movies.json?query_term={urllib.parse.quote(titulo)}&limit=1", timeout=5).json()
            if r_yts.get("data", {}).get("movies"):
                magnets.append(f"magnet:?xt=urn:btih:{r_yts['data']['movies'][0]['torrents'][0]['hash']}")
        except: pass

    for mag in magnets:
        try:
            # Upload do Magnet
            up = requests.get(f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(mag)}").json()
            if up.get("status") == "success":
                m_id = up["data"]["magnets"][0]["id"]
                
                # Loop de verificação (espera até 6 segundos)
                for _ in range(6):
                    time.sleep(1)
                    st = requests.get(f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={m_id}").json()
                    m_data = st.get("data", {}).get("magnets", {}).get(str(m_id), {})
                    
                    if m_data.get("statusCode") == 4: # Status 4 = Pronto
                        links = m_data.get("links", [])
                        if links:
                            un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(links[0]['link'])}").json()
                            if un.get("status") == "success":
                                return un["data"]["link"]
                    elif m_data.get("statusCode") > 4: break # Erro no Torrent
        except: continue
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    if not titulo: return "Vazio", 400
    
    t_busca = limpar_texto(titulo)
    
    # 🥇 1. ARCHIVE (SEU ACERVO)
    if t_busca in catalogo_pessoal:
        id_ia = catalogo_pessoal[t_busca]
        r = requests.get(f"https://archive.org/metadata/{id_ia}").json()
        for f in r.get("files", []):
            if f.get("name", "").lower().endswith(('.mp4', '.mkv')):
                return redirect(f"https://archive.org/download/{id_ia}/{urllib.parse.quote(f.get('name'))}")

    # 🥈 2. ALLDEBRID VIP (FORÇADO)
    # Com a chave corrigida (h minúsculo), ele vai destravar o torrent agora.
    link_vip = buscar_alldebrid_vip(t_busca, tmdb_id)
    if link_vip:
        res = make_response(redirect(link_vip))
        res.headers['Access-Control-Allow-Origin'] = '*'
        return res

    # 🥉 3. ZEROHOP (M3U)
    if t_busca in catalogo_filmes:
        return redirect(catalogo_filmes[t_busca][0])
    
    if tmdb_id:
        return redirect(f"https://vidsrc.to/embed/movie/{tmdb_id}")
    
    return "Não encontrado", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
