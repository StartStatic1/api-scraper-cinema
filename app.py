
import os
import re
import time
import json
import requests
import urllib.parse
import unicodedata
import hashlib
from rapidfuzz import fuzz
from flask import Flask, request, redirect, jsonify, make_response
from functools import lru_cache
import threading

app = Flask(__name__)

# ====== CONFIGURAÇÕES ======
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]

UPLOADER_USER = "cinemega"
ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"
TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"

# ====== HEADERS AVANÇADOS ======
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ====== CACHE E ESTADO ======
catalogo_pessoal = {}
catalogo_filmes = {}
cache_tmdb = {}
cache_alldebrid = {}
lock = threading.Lock()

# ====== FUNÇÕES UTILITÁRIAS ======
def limpar_texto(texto):
    """Limpa e normaliza título para busca"""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("utf-8").lower()
    texto = re.sub(r'\[.*?\]|\(.*?\)', ' ', texto)
    lixo = ["dublado", "dual", "1080p", "720p", "4k", "bluray", "webdl", "web-dl", 
            "torrent", "completo", "extended", "remastered", "unrated", "directors cut",
            "h264", "h265", "x264", "x265", "hevc", "aac", "dts", "hdma"]
    for l in lixo:
        texto = texto.replace(l, " ")
    return re.sub(r'\s+', ' ', re.sub(r'[^a-zA-Z0-9\s]', ' ', texto)).strip()

def extrair_ano(titulo):
    """Extrai ano do título se presente"""
    match = re.search(r'(19|20)\d{2}', titulo)
    return int(match.group()) if match else None

def is_video_file(filename):
    """Verifica se é arquivo de vídeo válido"""
    return any(filename.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm'])

def is_brasileiro(titulo):
    """Heurística para detectar conteúdo brasileiro/dublado"""
    sinais = ['dublado', 'dual', ' nacional', ' brasileir', ' pt-br', ' portugues', ' legendado']
    t_lower = titulo.lower()
    return any(s in t_lower for s in sinais)

# ====== CARREGAMENTO DE DADOS ======
def carregar_dados():
    global catalogo_pessoal, catalogo_filmes

    # 1. CARREGA ARCHIVE.ORG DO UPLOADER
    try:
        url = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title,date&output=json&rows=1000&sort[]=date+desc"
        r = requests.get(url, timeout=30, headers=HEADERS).json()
        docs = r.get('response', {}).get('docs', [])

        with lock:
            catalogo_pessoal = {}
            for doc in docs:
                if 'identifier' in doc:
                    titulo_limpo = limpar_texto(doc.get('title', doc['identifier']))
                    ano = extrair_ano(doc.get('title', ''))
                    catalogo_pessoal[titulo_limpo] = {
                        'identifier': doc['identifier'],
                        'titulo_original': doc.get('title', ''),
                        'ano': ano
                    }
        print(f"✅ Archive carregado: {len(catalogo_pessoal)} filmes de {UPLOADER_USER}")
    except Exception as e:
        print(f"❌ Erro Archive: {e}")

    # 2. CARREGA LISTAS M3U
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, timeout=30, headers=HEADERS).text
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

    print(f"✅ M3U carregado: {len(catalogo_filmes)} títulos")

# ====== BUSCA TMDB PARA METADADOS ======
def buscar_tmdb(titulo, ano=None):
    """Busca metadados no TMDB para melhorar precisão"""
    cache_key = f"{titulo}_{ano}"
    if cache_key in cache_tmdb:
        return cache_tmdb[cache_key]

    try:
        query = urllib.parse.quote(titulo)
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}&language=pt-BR"
        if ano:
            url += f"&year={ano}"

        r = requests.get(url, timeout=10, headers=HEADERS).json()
        results = r.get('results', [])

        if results:
            # Prioriza resultados brasileiros/dublados se o título parecer BR
            best = results[0]
            cache_tmdb[cache_key] = {
                'id': best['id'],
                'title': best.get('title', ''),
                'original_title': best.get('original_title', ''),
                'imdb_id': None,  # Precisa de chamada extra
                'ano': best.get('release_date', '')[:4] if best.get('release_date') else None
            }
            return cache_tmdb[cache_key]
    except Exception as e:
        print(f"❌ Erro TMDB: {e}")

    return None

def get_imdb_from_tmdb(tmdb_id):
    """Converte TMDB ID para IMDB ID"""
    try:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}"
        r = requests.get(url, timeout=10, headers=HEADERS).json()
        return r.get('imdb_id')
    except:
        return None

