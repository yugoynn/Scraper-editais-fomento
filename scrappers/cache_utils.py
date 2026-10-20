import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def carregar_lista_json(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return []
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return dados if isinstance(dados, list) else []
    except Exception:
        return []


def normalizar_titulo(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_url(valor):
    valor = str(valor or "").strip()
    if not valor:
        return ""
    try:
        p = urlsplit(valor)
        path = re.sub(r"/+$", "", p.path or "") or "/"
        # Fragmentos costumam ser navegação interna; mantemos query, removemos fragmento.
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ""))
    except Exception:
        return valor.rstrip("/").lower()


class CacheColeta:
    def __init__(self, itens):
        self.por_link = {}
        titulos = {}
        repetidos = set()

        for item in itens or []:
            if not isinstance(item, dict):
                continue
            link = normalizar_url(
                item.get("link") or item.get("pagina_edital") or item.get("url") or ""
            )
            titulo = normalizar_titulo(item.get("titulo") or item.get("nome") or "")
            if link:
                self.por_link[link] = item
            if titulo:
                if titulo in titulos:
                    repetidos.add(titulo)
                else:
                    titulos[titulo] = item

        self.por_titulo = {k: v for k, v in titulos.items() if k not in repetidos}

    def buscar(self, link="", titulo=""):
        link_n = normalizar_url(link)
        if link_n and link_n in self.por_link:
            return self.por_link[link_n]
        titulo_n = normalizar_titulo(titulo)
        if titulo_n:
            return self.por_titulo.get(titulo_n)
        return None


def cache_do_arquivo(caminho):
    return CacheColeta(carregar_lista_json(caminho))


def tem_conteudo(item, *campos):
    if not item:
        return False
    return any(str(item.get(campo, "") or "").strip() for campo in campos)


def data_coleta_antiga(item):
    if not item:
        return ""
    return str(item.get("coletado_em") or item.get("baixado_em") or "").strip()
