# Spec — Dashboard ONI, Fase 1 (dados existentes)

## Objetivo
Dashboard local em Python que mostra, ao vivo, os relatórios por ciclo do Oxygen Not Included, para o jogador decidir
enquanto joga. Esta fase usa só os JSON existentes. Não altera o mod.

Uso real: o jogo fica em um monitor; o dashboard fica em um **monitor vertical, dividido com vídeos**. Portanto a janela é
estreita (projete para 540–1080 px de largura), em **coluna única, com rolagem permitida**. Textos da interface em
português do Brasil.

## Limites (obrigatório)
- Trabalhe só em `C:\oni-dashboard`, branch atual `codex/dashboard-mvp`. Não faça commit, push nem merge.
- A pasta real de export (`<Documentos>\Klei\OxygenNotIncluded\export`) é **somente leitura**.
- Não toque em `C:\oni-report-extractor`, no monitor do Codex, em `<Documentos>\Codex`, na pasta Inicializar
  nem no Cérebro. Não encerre processos. Não crie atalhos.
- Dependências já instaladas em `.venv` (dash 4.5.0, plotly 7.1.0, pandas 3.1.0, pytest 9.2.0). Não instale outras.
  Rode tudo com `.venv\Scripts\python.exe`.
- Os arquivos em `tests/fixtures/export` são cópia fixa de 83 JSON (ciclos 171–253). Não os altere.

## Arquivos
```
.gitignore              .venv/, __pycache__/, .pytest_cache/, logs/
requirements.txt        versões exatas de dash, plotly, pandas, pytest
README.md               como rodar e testar; limites conhecidos
oni_dashboard/
  __init__.py
  __main__.py           CLI: --export-dir, --port (padrão 8050); host fixo 127.0.0.1; debug desligado
  load.py               leitura, cache, linha do tempo
  metrics.py            cálculos, sem dependência de Dash
  app.py                layout, gráficos, callbacks
tests/                  pytest
```
Pasta padrão de export: a real, citada acima. Se não existir na partida, o servidor sobe mesmo assim, mostra o aviso e
continua tentando.

## Formato de entrada
`report_cycle_N.json`: `Cycle`, `Timestamp` (ISO com fuso), `Entries[]` com `Category`, `Context` (null = total),
`NetValue`, `PositiveValue`, `NegativeValue`. Ler com `utf-8-sig`. Ignorar categorias `*Header`. Ignorar campos
desconhecidos: o formato ganhará campos novos.

## Carga (`load.py`)
- Cache por (caminho, mtime, tamanho). Reprocessar só o que mudou.
- Em erro ao ler ou interpretar um arquivo (o mod apaga o destino antes de renomear; o OneDrive pode travá-lo), manter a
  última versão válida em cache, sem derrubar nada; tentar de novo na próxima verificação.
- `Cycle` do conteúdo diferente do nome do arquivo: descartar o arquivo e gerar aviso.
- **Linha do tempo:** o arquivo com `Timestamp` mais recente define o ciclo atual. Ciclos maiores que ele pertencem a uma
  linha do tempo abandonada (save recarregado): ficam fora dos gráficos e geram aviso com a quantidade.
- Lacunas de ciclo: nunca interpolar. Gerar aviso com os ciclos faltantes.
- Queda grande: se o ciclo atual definido pela regra acima ocultar 50 ou mais ciclos, o aviso indica possível troca de colônia.

## Cálculos (`metrics.py`)
**Comida (kcal = cal ÷ 1000).** Contextos especiais: `Harvested`, `Butchered`, `Rotted`. Todo outro contexto é duplicante.
Ausência de um contexto especial = 0.
- `consumo` = soma dos contextos de duplicantes. Saldo = `NetValue`.
- Reconciliação: `Positive = Harvested + Butchered` e `Negative = duplicantes + Rotted`, com **tolerância de 5 cal**.
- Média móvel de 10 ciclos do saldo, com banda de mín–máx na mesma janela. Consumo por duplicante não é exibido.

**Oxigênio (kg).** Produzido = `PositiveValue`; "Respiração" = `NegativeValue` (rotule assim, não como "consumo"). Saldo =
`NetValue`. Média móvel de 10 ciclos.

**Energia.** Dados brutos em J; exibir ÷1000 com a unidade **"kJ (a confirmar)"**.
- Gerada = `EnergyCreated.PositiveValue`; consumida = `EnergyCreated.NegativeValue`; desperdiçada = `EnergyWasted.NetValue`.
- **Saldo real = `EnergyCreated.NetValue + EnergyWasted.NetValue`**. Não exibir `EnergyCreated.NetValue` sozinho como saldo.
- Acumulado do saldo real, rotulado **"variação estimada armazenada"**, a partir de 0 no primeiro ciclo visível.
- Nota fixa no painel: não indica falta de energia nem carga de bateria.

