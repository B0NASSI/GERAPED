import os
import sys

# Os módulos do app (teses, gerador_pedido, validacao...) ficam soltos na raiz do
# projeto, sem empacotamento - garante que "tests/" consiga importá-los independente
# de onde o pytest for chamado.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
