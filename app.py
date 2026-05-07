import os
import re
import time
import json
import queue
import requests
import threading
import urllib.parse
import unicodedata

from rapidfuzz import fuzz
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, redirect, jsonify

app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================

LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]

UPLOADER_USER = "rafaela_andrea_ferrada_flores"

ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"

TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124 Safari/537.36"
    )
}

# =========================================================
# CACHE
# =========================================================

cache_tmdb = {}
cache_busca = {}
cache_archive = {}
cache_debrid = {}

# =========================================================
# DATABASES
# =========================================================

catalogo_pessoal = {}
catalogo_filmes = {}

# =========================================================
# NORMALIZAÇÃO
# =========================================================

def limpar_texto(texto):

    texto = str(texto)

    texto = unicodedata.normalize(
        "NFKD",
        texto
    ).encode(
        "ASCII",
        "ignore"
    ).decode(
        "utf-8"
    )

    texto = texto.lower()

    texto = re.sub(r'\[[^\]]*\]', ' ', texto)
    texto = re.sub(r'\([^\)]*\)', ' ', texto)

    lixo = [
        "dublado",
        "dual audio",
        "1080p",
        "720p",
        "2160p",
        "4k",
        "bluray",
        "webdl",
        "webrip",
        "x264",
        "x265",
        "h264",
        "h265",
        "hdrip",
        "torrent",
        "oficial"
    ]

    for l in lixo:
        texto = texto.replace(l, " ")

    texto = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto)

    texto = re.sub(r'\s+', ' ', texto)

    return texto.strip()

# =========================================================
# MATCH FUZZY
# =========================================================

def melhor_match(busca, catalogo, minimo=82):

    melhor = None
    score_final = 0

    for titulo in catalogo:

        score = fuzz.ratio(busca, titulo)

        if score > score_final:
            score_final = score
            melhor = titulo

    if score_final >= minimo:
        return melhor

    return None

# =========================================================
# TMDB
# =========================================================

def buscar_tmdb(nome):

    if nome in cache_tmdb:
        return cache_tmdb[nome]

    try:

        url = (
            "https://api.themoviedb.org/3/search/movie"
        )

        r = requests.get(
            url,
            params={
                "api_key": TMDB_API_KEY,
                "query": nome,
                "language": "pt-BR"
            },
            headers=HEADERS,
            timeout=20
        )

        dados = r.json()

        if dados.get("results"):

            filme = dados["results"][0]

            cache_tmdb[nome] = filme

            return filme

    except:
        pass

    return None

# =========================================================
# ARCHIVE
# =========================================================

def carregar_acervo_pessoal():

    global catalogo_pessoal

    catalogo_pessoal = {}

    try:

        url = (
            "https://archive.org/advancedsearch.php"
            f"?q=uploader:({UPLOADER_USER})"
            "&fl[]=identifier,title"
            "&output=json"
            "&rows=10000"
        )

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=60
        )

        dados = r.json()

        docs = dados.get(
            "response",
            {}
        ).get(
            "docs",
            []
        )

        for doc in docs:

            identifier = doc.get("identifier")

            titulo = limpar_texto(
                doc.get(
                    "title",
                    identifier
                )
            )

            if identifier:
                catalogo_pessoal[titulo] = identifier

        print(f"✅ Archive: {len(catalogo_pessoal)}")

    except Exception as e:

        print("❌ Archive:", e)

# =========================================================
# M3U
# =========================================================

def carregar_m3u():

    global catalogo_filmes

    catalogo_filmes = {}

    for url in LISTAS_M3U:

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                stream=True,
                timeout=90
            )

            ultimo_nome = None

            for linha in r.iter_lines():

                if not linha:
                    continue

                l = linha.decode(
                    "utf-8",
                    errors="ignore"
                ).strip()

                if l.startswith("#EXTINF"):

                    try:

                        nome = l.split(",")[-1]

                        ultimo_nome = limpar_texto(nome)

                    except:

                        ultimo_nome = None

                elif l.startswith("http") and ultimo_nome:

                    if ultimo_nome not in catalogo_filmes:
                        catalogo_filmes[ultimo_nome] = []

                    if l not in catalogo_filmes[ultimo_nome]:
                        catalogo_filmes[ultimo_nome].append(l)

                    ultimo_nome = None

            print(f"✅ M3U OK")

        except Exception as e:

            print("❌ M3U:", e)

