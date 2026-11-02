# Dashboard ONI

Painel local para decidir enquanto joga. Lê os relatórios do mod e mostra saldo e reserva de comida, oxigênio, energia, materiais (algas, carvão, cobre, amálgama de ouro e ferro), stress por duplicante e eventos da colônia. Funciona só no seu computador, em `127.0.0.1`, e não envia dados para fora.

Para instalar, siga o [tutorial](../INSTALACAO.md).

## Como rodar

No PowerShell, nesta pasta:

```powershell
.venv\Scripts\python.exe -m oni_dashboard
```

O servidor local usa `127.0.0.1:8050`. Para abrir em janela de aplicativo, use:

```powershell
.venv\Scripts\python.exe -m oni_dashboard --open
```

`--open` aguarda o servidor responder e abre no Edge em modo app; se o Edge não estiver disponível, usa o navegador padrão. Para escolher outra pasta ou porta, use `--export-dir` e `--port`.

O script `tools/criar_atalho.ps1` cria o atalho **Dashboard ONI** na Área de Trabalho, usando `pythonw.exe` e esta pasta como pasta inicial.

## Pastas de export

O caminho padrão é `<Documentos>\Klei\OxygenNotIncluded\export`, usando a pasta Documentos real do Windows, mesmo redirecionada para o OneDrive. Também são lidos `colonies\<id>\report_cycle_N.json`. Havendo colônias, a mais recente por `Timestamp` é exibida e relatórios legados soltos só entram quando anteriores ao primeiro ciclo ativo. Arquivos soltos que identificam colônia não são combinados com a ativa. Sem a pasta `colonies`, somente os arquivos soltos são usados.

Para escolher uma pasta em testes ou outra instalação:

```powershell
.venv\Scripts\python.exe -m oni_dashboard --export-dir "C:\caminho\export" --port 8051
```

## Como os dados foram conferidos

Estes pontos foram comparados com a tela do jogo:

- Calorias vêm em cal no JSON e aparecem em kcal.
- Energia vem em J no JSON e aparece em kJ. A energia armazenada usa `TrackerBatteryRaw`.
- Materiais mostram o valor **Disponível** da tela de Recursos, que já desconta o reservado para construções.
- O stress de cada duplicante vem de `Snapshot.Duplicants[].Stress`.

O saldo real de energia é `EnergyCreated.Net + EnergyWasted.Net`. Ele bateu com a variação da bateria nas 2 amostras conferidas, o que apoia a regra, mas não é uma prova.

No painel de materiais, use **Materiais no gráfico** para pesquisar e escolher os recursos disponíveis nos relatórios da colônia. A seleção é salva localmente no navegador e é compartilhada pelo gráfico e pela tabela.

## Testes

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Os testes usam `tests/fixtures/export`, `tests/fixtures/export_v2` e diretórios temporários. Não altere as fixtures, que são relatórios reais de uma colônia.

A pasta `specs/` guarda as especificações usadas na delegação entre IAs, como foram escritas para cada fase.

## Limites conhecidos

A capacidade de bateria é aproximada porque a reserva interna dos transformadores pode divergir da tela do jogo. O nível de carga usa `TrackerBatteryRaw`; `BatteryJoules` não é usado. Os relatórios não identificam a causa da saída de um duplicante. A detecção do jogo depende de `OxygenNotIncluded.exe`. Só foi testado no Windows.
