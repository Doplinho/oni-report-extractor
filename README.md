# ONI Report Extractor

Mod e dashboard para **Oxygen Not Included**. O mod exporta o relatório de cada ciclo para JSON, e o dashboard mostra esses dados em gráficos que se atualizam sozinhos enquanto você joga. Testado na build **U59-744825**, no Windows.

> **Nota:** este projeto é mais um estudo da inter-relação entre IAs do que um projeto de programação. O interesse principal é ver como Claude e Codex trabalham juntos, com uma planejando e revisando e a outra implementando, sob a direção de uma pessoa. O código é o resultado desse estudo. O registro está em [docs/estudo-entre-ias.md](docs/estudo-entre-ias.md).

## O que tem aqui

| Parte | Pasta | Para que serve |
|---|---|---|
| Mod | `src/`, `build.ps1` | Exporta um JSON a cada anoitecer |
| Dashboard | [`dashboard/`](dashboard/README.md) | Mostra comida, oxigênio, energia, materiais e stress por duplicante |
| Exportação para CSV | `tools/reports_to_csv.py` | Junta os JSON para Power BI ou Excel |

**Para instalar, siga o [tutorial de instalação](INSTALACAO.md).**

## Como o mod funciona

Um patch Harmony em `ReportManager.OnNightTime` lê o relatório do ciclo recém-fechado e grava `report_cycle_N.json`. O formato mantém `Cycle`, `Timestamp` e `Entries` com os nomes e significados existentes. A versão 2 acrescenta `SchemaVersion`, identificação da colônia e `Snapshot`, com calorias brutas, baterias e estresse dos duplicantes por mundo. A versão 3 inclui `Name` e todos os recursos descobertos com quantidade maior que 0, além dos sete materiais fixos. Leituras parciais que falham são descritas em `Snapshot.Errors`.

O arquivo é gravado em UTF-8 com troca atômica. O caminho principal é:

```
Documentos\Klei\OxygenNotIncluded\export\colonies\<ColonyId>\report_cycle_N.json
```

Enquanto `WriteLegacyRoot` estiver habilitado, também é gravada uma cópia compatível em `Documentos\Klei\OxygenNotIncluded\export\report_cycle_N.json`, usada pelas ferramentas atuais.

Cada categoria em `Entries` gera uma linha total (`Context = null`) e linhas de detalhe por duplicante/construção (`Context` preenchido). As categorias de energia criada, energia desperdiçada e oxigênio criado também podem incluir notas.

## Compilar e instalar o mod

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
