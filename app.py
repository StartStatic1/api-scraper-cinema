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
        # Busca por uploader ou creator para garantir que pegue tudo
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000"
        
        r = requests.get(url_ia, headers=headers, timeout=20).json()
        items = r.get('response', {}).get('docs', [])
        
        for doc in items:
            id_ia = doc.get('identifier')
            titulo = doc.get('title', id_ia)
            if id_ia:
                # Guardamos o título limpo e o ID original
                catalogo_pessoal[limpar_texto(titulo)] = id_ia
        print(f"✅ Acervo Pessoal Carregado: {len(catalogo_pessoal)} títulos")
    except: 
        print("❌ Erro ao ler Archive.org")

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
                        catalogo_filmes[ultimo_nome] = l
                    ultimo_nome = None
        except: pass

# Carga inicial
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
    
    # 🔍 1. BUSCA PRIORITÁRIA NO SEU ARCHIVE (EXATA)
    if titulo_busca in catalogo_pessoal:
        link = obter_link_direto_ia(catalogo_pessoal[titulo_busca])
    
    # 🔍 2. BUSCA NO SEU ARCHIVE (CONTÉM) - Para casos como American Pie 1
    if not link:
        for nome_ia in catalogo_pessoal:
            if titulo_busca in nome_ia or nome_ia in titulo_busca:
                link = obter_link_direto_ia(catalogo_pessoal[nome_ia])
                if link: break

    # 🚀 3. BYPASS SNIPER (Tenta o link direto pelo ID se não achou na busca)
    if not link:
        id_tentativa = titulo_busca.replace(" ", "-")
        link = obter_link_direto_ia(id_tentativa)

    # 🔍 4. SE REALMENTE NÃO TIVER NO ARCHIVE, VAI PARA M3U (EXATA)
    if not link and titulo_busca in catalogo_filmes:
        link = catalogo_filmes[titulo_busca]
        
    # 🔍 5. ÚLTIMA CHANCE NA M3U (APROXIMADA - COM TRAVA ANTI-BUG 'MA')
    if not link and len(titulo_busca) > 4:
        for nome_cat in catalogo_filmes:
            if titulo_busca in nome_cat: # Título real deve conter a busca
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
    return jsonify({"status": "atualizado", "ia": len(catalogo_pessoal), "m3u": len(catalogo_filmes)})

@app.route("/")
def index():
    return f"Sniper Ativo | Seu Acervo: {len(catalogo_pessoal)} | M3U: {len(catalogo_filmes)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
