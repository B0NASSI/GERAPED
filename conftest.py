import os
import sys

# Os módulos do app (teses, gerador_pedido, validacao...) ficam soltos na raiz do
# projeto, sem empacotamento - garante que "tests/" consiga importá-los independente
# de onde o pytest for chamado.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# os testes de tela carregam petições: o log de análise delas vai para uma pasta temporária, não para logs/
import tempfile
os.environ.setdefault('GERAPED_PASTA_LOGS', tempfile.mkdtemp(prefix='geraped_logs_teste_'))