**Stress.** Não exibir saldo agregado como sinal. Por duplicante (contexto de `StressDelta`):
- heatmap duplicante × ciclo, escala divergente centrada em 0, com faixa de cor simétrica saturada no percentil 95 do módulo;
- ciclos positivos consecutivos até o ciclo atual;
- soma dos deltas positivos nos últimos 10 ciclos;
- "maior pressão de stress": duplicante presente no ciclo atual com a maior soma, rotulado como estimativa.

**Eventos**, do ciclo mais recente ao mais antigo:
- duplicante entrou ou saiu: presença = união dos contextos de `StressDelta` e `OxygenCreated`; compara ciclos consecutivos;
  sem evento no primeiro ciclo carregado. Uma saída não identifica a causa: escreva "saiu dos relatórios";
- `ToiletIncident`, `ContaminatedOxygenToilet` ou `ContaminatedOxygenSublimation` com `NetValue` diferente de 0;
- `DiseaseStatus` total acima de `DISEASE_ALERT = 10000` (constante nomeada).

Nenhuma cor vermelho/verde deve depender do sinal de um único saldo.

## Tela (`app.py`), de cima para baixo
1. **Estado:** último ciclo, horário e idade do dado, avisos de carga. Jogo aberto é detectado com `tasklist` por
   `OxygenNotIncluded.exe`; sem o jogo, mostrar "jogo fechado"; com o jogo aberto e dado com mais de 15 min, mostrar
   "exportação atrasada".
2. **O que olhar agora:** cartões. Com dados atuais: maior pressão de stress (estimativa), saldo de comida na média de 10
   ciclos, número de eventos nos últimos 10 ciclos. Cartões **"Reserva de comida"** e **"Energia armazenada"** com o texto
   "aguardando atualização do mod".
3. Comida. 4. Oxigênio. 5. Energia. 6. Stress. 7. Eventos.
8. **Materiais:** painel com Algae, Coal, Copper, Gold Amalgam e Iron marcados "aguardando atualização do mod".

Atualização: `dcc.Interval` de 5 s consulta uma revisão barata (arquivos + mtime) e só redesenha se mudou.

**Modo seguindo:** por padrão, a janela mostra os últimos 30 ciclos e anda sozinha. Controle para "últimos 30 / todos".
Se o usuário der zoom ou pan em um gráfico, esse gráfico sai do modo seguindo, o zoom é preservado entre atualizações e
aparece um botão visível "Voltar ao atual". O bloco Estado sempre mostra o ciclo mais recente.

Log: arquivo em `logs/dashboard.log`, tamanho limitado, nível WARNING, incluindo o logger `werkzeug`.

**Instância única:** mutex nomeado do Windows via `ctypes`, antes de subir o servidor. Segunda instância escreve no log e
sai com código 0.

Tema: fundo claro e escuro não são exigência; basta legibilidade em tema escuro. Cada gráfico com título e unidade.

## Critérios de aceite
Com testes `pytest` usando só `tests/fixtures/export` ou cópias em `tmp_path`:
1. Carrega 83 ciclos, 171–253, sem avisos.
2. Reconciliação de comida passa nos 83 ciclos com tolerância de 5 cal.
3. Valores de referência — ciclo 249: saldo +2437,649 kcal; `Rotted` 600; colheita 10800. Ciclo 219: saldo +305,9 kcal.
   Ciclo 220: `Rotted` 18175,992 kcal.
4. Energia nos 83 ciclos: gerada 52485 kJ, saldo real somado 171 kJ, `Net` somado 2326 kJ (arredondados).
5. Linha do tempo: reescrever uma cópia do ciclo 241 com o `Timestamp` mais recente oculta 242–253 e gera aviso.
6. Erro de leitura: corromper um arquivo já carregado mantém a versão em cache; apagar um ciclo gera aviso de lacuna.
7. Nome e conteúdo divergentes: arquivo descartado com aviso.
8. Eventos: detecta `ToiletIncident` nos ciclos 187, 197 e 211; Marie sai no 248 (último relatório dela é o 247); Nisbet entra no 247.
9. Campo JSON desconhecido não quebra a carga.
10. Layout do app constrói sem exceção, e todos os gráficos geram figura com dados das fixtures.
11. Teste de fumaça: o servidor sobe em porta livre e `/_dash-layout` responde 200 (encerrar o processo ao fim).

Antes de terminar: rode `.venv\Scripts\python.exe -m pytest -q` e informe o resultado literal. Informe também o que não
pôde verificar, em particular o comportamento visual no navegador.
