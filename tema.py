# -*- coding: utf-8 -*-
from ttkbootstrap.style import ThemeDefinition

NOME_TEMA = "requerid"

COR_PRIMARIA  = "#2D315F"   # navy (banner, destaque principal)
COR_SECUNDARIA = "#D3782A"  # laranja (ação principal, borda de cards)
COR_FUNDO     = "#F4F5F9"
COR_TEXTO     = "#22243F"
COR_SUCESSO   = "#1F7A4D"
COR_ERRO      = "#C00000"

CORES = {
    "primary":   COR_PRIMARIA,
    "secondary": COR_SECUNDARIA,
    "success":   COR_SUCESSO,
    "info":      "#3B82C4",
    "warning":   "#E0A526",
    "danger":    COR_ERRO,
    "light":     COR_FUNDO,
    "dark":      COR_TEXTO,
    "bg":        COR_FUNDO,
    "fg":        COR_TEXTO,
    "selectbg":  COR_PRIMARIA,
    "selectfg":  "#FFFFFF",
    "border":    "#C9CCE0",
    "inputfg":   COR_TEXTO,
    "inputbg":   "#FFFFFF",
    "active":    "#3B4070",
}

TEMA = ThemeDefinition(name=NOME_TEMA, colors=CORES, themetype="light")


def aplicar(root) -> "ttkbootstrap.Style":
    estilo = root.style
    estilo.register_theme(TEMA)
    estilo.theme_use(NOME_TEMA)

    F  = ("Segoe UI", 10)
    FB = ("Segoe UI", 10, "bold")

    estilo.configure(".",                 font=F)
    estilo.configure("TLabel",            font=F)
    estilo.configure("TButton",           font=F,  padding=(8, 5))
    estilo.configure("TEntry",            font=F,  padding=4)
    estilo.configure("TCombobox",         font=F,  padding=4)
    estilo.configure("TCheckbutton",      font=F)
    estilo.configure("TRadiobutton",      font=F)
    estilo.configure("TLabelframe.Label", font=FB)
    estilo.configure("TNotebook.Tab",     font=FB, padding=(14, 8))

    return estilo
