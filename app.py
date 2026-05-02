import os
import re
import requests
import difflib
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# Suas listas originais (A Mina de Ouro)
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP2/lista2.m3u"
]

catalogo_filmes = {}

def limpar_texto(texto):
    """Limpa o nome arrancando anos, tags HD e caracteres especiais"""
    t = re.sub(r'\[.*?\]|\(.*?\)', '', str(texto))
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado)', '', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    print("🚀 Iniciando Motor VIP Sniper no Render...")
    
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, stream=True, timeout=30)
            linhas = [l.decode('utf-8', errors='ignore').strip() for l in r.iter_lines() if l]
            
            for i in range(len(linhas)):
                if linhas[i].startswith("#EXTINF"):
                    nome_sujo = linhas[i].split(",")[-1]
                    nome_limpo = limpar_texto(nome_sujo)
                    
                    if i + 1 < len(linhas):
                        link = linhas[i+1]
                        if "movie" in link or ".mp4" in link or ".mkv" in link:
                            if nome_limpo not in catalogo_filmes:
                                catalogo_filmes[nome_limpo] = []
                            catalogo_filmes[nome_limpo].append(link)
        except Exception as e:
            print(f"Erro ao carregar lista: {e}")
            
    print(f"✅ Catálogo pronto! {len(catalogo_filmes)} títulos na memória.")

carregar_m3u()

def buscar_sniper_vip(titulo):
    titulo_busca = limpar_texto(titulo)
    links_encontrados = []
    
    # 1. ARRASTÃO: Pega tudo que tiver relação com o nome
    for nome_cat, links in catalogo_filmes.items():
        if titulo_busca == nome_cat or titulo_busca in nome_cat or nome_cat in titulo_busca:
            if len(titulo_busca) > 2:
                links_encontrados.extend(links)

    # 2. PLANO DE RESGATE (Para filmes como Se Beber Não Case)
    if not links_encontrados:
        for nome_cat, links in catalogo_filmes.items():
            if difflib.SequenceMatcher(None, titulo_busca, nome_cat).ratio() > 0.75:
                links_encontrados.extend(links)

    if not links_encontrados:
        return None

    # 3. A PENEIRA DE OURO (Prioridade VIP)
    link_vip = None
    link_secundario = None
    link_lixo = None

    for link in links_encontrados:
        # OS REIS DO CAMAROTE (Toca liso)
        if "209.131.122.80" in link or "serv99" in link or "master99999" in link:
            link_vip = link
            break 
        # O ESGOTO (fontedecanais)
        elif "fontedecanais" in link:
            link_lixo = link
        # O RESTO DA LISTA
        else:
            link_secundario = link

    if link_vip:
        return link_vip
    if link_secundario:
        return link_secundario
    return link_lixo

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo:
        return "Título vazio", 400
        
    link = buscar_sniper_vip(titulo)
    
    if link:
        return redirect(link)
    else:
        return jsonify({
            "status": "erro",
            "mensagem": "Filme não encontrado no acervo Cine Mega.",
        }), 404

@app.route("/")
def index():
    return f"🚀 Motor Cine Mega VIP (Render) | Títulos Indexados: {len(catalogo_filmes)}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
