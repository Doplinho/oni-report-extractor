# Spec — Dashboard ONI, Fase 3 (estoques no painel)

## Objetivo
O mod agora exporta estoques. O dashboard passa a mostrar o que falta para decidir enquanto joga: quanto há guardado e
quanto dura. Mantém tudo o que a spec `specs/dashboard-mvp.md` já entrega.

## Limites (obrigatório)
- Trabalhe só em `C:\oni-dashboard`, branch atual `codex/dashboard-estoques`. Sem commit, push ou merge.
- A pasta real de export é somente leitura. Não altere `tests/fixtures/`. Não toque em outras pastas. Não encerre processos
  que você não iniciou. Não instale nada. O jogo pode estar aberto: não interaja com ele.
- Não crie o atalho na Área de Trabalho; só o script que o cria.
- Use `.venv\Scripts\python.exe`. Grave em UTF-8 e confira os acentos: sem `Set-Content`/`Out-File` sem codificação.
- Código legível, no estilo dos arquivos atuais. Não refatore o que não precisa mudar.

## Dados validados no jogo (formato v2)
Veja um exemplo em `tests/fixtures/export_v2/colonies/<id>/report_cycle_256.json`. Campos novos, todos opcionais na leitura:
`SchemaVersion`, `ColonyName`, `ColonyId`, `Snapshot` e `Notes` nas entradas de `EnergyCreated`, `EnergyWasted` e
`OxygenCreated`. Regras:
- **Reserva de comida** = soma de `Worlds[].RationKcalRaw` ÷ 1000, em kcal.
- **Energia armazenada** = soma de `Worlds[].TrackerBatteryRaw`, em J, ÷1000 = kJ. **Não use `BatteryJoules`**: ele conta
  também a reserva interna de transformadores e fica acima da tela. Capacidade = soma de `BatteryCapacityJoules`, rotulada como
  aproximada pelo mesmo motivo.
- **Energia:** a unidade está confirmada. Troque "kJ (a confirmar)" por "kJ" em todo lugar.
- **Stress real** = `Duplicants[].Stress`, em %.
- **Materiais:** `Materials[].Kg` por `Tag` é o valor **disponível** da tela de recursos, já sem o reservado. Rotule como
  "Disponível". Nomes na tela: `Algae` Algae, `Carbon` Coal, `Cuprite` Copper Ore, `Copper` Copper, `GoldAmalgam` Gold Amalgam,
  `IronOre` Iron Ore, `Iron` Iron. Some entre mundos.
- `Snapshot.Errors` não vazio vira aviso no bloco Estado, com o ciclo.
- **Notas:** texto com marcação `<link="X">Nome</link>`: mostre só `Nome`.

