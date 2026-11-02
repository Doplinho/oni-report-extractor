# Spec — Mod ONI, Fase 2 (estoques, colônia e escrita segura)

## Objetivo
O relatório diário só traz fluxos. Para decidir enquanto joga, o usuário precisa de estoques. O mod passa a exportar, no
mesmo JSON de cada ciclo, um retrato do estado da colônia ao anoitecer: reserva de comida, baterias, stress absoluto por
duplicante e 5 materiais. Também passa a separar os dados por colônia e a escrever arquivos com mais segurança.

A exportação atual **não pode quebrar**: é o que já funciona e o que o dashboard e o monitor consomem.

## Limites (obrigatório)
- Trabalhe em `C:\oni-report-extractor`, branch atual `codex/mod-snapshot`. Sem commit, push ou merge.
- Altere só `src/ReportExtractorMod.cs`, `build.ps1` e `README.md`.
- **Não rode `build.ps1 -Install`** nem altere a pasta `mods\dev` do jogo. Compile só com `.\build.ps1`.
- Não toque em `C:\oni-dashboard`, na pasta de export, no monitor ou no Cérebro. Não encerre processos. Não instale nada.
- Só C# 5: sem `$"..."`, `?.`, `nameof`, inicializador de auto-propriedade. `DateTime` colide com uma classe do jogo: use
  `System.DateTime`. `ArrayRef<T>` se itera por índice com `.Count`.
- Grave arquivos em UTF-8, preservando acentos e sem usar `Set-Content`/`Out-File` sem codificação.

## APIs já confirmadas por compilação contra a build U59-744825
Todas compilam; **a semântica ainda não foi validada no jogo**. Não use outros nomes do jogo sem compilar antes.
```csharp
ClusterManager.Instance.WorldContainers            // foreach WorldContainer
world.id; world.GetProperName(); world.IsDiscovered; world.worldInventory
inventory.GetAmount(SimHashes.Algae.CreateTag(), false)
RationTracker.Get().CountAmount(new Dictionary<string, float>(), inventory, true)
TrackerTool.Instance.GetWorldTracker<KCalTracker>(id).GetCurrentValue()
TrackerTool.Instance.GetWorldTracker<BatteryTracker>(id).GetCurrentValue()
Components.Batteries.Items      // Battery: JoulesAvailable, Capacity, GetMyWorldId()
Components.LiveMinionIdentities.Items  // MinionIdentity: GetProperName()
Db.Get().Amounts.Stress.Lookup(minion).value
SaveLoader.Instance.GameInfo.baseName; SaveLoader.Instance.GameInfo.colonyGuid
entry.IterateNotes(delegate(ReportManager.ReportEntry.Note note) { note.note; note.value; });
```

## Formato do JSON
Tudo o que existe hoje permanece com o mesmo nome e significado. Acrescente:
```json
{
  "SchemaVersion": 2,
  "ColonyName": "...",
  "ColonyId": "...",
  "Snapshot": {
    "CaptureMs": 1.2,
    "Errors": [],
    "Worlds": [
      {
        "WorldId": 0,
        "WorldName": "...",
        "RationKcalRaw": 0.0,
        "TrackerKcalRaw": 0.0,
        "BatteryJoules": 0.0,
        "BatteryCapacityJoules": 0.0,
        "TrackerBatteryRaw": 0.0,
        "Materials": [{ "Tag": "Algae", "Kg": 0.0 }]
      }
    ],
    "Duplicants": [{ "Name": "...", "WorldId": 0, "Stress": 0.0 }]
  }
}
```
- `Worlds`: só mundos com `IsDiscovered`.
- `RationKcalRaw` e `TrackerKcalRaw` ficam **as duas e sem conversão**: a validação no jogo decide qual usar e em que unidade.
- `BatteryJoules` e `BatteryCapacityJoules`: soma de `Components.Batteries.Items` com `GetMyWorldId()` igual ao mundo.
- `Materials`, sempre estes 7, nesta ordem: `Algae`, `Carbon`, `Cuprite`, `Copper`, `GoldAmalgam`, `IronOre`, `Iron`. O nome
  gravado é o do `SimHashes`.
- `Duplicants.WorldId`: use `minion.GetMyWorldId()`, compilando antes para confirmar.
- `Notes`: nas entradas das categorias `EnergyCreated`, `EnergyWasted` e `OxygenCreated`, tanto total quanto contexto, inclua
  `"Notes": [{ "Note": "...", "Value": 0.0 }]` quando houver notas. Nas outras categorias e sem notas, o campo fica fora do
  JSON (`NullValueHandling.Ignore` só nesse campo). Texto de nota é gravado cru.

## Isolamento de falhas
- Cada mundo, cada grupo de leitura (comida, baterias, materiais, duplicantes) e o bloco de notas têm `try/catch` próprio.
  Uma falha acrescenta a mensagem a `Snapshot.Errors` e os demais campos continuam. Falha no snapshot **nunca** impede a
  gravação do relatório, nem altera `Entries`.
- `CaptureMs` é medido com `System.Diagnostics.Stopwatch`, cobrindo todo o snapshot.

## Colônia e gravação
- `ColonyId` = `colonyGuid.ToString()`. Se o GUID for vazio ou a leitura falhar, use `baseName` com caracteres inválidos de
  nome de arquivo trocados por `_`; se também falhar, use `sem_id`.
- Destino principal: `export\colonies\<ColonyId>\report_cycle_N.json`.
- **Cópia de compatibilidade:** enquanto a constante `WriteLegacyRoot = true`, grave também em `export\report_cycle_N.json`.
  O dashboard e o monitor atuais leem essa pasta. Falha em um destino não impede o outro. Os dois sempre tentam.
- Escrita: grave em `.tmp` e, se o destino existir, use `File.Replace(tmp, destino, null)`; senão `File.Move`. Até 3
  tentativas, com pausa de 50 ms, só para `IOException` e `UnauthorizedAccessException`. Falha final: `Debug.LogError` com o
  caminho, e apague o `.tmp` restante. Remova o padrão atual de apagar o destino antes de mover.

## `build.ps1`
- `-Install` falha com mensagem clara se o processo `OxygenNotIncluded` estiver aberto.
- Antes de copiar, `-Install` guarda `OniExtract.dll`, `mod.yaml` e `mod_info.yaml` instalados em
  `<Documentos>\Klei\OxygenNotIncluded\mods_backup\OniExtract-<yyyyMMdd-HHmmss>\`, fora da pasta `mods`.
- Depois de instalar, imprime o SHA-256 da DLL instalada.
- Novo parâmetro `-Restore <pasta>`: com o jogo fechado, copia de volta os arquivos daquele backup e imprime o SHA-256.
- Compilar sem parâmetros continua igual.

## `README.md`
Atualize formato, pastas, backup e restauração, em português, com os mesmos acentos corretos do restante do arquivo.

## Critérios de aceite
1. `.\build.ps1` compila sem erros.
2. Inspeção do código: cada grupo do snapshot tem `try/catch`; `Entries` não dependem do snapshot; as duas gravações são independentes.
3. `Entries` continuam iguais em nome e significado para quem lê.
4. Teste por script, sem instalar: `tools\reports_to_csv.py`, sem alteração, processa uma cópia em pasta temporária de um JSON
   com os campos novos.
5. `build.ps1`: teste `-Install` e `-Restore` só com pastas temporárias, se for possível sem tocar na pasta real do jogo. Senão,
   declare que não testou. A verificação de jogo aberto pode ser testada por inspeção.

Antes de terminar, informe a saída literal da compilação e o que não pôde verificar. O revisor fará a validação no jogo.