# =========================================================
# ARCHIVE LINK
# =========================================================

def obter_link_archive(identifier):

    if identifier in cache_archive:
        return cache_archive[identifier]

    try:

        url = f"https://archive.org/metadata/{identifier}"

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        dados = r.json()

        arquivos = dados.get("files", [])

        melhores = []

        for f in arquivos:

            nome = f.get("name", "").lower()

            if nome.endswith((
                ".mp4",
                ".mkv",
                ".avi",
                ".mov"
            )):

                tamanho = int(
                    f.get("size", 0)
                )

                melhores.append(
                    (
                        tamanho,
                        f.get("name")
                    )
                )

        if melhores:

            melhores.sort(reverse=True)

            arquivo = melhores[0][1]

            final = (
                f"https://archive.org/download/"
                f"{identifier}/"
                f"{urllib.parse.quote(arquivo)}"
            )

            cache_archive[identifier] = final

            return final

    except:
        pass

    return None

# =========================================================
# ALLDEBRID
# =========================================================

def buscar_debrid(titulo, tmdb_id=""):

    cache_key = f"{titulo}_{tmdb_id}"

    if cache_key in cache_debrid:
        return cache_debrid[cache_key]

    try:

        termos = [titulo]

        if tmdb_id:

            try:

                tmdb = requests.get(
                    f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                    params={
                        "api_key": TMDB_API_KEY
                    },
                    headers=HEADERS,
                    timeout=20
                ).json()

                imdb = tmdb.get("imdb_id")

                original = tmdb.get("original_title")

                if imdb:
                    termos.insert(0, imdb)

                if original:
                    termos.append(original)

            except:
                pass

        for termo in termos:

            termo = termo.strip()

            if not termo:
                continue

            instant = requests.get(
                "https://api.alldebrid.com/v4/magnets/instant",
                params={
                    "agent": "CineMega",
                    "apikey": ALLDEBRID_API,
                    "magnets[]": termo
                },
                headers=HEADERS,
                timeout=40
            ).json()

            if instant.get("status") != "success":
                continue

            magnets = instant.get(
                "data",
                {}
            ).get(
                "magnets",
                []
            )

            if not magnets:
                continue

            for mag in magnets:

                if not mag.get("instant"):
                    continue

                magnet_hash = mag.get("hash")

                if not magnet_hash:
                    continue

                magnet_link = (
                    f"magnet:?xt=urn:btih:{magnet_hash}"
                )

                upload = requests.get(
                    "https://api.alldebrid.com/v4/magnet/upload",
                    params={
                        "agent": "CineMega",
                        "apikey": ALLDEBRID_API,
                        "magnets[]": magnet_link
                    },
                    headers=HEADERS,
                    timeout=40
                ).json()

                if upload.get("status") != "success":
                    continue

                mags = upload.get(
                    "data",
                    {}
                ).get(
                    "magnets",
                    []
                )

                if not mags:
                    continue

                magnet_id = mags[0].get("id")

                if not magnet_id:
                    continue

                time.sleep(3)

                status = requests.get(
                    "https://api.alldebrid.com/v4/magnet/status",
                    params={
                        "agent": "CineMega",
                        "apikey": ALLDEBRID_API,
                        "id": magnet_id
                    },
                    headers=HEADERS,
                    timeout=40
                ).json()

                links = (
                    status.get("data", {})
                    .get("magnets", {})
                    .get(str(magnet_id), {})
                    .get("links", [])
                )

                if not links:
                    continue

                melhores = []

                for l in links:

                    nome = l.get("filename", "").lower()

                    if any(
                        x in nome
                        for x in [
                            ".mp4",
                            ".mkv",
                            ".avi"
                        ]
                    ):

                        tamanho = l.get("size", 0)

                        melhores.append(
                            (
                                tamanho,
                                l
                            )
                        )

                if not melhores:
                    continue

                melhores.sort(reverse=True)

                link_original = melhores[0][1].get("link")

                unlock = requests.get(
                    "https://api.alldebrid.com/v4/link/unlock",
                    params={
                        "agent": "CineMega",
                        "apikey": ALLDEBRID_API,
                        "link": link_original
                    },
                    headers=HEADERS,
                    timeout=40
                ).json()

                final = unlock.get(
                    "data",
                    {}
                ).get(
                    "link"
                )

                if final:

                    cache_debrid[cache_key] = final

                    return final

    except Exception as e:

        print("❌ Debrid:", e)

    return None

