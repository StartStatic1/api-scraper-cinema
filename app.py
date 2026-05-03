import os
import re
import requests
import urllib.parse
import unicodedata
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

LISTAS_M3U = [
    # Mestre, deixe aqui apenas o link da M3U boa que sobrou!
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u"
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
    print("🗄️ Carregando Archive.org...")
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
    print("🚀 Carregando M3U...")
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

def procurar_no_catalogo(termo):
    if not termo or len(termo) < 2: return None
    
    # ========================================================
    # 1. PRIORIDADE ABSOLUTA: O SEU ACERVO (ARCHIVE.ORG)
    # ========================================================
    # Checa se o nome bate exato
    if termo in catalogo_pessoal: 
        return obter_link_direto_ia(catalogo_pessoal[termo])
    
    # Checa se o nome é parecido (Ex: "brinquedo assassino" acha "brinquedo assassino 1988")
    for nome_cat, ident in catalogo_pessoal.items():
        if termo in nome_cat or nome_cat in termo: 
            return obter_link_direto_ia(ident)
            
    # ========================================================
    # 2. PLANO B: LISTA M3U (SÓ VEM PRA CÁ SE FALHAR LÁ EM CIMA)
    # ========================================================
    if termo in catalogo_filmes: 
        return catalogo_filmes[termo]
        
    for nome_cat in catalogo_filmes:
        if termo in nome_cat or nome_cat in termo: 
            return catalogo_filmes[nome_cat]
            
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo: return "Título vazio", 400
    
    titulo_busca = limpar_texto(titulo)
    titulo_sem_ano = re.sub(r'\s\d{4}$', '', titulo_busca).strip()

    link = procurar_no_catalogo(titulo_busca)
    
    if not link and titulo_sem_ano != titulo_busca:
        link = procurar_no_catalogo(titulo_sem_ano)

    if link: 
        return redirect(link)
    
    return jsonify({"status": "erro", "procurado": titulo_busca}), 404

@app.route("/atualizar")
def atualizar():
    carregar_acervo_pessoal()
    return jsonify({"status": "sucesso"}), 200

@app.route("/")
def index():
    return f"🚀 Sniper Online | IA: {len(catalogo_pessoal)} | M3U: {len(catalogo_filmes)}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
