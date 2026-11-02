# Estudo: duas IAs trabalhando juntas

Este projeto é mais um estudo da inter-relação entre IAs do que um projeto de programação. O dashboard resolve um problema real de quem joga, mas a pergunta principal foi outra: **o que acontece quando uma IA planeja e revisa, e outra implementa?**

Este é o relato de um único projeto, não uma medição controlada.

## Quem fez o quê

| Papel | Quem | O que fez |
|---|---|---|
| Direção | A pessoa | Definiu o objetivo, decidiu os materiais e os limites, conferiu os dados contra a tela do jogo e aprovou o resultado |
| Orquestração e revisão | Claude | Planejou, escreveu as especificações, revisou os diffs, rodou os testes e usou a tela de verdade. Não implementou o código da aplicação |
| Execução | Codex | Implementou o código e os testes a partir das especificações |
| Revisão do plano | Um agente sem contexto | Procurou pontos fracos no plano antes de começar |

## Como funcionou

1. Cada fase virou uma especificação em [`dashboard/specs/`](../dashboard/specs/), com objetivo, arquivos, limites e critérios de aceite.
2. O Codex implementou e rodou os testes.
3. O Claude revisou o diff, repetiu os testes e testou no navegador. Quando reprovava, mandava correções numeradas.
4. A pessoa comparou os números com o jogo e decidiu quando seguir.

Foram 5 ciclos de correção na Fase 1 e 4 na Fase 3. A correção para a publicação levou mais 2, e o filtro de materiais, 3 rodadas.

## O que cada um encontrou

| Defeito | Testes passavam? | Quem encontrou |
|---|---|---|
| Acentos trocados por `?`, painéis colapsando e zoom perdido | Sim | Claude, no navegador |
| Erro 500 depois de dar zoom | Sim | Claude, no navegador |
| Altura dos gráficos removida ao reescrever o layout | Sim | Claude, no navegador |
| `--open` travava com `pythonw`, e a janela nunca abria | Sim | Claude, rodando de verdade |
| Identificador errado da pasta Documentos: a API falhava em silêncio e o caminho alternativo escondia o erro | Sim | Claude, conferindo o caminho calculado |
| Filtro de materiais abria vazio e apagava a seleção salva, porque a lista começava sem opções | Sim | Claude, no navegador |
| Filtro quase ilegível e em inglês: o CSS e os textos usavam nomes que não existem nesta versão do Dash | Sim | Claude, no navegador |
| Filtro limitado aos 7 materiais do teste, porque o mod só exportava esses | Não se aplica | Claude, lendo o código do mod antes de escrever a especificação |
| Diferença de 4% nos minérios, que parecia defeito | Não se aplica | A pessoa: o painel mostra o Disponível, e o print comparado mostrava o Total. Não havia defeito |
| Ciclo errado na especificação: dizia que um duplicante saiu no 247, mas foi no 248 | Não se aplica | Corrigido durante o trabalho: o erro era do orquestrador |

## O que ficou de aprendizado

- **Teste passando não é o mesmo que funcionar.** Quase todos os defeitos acima passaram pelos testes. Eles apareceram ao usar a tela e ao rodar o programa como a pessoa rodaria.
- **Cada defeito encontrado virou teste.** O teste novo impede a mesma falha de voltar.
- **Separar quem escreve de quem revisa ajudou.** Quem revisa desconfia do resultado e olha o que o autor não olhou.
- **O orquestrador também erra.** Sem a conferência da pessoa contra o jogo, a IA não tinha como saber se os números estavam certos.
- **A pessoa continua necessária.** Só ela tinha acesso à tela do jogo durante a partida e pôde explicar a diferença entre Total e Disponível.
- **A ferramenta também limita.** O plugin do Codex não conseguia escrever fora da área de trabalho nem rodar Python. Foi preciso passar a chamá-lo direto, com permissão dada pela pessoa a cada execução.
