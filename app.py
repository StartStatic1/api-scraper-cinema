import os
import re
import requests
import unicodedata
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP4/lista2.m3u"
]

UPLOADER_IA = "rafaela_andrea_ferrada_flores"

catalogo_pessoal = {} 
catalogo_filmes = {}  

def limpar_texto(texto):
    """Remove acentos, tags e limpa o nome para não ter erro na busca"""
    # 1. Normaliza acentos: "Não" vira "Nao", "Herói" vira "Heroi"
    t = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8')
    # 2. Tira tags e anos entre parênteses/colchetes
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    # 3. Tira palavras inúteis de qualidade
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado|completo|filmes|filme)', '', t)
    # 4. Deixa só letras e números
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_acervo_pessoal():
    global catalogo_pessoal
    catalogo_pessoal = {}
    print("🗄️ Carregando Acervo Pessoal do Archive.org...")
    try:
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_IA})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, timeout=15).json()
        
        for doc in r.get('response', {}).get('docs', []):
            id_ia = doc.get('identifier')
            titulo = doc.get('title', id_ia)
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
                    print("⚠️ RAM protegida! Parando carga M3U aos 160k.")
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

# Executa ao ligar o servidor
carregar_acervo_pessoal()
carregar_m3u()

def obter_link_direto_ia(identifier):
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        for arquivo in r.get("files", []):
            nome_arq = arquivo.get("name", "")
            if nome_arq.lower().endswith(('.mp4', '.mkv', '.avi', '.ts')):
                return f"https://archive.org/download/{identifier}/{nome_arq}"
    except: pass
    return None

def procurar_no_catalogo(termo):
    """Busca o termo exato ou aproximado nas duas bases"""
    # 1. Tenta no Archive.org primeiro
    if termo in catalogo_pessoal: return obter_link_direto_ia(catalogo_pessoal[termo])
    for nome_cat, ident in catalogo_pessoal.items():
        if termo in nome_cat or nome_cat in termo: return obter_link_direto_ia(ident)
        
    # 2. Tenta na M3U se não achou no Archive
    if termo in catalogo_filmes: return catalogo_filmes[termo]
    for nome_cat in catalogo_filmes:
        if termo in nome_cat or nome_cat in termo: return catalogo_filmes[nome_cat]
        
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo: return "Título vazio", 400
    
    # Ex: "Se Beber Nao Case 2009"
    titulo_busca = limpar_texto(titulo)
    # Ex: "Se Beber Nao Case" (Arranca os últimos 4 números se houver espaço antes)
    titulo_sem_ano = re.sub(r'\s\d{4}$', '', titulo_busca).strip()

    # Tentativa 1: Busca com o ano junto
    link = procurar_no_catalogo(titulo_busca)
    
    # Tentativa 2: Se falhou, busca ignorando o ano
    if not link and titulo_sem_ano != titulo_busca:
        link = procurar_no_catalogo(titulo_sem_ano)

    if link: 
        return redirect(link)
    
    # Se der erro agora, ele vai te mostrar na tela preta EXATAMENTE o que ele procurou
    return jsonify({"status": "erro", "procurado": titulo_busca}), 404

@app.route("/")
def index():
    return f"🚀 Motor Sniper Online | 🗄️ Seu Acervo: {len(catalogo_pessoal)} | 🎬 M3U: {len(catalogo_filmes)}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
