import os
import re
import requests
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# Suas listas M3U de Elite
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP2/lista2.m3u"
]

catalogo_filmes = {}

def limpar_texto(texto):
    """Limpa o nome para busca ultra-eficiente"""
    t = str(texto)
    # Remove tags entre colchetes e parênteses
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    # Remove termos técnicos que poluem a busca
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado|completo|filmes|filme|h264|x264|webdl)', '', t)
    # Mantém apenas letras e números
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    print("🚀 Iniciando Motor VIP Sniper...")
    
    for url in LISTAS_M3U:
        try:
            # stream=True lê o arquivo aos poucos para não estourar a RAM do Koyeb
            r = requests.get(url, stream=True, timeout=60)
            it = r.iter_lines()
            
            contador = 0
            for linha in it:
                # LIMITE DE SEGURANÇA: 180 mil títulos para estabilizar a RAM em ~50%
                if contador > 180000: 
                    print("⚠️ Limite de segurança atingido. RAM protegida.")
                    break
                
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                
                if l.startswith("#EXTINF"):
                    nome_sujo = l.split(",")[-1]
                    nome_limpo = limpar_texto(nome_sujo)
                    
                    try:
                        link = next(it).decode('utf-8', errors='ignore').strip()
                        if link.startswith("http"):
                            # Prioriza links de servidores conhecidos como bons
                            if nome_limpo not in catalogo_filmes or "serv99" in link:
                                catalogo_filmes[nome_limpo] = link
                                contador += 1
                    except StopIteration: break
        except Exception as e:
            print(f"Erro ao carregar lista: {e}")
            
    print(f"✅ Motor Pronto! {len(catalogo_filmes)} títulos indexados.")

# Carga inicial do sistema
carregar_m3u()

def buscar_sniper_vip(titulo):
    titulo_busca = limpar_texto(titulo)
    
    # 1. TIRO DE SNIPER (Nome Exato) - Instantâneo
    if titulo_busca in catalogo_filmes:
        return catalogo_filmes[titulo_busca]

    # 2. BUSCA POR PALAVRA-CHAVE (Se o sniper falhar)
    # Procura se o que você digitou está dentro de algum nome do catálogo
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
        # Redireciona para o link direto do vídeo
        return redirect(link)
    else:
        return jsonify({
            "status": "erro",
            "mensagem": "Filme não encontrado no Motor VIP.",
        }), 404

@app.route("/")
def index():
    # Página de status para você conferir se o motor está vivo
    return f"🚀 Motor Cine Mega VIP Online! | Títulos Indexados: {len(catalogo_filmes)}", 200

@app.route("/refresh")
def refresh():
    """Rota para atualizar a lista sem precisar reiniciar o servidor"""
    carregar_m3u()
    return "Catálogo atualizado com sucesso!", 200

if __name__ == "__main__":
    # Detecta a porta automaticamente (Koyeb/Render)
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
