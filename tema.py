# -*- coding: utf-8 -*-
"""
Tema visual (ttkbootstrap) do GERAPED.

Layout "barra lateral": navegação em azul-marinho à esquerda, conteúdo em
branco com cards de borda fina, e o laranja reservado pra ação principal.
"""

from ttkbootstrap.style import ThemeDefinition

NOME_TEMA = "requerid"

COR_PRIMARIA = "#2D315F"        # azul-marinho (barra lateral, títulos)
COR_SECUNDARIA = "#D3782A"      # laranja (ação principal)
COR_FUNDO = "#FFFFFF"
COR_FUNDO_SUAVE = "#EEF0F5"     # botões secundários "macios", caixa de resultado
COR_BORDA = "#E3E6EF"           # borda dos cards
COR_TEXTO = "#22243F"
COR_SUCESSO = "#1F7A4D"
COR_ERRO = "#C00000"
COR_AJUDA = "#6B7085"           # cinza-azulado: legendas de ajuda, sem disputar com o laranja da ação principal
COR_AVISO = "#8A5A00"           # âmbar escuro: avisos de verdade (com ⚠), distinto do laranja de "clique aqui"

COR_NAV_ATIVO = "#3B4070"       # item selecionado / hover na barra lateral
COR_NAV_TEXTO = "#C9CCE0"       # texto dos itens não selecionados
COR_NAV_ICONE = "#7FA8FF"       # azul mais vivo (céu) para o ícone do rodapé da sidebar -
                                 # dá um ponto de cor num canto que, só com COR_NAV_TEXTO em
                                 # tudo, ficava monocromático/apagado
COR_NAV_DIVISOR = "#454A7D"     # linha sutil acima do rodapé da sidebar, mais clara que o
                                 # fundo mas sem chamar tanta atenção quanto o laranja

CORES = {
    "primary": COR_PRIMARIA,
    "secondary": COR_SECUNDARIA,
    "success": COR_SUCESSO,
    "info": "#3B82C4",
    "warning": COR_AVISO,
    "danger": COR_ERRO,
    "light": COR_FUNDO_SUAVE,
    "dark": COR_TEXTO,
    "bg": COR_FUNDO,
    "fg": COR_TEXTO,
    "selectbg": COR_PRIMARIA,
    "selectfg": "#FFFFFF",
    "border": "#D5D9E5",
    "inputfg": COR_TEXTO,
    "inputbg": "#FFFFFF",
    "active": "#3B4070",
}

TEMA = ThemeDefinition(name=NOME_TEMA, colors=CORES, themetype="light")


