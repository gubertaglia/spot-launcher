# Correções da auditoria técnica — Spot Launcher 2.0.0

Release baseada na auditoria da versão 1.8.0.

As correções abaixo sucedem a auditoria do commit `3c7b8a6`. O relatório original e seus dados permanecem como registro histórico.

## Alterações

- **AUD-01:** merge recusa sobrescrita de arquivos ignorados, além de manter avanço fast-forward e proteção de alterações rastreadas.
- **AUD-02:** preferências reutilizam uma janela oculta; seu worker permanece utilizável e encerra no shutdown.
- **AUD-03:** ofertas marcadas com `x-kde-passwordManagerHint` são ignoradas antes da leitura. A geração anterior também é invalidada.
- **AUD-04:** configurações Python validam tipos, resultados e escala; preservam posição válida e campos desconhecidos. A extensão valida objeto e flags booleanas.
- **AUD-05:** atualização da mesma busca preserva a identidade do resultado selecionado, inclusive nas páginas seguintes.
- **AUD-06:** o parser preserva símbolos SI, mantendo aliases de idioma e temperatura. `Mm` e `mm` produzem valores diferentes.
- **AUD-07 e AUD-13:** cópia usa a precisão apresentada e resultados monetários não finitos são recusados.
- **AUD-08:** clipboard usa uma fila de I/O ordenada. Histórico e preferências gravam snapshots fora do loop GTK. Shutdown drena a fila; mudança de idioma confirma a gravação antes de reiniciar. Escrita atômica e permissões privadas permanecem.
- **AUD-09:** erro ao abrir aplicativo ou arquivo mantém o launcher visível e apresenta diálogo traduzido.
- **AUD-10:** lançamento em terminal preserva `Path` no arquivo desktop construído, mantendo `Exec` e seus argumentos.
- **AUD-11:** removida a alteração de GSettings do Blur my Shell. A opção modifica apenas o CSS do launcher, conforme documentado.
- **AUD-12:** o worker expõe validade da tarefa em seu contexto de thread. O dicionário verifica essa validade antes de iniciar cada fetch adicional.

## Validação

- **157 testes aprovados:** [log](resultados-correcoes/testes.log). Incluem colisão de arquivo ignorado, configurações inválidas, símbolos SI, precisão monetária, marcador sensível, falha de abertura, I/O ordenado fora da thread chamadora, cancelamento entre fetches e diretório de trabalho real do terminal.
- **GTK real, em sessão isolada:** [dados](resultados-correcoes/interface-regression-wayland.json). Após 100 aberturas, existe uma única instância de preferências; PSS passou de aproximadamente 47,8 MiB antes das preferências para 51,3 MiB após 50 e 51,4 MiB após 100, sem o crescimento linear anterior. A seleção permaneceu em Alpha. O segredo sintético não foi persistido, inclusive após limpar o clipboard.
- **GNOME Shell 51.1 real:** [dados](resultados-correcoes/gnome-51.json). Configuração `null` mantém Super funcional. Foram executados 200 ciclos, restauração de sinais/métodos, posicionamento e convivência com hook concorrente.

Repetição dos ensaios gráficos:

```bash
python3 -B docs/auditoria/sessao-isolada.py regression docs/auditoria/resultados-novos
python3 -B docs/auditoria/sessao-isolada.py gnome-regression docs/auditoria/resultados-novos
```

Os modos antigos e `reproducoes.py` documentam comportamentos defeituosos do commit auditado; não são a suíte de regressão da versão corrigida.

## Limites e aplicação

Não foram repetidos os 60 minutos de ociosidade, GNOME 45–50 ou cenários de hardware físico. Os avisos de depreciação de Gio continuam presentes. Dados antigos do clipboard não foram apagados: não é possível identificar retroativamente quais textos eram segredos sem metadados de origem.

Reinicie o launcher para carregar o Python atualizado. Atualize a extensão pela integração do Spot e recarregue a sessão GNOME para carregar o JavaScript corrigido. Nenhuma configuração da sessão pessoal foi alterada pelos ensaios.
