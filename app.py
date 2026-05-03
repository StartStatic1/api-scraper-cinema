import os
import re
import requests
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP4/lista2.m3u"
]

UPLOADER_IA = "rafaela_andrea_ferrada_flores"

catalogo_pessoal = {} # Guarda os seus filmes do Archive.org
catalogo_filmes = {}  # Guarda os filmes das listas M3U

def limpar_texto(texto):
    t = re.sub(r'\[.*?\]|\(.*?\)', '', str(texto))
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado|completo|filmes|filme)', '', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_acervo_pessoal():
    global catalogo_pessoal
    catalogo_pessoal = {}
    print("🗄️ Carregando Acervo Pessoal do Archive.org...")
    try:
        # Usa a API oficial do Archive.org para buscar apenas os seus uploads
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_IA})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, timeout=15).json()
        
        docs = r.get('response', {}).get('docs', [])
        for doc in docs:
            id_ia = doc.get('identifier')
            titulo = doc.get('title', id_ia) # Se não tiver título claro, usa o ID
            nome_limpo = limpar_texto(titulo)
            catalogo_pessoal[nome_limpo] = id_ia
            
        print(f"✅ Acervo Pessoal pronto! {len(catalogo_pessoal)} filmes garantidos.")
    except Exception as e:
        print(f"⚠️ Erro ao carregar Archive.org: {e}")

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    print("🚀 Iniciando Motor VIP Sniper...")
    
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, stream=True, timeout=60)
            it = r.iter_lines()
            
            contador = 0
            for linha in it:
                if contador > 160000: 
                    print("⚠️ RAM em risco! Parando carga M3U.")
                    break
                
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                
                if l.startswith("#EXTINF"):
                    nome_sujo = l.split(",")[-1]
                    nome_limpo = limpar_texto(nome_sujo)
                    
                    try:
                        link = next(it).decode('utf-8', errors='ignore').strip()
                        if link.startswith("http"):
                            if nome_limpo not in catalogo_filmes:
                                catalogo_filmes[nome_limpo] = link
                                contador += 1
                    except StopIteration: break
        except Exception as e:
            print(f"Erro ao carregar M3U: {e}")
            
    print(f"✅ Catálogo M3U pronto! {len(catalogo_filmes)} títulos na memória.")

# Carrega as duas bases de dados ao iniciar
carregar_acervo_pessoal()
carregar_m3u()

def obter_link_direto_ia(identifier):
    """Acha o arquivo de vídeo (.mp4 ou .mkv) dentro do seu upload no Archive.org"""
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        for arquivo in r.get("files", []):
            nome_arq = arquivo.get("name", "")
            # Procura a extensão de vídeo
            if nome_arq.lower().endswith(('.mp4', '.mkv', '.avi', '.ts')):
                # Monta o link direto de download/streaming
                return f"https://archive.org/download/{identifier}/{nome_arq}"
    except: pass
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo: return "Título vazio", 400
    
    titulo_busca = limpar_texto(titulo)
    link = None

    # 1️⃣ PRIORIDADE MÁXIMA: O SEU ACERVO NO ARCHIVE.ORG
    id_ia = None
    if titulo_busca in catalogo_pessoal:
        id_ia = catalogo_pessoal[titulo_busca]
    else:
        # Busca por aproximação
        for nome_cat, ident in catalogo_pessoal.items():
            if titulo_busca in nome_cat or nome_cat in titulo_busca:
                id_ia = ident
                break
    
    if id_ia:
        print(f"🎯 Puxando filme do Acervo Pessoal: {id_ia}")
        link = obter_link_direto_ia(id_ia)

    # 2️⃣ PLANO B: BUSCA NAS LISTAS M3U
    if not link:
        link = catalogo_filmes.get(titulo_busca)
        if not link:
            for nome_cat in catalogo_filmes:
                if titulo_busca in nome_cat:
                    link = catalogo_filmes[nome_cat]
                    break

    if link: 
        return redirect(link)
    
    return jsonify({"status": "erro"}), 404

@app.route("/")
def index():
    return f"🚀 Motor Sniper Online | 🗄️ Seu Acervo: {len(catalogo_pessoal)} | 🎬 M3U: {len(catalogo_filmes)}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
