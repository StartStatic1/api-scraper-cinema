import os
import re
import requests
import urllib.parse
import unicodedata
from flask import Flask, request, redirect, jsonify, make_response

app = Flask(__name__)

# MESTRE: Suas listas integradas
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]

# Nome de Usuário Público do seu Archive.org
UPLOADER_USER = "rafaela_andrea_ferrada_flores"

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
        print(f"✅ Acervo Pessoal: {len(catalogo_pessoal)} títulos")
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
            print(f"✅ Lista OK: {url}")
        except: pass

# Carga inicial
carregar_acervo_pessoal()
carregar_m3u()

def obter_link_direto_ia(identifier):
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        arquivos = r.get("files", [])
        
        # PRIORIDADE: Formato que roda direto no player (H.264 / MP4)
        for f in arquivos:
            nome = f.get("name", "").lower()
            formato = f.get("format", "").lower()
            if nome.endswith('.mp4') and ("h.264" in formato or "h264" in formato or "mpeg4" in formato):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
        
        # SEGUNDA OPÇÃO: Qualquer MP4
        for f in arquivos:
            nome = f.get("name", "").lower()
            if nome.endswith('.mp4'):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
    except: pass
    return None

def testar_link(url):
    """Simula o player VLC para testar se o link M3U retorna 403 (lotado)"""
    try:
        headers = {'User-Agent': 'VLC/3.0.16 LibVLC/3.0.16'}
        # Faz um GET parcial (apenas cabeçalho) para não consumir banda
        r = requests.get(url, headers=headers, stream=True, timeout=3)
        status = r.status_code
        r.close()
        return status in [200, 206, 301, 302]
    except: return False

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    if not titulo: return "Título vazio", 400
    
    titulo_busca = limpar_texto(titulo)
    link = None
    
    # 🔍 1. TENTA NO SEU ACERVO (IA) - PRIORIDADE 1
    if titulo_busca in catalogo_pessoal:
        link = obter_link_direto_ia(catalogo_pessoal[titulo_busca])
    
    # 🔍 2. BUSCA NO SEU ACERVO (CONTÉM) - Para títulos longos no Archive
    if not link:
        for nome_ia, id_ia in catalogo_pessoal.items():
            if titulo_busca in nome_ia:
                link = obter_link_direto_ia(id_ia)
                if link: break

    # 🔍 3. FAILOVER M3U (Pula links 403/Lotados)
    if not link and titulo_busca in catalogo_filmes:
        links_m3u = catalogo_filmes[titulo_busca]
        for l in links_m3u:
            if testar_link(l):
                link = l
                break
        if not link: link = links_m3u[0] # Se todos derem 403, joga o primeiro

    # 🔍 4. BUSCA APROXIMADA NA M3U
    if not link and len(titulo_busca) > 4:
        for nome_cat, links in catalogo_filmes.items():
            if titulo_busca in nome_cat:
                for l in links:
                    if testar_link(l):
                        link = l
                        break
                if link: break

    # 🚀 5. MODO PRO (EMBED GLOBAL) - SE TUDO ACIMA FALHAR
    if not link:
        # Se falhou tudo, redireciona para um servidor que não tem limite de conexão
        return redirect(f"https://vidsrc.me/embed/movie?tmdb={tmdb_id if tmdb_id else titulo_busca}")

    if link:
        response = make_response(redirect(link))
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    return jsonify({"status": "erro", "procurado": titulo_busca}), 404

@app.route("/atualizar")
def atualizar():
    carregar_acervo_pessoal(); carregar_m3u()
    return jsonify({"status": "sucesso", "ia": len(catalogo_pessoal), "m3u": len(catalogo_filmes)})

@app.route("/")
def index():
    return f"🚀 Sniper Online | Acervo IA: {len(catalogo_pessoal)} | Filmes M3U: {len(catalogo_filmes)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