# ====== BUSCA ARCHIVE.ORG (PRIORIDADE 1) ======
def buscar_archive(titulo, ano=None):
    """Busca no acervo pessoal do Archive com fuzzy matching avançado"""
    melhor_match = None
    melhor_score = 0

    with lock:
        catalogo = catalogo_pessoal.copy()

    for t, info in catalogo.items():
        score = fuzz.ratio(titulo, t)

        # Bonus se ano bater
        if ano and info.get('ano') == ano:
            score += 15

        if score > melhor_score:
            melhor_score = score
            melhor_match = info

    # Threshold mais alto para acervo pessoal (75%)
    if melhor_score < 75:
        return None

    ident = melhor_match['identifier']
    try:
        meta = requests.get(f"https://archive.org/metadata/{ident}", timeout=30, headers=HEADERS).json()
        arquivos = meta.get('files', [])

        # PRIORIDADE: MP4 > MKV > AVI (streaming nativo)
        videos = [f for f in arquivos if is_video_file(f['name'])]

        # Ordena por tamanho (maior = melhor qualidade)
        videos.sort(key=lambda x: x.get('size', 0), reverse=True)

        for f in videos:
            nome_f = f['name']
            if nome_f.lower().endswith('.mp4'):
                return f"https://archive.org/download/{ident}/{urllib.parse.quote(nome_f)}"

        # Fallback para MKV
        for f in videos:
            if f['name'].lower().endswith('.mkv'):
                return f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"

    except Exception as e:
        print(f"❌ Erro metadata Archive: {e}")

    return None

# ====== ALLDEBRID AVANÇADO (PRIORIDADE 2) ======
def buscar_hash_torrent(titulo, tmdb_data=None):
    """
    Busca hashes de torrent em múltiplas fontes:
    1. 1337x (se acessível)
    2. YTS (para filmes)
    3. Torrent API genérica
    """
    hashes = []

    # Busca no 1337x via scraping
    try:
        query = titulo.replace(' ', '+')
        url = f"https://1337x.to/search/{query}/1/"
        r = requests.get(url, timeout=15, headers=HEADERS)

        if r.status_code == 200:
            # Extrai links de torrent
            torrent_links = re.findall(r'href="(/torrent/[^"]+)"', r.text)

            for link in torrent_links[:5]:  # Top 5 resultados
                try:
                    torrent_page = requests.get(f"https://1337x.to{link}", timeout=15, headers=HEADERS).text
                    # Extrai magnet link
                    magnet = re.search(r'href="(magnet:\?xt=urn:btih:([^"]+))"', torrent_page)
                    if magnet:
                        hash_val = magnet.group(2).upper()
                        if hash_val not in hashes:
                            hashes.append(hash_val)
                except:
                    continue
    except Exception as e:
        print(f"❌ Erro 1337x: {e}")

    # Busca no YTS (filmes em alta qualidade, muitos com legendas)
    try:
        query = titulo.replace(' ', '%20')
        url = f"https://yts.mx/api/v2/list_movies.json?query_term={query}"
        r = requests.get(url, timeout=15, headers=HEADERS).json()

        movies = r.get('data', {}).get('movies', [])
        for movie in movies:
            for torrent in movie.get('torrents', []):
                hash_val = torrent.get('hash', '').upper()
                if hash_val and hash_val not in hashes:
                    hashes.append(hash_val)
    except Exception as e:
        print(f"❌ Erro YTS: {e}")

    return hashes

def check_alldebrid_instant(hashes):
    """Verifica disponibilidade instantânea no AllDebrid"""
    if not hashes:
        return []

    try:
        # AllDebrid permite check de múltiplos hashes
        hashes_str = ','.join(hashes[:10])  # Máximo 10 por chamada
        url = f"https://api.alldebrid.com/v4/magnet/instant?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={hashes_str}"

        r = requests.get(url, timeout=30, headers=HEADERS).json()

        if r.get("status") == "success":
            available = []
            for mag in r.get("data", {}).get("magnets", []):
                if mag.get("instant"):
                    available.append(mag.get("hash"))
            return available
    except Exception as e:
        print(f"❌ Erro AllDebrid instant: {e}")

    return []

