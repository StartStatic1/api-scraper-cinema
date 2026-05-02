import os
import re
import requests
import difflib
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# Suas listas M3U originais
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP2/lista2.m3u"
]

catalogo_filmes = {}

def limpar_texto(texto):
    """Limpa o nome arrancando anos, tags HD e sujeiras de texto"""
    t = re.sub(r'\[.*?\]|\(.*?\)', '', str(texto))
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado)', '', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    print("🚀 Carregando Motor Sniper de Elite...")
    
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
            
    print(f"✅ Catálogo pronto! {len(catalogo_filmes)} títulos isolados.")

carregar_m3u()

def extrair_melhor_link(links):
    """Função separada só para escolher o melhor link de uma lista isolada"""
    link_vip = None
    link_secundario = None
    link_lixo = None

    for link in links:
        # A REDE VIP
        if "209.131.122." in link or "serv99" in link or "master99999" in link:
            link_vip = link
            break 
        elif "fontedecanais" in link:
            link_lixo = link
        else:
            link_secundario = link

    if link_vip: return link_vip
    if link_secundario: return link_secundario
    return link_lixo


def buscar_sniper_vip(titulo):
    titulo_busca = limpar_texto(titulo)
    
    # 1. TIRO DE SNIPER (Nome Exato) - Isso salva o American Pie!
    if titulo_busca in catalogo_filmes:
        links_do_filme = catalogo_filmes[titulo_busca]
        return extrair_melhor_link(links_do_filme)

    # 2. MATEMÁTICA ALTA (Apenas se o nome exato falhar)
    melhores_matches = []
    for nome_cat, links in catalogo_filmes.items():
        score = difflib.SequenceMatcher(None, titulo_busca, nome_cat).ratio()
        # Exigimos 85% de semelhança para não confundir filme 1 com filme 2
        if score > 0.85:
            melhores_matches.append((score, links))

    if melhores_matches:
        # Pega a lista de links do filme com a MAIOR semelhança matemática
        melhores_matches.sort(key=lambda x: x[0], reverse=True)
        links_do_filme_parecido = melhores_matches[0][1]
        return extrair_melhor_link(links_do_filme_parecido)

    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo:
        return "Título não enviado", 400
        
    link = buscar_sniper_vip(titulo)
    
    if link:
        return redirect(link)
    else:
        return jsonify({
            "status": "erro",
            "mensagem": "Filme não encontrado.",
        }), 404

@app.route("/")
def index():
    return f"🚀 Motor Cine Mega Sniper | Títulos: {len(catalogo_filmes)}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
