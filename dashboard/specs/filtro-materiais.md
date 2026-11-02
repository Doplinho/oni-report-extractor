# Spec: todos os materiais e filtro no gráfico

## Objetivo

Hoje o mod exporta 7 materiais fixos, escolhidos para teste, e o gráfico mostra sempre os 7. A pessoa quer escolher, em uma lista pesquisável com os materiais disponíveis no relatório, quais aparecem no gráfico. A escolha fica mantida.

## Arquivos

- `src/ReportExtractorMod.cs`: exportar todos os materiais.
- `README.md` (raiz): descrição do formato.
- `dashboard/oni_dashboard/metrics.py`, `app.py`, `assets/dashboard.css`: dados e filtro.
- `dashboard/tests/test_dashboard.py`: testes.
- `dashboard/README.md`: como usar o filtro.

Limites: só `C:\oni-report-extractor`. Sem commit, push ou merge. Não altere `dashboard/tests/fixtures/` nem `build.ps1`. Rode `.\build.ps1` só **sem** `-Install`: o jogo está aberto. Não encerre processos que não iniciou. Não abra janelas do navegador. Grave em UTF-8. No C#, só C# 5.

## Parte 1: mod

1. `Snapshot.Worlds[].Materials` passa a listar todo recurso descoberto com quantidade maior que 0 no mundo, mais os 7 atuais sempre, mesmo com 0, para manter a compatibilidade.
2. Fonte da lista: `DiscoveredResources.Instance.GetDiscovered()`, se existir nesta build, com `world.worldInventory.GetAmount(tag, false)`, a mesma leitura de hoje, que dá o Disponível. **Nomes vêm de memória: valide compilando contra as DLLs do jogo.** Se a API não existir, procure a equivalente nas DLLs e diga no relatório qual usou e por quê.
3. `MaterialDto` ganha `Name`: nome de exibição sem marcação de link, como `TagManager.GetProperName(tag, true)`, se existir. Em falha, use o texto do tag.
4. `Tag` continua sendo o identificador estável: para os 7 atuais, o valor não muda (`Algae`, `Carbon`, `Cuprite`, `Copper`, `GoldAmalgam`, `IronOre`, `Iron`). Para os demais, use `tag.ToString()`.
5. Falha em um material não pode impedir os outros; registre em `Snapshot.Errors`, como hoje. Falha ao obter a lista descoberta não pode impedir os 7.
6. `SchemaVersion` passa a 3. Procure no repositório quem depende do valor. Os demais campos não mudam.

## Parte 2: dashboard

1. **Lista:** `dcc.Dropdown` com `id='material-filter'`, `multi=True`, `searchable=True`, logo acima do gráfico de materiais, no mesmo painel. O rótulo do campo é "Materiais no gráfico". As opções são todos os materiais vistos em qualquer relatório carregado da colônia ativa, em ordem alfabética, sem repetir. O valor de cada opção é o `Tag`.
2. **Nome:** use o `Name` mais recente do tag. Sem `Name`, use a tabela atual (`Carbon` = Coal, `Cuprite` = Copper Ore etc.). Sem nada disso, use o `Tag`.
3. **Padrão:** na primeira vez, os 7 materiais atuais selecionados.
4. **Escolha mantida:** a seleção sobrevive à chegada de novo ciclo, à troca de "Últimos 30"/"Todos", ao recarregar a página e ao reiniciar o servidor. Use `persistence=True`, `persistence_type='local'`. A atualização periódica não pode limpar a seleção nem o texto sendo digitado na pesquisa: só atualize `options` quando o conjunto de opções mudar (senão `no_update`).
5. **Gráfico e tabela:** o gráfico e a tabela abaixo dele mostram só os selecionados. Trocar a seleção **não pode** perder o zoom, nem de materiais nem de outro gráfico, nem marcar o gráfico como zoom manual. Sem seleção: gráfico vazio, com a mensagem "Selecione materiais na lista", e sem erro.
6. **Cores:** cada material mantém a mesma cor quando outros entram ou saem da seleção.
7. **Colunas dinâmicas:** troque as colunas fixas `material_<nome>` por um cálculo por `Tag`. Mantenha estoque, variação no ciclo e média de 10 ciclos.
8. **Ausência no relatório:** com `SchemaVersion >= 3`, material ausente em um ciclo vale 0 kg, pois a lista é completa. Com `SchemaVersion < 3`, material ausente fica sem dado (`NaN`), e nunca 0, para não desenhar uma queda falsa antes da mudança.
9. Relatórios v1 (sem `Snapshot`) e v2 continuam funcionando.

