# ONI Report Extractor

Mod para **Oxygen Not Included** que exporta o relatório diário de cada ciclo para JSON, para análise no Power BI, Excel ou Python. Testado na build **U59-744825**.

## Como funciona

Um patch Harmony em `ReportManager.OnNightTime` lê o relatório do ciclo recém-fechado e grava `report_cycle_N.json`. O formato mantém `Cycle`, `Timestamp` e `Entries` com os nomes e significados existentes. A versão 2 acrescenta `SchemaVersion`, identificação da colônia e `Snapshot`, com calorias brutas, baterias, sete materiais e estresse dos duplicantes por mundo. Leituras parciais que falham são descritas em `Snapshot.Errors`.

O arquivo é gravado em UTF-8 com troca atômica. O caminho principal é:

```
Documentos\Klei\OxygenNotIncluded\export\colonies\<ColonyId>\report_cycle_N.json
```

Enquanto `WriteLegacyRoot` estiver habilitado, também é gravada uma cópia compatível em `Documentos\Klei\OxygenNotIncluded\export\report_cycle_N.json`, usada pelas ferramentas atuais.

Cada categoria em `Entries` gera uma linha total (`Context = null`) e linhas de detalhe por duplicante/construção (`Context` preenchido). As categorias de energia criada, energia desperdiçada e oxigênio criado também podem incluir notas.

## Compilar e instalar

Requer o jogo instalado para as DLLs de referência em `OxygenNotIncluded_Data\Managed` e `csc.exe` do .NET Framework 4.x.

```powershell
.\build.ps1
.\build.ps1 -Install
```

`-Install` interrompe se `OxygenNotIncluded` estiver aberto. Antes de copiar os arquivos, guarda os arquivos instalados em `Documentos\Klei\OxygenNotIncluded\mods_backup\OniExtract-<yyyyMMdd-HHmmss>\` e, após instalar, mostra o SHA-256 da DLL. Para outra instalação do jogo, use `-Managed "<caminho>\OxygenNotIncluded_Data\Managed"`.

Para restaurar os arquivos de um backup, com o jogo fechado:

```powershell
.\build.ps1 -Restore "<Documentos>\Klei\OxygenNotIncluded\mods_backup\OniExtract-<yyyyMMdd-HHmmss>"
```

A restauração copia `OniExtract.dll`, `mod.yaml` e `mod_info.yaml` para `mods\dev\OniExtract` e imprime o SHA-256 da DLL restaurada.

## Exportar para CSV

```powershell
python tools\reports_to_csv.py                      # lê a pasta export padrão
python tools\reports_to_csv.py <pasta_export> <saida.csv>
```

Gera um CSV longo, separado por `;`, com as colunas `Cycle, Timestamp, Category, Context, IsDetail, Net, Positive, Negative`. No Excel em português, importe pelo Power Query com localidade "Inglês (EUA)" para os decimais com ponto.