def upload_to_alldebrid(hash_val):
    """Upload magnet para AllDebrid e retorna link de streaming"""
    try:
        magnet = f"magnet:?xt=urn:btih:{hash_val}"

        # Upload via POST (correto)
        url = "https://api.alldebrid.com/v4/magnet/upload"
        payload = {
            "agent": "CineMega",
            "apikey": ALLDEBRID_API,
            "magnets[]": magnet
        }

        r = requests.post(url, data=payload, timeout=30, headers=HEADERS).json()

        if r.get("status") == "success":
            magnet_data = r["data"]["magnets"][0]
            mag_id = magnet_data["id"]

            # Aguarda processamento (máximo 30s)
            for _ in range(10):
                time.sleep(3)

                status_url = f"https://api.alldebrid.com/v4.1/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={mag_id}"
                st = requests.get(status_url, timeout=30, headers=HEADERS).json()

                if st.get("status") == "success":
                    mag_status = st["data"]["magnets"][str(mag_id)]

                    if mag_status.get("status") == "Ready":
                        links = mag_status.get("links", [])
                        if links:
                            # Pega o maior arquivo (provavelmente o filme)
                            largest = max(links, key=lambda x: x.get('size', 0))

                            # Unlock do link
                            unlock_url = f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(largest['link'])}"
                            un = requests.get(unlock_url, timeout=30, headers=HEADERS).json()

                            if un.get("status") == "success":
                                return un["data"].get("link")
                        break
                    elif mag_status.get("status") in ["Error", "Dead"]:
                        break

    except Exception as e:
        print(f"❌ Erro AllDebrid upload: {e}")

    return None

def buscar_alldebrid(titulo, tmdb_data=None):
    """Pipeline completo AllDebrid: busca hash -> check instant -> upload -> stream"""
    # 1. Busca hashes de torrent
    hashes = buscar_hash_torrent(titulo, tmdb_data)

    if not hashes and tmdb_data:
        # Fallback: busca por IMDB ID
        imdb = tmdb_data.get('imdb_id') or get_imdb_from_tmdb(tmdb_data.get('id'))
        if imdb:
            hashes = buscar_hash_torrent(imdb, None)

    if not hashes:
        return None

    # 2. Verifica disponibilidade instantânea
    available = check_alldebrid_instant(hashes)

    # 3. Tenta upload dos disponíveis
    for hash_val in available:
        link = upload_to_alldebrid(hash_val)
        if link:
            return link

    # 4. Se nenhum instant, tenta o primeiro hash mesmo assim (pode estar no cache)
    for hash_val in hashes:
        link = upload_to_alldebrid(hash_val)
        if link:
            return link

    return None

# ====== M3U (PRIORIDADE 3) ======
def buscar_m3u(titulo, ano=None):
    """Busca em listas M3U com fuzzy matching"""
    with lock:
        catalogo = catalogo_filmes.copy()

    melhor_match = None
    melhor_score = 0

    for t, links in catalogo.items():
        score = fuzz.ratio(titulo, t)
        if ano and str(ano) in t:
            score += 10

        if score > melhor_score:
            melhor_score = score
            melhor_match = links

    if melhor_score > 85 and melhor_match:
        return melhor_match[0]  # Retorna primeiro link

    return None

# ====== SCRAPER DE FONTES ADICIONAIS (PRIORIDADE 4) ======
def buscar_fontes_extras(titulo, tmdb_id=None):
    """
    Busca em fontes alternativas quando tudo falha.
    Retorna link direto de streaming se encontrar.
    """
    resultados = []

    # 1. VidSrc (sem embed, tenta API direta se existir)
    if tmdb_id:
        try:
            # VidSrc.me API (não oficial, pode mudar)
            url = f"https://vidsrc.to/embed/movie/{tmdb_id}"
            # Retorna o embed, mas sem ads seria ideal
            # Como não temos controle sobre os ads do VidSrc, 
            # vamos deixar como último recurso
            resultados.append({
                'fonte': 'vidsrc',
                'url': url,
                'tipo': 'embed',
                'qualidade': 'variable'
            })
        except:
            pass

    # 2. SuperEmbed (alternativa ao VidSrc, menos ads)
    if tmdb_id:
        try:
            url = f"https://multiembed.mov/?video_id={tmdb_id}&tmdb=1"
            resultados.append({
                'fonte': 'superembed',
                'url': url,
                'tipo': 'embed',
                'qualidade': 'variable'
            })
        except:
            pass

    return resultados

