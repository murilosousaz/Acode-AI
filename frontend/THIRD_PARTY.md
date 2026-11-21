# Bibliotecas de terceiros embutidas (`assets/vendor/`)

Copiadas sem alterações (exceto o CSS do KaTeX, em que se removeram as referências aos
formatos de fonte `woff`/`ttf`; só `woff2` é distribuído) para a interface funcionar sem internet.

| Biblioteca | Versão  | Licença                | Uso                                   |
|------------|---------|------------------------|---------------------------------------|
| marked     | 18.0.10 | MIT                    | Converte o Markdown da resposta em HTML |
| DOMPurify  | 3.4.14  | Apache-2.0 ou MPL-2.0  | Sanitiza o HTML antes de exibir        |
| KaTeX      | 0.16.47 | MIT                    | Renderiza as fórmulas LaTeX            |

Para atualizar, substitua os arquivos pelos da nova versão e rode a suíte E2E.
