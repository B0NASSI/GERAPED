"""Log de análise: um arquivo de texto por petição carregada, com o PORQUÊ de cada decisão do programa.

Serve para investigar depois um pedido estranho: qual tese foi aplicada e por quê (título, trecho que casou,
confiança, teses candidatas), como cada tabela foi lida, quais benefícios entraram e por quê (anterior x
excluído, critério usado), como foram decididos quantidade, espécies, índice singular/plural e NTP, o que ficou
pendente e, ao gerar o Word, o que o usuário mudou em relação à proposta.

Tudo local (pasta logs/analises ao lado do programa). Guarda números de NB/NIT/CNPJ e títulos de seção, mas
NÃO guarda nomes de empregados nem o texto dos parágrafos da petição.
"""
from __future__ import annotations

import re
import traceback
from datetime import datetime
from pathlib import Path

from .beneficios import eh_tabela_de_beneficios, ler_beneficios
from .pedidos import TESES_DE_NTP

MANTER_ARQUIVOS = 150            # análises mais antigas que isso são apagadas
LINHA = '=' * 100
SUB = '-' * 100


def pasta_de_analises(base_dir) -> Path:
    pasta = Path(base_dir) / 'logs' / 'analises'
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _nome_seguro(texto):
    return re.sub(r'[^\w\- ().]+', '_', texto).strip()[:70] or 'peticao'


def _podar(pasta: Path):
    arquivos = sorted(pasta.glob('ANALISE *.log'), key=lambda p: p.stat().st_mtime)
    for antigo in arquivos[:-MANTER_ARQUIVOS]:
        try:
            antigo.unlink()
        except OSError:
            pass


def _cortar(texto, n=90):
    texto = re.sub(r'\s+', ' ', texto or '').strip()
    return texto if len(texto) <= n else texto[:n - 1] + '…'


def _tabelas_da_secao(sec, so_ntp):
    linhas = []
    for i, t in enumerate(sec.tabelas, 1):
        corpo = t.linhas[1:]
        larg = len(t.cabecalho)
        fora = sum(1 for l in corpo if len(l) != larg)
        linhas.append(f'    tabela {i}: {len(corpo)} linha(s) de dados, {larg} colunas'
                      f'{", continuada (cabeçalho repetido ou tabela sem cabeçalho unida)" if t.continuada else ""}')
        linhas.append(f'      cabeçalho: {[_cortar(c, 40) for c in t.cabecalho]}')
        try:
            if eh_tabela_de_beneficios(t, sem_especie=so_ntp):
                bs = ler_beneficios(t, sem_especie=so_ntp)
                especies = {}
                for b in bs:
                    especies[b.especie or '(sem espécie)'] = especies.get(b.especie or '(sem espécie)', 0) + 1
                linhas.append(f'      reconhecida como TABELA DE BENEFÍCIOS: {len(bs)} benefício(s) distintos; espécies {especies}'
                              f'{"; leitura sem exigir espécie (tese de NTP)" if so_ntp else ""}')
                if fora:
                    linhas.append(f'      {fora} linha(s) com largura diferente do cabeçalho (célula mesclada): lidas por formato')
                repetidos = len(corpo) - len(bs)
                if repetidos > 0:
                    linhas.append(f'      {repetidos} linha(s) repetem um NB já lido (benefício em mais de uma vigência/CNPJ): unidas')
            else:
                linhas.append('      não é tabela de benefícios (usada só para vigências/CNPJ, se a tese for por vigência)')
        except Exception as e:      # noqa: BLE001 - o log nunca pode derrubar o programa
            linhas.append(f'      (erro ao reler a tabela para o log: {type(e).__name__}: {e})')
    return linhas


