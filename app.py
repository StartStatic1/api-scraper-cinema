import os
import re
import requests
import urllib.parse
import unicodedata
from flask import Flask, request, redirect, jsonify, make_response, Response

app = Flask(__name__)

# MESTRE: Mantive sua lista e uploader
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u"
]
UPLOADER_IA = "rafaela_andrea_ferrada_flores"

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
    try:
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_IA})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, timeout=15).json()
        for doc in r.get('response', {}).get('docs', []):
            id_ia = doc.get('identifier')
            titulo = doc.get('title', id_ia)
            catalogo_pessoal[limpar_texto(titulo)] = id_ia
    except: pass

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, stream=True, timeout=60)
            it = r.iter_lines()
            contador = 0
            for linha in it:
                if contador > 160000: break
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                if l.startswith("#EXTINF"):
                    nome_limpo = limpar_texto(l.split(",")[-1])
                    try:
                        link = next(it).decode('utf-8', errors='ignore').strip()
                        if link.startswith("http") and nome_limpo not in catalogo_filmes:
                            catalogo_filmes[nome_limpo] = link
                            contador += 1
                    except StopIteration: break
        except: pass

# Carga inicial
carregar_acervo_pessoal()
carregar_m3u()

# --- MOTOR PROXY CAMALEÃO (NOVO) ---
@app.route("/stream")
def proxy_stream():
    """ Rota que disfarça o site como ExoPlayer para burlar bloqueios """
    video_url = request.args.get('url')
    if not video_url: return "URL vazia", 400
    
    # O DISFARCE DE MESTRE (ExoPlayer)
    headers = {
        'User-Agent': 'ExoPlayerDemo/2.17.1 (Linux;Android 11) ExoPlayerLib/2.17.1',
        'Referer': video_url
    }
    
    try:
        # Faz a requisição ao servidor de IPTV original
        req = requests.get(video_url, headers=headers, stream=True, timeout=15)
        
        # Repassa o vídeo em pedaços (chunks) para não estourar a memória do Render
        def generate():
            for chunk in req.iter_content(chunk_size=8192):
                yield chunk

        # Cria a resposta com os cabeçalhos de vídeo corretos e libera o CORS
        response = Response(generate(), content_type=req.headers.get('content-type'))
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        return f"Erro no streaming: {str(e)}", 500

# --- FIM DO MOTOR PROXY ---

def obter_link_direto_ia(identifier):
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        for arquivo in r.get("files", []):
            nome_arq = arquivo.get("name", "")
            if nome_arq.lower().endswith(('.mp4', '.mkv', '.avi', '.ts')):
                nome_codificado = urllib.parse.quote(nome_arq)
                return f"https://archive.org/download/{identifier}/{nome_codificado}"
    except: pass
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo: return "Título vazio", 400
    
    titulo_busca = limpar_texto(titulo)
    link = None
    
    if titulo_busca in catalogo_pessoal:
        link = obter_link_direto_ia(catalogo_pessoal[titulo_busca])
    
    if not link:
        for nome_cat, ident in catalogo_pessoal.items():
            if titulo_busca in nome_cat or nome_cat in titulo_busca:
                link = obter_link_direto_ia(ident)
                break
    
    if not link:
        if titulo_busca in catalogo_filmes:
            link = catalogo_filmes[titulo_busca]
        else:
            if len(titulo_busca) > 4:
                for nome_cat in catalogo_filmes:
                    if titulo_busca in nome_cat or nome_cat in titulo_busca:
                        link = catalogo_filmes[nome_cat]
                        break

    if link:
        # MESTRE: Se for link de IPTV (não Archive.org), usamos o Proxy automaticamente
        if "archive.org" not in link:
            # Redireciona para a nossa rota de stream que tem o disfarce
            proxy_url = f"/stream?url={urllib.parse.quote(link)}"
            return redirect(proxy_url)
        
        response = make_response(redirect(link))
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
        
    return jsonify({"status": "erro", "procurado": titulo_busca}), 404

@app.route("/atualizar")
def atualizar():
    carregar_acervo_pessoal()
    carregar_m3u()
    return jsonify({"status": "sucesso", "ia": len(catalogo_pessoal), "m3u": len(catalogo_filmes)}), 200

@app.route("/")
def index():
    return f"🚀 Cine Mega Sniper | Render | IA: {len(catalogo_pessoal)} | M3U: {len(catalogo_filmes)}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
