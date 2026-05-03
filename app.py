import os
import re
import requests
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_backup/lista.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP4/lista2.m3u"
]

catalogo_filmes = {}

def limpar_texto(texto):
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
            # Usamos stream=True para não carregar o arquivo bruto na RAM
            r = requests.get(url, stream=True, timeout=60)
            it = r.iter_lines()
            
            contador = 0
            for linha in it:
                # TRAVA DE SEGURANÇA: Reduzi para 160k para dar folga total na CPU/RAM
                if contador > 160000: 
                    print("⚠️ RAM em risco! Parando carga para manter o site vivo.")
                    break
                
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                
                if l.startswith("#EXTINF"):
                    nome_sujo = l.split(",")[-1]
                    nome_limpo = limpar_texto(nome_sujo)
                    
                    try:
                        link = next(it).decode('utf-8', errors='ignore').strip()
                        if link.startswith("http"):
                            # Só guarda se o nome for novo (economiza muita RAM)
                            if nome_limpo not in catalogo_filmes:
                                catalogo_filmes[nome_limpo] = link
                                contador += 1
                    except StopIteration: break
        except Exception as e:
            print(f"Erro ao carregar: {e}")
            
    print(f"✅ Catálogo pronto! {len(catalogo_filmes)} títulos na memória.")

carregar_m3u()

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    if not titulo: return "Título vazio", 400
    
    titulo_busca = limpar_texto(titulo)
    link = catalogo_filmes.get(titulo_busca)
    
    if not link:
        # Busca rápida de contenção
        for nome_cat in catalogo_filmes:
            if titulo_busca in nome_cat:
                link = catalogo_filmes[nome_cat]
                break

    if link: return redirect(link)
    return jsonify({"status": "erro"}), 404

@app.route("/")
def index():
    return f"🚀 Motor Sniper Online | {len(catalogo_filmes)} Títulos", 200

if __name__ == "__main__":
    # Comando para o Koyeb rodar estável
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
