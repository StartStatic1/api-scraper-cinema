import os, re, requests, urllib.parse, unicodedata, time
from flask import Flask, request, redirect, jsonify, make_response

app = Flask(__name__)

# ====== CONFIGURAÇÕES DO MESTRE ======
LISTAS_M3U = [
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP5/serv_zerohop.m3u",
    "https://github.com/StartStatic1/meus-apks/releases/download/V_BACKUP6/lista_serv_dns.cdnxjp.m3u"
]
UPLOADER_USER = "rafaela_andrea_ferrada_flores"
ALLDEBRID_API = "HGt5I30bMYFLdhzDKZ06"
TMDB_API_KEY = "c90fb79a2f7d756a49bee848bce5f413"

catalogo_pessoal = {}
catalogo_filmes = {}

def limpar_texto(texto):
    t = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8')
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    return " ".join(t.split()).lower().strip()

def carregar_acervo_pessoal():
    global catalogo_pessoal
    catalogo_pessoal = {}
    try:
        # Busca tudo do seu usuário no Archive
        url_ia = f"https://archive.org/advancedsearch.php?q=uploader:({UPLOADER_USER})&fl[]=identifier,title&output=json&rows=1000"
        r = requests.get(url_ia, timeout=20).json()
        for doc in r.get('response', {}).get('docs', []):
            identificador = doc.get('identifier')
            # Guarda o título limpo para bater com a busca
            catalogo_pessoal[limpar_texto(doc.get('title', identificador))] = identificador
        print(f"✅ Acervo Pessoal: {len(catalogo_pessoal)} filmes")
    except: print("❌ Erro Archive.org")

def carregar_m3u():
    global catalogo_filmes
    catalogo_filmes = {} 
    for url in LISTAS_M3U:
        try:
            r = requests.get(url, stream=True, timeout=60)
            ultimo_nome = None 
            for linha in r.iter_lines():
                if not linha: continue
                l = linha.decode('utf-8', errors='ignore').strip()
                if l.startswith("#EXTINF"): ultimo_nome = limpar_texto(l.split(",")[-1])
                elif l.startswith("http") and ultimo_nome:
                    if ultimo_nome not in catalogo_filmes: catalogo_filmes[ultimo_nome] = []
                    catalogo_filmes[ultimo_nome].append(l)
                    ultimo_nome = None
        except: pass

carregar_acervo_pessoal()
carregar_m3u()

def obter_link_direto_ia(identifier):
    try:
        r = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        for f in r.get("files", []):
            nome_arq = f.get("name", "").lower()
            # AGORA ACEITA MP4 E MKV (Fome Animal pode ser MKV)
            if nome_arq.endswith(('.mp4', '.mkv')):
                return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f.get('name'))}"
    except: pass
    return None

def buscar_alldebrid_pro(titulo, id_tmdb=""):
    if not ALLDEBRID_API: return None
    try:
        termos = [titulo]
        if id_tmdb:
            tm = requests.get(f"https://api.themoviedb.org/3/movie/{id_tmdb}?api_key={TMDB_API_KEY}").json()
            if tm.get("imdb_id"): termos.insert(0, tm["imdb_id"])
            if tm.get("original_title"): termos.append(tm["original_title"])

        for t in termos:
            # Busca Instantânea (Trackers mundiais)
            inst = requests.get(f"https://api.alldebrid.com/v4/magnets/instant?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(t)}").json()
            if inst.get("status") == "success" and inst["data"]["magnets"][0]["instant"]:
                mag = f"magnet:?xt=urn:btih:{inst['data']['magnets'][0]['hash']}"
                up = requests.get(f"https://api.alldebrid.com/v4/magnet/upload?agent=CineMega&apikey={ALLDEBRID_API}&magnets[]={urllib.parse.quote(mag)}").json()
                if up.get("status") == "success":
                    m_id = up["data"]["magnets"][0]["id"]
                    time.sleep(4)
                    st = requests.get(f"https://api.alldebrid.com/v4/magnet/status?agent=CineMega&apikey={ALLDEBRID_API}&id={m_id}").json()
                    links = st.get("data", {}).get("magnets", {}).get(str(m_id), {}).get("links", [])
                    if links:
                        un = requests.get(f"https://api.alldebrid.com/v4/link/unlock?agent=CineMega&apikey={ALLDEBRID_API}&link={urllib.parse.quote(links[0]['link'])}").json()
                        return un.get("data", {}).get("link")
        return None
    except: return None

@app.route("/buscar")
def buscar():
    titulo = request.args.get("titulo", "")
    tmdb_id = request.args.get("id", "")
    if not titulo: return "Vazio", 400
    
    t_busca = limpar_texto(titulo)
    
    # 1. TENTA SEU ARCHIVE PRIMEIRO (Fome Animal tem que sair daqui!)
    if t_busca in catalogo_pessoal:
        link = obter_link_direto_ia(catalogo_pessoal[t_busca])
        if link: return redirect(link)
    
    # 2. TENTA ALLDEBRID (Multi-Tracker)
    link_debrid = buscar_alldebrid_pro(t_busca, tmdb_id)
    if link_debrid: return redirect(link_debrid)

    # 3. TENTA M3U
    if t_busca in catalogo_filmes:
        return redirect(catalogo_filmes[t_busca][0])

    # 4. ÚLTIMO RECURSO (VIDSRC)
    if tmdb_id:
        return redirect(f"https://vidsrc.to/embed/movie/{tmdb_id}")
    
    return "Não encontrado", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