def aplicar(root) -> "ttkbootstrap.Style":
    estilo = root.style
    estilo.register_theme(TEMA)
    estilo.theme_use(NOME_TEMA)

    estilo.configure(".", font=("Segoe UI", 10))
    estilo.configure("TButton", padding=(14, 8))
    estilo.configure("TEntry", padding=(8, 6))

    # Cards NÃO usam mais ttk.Labelframe nativo (ver _criar_cartao em interface.py) - o
    # Labelframe tem um bug de renderização real (reproduzido isolado, fora deste app, com
    # qualquer tema ttkbootstrap): o traço da borda antes do texto do título simplesmente
    # não desenha. Inofensivo em branco-sobre-branco (o padrão de antes), mas visível assim
    # que a página ganhou um fundo cinza ao redor dos cards (ver Pagina.TFrame). O título
    # do card volta a ficar DENTRO do quadrado branco (fundo COR_FUNDO, não COR_FUNDO_SUAVE),
    # encostado na borda superior - só que como um Label de verdade, não embutido na borda
    # do jeito que o Labelframe fazia (a borda em si é montada com Frames simples).
    estilo.configure(
        "TituloCartaoInterno.TLabel", foreground=COR_PRIMARIA, background=COR_FUNDO,
        font=("Segoe UI", 11, "bold"),
    )
    estilo.configure("Ajuda.TLabel", foreground=COR_AJUDA, font=("Segoe UI", 9))
    estilo.configure("Aviso.TLabel", foreground=COR_AVISO, font=("Segoe UI", 9))
    estilo.configure("Titulo.TLabel", foreground=COR_PRIMARIA, background=COR_FUNDO_SUAVE, font=("Segoe UI", 16, "bold"))
    estilo.configure("Descricao.TLabel", foreground=COR_AJUDA, background=COR_FUNDO_SUAVE, font=("Segoe UI", 10))
    # Fundo cinza-clarinho por trás dos cards nas páginas (Pedido/Ordem/Histórico) - só
    # branco (COR_FUNDO) tanto na página quanto no card deixava os dois "mesclados", sem
    # nada delimitando onde um card começa e a página termina. O card em si continua branco
    # (TLabelframe não é tocado aqui) - só o que fica AO REDOR do card muda de cor.
    estilo.configure("Pagina.TFrame", background=COR_FUNDO_SUAVE)

    # barra lateral
    estilo.configure("Sidebar.TFrame", background=COR_PRIMARIA)
    estilo.configure("Acento.TFrame", background=COR_SECUNDARIA)
    estilo.configure("Sidebar.TLabel", background=COR_PRIMARIA, foreground="#FFFFFF")
    estilo.configure("SidebarSuave.TLabel", background=COR_PRIMARIA, foreground=COR_NAV_TEXTO, font=("Segoe UI", 9))
    for nome, fundo, texto, fonte, preenchimento in (
        ("Nav.TButton", COR_PRIMARIA, COR_NAV_TEXTO, ("Segoe UI", 11), (20, 12)),
        ("NavAtivo.TButton", COR_NAV_ATIVO, "#FFFFFF", ("Segoe UI", 11, "bold"), (20, 12)),
    ):
        estilo.configure(
            nome, background=fundo, foreground=texto, bordercolor=fundo, lightcolor=fundo, darkcolor=fundo,
            focuscolor=fundo, focusthickness=0, relief="flat", anchor="w", padding=preenchimento, font=fonte,
        )
        estilo.map(
            nome,
            background=[("active", COR_NAV_ATIVO), ("pressed", COR_NAV_ATIVO)],
            bordercolor=[("active", COR_NAV_ATIVO), ("pressed", COR_NAV_ATIVO)],
            lightcolor=[("active", COR_NAV_ATIVO), ("pressed", COR_NAV_ATIVO)],
            darkcolor=[("active", COR_NAV_ATIVO), ("pressed", COR_NAV_ATIVO)],
            foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")],
        )

    # link do rodapé (Notas de atualização): ícone e texto em rótulos separados, com o
    # ícone numa coluna de largura fixa - hover só com texto/ícone laranja (sem preencher a
    # barra inteira com um bloco de fundo como os itens de navegação acima, que chamava
    # atenção demais pra um link secundário). Trocado manualmente via bind, não .map,
    # porque fonte (o sublinhado do hover) não é confiável de mapear por estado.
    estilo.configure("SidebarLink.TLabel", background=COR_PRIMARIA, foreground=COR_NAV_TEXTO, font=("Segoe UI", 9))
    estilo.configure(
        "SidebarLinkAtivo.TLabel", background=COR_PRIMARIA, foreground=COR_SECUNDARIA,
        font=("Segoe UI", 9, "underline"),
    )
    # ícone do link em azul mais vivo que o texto (ver COR_NAV_ICONE) - dá hierarquia entre
    # o "marcador" (ícone) e o texto secundário, em vez dos dois na mesma cor apagada
    estilo.configure("SidebarIcone.TLabel", background=COR_PRIMARIA, foreground=COR_NAV_ICONE, font=("Segoe UI", 9))
    estilo.configure("SidebarIconeAtivo.TLabel", background=COR_PRIMARIA, foreground=COR_SECUNDARIA, font=("Segoe UI", 9))
    estilo.configure("SidebarDivisor.TFrame", background=COR_NAV_DIVISOR)

    estilo.configure("Treeview", rowheight=26)
    return estilo