# ====== ENDPOINTS FLASK ======
@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "").strip()
    tmdb_id = request.args.get("id", "").strip()
    preferencia = request.args.get("lang", "pt").strip()  # pt ou en

    if not titulo:
        return jsonify({"erro": "Título não fornecido"}), 400

    t_limpo = limpar_texto(titulo)
    ano = extrair_ano(titulo)

    # Busca metadados TMDB
    tmdb_data = None
    if tmdb_id:
        tmdb_data = {'id': tmdb_id}
    else:
        tmdb_data = buscar_tmdb(t_limpo, ano)

    resultados = {
        "titulo": titulo,
        "titulo_limpo": t_limpo,
        "fonte": None,
        "link": None,
        "tmdb": tmdb_data,
        "alternativas": []
    }

    # ========== PRIORIDADE 1: ARCHIVE.ORG PESSOAL ==========
    link = buscar_archive(t_limpo, ano)
    if link:
        resultados.update({
            "fonte": "archive_pessoal",
            "link": link,
            "qualidade": "original",
            "observacao": "Sem anúncios - Acervo próprio"
        })
        return redirect(link) if request.args.get("redirect", "true") == "true" else jsonify(resultados)

    # ========== PRIORIDADE 2: ALLDEBRID (TORRENT) ==========
    link = buscar_alldebrid(t_limpo, tmdb_data)
    if link:
        resultados.update({
            "fonte": "alldebrid",
            "link": link,
            "qualidade": "alta",
            "observacao": "Torrent cacheado via AllDebrid"
        })
        return redirect(link) if request.args.get("redirect", "true") == "true" else jsonify(resultados)

    # ========== PRIORIDADE 3: LISTAS M3U ==========
    link = buscar_m3u(t_limpo, ano)
    if link:
        resultados.update({
            "fonte": "m3u",
            "link": link,
            "qualidade": "variable",
            "observacao": "Lista IPTV"
        })
        return redirect(link) if request.args.get("redirect", "true") == "true" else jsonify(resultados)

    # ========== PRIORIDADE 4: FONTES EXTRAS ==========
    extras = buscar_fontes_extras(t_limpo, tmdb_id if tmdb_id else (tmdb_data.get('id') if tmdb_data else None))

    if extras:
        # Filtra por preferência de idioma
        for extra in extras:
            if extra['fonte'] == 'superembed':
                resultados.update({
                    "fonte": extra['fonte'],
                    "link": extra['url'],
                    "qualidade": extra['qualidade'],
                    "observacao": "Fonte alternativa (pode conter anúncios)"
                })
                return redirect(extra['url']) if request.args.get("redirect", "true") == "true" else jsonify(resultados)

        # Último recurso: VidSrc
        if extras and extras[-1]['fonte'] == 'vidsrc':
            resultados.update({
                "fonte": "vidsrc",
                "link": extras[-1]['url'],
                "qualidade": "variable",
                "observacao": "Último recurso - Embed externo"
            })
            return redirect(extras[-1]['url']) if request.args.get("redirect", "true") == "true" else jsonify(resultados)

    return jsonify({
        "erro": "Não encontrado",
        "titulo": titulo,
        "titulo_limpo": t_limpo,
        "tmdb": tmdb_data,
        "alternativas": extras
    }), 404

@app.route("/")
def home():
    with lock:
        return jsonify({
            "status": "online",
            "archive_pessoal": len(catalogo_pessoal),
            "m3u": len(catalogo_filmes),
            "uploader": UPLOADER_USER,
            "cache_tmdb": len(cache_tmdb),
            "alldebrid_api": "configurada" if ALLDEBRID_API else "não configurada"
        })

@app.route("/reload")
def reload():
    carregar_dados()
    return jsonify({"status": "Banco de Dados Atualizado!", "timestamp": time.time()})

@app.route("/status/<titulo>")
def status_busca(titulo):
    """Endpoint para verificar status de uma busca sem redirecionar"""
    t_limpo = limpar_texto(titulo)
    ano = extrair_ano(titulo)
    tmdb_data = buscar_tmdb(t_limpo, ano)

    return jsonify({
        "titulo": titulo,
        "titulo_limpo": t_limpo,
        "disponivel_archive": any(fuzz.ratio(t_limpo, k) > 75 for k in catalogo_pessoal.keys()),
        "disponivel_m3u": any(fuzz.ratio(t_limpo, k) > 85 for k in catalogo_filmes.keys()),
        "tmdb": tmdb_data,
        "hashes_encontrados": len(buscar_hash_torrent(t_limpo, tmdb_data)) if ALLDEBRID_API else 0
    })

if __name__ == "__main__":
    carregar_dados()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True)