## Critérios de aceite

Testes novos, com relatórios v3 gerados em `tmp_path` a partir das fixtures:

- opções em ordem alfabética, com todos os materiais, usando `Name`, a tabela e o `Tag` nessa ordem;
- regra do item 8: v2 sem o tag dá `NaN`; v3 sem o tag dá 0;
- figura só com os selecionados; seleção vazia não gera erro;
- cor igual para o mesmo tag em seleções diferentes;
- POST real ao callback: mudar a seleção não altera `manual-graphs` nem `zoom-ranges`;
- callback periódico sem mudança de opções devolve `no_update` em `options`;
- o dropdown tem `searchable`, `multi` e `persistence` no layout.

Antes de terminar: rode `C:\oni-dashboard\.venv\Scripts\python.exe -m pytest -q` a partir de `dashboard/` e `.\build.ps1` na raiz. Informe os dois resultados literais e a API usada na Parte 1. Diga o que não pôde verificar.

## Parte 3: unidade dos itens

O relatório real do ciclo 270 trouxe sementes, comida e trajes em `Kg` (Atmo Suit = 5, Mealwood Seed = 1.077). Esses números parecem ser contagens, mas a tela diz kg.

### Mod

1. `MaterialDto` ganha `Unit`, com `"kg"` ou `"un"`.
2. A regra deve ser a mesma do jogo na tela de Recursos. Procure nas DLLs o que ele usa, como `GameTags.DisplayAsUnits`, `GameTags.UnitCategories`, `GameTags.MaterialCategories`, `GameTags.CalorieCategories` e `DiscoveredResources.Instance.GetCategoryForTag(tag)`. **Nomes vêm de memória: valide compilando, com chamadas diretas, sem reflexão.** Elementos são sempre `"kg"`. Itens da categoria de comida ficam `"un"`, sem converter para kcal.
3. Se não conseguir determinar a unidade, registre em `Snapshot.Errors` e use `"kg"`. Essa falha não pode impedir a exportação do material.
4. `SchemaVersion` continua 3: o campo é opcional, e a ausência dele significa `"kg"`.

### Dashboard

1. Use o `Unit` mais recente de cada tag, no mesmo helper dos nomes. Sem `Unit`, vale `"kg"`.
2. **Tabela:** a coluna passa a ser "Disponível" e ganha a coluna "Unidade". As colunas de variação continuam sem unidade própria.
3. **Gráfico:** itens em `"kg"` usam o eixo da esquerda, com título `kg`. Itens em `"un"` usam um eixo à direita, com título `unidades`, sobreposto (`yaxis2`, `overlaying='y'`, `side='right'`). Com só itens `"un"` selecionados, continuam no eixo da direita. O eixo da direita só existe se houver item `"un"` selecionado.
4. **Legenda:** itens em `"un"` aparecem como `Nome (un)`. A lista de seleção não muda.
5. Zoom, seguir o último ciclo, cores e seleção não podem mudar de comportamento.

### Critérios de aceite

Testes novos: `Unit` mais recente vale; ausência vale `"kg"`; `kg` e `un` selecionados geram dois eixos com cada trace no eixo certo; só `kg` não cria `yaxis2`; a tabela mostra a unidade; a legenda usa `(un)`.
