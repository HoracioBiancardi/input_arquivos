# Arquivos de exemplo para testar o upload

Todos os arquivos representam a mesma tabela de vendas (produto, quantidade, valor_unitario), num
formato diferente cada — para testar rapidamente o upload de cada tipo de arquivo suportado pelo
sistema, pela tela `/` (upload) ou criando um contexto de teste em `/admin`.

| Arquivo | Tipo | Observação |
|---|---|---|
| `vendas.xlsx` | Excel | |
| `vendas.csv` | CSV | |
| `vendas.txt` | TXT | Delimitado por `;`, mesma lógica de detecção automática do CSV |
| `vendas.json` | JSON | Lista de objetos na raiz |
| `vendas.yaml` | YAML | Lista de objetos na raiz |
| `vendas.xml` | XML | Elementos `<item>` repetidos dentro de `<vendas>` |
| `vendas.ods` | ODS | Planilha do LibreOffice/OpenOffice Calc |
| `vendas.html` | HTML | Uma `<table>` dentro da página |
| `tabela_com_grade.png` | Imagem | Tabela com linhas de grade desenhadas — use um context com `image_mode = table_grid` |
| `tabela_sem_grade.png` | Imagem | Só texto alinhado por posição, sem grade — use `image_mode = table_borderless` |

As imagens usam só 2 colunas (`produto` já com a quantidade embutida no texto, ex. "Notebook
Prata (3 un)", e `valor_total`), em vez das 3 colunas separadas dos outros formatos. Isso não é
limitação do sistema — é uma escolha de conteúdo, baseada em duas descobertas testando manualmente
contra o OCR local (`RapidOCR`, via `img2table`):
1. Uma tabela com 3+ colunas onde uma delas é só um número curto isolado (ex. só "3") fica instável
   em OCR sobre texto sintético — a coluna inteira às vezes nem é detectada. Embutir a quantidade no
   texto do produto evita isso.
2. No modo sem grade (`table_borderless`), a primeira coluna precisa de bastante folga entre o fim
   do texto mais longo e o início da coluna de valor — com pouca margem, o OCR funde as duas colunas
   numa célula só na linha mais comprida. Por isso a primeira coluna é bem mais larga que o texto
   mais longo esperado.

Testado 3x em cada modo, 100% de acerto célula a célula.

## Notas

- Para testar as imagens, o context de teste precisa ter "Imagem" marcada nos tipos de arquivo
  aceitos, com o `image_mode` correspondente — não é preciso instalar nada além do `uv sync` normal
  (o OCR local usa `RapidOCR`, 100% Python/ONNX, sem binário de sistema).
- `tabela_sem_grade.png` tem uma linha extra no topo ("Cabo HDMI (1 un)") que não é venda real —
  é sacrificial. A detecção de tabela "sem grade" do img2table não separa uma linha de cabeçalho da
  tabela de dados, e o `ImageTableReader` sempre promove a primeira linha lida a cabeçalho de
  coluna; sem essa linha extra, a primeira venda real seria perdida (viraria nome de coluna em vez
  de dado). Em `tabela_com_grade.png` isso não é necessário porque o modo com grade detecta a linha
  de cabeçalho separadamente.
- Não há exemplo de PDF aqui: gerar um PDF com tabela de verdade exige uma biblioteca de escrita de
  PDF que não é dependência do projeto (mesmo motivo pelo qual não há teste automatizado de PDF —
  ver `tests/test_ingestion.py`). Para testar o caminho de PDF, exporte qualquer planilha/documento
  como PDF (Excel/LibreOffice → "Salvar como PDF") e envie esse arquivo.
- Esta pasta não faz parte da aplicação — é só material de apoio para teste manual.
