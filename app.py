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
ALLDEBRID_API = "hGt5I30bMYFLdhzDKZ06" 

# link RAW do seu repositório
URL_BANCO_DE_CHAVES = "https://raw.githubusercontent.com/StartStatic1/cine-mega-mobile/main/chaves_vip.txt"

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
    except: pass

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
        except: pass

carregar_acervo_pessoal()
carregar_m3u()

def obter_link_archive(identifier):
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        arquivos = r.get("files", [])
        for f in arquivos:
            nome = f.get("name", "")
            if nome.lower().endswith('.mp4'):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(nome)}"
        for f in arquivos:
            nome = f.get("name", "")
            if nome.lower().endswith('.mkv'):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(nome)}"
    except: pass
    return None

def buscar_alldebrid_vip(titulo, tmdb_id=None):
    magnets = []
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

    if not magnets:
        try:
            r_yts = requests.get(f"https://yts.mx/api/v2/list_movies.json?query_term={urllib.parse.quote(titulo)}&limit=1").json()
            if r_yts.get("data", {}).get("movies"):
                magnets.append(f"magnet:?xt=urn:btih:{r_yts['data']['movies'][0]['torrents'][0]['hash']}")
        except: pass

    for mag in magnets:
        try:
            up = requests.get(f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(mag)}").json()
            if up.get("status") == "success":
                m_id = up["data"]["magnets"][0].get("id")
                for _ in range(5):
                    time.sleep(1)
                    st = requests.get(f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={m_id}").json()
                    m_data = st.get("data", {}).get("magnets", {}).get(str(m_id), {})
                    if m_data.get("statusCode") == 4:
                        links = m_data.get("links", [])
                        if links:
                            un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(links[0]['link'])}").json()
                            if un.get("status") == "success":
                                return un["data"]["link"]
        except: continue
    return None

# ==========================================
# 🔐 VALIDAÇÃO VIP (COM QUEBRA DE CACHE NO SERVIDOR)
# ==========================================
@app.route("/validar")
def validar_chave():
    chave_recebida = request.args.get("key", "").strip()
    
    # Chave Mestra
    if chave_recebida == "MESTRE-2026":
        return jsonify({"status": "sucesso"}), 200, {'Access-Control-Allow-Origin': '*'}

    try:
        # Forçamos o GitHub a ignorar o cache usando um parâmetro de tempo (?t=...)
        # E enviamos headers de controle para garantir a leitura real
        headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
        url_fresca = f"{URL_BANCO_DE_CHAVES}?t={int(time.time())}"
        
        req = requests.get(url_fresca, headers=headers, timeout=10)
        chaves_ativas = [linha.strip() for linha in req.text.split('\n') if linha.strip()]
        
        if chave_recebida in chaves_ativas:
            return jsonify({"status": "sucesso"}), 200, {'Access-Control-Allow-Origin': '*'}
        else:
            return jsonify({"status": "erro"}), 200, {'Access-Control-Allow-Origin': '*'}
            
    except Exception:
        # Se houver erro de rede com o GitHub, retorna erro por segurança
        return jsonify({"status": "erro"}), 200, {'Access-Control-Allow-Origin': '*'}

# ==========================================
# ROTA INICIAL
# ==========================================
@app.route("/")
def home():
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Status - Motor Cine Mega</title>
        <style>
            body {{ background: #050505; color: #fff; font-family: sans-serif; text-align: center; padding-top: 50px; }}
            h1 {{ color: #e50914; }}
            .card {{ background: #111; border: 1px solid #333; border-radius: 10px; padding: 20px; display: inline-block; margin: 10px; min-width: 250px; }}
            .num {{ font-size: 30px; font-weight: bold; color: #ffcc00; display: block; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <h1>MOTOR CINE MEGA PRO - ONLINE</h1>
        <div class="card">🎬 Acervo Archive <span class="num">{len(catalogo_pessoal)}</span></div>
        <div class="card">📺 Acervo M3U <span class="num">{len(catalogo_filmes)}</span></div>
        <br><br><p style="color:#666; font-size:12px;">Desenvolvido por: @StartStatic</p>
    </body>
    </html>
    """
    return html

# ==========================================
# ROTA DE BUSCA E AVISO
# ==========================================
@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    tipo = request.args.get("tipo", "filme")
    if not titulo: return "Vazio", 400
    t_busca = limpar_texto(titulo)
    if t_busca in catalogo_pessoal:
        link = obter_link_archive(catalogo_pessoal[t_busca])
        if link: return redirect(link)
    link_vip = buscar_alldebrid_vip(t_busca, tmdb_id)
    if link_vip: return redirect(link_vip, code=302, Response=make_response().headers.add('Access-Control-Allow-Origin', '*'))
    if t_busca in catalogo_filmes: return redirect(catalogo_filmes[t_busca][0])
    if tmdb_id:
        prefixo = "serie" if tipo == "serie" else "filme"
        return redirect(f"https://myembed.biz/{prefixo}/{tmdb_id}")
    return redirect("/aguarde")

@app.route("/aguarde")
def aguarde():
    return """<body style="background:#000;color:#fff;text-align:center;padding-top:100px;"><h1>Processando...</h1><p>CINE MEGA OFICIAL</p></body>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
