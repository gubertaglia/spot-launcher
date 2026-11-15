# Contribuir

Siga a instalação do [README](README.md#instalar). O ambiente `.venv` precisa
acessar PyGObject e as bibliotecas nativas fornecidas pela distribuição.

Antes de enviar uma mudança:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
git diff --check
```

Corrija o problema no código compartilhado e acrescente uma regressão pequena.
Mantenha acesso à rede e disco fora da thread GTK. Não execute ações do sistema
durante a busca; preserve a confirmação das ações destrutivas.

Textos novos da interface precisam dos catálogos `.po` e `.mo` em
`data/locales/{en,es,fr}/LC_MESSAGES/`. O teste de idiomas verifica cobertura e
placeholders. Os testes de rede usam respostas simuladas.

Os diretórios `docs/auditoria/resultados-*` são evidências históricas. Grave novas
medições em outro diretório e registre ambiente, versão e limites do ensaio.
Consulte o [índice da documentação](docs/README.md).