# =========================================================
# BUSCA M3U
# =========================================================

def buscar_m3u(titulo):

    match = melhor_match(
        titulo,
        catalogo_filmes
    )

    if not match:
        return None

    links = catalogo_filmes.get(match)

    if not links:
        return None

    return links[0]

# =========================================================
# BUSCA ARCHIVE
# =========================================================

def buscar_archive(titulo):

    match = melhor_match(
        titulo,
        catalogo_pessoal
    )

    if not match:
        return None

    identifier = catalogo_pessoal.get(match)

    if not identifier:
        return None

    return obter_link_archive(identifier)

# =========================================================
# SEARCH ENGINE
# =========================================================

def motor_busca(titulo, tmdb_id=""):

    cache_key = f"{titulo}_{tmdb_id}"

    if cache_key in cache_busca:
        return cache_busca[cache_key]

    resultados = queue.Queue()

    def tentativa_archive():

        try:

            r = buscar_archive(titulo)

            if r:
                resultados.put(r)

        except:
            pass

    def tentativa_debrid():

        try:

            r = buscar_debrid(
                titulo,
                tmdb_id
            )

            if r:
                resultados.put(r)

        except:
            pass

    def tentativa_m3u():

        try:

            r = buscar_m3u(titulo)

            if r:
                resultados.put(r)

        except:
            pass

    threads = [
        threading.Thread(target=tentativa_archive),
        threading.Thread(target=tentativa_debrid),
        threading.Thread(target=tentativa_m3u)
    ]

    for t in threads:
        t.start()

    inicio = time.time()

    while time.time() - inicio < 25:

        try:

            link = resultados.get_nowait()

            if link:

                cache_busca[cache_key] = link

                return link

        except:
            pass

        time.sleep(0.2)

    return None

# =========================================================
# INIT
# =========================================================

carregar_acervo_pessoal()
carregar_m3u()

# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return jsonify({
        "status": "online",
        "archive": len(catalogo_pessoal),
        "m3u": len(catalogo_filmes),
        "cache": len(cache_busca)
    })

# =========================================================
# RELOAD
# =========================================================

@app.route("/reload")
def reload():

    carregar_acervo_pessoal()
    carregar_m3u()

    return jsonify({
        "status": "reloaded"
    })

# =========================================================
# BUSCAR
# =========================================================

@app.route("/buscar")
def buscar():

    titulo = request.args.get(
        "titulo",
        ""
    ).strip()

    tmdb_id = request.args.get(
        "id",
        ""
    ).strip()

    if not titulo:

        return jsonify({
            "erro": "titulo vazio"
        }), 400

    titulo_limpo = limpar_texto(titulo)

    # =========================================
    # SEARCH ENGINE
    # =========================================

    link = motor_busca(
        titulo_limpo,
        tmdb_id
    )

    if link:
        return redirect(link)

    # =========================================
    # FALLBACK TMDB
    # =========================================

    filme = buscar_tmdb(titulo)

    if filme:

        tmdb = filme.get("id")

        if tmdb:

            # FALLBACKS MELHORES QUE VIDSRC

            embeds = [

                f"https://embed.su/embed/movie/{tmdb}",

                f"https://vidlink.pro/movie/{tmdb}",

                f"https://moviesapi.club/movie/{tmdb}",

                f"https://multiembed.mov/directstream.php?video_id={tmdb}&tmdb=1"

            ]

            return redirect(embeds[0])

    return jsonify({
        "erro": "nao encontrado"
    }), 404

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    PORT = int(
        os.environ.get(
            "PORT",
            8000
        )
    )

    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True
    )
