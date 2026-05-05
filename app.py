import os
import re
import requests
import urllib.parse
import unicodedata
from flask import Flask, request, redirect, jsonify, make_response

app = Flask(__name__)

# MESTRE: Suas duas listas integradas
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]

# Seu e-mail real para o Sniper não errar o alvo
UPLOADER_EMAIL = "rafflores17@gmail.com"

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
        # Busca oficial pelo e-mail do uploader
        email_seguro = urllib.parse.quote(UPLOADER_EMAIL)
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({email_seguro})&fl[]=identifier,title&output=json&rows=1000"
        
        r = requests.get(url_ia, headers=headers, timeout=20).json()
        items = r.get('response', {}).get('docs', [])
        
        for doc in items:
            id_ia = doc.get('identifier')
            titulo = doc.get('title', id_ia)
            if id_ia:
                catalogo_pessoal[limpar_texto(titulo)] = id_ia
        print(f"✅ IA Carregada: {len(catalogo_pessoal)} filmes")
    except: 
        print("❌ Falha ao carregar Archive.org")

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, stream=True, timeout=60)
            ultimo_nome = None 
            contador_lista = 0
            
            for linha in r.iter_lines():
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                
                if l.startswith("#EXTINF"):
                    ultimo_nome = limpar_texto(l.split(",")[-1])
                elif l.startswith("http") and ultimo_nome:
                    if ultimo_nome not in catalogo_filmes:
                        catalogo_filmes[ultimo_nome] = l
                        contador_lista += 1
                    ultimo_nome = None
            print(f"✅ Lista OK: {url} | Total: {contador_lista}")
        except: pass

# Carga inicial ao ligar o servidor
carregar_acervo_pessoal()
carregar_m3u()

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
    
    # 🔍 ORDEM DE PESQUISA (A LÓGICA):
    
    # 1. TENTA NO SEU ACERVO (IA) PRIMEIRO
    if titulo_busca in catalogo_pessoal:
        link = obter_link_direto_ia(catalogo_pessoal[titulo_busca])
    
    # 2. SE NÃO ACHOU, TENTA NA M3U (BUSCA EXATA)
    if not link and titulo_busca in catalogo_filmes:
        link = catalogo_filmes[titulo_busca]
        
    # 3. ÚLTIMA CHANCE: BUSCA APROXIMADA NA M3U
    if not link and len(titulo_busca) > 4:
        for nome_cat in catalogo_filmes:
            if titulo_busca in nome_cat or nome_cat in titulo_busca:
                link = catalogo_filmes[nome_cat]
                break

    if link:
        response = make_response(redirect(link))
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
        
    return jsonify({"status": "erro", "procurado": titulo_busca}), 404

@app.route("/atualizar")
def atualizar():
    carregar_acervo_pessoal()
    carregar_m3u()
    return jsonify({
        "status": "sucesso", 
        "ia": len(catalogo_pessoal), 
        "m3u": len(catalogo_filmes)
    }), 200

@app.route("/")
def index():
    return f"🚀 Sniper Online | IA: {len(catalogo_pessoal)} | M3U: {len(catalogo_filmes)}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
