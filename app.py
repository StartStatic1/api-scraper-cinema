import os
import requests
import re
from bs4 import BeautifulSoup
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# =====================================================================
# 🕷️ MOTOR DE SCRAPING - ALVO: REDE CANAIS / MULTI-SERVER
# =====================================================================

def capturar_mp4_premium(titulo):
    """
    Tenta localizar o filme em servidores de alta qualidade 
    e extrair o link direto do player.
    """
    try:
        # 1. Formatamos o título para a busca (Ex: O Mentiroso -> o-mentiroso)
        termo_busca = titulo.lower().replace(" ", "-").replace("!", "").replace(",", "")
        
        # Alvos de busca (sites que o seu bot vai "raspar")
        # Tentamos uma rota de API de embeds que costuma alimentar o Rede Canais
        url_alvo = f"https://embed.warezcdn.com/film/{termo_busca}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://redecanais.zip/'
        }

        # Fazemos o pedido ao servidor
        resposta = requests.get(url_alvo, headers=headers, timeout=10)
        
        if resposta.status_code == 200:
            # Procuramos por links que terminam em .mp4 ou códigos de servidores como 'master99999'
            conteudo = resposta.text
            
            # MÁGICA: Procura padrões de URL de vídeo no código fonte
            links_encontrados = re.findall(r'(https?://[^\s"\']+\.(?:mp4|mkv|m3u8))', conteudo)
            
            if links_encontrados:
                # Prioriza links que contenham 'master' ou 'serv' (os que você gosta)
                for link in links_encontrados:
                    if "master" in link or "serv" in link or "209.131" in link:
                        return link
                return links_encontrados[0] # Se não achar o VIP, manda o primeiro que achar

    except Exception as e:
        print(f"Erro na raspagem: {e}")
    
    return None

# =====================================================================
# 🌐 ROTAS DA API
# =====================================================================

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo:
        return "Mestre, mande o título!", 400

    print(f"🕵️ Robô em ação para: {titulo}")
    
    link_final = capturar_mp4_premium(titulo)
    
    if link_final:
        # Sucesso! O VLC ou MX Player vai abrir o link direto aqui
        return redirect(link_final)
    else:
        # Se falhar a raspagem, podemos tentar um redirecionamento de busca manual como fallback
        return jsonify({
            "status": "erro",
            "mensagem": "O robô não conseguiu furar o bloqueio deste filme ainda.",
            "dica": "Verifique se o nome está correto no TMDB."
        }), 404

@app.route("/")
def index():
    return "🚀 Cine Mega Scraper VIP V1.0 Online!", 200

if __name__ == "__main__":
    # Porta padrão para o Koyeb/Render
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
