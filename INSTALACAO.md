# Tutorial de instalação

São duas partes: o **mod**, que grava os dados, e o **dashboard**, que os mostra. O dashboard precisa do mod para receber dados novos.

## O que você precisa

- Windows, com Oxygen Not Included instalado pela Steam. Foi testado na build U59-744825, no Windows 10.
- [Python](https://www.python.org/downloads/) 3.13, a versão testada. No instalador, marque **Add python.exe to PATH**.
- O Microsoft Edge é opcional: abre o dashboard em janela própria. Sem ele, abre no navegador padrão.

O compilador do mod (`csc.exe`) já vem com o Windows. Não é preciso instalar .NET SDK.

## 1. Baixar o projeto

No [repositório](https://github.com/Doplinho/oni-report-extractor), clique em **Code > Download ZIP** e extraia para uma pasta curta, como `C:\oni-report-extractor`. Se preferir usar Git:

```powershell
git clone https://github.com/Doplinho/oni-report-extractor.git C:\oni-report-extractor
```

Os comandos abaixo usam essa pasta. Se escolheu outra, troque o caminho.

## 2. Instalar o mod

1. Feche o jogo.
2. Abra o PowerShell e rode:

   ```powershell
   cd C:\oni-report-extractor
   powershell -ExecutionPolicy Bypass -File .\build.ps1 -Install
   ```

   Se o jogo não estiver na pasta padrão da Steam, informe onde ele está:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\build.ps1 -Install -Managed "D:\Steam\steamapps\common\OxygenNotIncluded\OxygenNotIncluded_Data\Managed"
   ```

3. Abra o jogo, entre em **Mods**, ative o mod **ONI Report Extractor** e deixe o jogo reiniciar.
4. Carregue sua colônia e deixe o ciclo chegar à noite. O mod grava um relatório a cada anoitecer, em `Documentos\Klei\OxygenNotIncluded\export`.

O mod só exporta a partir do momento em que foi ativado. Ciclos anteriores do save não aparecem.

Quando o jogo atualizar, rode de novo o comando de instalação. Se o mod deixar de compilar ou de carregar, pode ser mudança na API do jogo.

## 3. Instalar o dashboard

```powershell
cd C:\oni-report-extractor\dashboard
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 4. Abrir o dashboard

```powershell
cd C:\oni-report-extractor\dashboard
.venv\Scripts\python.exe -m oni_dashboard --open
```

Para ter um atalho **Dashboard ONI** na Área de Trabalho, rode uma vez:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\criar_atalho.ps1
```

O atalho abre sem janela de console. Depois é só deixar a janela aberta, de preferência em um segundo monitor, e jogar: a tela confere se há relatório novo a cada 5 segundos.

## Encerrar

Fechar a janela não encerra o servidor, e clicar no atalho de novo só reabre a janela. Para encerrar de vez, finalize `pythonw.exe` no Gerenciador de Tarefas. Se você abriu pelo PowerShell, feche esse PowerShell.

## Desinstalar

1. Desative o mod no jogo e apague `Documentos\Klei\OxygenNotIncluded\mods\dev\OniExtract`.
2. Apague a pasta do projeto e o atalho.
3. Os relatórios ficam em `Documentos\Klei\OxygenNotIncluded\export`. Apague essa pasta só se não quiser mais os dados.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `Feche OxygenNotIncluded antes de instalar` | Feche o jogo e rode o comando de novo |
| O dashboard não mostra dados | Confira se há `report_cycle_*.json` na pasta `export` e se já passou um anoitecer com o mod ativo |
| Os dados estão em outra pasta | Rode com `--export-dir "C:\caminho\export"` |
| A porta 8050 está ocupada | Rode com `--port 8051` |
| Outro erro no dashboard | Veja `dashboard\logs\dashboard.log` |
| O jogo fecha ao carregar | Desative o mod e veja `Player.log` em `%USERPROFILE%\AppData\LocalLow\Klei\Oxygen Not Included` |