def relatorio_analise(caminho, peticao, deteccao, proposta, versao='') -> str:
    L = []
    caminho = Path(caminho)
    L += [LINHA, f'ANÁLISE DE PETIÇÃO — GERAPED {versao}'.strip(), LINHA,
          f'Data/hora : {datetime.now():%d/%m/%Y %H:%M:%S}',
          f'Arquivo   : {caminho.name}',
          f'Pasta     : {caminho.parent}',
          f'Seções    : {len(peticao.secoes)} ({sum(1 for s in peticao.secoes if s.numero)} numeradas); '
          f'tabelas no documento: {len(peticao.tabelas)}']
    if peticao.avisos:
        L.append('Avisos da leitura do documento:')
        L += [f'  ! {a}' for a in peticao.avisos]

    # 1. teses por seção
    L += ['', SUB, '1. SEÇÕES E TESES — por que cada tese foi aplicada', SUB]
    por_secao = {d.secao_numero: d for d in deteccao.deteccoes}
    estruturais = {n for n, _ in deteccao.estruturais}
    nao_class = {n for n, _ in deteccao.nao_classificadas}
    for s in peticao.secoes:
        if not s.nivel:
            continue
        rotulo = f'[{s.numero or "-"}] {_cortar(s.titulo)}'
        d = por_secao.get(s.numero) if s.numero else None
        if d:
            L.append(f'{rotulo}')
            L.append(f'    -> TESE {d.tese_key} | confiança {d.confianca} | origem {d.origem} | evidência {d.evidencia!r}')
            if d.candidatas:
                L.append('    candidatas (pontos): ' + ', '.join(f'{k}={p}' for k, p in d.candidatas))
            if d.origem == 'herdada':
                L.append('    (sem pista própria: herdou a tese da seção-mãe)')
            elif d.origem == 'corpo':
                L.append('    (o título não bastou: a tese veio de palavras-chave no texto da seção; nunca é confiança alta)')
        elif s.numero in estruturais:
            L.append(f'{rotulo}\n    -> seção estrutural (não é tese): ignorada')
        elif s.numero in nao_class:
            L.append(f'{rotulo}\n    -> NÃO CLASSIFICADA: nenhuma regra reconheceu o título nem o corpo')
        else:
            L.append(f'{rotulo}\n    -> sem classificação')
    if deteccao.possiveis_nao_detectadas:
        L.append('')
        L.append('Teses citadas no texto sem seção própria (só aviso):')
        for chave, ocorrencias, evid in deteccao.possiveis_nao_detectadas:
            L.append(f'  - {chave}: {ocorrencias} ocorrência(s); trecho {evid!r}')

    # 2. tabelas
    L += ['', SUB, '2. TABELAS — como cada uma foi lida', SUB]
    for s in peticao.secoes:
        if not s.tabelas:
            continue
        d = por_secao.get(s.numero) if s.numero else None
        so_ntp = bool(d and d.tese_key in TESES_DE_NTP)
        L.append(f'Seção {s.numero or "-"} ({_cortar(s.titulo, 60)}):')
        L += _tabelas_da_secao(s, so_ntp)

    # 3. pedidos
    L += ['', SUB, f'3. PEDIDOS PROPOSTOS ({len(proposta.pedidos)}) — na ordem em que aparecem na tela', SUB]
    for i, p in enumerate(proposta.pedidos, 1):
        dd = p.dados
        L.append('')
        L.append(f'PEDIDO {i} | seção {p.secao_numero} | item {dd["item_peticao"]} | {p.tese_nome} | '
                 f'confiança {p.confianca} | válido: {"sim" if p.valido else "NÃO"}')
        L.append(f'  quantidade={dd["quantidade"]}  espécies={dd["especies"]}  índice_singular={dd["indice_singular"]}  '
                 f'índice_plural={dd.get("indice_plural")}  excluir_NTP={dd["excluir_ntp"]}  '
                 f'parâmetro={dd["parametro_valor"]!r}  vigências={dd["campo_texto_valor"]!r}  '
                 f'vários_estabelecimentos={dd["varios_estabelecimentos"]}  incluir_tabela={p.incluir_tabela}')
        for g in dd['grupos_subsidiarios']:
            L.append(f'  subsidiária: tese {g["tese_subsidiaria_key"]} (item {g["item_peticao"]}), '
                     f'{"todos os benefícios do principal" if g["todos_beneficios_principal"] else str(g["numeros_com_especie"])}')
        if p.logica:
            L.append('  LÓGICA:')
            L += [f'    - {t}' for t in p.logica]
        if p.beneficios:
            L.append(f'  BENEFÍCIOS NO PEDIDO ({len(p.beneficios)}):')
            for b in p.beneficios:
                L.append(f'    NB {b.numero} | {b.especie or "(sem espécie)"} | NIT {b.nit or "-"} | item da planilha {b.item or "-"} | '
                         f'ordem {b.ordem} | DIB {b.dib or "-"} DCB {b.dcb or "-"} | vigências {sorted(b.vigencias)} | '
                         f'CNPJ {sorted(b.cnpjs)} | NTP {b.ntp}')
                L.append(f'       decisão: {b.decisao or "excluído (a tese exclui todos os benefícios da tabela)"}')
        if p.notas:
            L.append('  NOTAS:')
            L += [f'    * {t}' for t in p.notas]
        if p.pendencias:
            L.append('  PENDÊNCIAS (o usuário precisa conferir):')
            L += [f'    ! {t}' for t in p.pendencias]

    # 4. teses sem pedido
    com_pedido = {p.secao_numero for p in proposta.pedidos}
    sem = [d for d in deteccao.deteccoes if d.secao_numero and d.secao_numero not in com_pedido]
    L += ['', SUB, '4. SEÇÕES COM TESE QUE NÃO VIRARAM PEDIDO PRÓPRIO', SUB]
    if sem:
        for d in sem:
            L.append(f'  [{d.secao_numero}] {d.tese_key}: a tabela é só um resumo das subseções (os benefícios já estão '
                     'nos pedidos filhos) ou a seção não gerou pedido válido')
    else:
        L.append('  (nenhuma)')

    # 5. resumo
    pend = sum(1 for p in proposta.pedidos if p.pendencias)
    L += ['', SUB, '5. RESUMO', SUB,
          f'pedidos propostos: {len(proposta.pedidos)} | com pendência: {pend} | inválidos: '
          f'{sum(1 for p in proposta.pedidos if not p.valido)}',
          f'seções não classificadas: {len(deteccao.nao_classificadas)} | teses citadas sem seção: '
          f'{len(deteccao.possiveis_nao_detectadas)}', '']
    return '\n'.join(L)


