import os
import re
import time
import json
import requests
import urllib.parse
import unicodedata
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# ====== CONFIGURAÇÕES ======
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]
UPLOADER_USER = "cinemega"
ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"
TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

catalogo_pessoal = {}
catalogo_filmes = {}

# ========== FUNÇÕES AUXILIARES ==========
def limpar_texto(texto):
    if not texto: return ""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("utf-8").lower()
    texto = re.sub(r'\[.*?\]|\(.*?\)', ' ', texto)
    lixo = ["dublado", "dual", "1080p", "720p", "4k", "bluray", "webdl", "torrent", "completo",
            "5.1", "h264", "h265", "x264", "x265", "hevc", "aac", "dts"]
    for l in lixo: texto = texto.replace(l, " ")
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', texto).strip()

def carregar_dados():
    global catalogo_pessoal, catalogo_filmes
    try:
        url = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url, timeout=30).json()
        docs = r.get('response', {}).get('docs', [])
        catalogo_pessoal = {limpar_texto(doc.get('title', doc['identifier'])): doc['identifier'] for doc in docs if 'identifier' in doc}
        print(f"✅ Archive carregado: {len(catalogo_pessoal)} filmes")
    except Exception as e:
        print(f"❌ Erro Archive: {e}")
    
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, timeout=30).text
            nome = None
            for linha in r.splitlines():
                if linha.startswith("#EXTINF"):
                    nome = limpar_texto(linha.split(",")[-1])
                elif linha.startswith("http") and nome:
                    if nome not in catalogo_filmes:
                        catalogo_filmes[nome] = []
                    catalogo_filmes[nome].append(linha)
                    nome = None
        except Exception as e:
            print(f"❌ Erro M3U {url}: {e}")

carregar_dados()

def buscar_archive(titulo_limpo):
    """Acervo pessoal do Archive.org"""
    melhor_t = None
    melhor_score = 0
    for t in catalogo_pessoal:
        score = fuzz.ratio(titulo_limpo, t)
        if score > melhor_score:
            melhor_score = score
            melhor_t = t
    if melhor_score < 65 or not melhor_t:
        return None
    ident = catalogo_pessoal[melhor_t]
    try:
        meta = requests.get(f"https://archive.org/metadata/{ident}", timeout=10).json()
        arquivos = meta.get('files', [])
        for f in arquivos:
            if f['name'].lower().endswith('.mp4'):
                return f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
        for f in arquivos:
            if f['name'].lower().endswith('.mkv'):
                return f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
    except:
        pass
    return None

def obter_imdb_id(tmdb_id):
    if not tmdb_id: return None
    try:
        tm = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=pt-BR", timeout=10).json()
        return tm.get("imdb_id")
    except:
        return None

def torrentio_streams(imdb_id):
    """Puxa lista de torrents do Torrentio (já ordenada por idioma)"""
    if not imdb_id: return []
    try:
        url = f"https://torrentio.strem.fun/stream/movie/{imdb_id}.json"
        resp = requests.get(url, headers=HEADERS, timeout=15).json()
        streams = resp.get("streams", [])
        results = []
        for s in streams:
            title = s.get("title", "")
            info_hash = s.get("infoHash")
            if not info_hash: continue
            magnet = f"magnet:?xt=urn:btih:{info_hash}"
            lang_score = 0
            lower = title.lower()
            if any(x in lower for x in ["dual audio", "dublado", "portugues", "pt-br"]): lang_score = 3
            elif "legendado" in lower or "subs" in lower: lang_score = 2
            elif "english" in lower: lang_score = 1
            if "2160p" in lower or "4k" in lower: lang_score += 0.5
            elif "1080p" in lower: lang_score += 0.3
            results.append({"title": title, "magnet": magnet, "info_hash": info_hash, "lang_score": lang_score})
        results.sort(key=lambda x: x["lang_score"], reverse=True)
        return results
    except Exception as e:
        print(f"❌ Torrentio: {e}")
        return []

