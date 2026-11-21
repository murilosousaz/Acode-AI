// Configuração do frontend. O normal é NÃO mexer aqui: a própria API serve esta página,
// então o endereço da API é o mesmo da página.
//
// Só edite `apiBase` se hospedar o frontend separado da API (ex.: Vercel/Netlify).
// Nesse caso, coloque o endereço do frontend em CORS_ALLOW_ORIGINS no .env da API.
window.ACODEAI = {
  apiBase: "", // "" = mesma origem. Exemplo: "https://api.minhaescola.com.br"
  // chatTimeoutMs: 200000, // quanto esperar por uma resposta antes de desistir
};
