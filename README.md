# ONI Report Extractor

Mod para **Oxygen Not Included** que exporta o relatório diário de cada ciclo (oxigênio, energia, calorias, estresse etc.) para JSON, para análise no Power BI, Excel ou Python.

Testado na build **U59-744825**.

## Como funciona

Um patch Harmony em `ReportManager.OnNightTime` lê o relatório do ciclo recém-fechado (`ReportManager.Instance.YesterdaysReport`) e grava:

```
Documentos\Klei\OxygenNotIncluded\export\report_cycle_N.json
```

Cada categoria gera uma linha de total (`Context = null`) e linhas de detalhe por duplicante/construção (`Context` preenchido).

```json
{
  "Cycle": 10,
  "Timestamp": "2026-10-31T20:00:00-03:00",
  "Entries": [
    { "Category": "OxygenCreated", "Context": null, "NetValue": 1.5, "PositiveValue": 3.0, "NegativeValue": -1.5 }
  ]
}
```

## Compilar e instalar

Requer o jogo instalado (as DLLs de referência vêm de `OxygenNotIncluded_Data\Managed`) e o `csc.exe` do .NET Framework 4.x, que já vem no Windows.

```powershell
.\build.ps1 -Install
```

Isso compila `bin\OniExtract.dll` e copia o mod para `Documentos\Klei\OxygenNotIncluded\mods\dev\OniExtract\`. Se o jogo estiver em outro lugar, use `-Managed "<caminho>\OxygenNotIncluded_Data\Managed"`.

Depois, ative **ONI Report Extractor** no menu Mods do jogo.

## Exportar para CSV

```powershell
python tools\reports_to_csv.py                      # lê a pasta export padrão
python tools\reports_to_csv.py <pasta_export> <saida.csv>
```

Gera um CSV longo, separado por `;`, com as colunas `Cycle, Timestamp, Category, Context, IsDetail, Net, Positive, Negative`. No Excel em português, importe pelo Power Query com localidade "Inglês (EUA)" para os decimais com ponto.
