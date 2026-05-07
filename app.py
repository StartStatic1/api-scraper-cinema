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

# 🔑 O SEGREDO: Usamos o seu e-mail de uploader que apareceu no XML
UPLOADER_EMAIL = "rafflores17@gmail.com"

# 💎 SUA CHAVE PREMIUM ATIVADA
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
        # BUSCA PELO E-MAIL: Garante que pegue TUDO que é seu, independente do título
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_EMAIL})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, headers=headers, timeout=20).json()
        items = r.get('response', {}).get('docs', [])
        
        for doc in items:
            id_ia = doc.get('identifier')
            titulo_xml = doc.get('title', id_ia)
            
            if id_ia:
                # O PULO DO GATO: Registra o título (Braindead) E o ID (fome-animal)
                # Assim, se você buscar qualquer um dos dois, o motor acha!
                catalogo_pessoal[limpar_texto(titulo_xml)] = id_ia
                catalogo_pessoal[limpar_texto(id_ia)] = id_ia
                
        print(f"✅ Acervo Pessoal: {len(catalogo_pessoal)} títulos carregados (via {UPLOADER_EMAIL})")
    except: 
        print("❌ Erro Archive.org - Verifique a conexão")

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
            print(f"✅ Lista OK: {url}")
        except: pass

# Carga inicial
carregar_acervo_pessoal()
carregar_m3u()

def obter_link_direto_ia(identifier):
    try:
        # Pega os metadados do item específico
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        arquivos = r.get("files", [])
        
        # 1ª OPÇÃO: Busca o MP4 (H.264) que o Archive gera para streaming (melhor para celular)
        for f in arquivos:
            nome = f.get("name", "").lower()
            fmt = f.get("format", "").lower()
            if nome.endswith('.mp4') and ("h.264" in fmt or "h264" in fmt):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
        
        # 2ª OPÇÃO: Qualquer MP4 ou MKV se o primeiro falhar
        for f in arquivos:
            nome = f.get("name", "").lower()
            if nome.endswith(('.mp4', '.mkv')):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
    except: pass
    return None

def testar_link(url):
    try:
        headers = {'User-Agent': 'VLC/3.0.16 LibVLC/3.0.16'}
        r = requests.get(url, headers=headers, stream=True, timeout=3)
        status = r.status_code
        r.close()
        return status in [200, 206, 301, 302]
    except: return False

def buscar_alldebrid_pro(titulo):
    try:
        url_yts = f"https://yts.mx/api/v2/list_movies.json?query_term={urllib.parse.quote(titulo)}&limit=1"
        r_yts = requests.get(url_yts, timeout=5).json()
        if not r_yts.get("data", {}).get("movies"): return None
        
        magnet = f"magnet:?xt=urn:btih:{r_yts['data']['movies'][0]['torrents'][0]['hash']}"
        url_up = f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(magnet)}"
        r_up = requests.get(url_up, timeout=5).json()
        
        if r_up.get("status") != "success": return None
        m_id = r_up["data"]["magnets"][0]["id"]
        time.sleep(2)
        
        url_st = f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={m_id}"
        r_st = requests.get(url_st, timeout=5).json()
        links = r_st.get("data", {}).get("magnets", {}).get(str(m_id), {}).get("links", [])
        if not links: return None
        
        url_un = f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(links[0]['link'])}"
        r_un = requests.get(url_un, timeout=5).json()
        
        if r_un.get("status") == "success":
            return r_un["data"]["link"]
        return None
    except: return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    if not titulo: return "Título vazio", 400
    
    t_busca = limpar_texto(titulo)
    link = None
    
    # 🥇 1. SEU ACERVO (IA) - PRIORIDADE ABSOLUTA
    if t_busca in catalogo_pessoal:
        link = obter_link_direto_ia(catalogo_pessoal[t_busca])
    
    # Busca parcial se a exata falhar
    if not link:
        for n_ia, i_ia in catalogo_pessoal.items():
            if t_busca in n_ia or n_ia in t_busca:
                link = obter_link_direto_ia(i_ia)
                if link: break

    # 🥈 2. ALLDEBRID (MODO PRO)
    if not link:
        link = buscar_alldebrid_pro(t_busca)

    # 🥉 3. FAILOVER M3U
    if not link and t_busca in catalogo_filmes:
        for l in catalogo_filmes[t_busca]:
            if testar_link(l):
                link = l
                break
        if not link: link = catalogo_filmes[t_busca][0]

    if link:
        res = make_response(redirect(link))
        res.headers['Access-Control-Allow-Origin'] = '*'
        return res
    
    # 🎬 4. FALLBACK FINAL (Ok.ru / Vidsrc)
    if tmdb_id and tmdb_id.isdigit():
        return redirect(f"https://m.ok.ru/video/movie?tmdb={tmdb_id}")
    else:
        return "Filme não encontrado.", 404

@app.route("/atualizar")
def atualizar():
    carregar_acervo_pessoal(); carregar_m3u()
    return jsonify({"status": "sucesso", "ia": len(catalogo_pessoal), "m3u": len(catalogo_filmes)})

@app.route("/")
def index():
    return f"🚀 Cine Mega PRO | IA: {len(catalogo_pessoal)} | M3U: {len(catalogo_filmes)} | Uploader: {UPLOADER_EMAIL}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