## Carga (`load.py`)
Pastas: `export\colonies\<id>\report_cycle_N.json` e os arquivos soltos em `export\`.
- **Colônia ativa** = a pasta em `colonies\` com o `Timestamp` mais recente. Mostrar o `ColonyName` no bloco Estado. Se houver
  mais de uma colônia, avisar quantas e qual está exibida.
- Dentro da colônia ativa valem os arquivos da pasta dela.
- Arquivos soltos: os com `ColonyId` igual ao da colônia ativa são cópias e são ignorados; com outro `ColonyId`, ignorados.
  Os sem `ColonyId` são **legado**: entram só se o ciclo for menor que o primeiro ciclo da colônia ativa.
- Sem pasta `colonies\`: comportamento atual, só com os arquivos soltos.
- Regras de linha do tempo, lacuna, cache e erro continuam valendo sobre o conjunto resultante.
- `revision()` cobre os dois locais.

## Cálculos (`metrics.py`)
Ciclos sem snapshot têm `None`, nunca 0, e os gráficos não interpolam entre eles.
- `food_stock_kcal`; `energy_stored_kj`; `energy_capacity_kj`; materiais por nome.
- **Ciclos de comida restantes** = reserva atual ÷ média de consumo dos últimos 10 ciclos (consumo positivo, só duplicantes).
  Rotule como estimativa. Sem consumo ou sem reserva: "—".
- Variação de cada material: em relação ao ciclo anterior e média por ciclo nos últimos 10.
- `Stress` atual por duplicante, do snapshot do último ciclo.
- Fontes de energia e oxigênio no último ciclo com notas, em função pura e testada:
  - energia: geradores (`Value` positivo) e consumidores (`Value` negativo) em `EnergyCreated` total, somando nomes iguais, do
    maior para o menor; perdas de `EnergyWasted` total;
  - oxigênio: produtores (`Value` positivo) em `OxygenCreated` total. Notas com nome de duplicante não entram: a respiração já
    aparece no painel.

## Tela (`app.py`)
**O que olhar agora:** 5 cartões, nesta ordem:
1. Reserva de comida: kcal e ciclos restantes (estimativa).
2. Energia armazenada: kJ e percentual da capacidade.
3. Maior stress: nome e % real. Sem snapshot, mantém a estimativa atual, rotulada como tal.
4. Saldo de comida na média de 10 ciclos. 5. Eventos nos últimos 10 ciclos.

Sem dado de snapshot, mostrar "aguardando atualização do mod", como hoje.

**Gráficos**, seguindo o mesmo modo seguindo/zoom dos atuais:
- `food-stock`, novo, logo depois de Comida: reserva em kcal.
- Energia: linha nova "Armazenada", em kJ. A nota fixa passa a ser "A variação estimada não mede a carga: use a linha Armazenada.".
- `materials`, novo, substitui o painel "aguardando": uma linha por material, em kg, disponível, com legenda clicável. Abaixo,
  tabela com disponível atual, variação no último ciclo e média por ciclo em 10 ciclos.

**Tabelas:**
- Stress: nova coluna "Stress atual" antes das demais, ordenando por ela quando houver dado.
- Abaixo de Energia: geradores, consumidores e perdas do último ciclo. Abaixo de Oxigênio: produtores. Sem notas: "sem dados de
  fonte".

## Abertura
- `python -m oni_dashboard --open`: garante o servidor e abre uma janela em modo app no endereço do dashboard, com Edge
  (`msedge --app=`), e `webbrowser` se o Edge não existir. A abertura só ocorre depois de o servidor responder.
- Se já houver instância (mutex): não sobe outra; só abre a janela.
- Deve funcionar sob `pythonw.exe`, sem console: `sys.stdout`/`sys.stderr` podem ser `None`. Trate isso antes de subir o Dash.
- `tools/criar_atalho.ps1`: cria na Área de Trabalho o atalho "Dashboard ONI", chamando `.venv\Scripts\pythonw.exe -m
  oni_dashboard --open`, com pasta inicial na raiz do projeto. Só escreve esse atalho. Não o execute.

## README
Atualize com abertura, atalho, pastas e limites conhecidos.

## Critérios de aceite
Com `pytest`, usando `tests/fixtures/export`, `tests/fixtures/export_v2` e cópias em `tmp_path`:
1. Todos os testes anteriores continuam passando, ajustando só o que a spec mudou de propósito.
2. Valores do ciclo 256: reserva 17132,928 kcal; armazenada 288,929 kJ; Coal 4187,2 kg (±0,1); Gold Amalgam 12117,9 kg (±0,1); e
   `BatteryJoules` nunca é usado para energia armazenada.
3. Junção: legado 171–253 mais v2 254–256 resulta em 171–256, sem duplicar e sem aviso de lacuna.
4. Cópia solta de ciclo v2 é ignorada. Arquivo solto de outra colônia é ignorado.
5. Duas colônias: exibe a de `Timestamp` mais recente e avisa. Legado com ciclo maior ou igual ao primeiro da colônia não entra.
6. Ciclos de legado têm `None` em estoque, e a figura de reserva não preenche com 0.
7. Ciclos de comida restantes: conta verificada em um caso calculado à mão; sem consumo retorna "—".
8. Fontes: marcação `<link>` removida; nomes iguais somados; duplicantes fora dos produtores de oxigênio; ciclo sem notas tratado.
9. POST real ao callback de redesenho com fixtures v2 retorna 200, com os novos gráficos e cartões. Repetir com zoom em `materials`.
10. `--open`: testes de unidade com a abertura do navegador simulada, para os casos com e sem instância.
11. Nenhum `?` entre letras nem U+FFFD nos `.py` de `oni_dashboard/`.

Antes de terminar, rode `.venv\Scripts\python.exe -m pytest -q` e informe o resultado literal. Diga o que não pôde verificar. O
revisor fará a validação no navegador.
