import os
import re
import requests
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP2/lista2.m3u"
]

catalogo_filmes = {}

def limpar_texto(texto):
    t = re.sub(r'\[.*?\]|\(.*?\)', '', str(texto))
    t = re.sub(r'(?i)(1080p|720p|4k|fhd|hd|dual|dublado|legendado)', '', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {}
    print("🚀 Carregando Motor Sniper...")
    
    for url in LISTAS_M3U:
        try:
            # Usamos stream=True e iter_lines para não jogar o arquivo inteiro na RAM de uma vez
            r = requests.get(url, stream=True, timeout=30)
            it = r.iter_lines()
            
            contador = 0
            for linha in it:
                # LIMITE DE SEGURANÇA: Se passar de 150 mil títulos, paramos para não dar crash na RAM
                if contador > 150000: 
                    print("⚠️ Limite de segurança atingido para evitar crash de RAM.")
                    break
                
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                
                if l.startswith("#EXTINF"):
                    nome_sujo = l.split(",")[-1]
                    nome_limpo = limpar_texto(nome_sujo)
                    
                    try:
                        link = next(it).decode('utf-8', errors='ignore').strip()
                        if "http" in link:
                            # Guardamos apenas o link (string simples) para economizar memória
                            if nome_limpo not in catalogo_filmes:
                                catalogo_filmes[nome_limpo] = link
                                contador += 1
                    except StopIteration: break
        except Exception as e:
            print(f"Erro: {e}")
            
    print(f"✅ Motor Pronto! Títulos: {len(catalogo_filmes)}")

carregar_m3u()

def buscar_sniper_vip(titulo):
    titulo_busca = limpar_texto(titulo)
    # Busca exata é instantânea e não gasta CPU
    if titulo_busca in catalogo_filmes:
        return catalogo_filmes[titulo_busca]
    return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo: return "Título vazio", 400
    link = buscar_sniper_vip(titulo)
    if link: return redirect(link)
    return jsonify({"status": "erro", "mensagem": "Não encontrado"}), 404

@app.route("/")
def index():
    return f"🚀 Motor Sniper Ativo | Títulos: {len(catalogo_filmes)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