def salvar_analise(base_dir, caminho_peticao, peticao, deteccao, proposta, versao='') -> Path:
    pasta = pasta_de_analises(base_dir)
    nome = f'ANALISE {datetime.now():%Y-%m-%d %Hh%M-%S} - {_nome_seguro(Path(caminho_peticao).stem)}.log'
    arquivo = pasta / nome
    arquivo.write_text(relatorio_analise(caminho_peticao, peticao, deteccao, proposta, versao), encoding='utf-8')
    _podar(pasta)
    return arquivo


def salvar_erro(base_dir, caminho_peticao, exc, versao='') -> Path:
    """Falha ao ler a petição: grava o rastro completo para investigar."""
    pasta = pasta_de_analises(base_dir)
    nome = f'ANALISE {datetime.now():%Y-%m-%d %Hh%M-%S} - ERRO - {_nome_seguro(Path(caminho_peticao).stem)}.log'
    arquivo = pasta / nome
    arquivo.write_text('\n'.join([
        LINHA, f'ERRO AO LER A PETIÇÃO — GERAPED {versao}'.strip(), LINHA,
        f'Data/hora : {datetime.now():%d/%m/%Y %H:%M:%S}', f'Arquivo   : {Path(caminho_peticao).name}', '',
        ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))]), encoding='utf-8')
    _podar(pasta)
    return arquivo


_CAMPOS = ('tese_key', 'item_peticao', 'quantidade', 'especies', 'parametro_valor', 'campo_texto_valor',
           'indice_singular', 'excluir_ntp', 'ntp_singular', 'varios_estabelecimentos')


def anotar_geracao(arquivo_analise, proposta, blocos, dados_finais, caminho_docx):
    """Acrescenta ao log da análise o que foi gerado e o que o usuário mudou em relação à proposta."""
    L = ['', LINHA, f'GERAÇÃO DO WORD — {datetime.now():%d/%m/%Y %H:%M:%S}', LINHA,
         f'Arquivo salvo: {caminho_docx}', f'Pedidos no documento: {len(dados_finais)}', '']
    propostos_usados = set()
    for i, (bloco, final) in enumerate(zip(blocos, dados_finais), 1):
        prop = getattr(bloco, 'proposto', None)
        cab = f'PEDIDO {i} | item {final["item_peticao"]} | tese {final["tese_key"]}'
        if prop is None:
            L.append(f'{cab}: ADICIONADO À MÃO (não veio da petição)')
            continue
        propostos_usados.add(id(prop))
        difs = [f'{c}: {prop.dados.get(c)!r} -> {final.get(c)!r}' for c in _CAMPOS if prop.dados.get(c) != final.get(c)]
        if len(prop.dados.get('grupos_subsidiarios', [])) != len(final.get('grupos_subsidiarios', [])):
            difs.append(f'subsidiárias: {len(prop.dados["grupos_subsidiarios"])} -> {len(final["grupos_subsidiarios"])}')
        if prop.pendencias:
            difs.append(f'(tinha {len(prop.pendencias)} pendência(s) na proposta)')
        L.append(f'{cab}: ' + ('igual à proposta' if not difs else 'ALTERADO pelo usuário'))
        L += [f'    {d}' for d in difs]
    for p in proposta.pedidos:
        if id(p) not in propostos_usados:
            L.append(f'REMOVIDO pelo usuário: pedido proposto da seção {p.secao_numero} (item {p.dados["item_peticao"]}, {p.tese_nome})')
    L.append('')
    with open(arquivo_analise, 'a', encoding='utf-8') as f:
        f.write('\n'.join(L))
