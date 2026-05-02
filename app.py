import os
import re
import requests
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# Suas listas M3U oficiais
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP2/lista2.m3u"
]

catalogo_filmes = {}

def limpar_texto(texto):
    """Limpa o nome para busca eficiente"""
    t = re.sub(r'\[.*?\]|\(.*?\)', '', str(texto))
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado|completo|filmes|filme)', '', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    print("🚀 Iniciando Motor VIP Sniper...")
    
    for url in LISTAS_M3U:
        try:
            # Stream=True para ler grandes volumes sem estourar a RAM
            r = requests.get(url, stream=True, timeout=60)
            it = r.iter_lines()
            
            contador = 0
            for linha in it:
                # Limite de segurança para plano gratuito (evita o SIGKILL)
                if contador > 180000: break 
                
                l = linha.decode('utf-8', errors='ignore').strip()
                if l.startswith("#EXTINF"):
                    nome_sujo = l.split(",")[-1]
                    nome_limpo = limpar_texto(nome_sujo)
                    
                    try:
                        link = next(it).decode('utf-8', errors='ignore').strip()
                        if "http" in link:
                            # Prioriza links que não sejam "lixo"
                            if nome_limpo not in catalogo_filmes or "serv99" in link:
                                catalogo_filmes[nome_limpo] = link
                            contador += 1
                    except StopIteration:
                        break
        except Exception as e:
            print(f"Erro ao carregar lista: {e}")
            
    print(f"✅ Catálogo pronto! {len(catalogo_filmes)} títulos na memória.")

# Carga inicial
carregar_m3u()

def buscar_sniper_vip(titulo):
    titulo_busca = limpar_texto(titulo)
    
    # 1. TIRO DE SNIPER (Nome Exato) - Instantâneo
    if titulo_busca in catalogo_filmes:
        return catalogo_filmes[titulo_busca]

    # 2. BUSCA POR CONTINGÊNCIA (Contém o nome)
    # Se o nome exato falhar, procura se o título faz parte de algum nome do catálogo
    # Isso resolve casos onde o catálogo tem "Filme Nome (2024)" e você busca "Nome"
    for nome_cat, link in catalogo_filmes.items():
        if titulo_busca in nome_cat or nome_cat in titulo_busca:
            return link

    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo:
        return "Título não enviado", 400
        
    link = buscar_sniper_vip(titulo)
    
    if link:
        # Redireciona direto para o fluxo de vídeo
        return redirect(link)
    else:
        return jsonify({
            "status": "erro",
            "mensagem": "Filme não encontrado no Motor Sniper.",
        }), 404

@app.route("/")
def index():
    return f"🚀 Motor Cine Mega Sniper Ativo | Títulos: {len(catalogo_filmes)}", 200

# Rota para forçar atualização da lista sem reiniciar o servidor
@app.route("/atualizar")
def atualizar():
    carregar_m3u()
    return "Lista atualizada com sucesso!", 200

if __name__ == "__main__":
    # Porta padrão para o Koyeb/Render
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
