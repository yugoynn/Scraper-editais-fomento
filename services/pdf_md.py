import pymupdf4llm
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PDF_DIR = (
    PROJECT_ROOT
    / "dados"
    / "fapesc"
    / "pdf"
)

MARKDOWN_DIR = (
    PROJECT_ROOT
    / "dados"
    / "fapesc"
    / "markdown"
)


def converter_pdfs(progresso=None):

    MARKDOWN_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    pdfs = list(
        PDF_DIR.glob("*.pdf")
    )

    total = len(pdfs)

    convertidos = 0
    pulados = 0
    erros = 0

    arquivos_convertidos = []

    print()
    print("=" * 60)
    print("PDF -> MARKDOWN")
    print("=" * 60)

    print(
        f"PDFs encontrados: {total}"
    )

    if progresso:
        progresso(
            processados=0,
            total=total,
            convertidos=0,
            pulados=0,
            erros=0,
            etapa="convertendo",
        )

    for indice, pdf_path in enumerate(
        pdfs,
        start=1
    ):

        print()
        print(
            f"[{indice}/{total}] "
            f"{pdf_path.name}"
        )

        md_path = (
            MARKDOWN_DIR
            / f"{pdf_path.stem}.md"
        )

        # Já existe
        if md_path.exists():

            print(
                "[PULADO] Markdown já existe."
            )

            # O PDF já cumpriu sua função. Remove a cópia redundante para que
            # ele não volte a aparecer na fila em execuções futuras.
            try:
                pdf_path.unlink()
                print("[PDF REDUNDANTE APAGADO]")
            except FileNotFoundError:
                pass
            except Exception as erro:
                print(f"[AVISO] Não foi possível apagar PDF redundante: {erro}")

            pulados += 1
            if progresso:
                progresso(
                    processados=indice,
                    total=total,
                    convertidos=convertidos,
                    pulados=pulados,
                    erros=erros,
                    item=pdf_path.name,
                    etapa="convertendo",
                )
            continue

        try:

            markdown = (
                pymupdf4llm
                .to_markdown(
                    str(pdf_path)
                )
            )

            # Validação
            if not markdown:

                print(
                    "[ERRO] Markdown vazio."
                )

                erros += 1
                if progresso:
                    progresso(
                        processados=indice,
                        total=total,
                        convertidos=convertidos,
                        pulados=pulados,
                        erros=erros,
                        item=pdf_path.name,
                        etapa="convertendo",
                    )
                continue

            if len(
                markdown.strip()
            ) < 100:

                print(
                    "[ERRO] Conteúdo insuficiente."
                )

                erros += 1
                if progresso:
                    progresso(
                        processados=indice,
                        total=total,
                        convertidos=convertidos,
                        pulados=pulados,
                        erros=erros,
                        item=pdf_path.name,
                        etapa="convertendo",
                    )
                continue

            # Salvar MD
            md_path.write_text(
                markdown,
                encoding="utf-8"
            )

            # Confirma se realmente existe
            if (
                md_path.exists()
                and md_path.stat().st_size > 0
            ):

                print(
                    f"[OK] {md_path.name}"
                )

                arquivos_convertidos.append({
                    "pdf": pdf_path.name,
                    "markdown": md_path.name,
                    "caracteres": len(markdown)
                })

                convertidos += 1

                # ==========================================
                # APAGAR PDF
                # ==========================================

                pdf_path.unlink()

                print(
                    "[PDF APAGADO]"
                )

            else:

                erros += 1

                print(
                    "[ERRO] Arquivo Markdown não salvo."
                )

        except Exception as erro:

            erros += 1

            print(
                f"[ERRO] {erro}"
            )

        if progresso:
            progresso(
                processados=indice,
                total=total,
                convertidos=convertidos,
                pulados=pulados,
                erros=erros,
                item=pdf_path.name,
                etapa="convertendo",
            )

    print()
    print("=" * 60)
    print("FINALIZADO")
    print("=" * 60)

    print(
        f"PDFs encontrados : {total}"
    )

    print(
        f"Convertidos       : {convertidos}"
    )

    print(
        f"Pulados           : {pulados}"
    )

    print(
        f"Erros             : {erros}"
    )

    return {
        "sucesso": True,
        "encontrados": total,
        "convertidos": convertidos,
        "pulados": pulados,
        "erros": erros,
        "arquivos": arquivos_convertidos
    }


if __name__ == "__main__":

    resultado = converter_pdfs()

    print(resultado)