def scrape_1337x(imdb_id, titulo_limpo):
    """
    Raspagem direta no 1337x.to buscando filme (prioriza PT-BR).
    Retorna lista de magnets ordenados por pontuação de idioma.
    """
    if not imdb_id and not titulo_limpo: return []
    # Constrói query usando IMDB ID primeiro (mais preciso) ou título
    query = imdb_id or titulo_limpo
    search_url = f"https://1337x.to/search/{urllib.parse.quote(query)}+1080p/1/"
    magnets = []
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")  # usa html.parser (já incluso)
        # Localiza a tabela de resultados
        table = soup.find("table", class_="table-list")
        if not table: return magnets
        rows = table.find_all("tr")[1:]  # pula cabeçalho
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4: continue
            name_cell = cells[0].find_all("a")[-1]  # último link é o nome
            title = name_cell.get_text(strip=True)
            # Determina pontuação de idioma
            lang_score = 0
            lower = title.lower()
            if any(x in lower for x in ["dual audio", "dublado", "portugues", "pt-br"]): lang_score = 3
            elif "legendado" in lower or "subs" in lower: lang_score = 2
            elif "english" in lower: lang_score = 1
            # Pega link da página do torrent para extrair magnet
            torrent_page = "https://1337x.to" + name_cell["href"]
            # Visita a página individual
            try:
                page_resp = requests.get(torrent_page, headers=HEADERS, timeout=10)
                page_soup = BeautifulSoup(page_resp.text, "html.parser")
                # Procura o link magnet
                magnet_link = None
                for a in page_soup.find_all("a"):
                    href = a.get("href", "")
                    if href.startswith("magnet:"):
                        magnet_link = href
                        break
                if magnet_link:
                    magnets.append({"magnet": magnet_link, "title": title, "lang_score": lang_score})
            except:
                continue
        # Ordena por score
        magnets.sort(key=lambda x: x["lang_score"], reverse=True)
        return magnets
    except Exception as e:
        print(f"❌ 1337x scrape: {e}")
        return []

def alldebrid_instant(magnet):
    try:
        encoded = urllib.parse.quote(magnet)
        url = f"https://api.alldebrid.com/v4/magnets/instant?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={encoded}"
        resp = requests.get(url, timeout=10).json()
        if resp.get("status") == "success":
            magnet_data = resp["data"]["magnets"][0]
            return magnet_data.get("instant", False), magnet_data.get("hash")
    except:
        pass
    return False, None

def alldebrid_unlock(link):
    try:
        encoded = urllib.parse.quote(link)
        un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={encoded}", timeout=10).json()
        if un.get("status") == "success":
            return un["data"]["link"]
    except:
        pass
    return None

def alldebrid_upload_and_wait(magnet, timeout=15):
    try:
        up = requests.get(
            f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(magnet)}",
            timeout=10
        ).json()
        if up.get("status") != "success": return None
        magnet_id = up["data"]["magnets"][0]["id"]
        start = time.time()
        while time.time() - start < timeout:
            st = requests.get(
                f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={magnet_id}", timeout=10
            ).json()
            if st.get("status") == "success":
                links = st["data"]["magnets"].get(str(magnet_id), {}).get("links", [])
                if links:
                    return alldebrid_unlock(links[0]["link"])
            time.sleep(3)
    except:
        pass
    return None

def processar_magnets(magnets):
    """Percorre uma lista de magnets e retorna o primeiro link de streaming funcional."""
    for m in magnets:
        instant, _ = alldebrid_instant(m["magnet"])
        if instant:
            # Tenta obter link instantâneo
            up = requests.get(
                f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(m['magnet'])}",
                timeout=10
            ).json()
            if up.get("status") == "success":
                mid = up["data"]["magnets"][0]["id"]
                st = requests.get(
                    f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={mid}", timeout=10
                ).json()
                if st.get("status") == "success":
                    links = st["data"]["magnets"].get(str(mid), {}).get("links", [])
                    if links:
                        play_link = alldebrid_unlock(links[0]["link"])
                        if play_link: return play_link
        # Se não instantâneo, faz upload e espera
        play_link = alldebrid_upload_and_wait(m["magnet"], timeout=15)
        if play_link:
            return play_link
    return None

# ========== ROTA PRINCIPAL ==========
@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    if not titulo: return "Título vazio", 400

    titulo_limpo = limpar_texto(titulo)
    # 1. ACERVO PESSOAL (Archive.org)
    link = buscar_archive(titulo_limpo)
    if link: return redirect(link)

    imdb_id = obter_imdb_id(tmdb_id) if tmdb_id else None

    # 2. TORRENTIO
    magnets = torrentio_streams(imdb_id)
    play = processar_magnets(magnets)
    if play: return redirect(play)

    # 3. RASPAGEM NO 1337x
    magnets_1337x = scrape_1337x(imdb_id, titulo_limpo)
    play = processar_magnets(magnets_1337x)
    if play: return redirect(play)

    # 4. FALLBACK M3U
    for t in catalogo_filmes:
        if fuzz.ratio(titulo_limpo, t) > 85:
            return redirect(catalogo_filmes[t][0])

    return "Não encontrado", 404

@app.route("/")
def home():
    return jsonify({
        "archive_filmes": len(catalogo_pessoal),
        "m3u_canais": len(catalogo_filmes),
        "uploader": UPLOADER_USER
    })

@app.route("/reload")
def reload():
    carregar_dados()
    return "Banco de Dados Atualizado!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
