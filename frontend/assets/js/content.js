// Textos e conteúdo da interface, separados da lógica para facilitar a edição.

// Usadas só se GET /subjects falhar; espelham o enum Subject do backend.
export const FALLBACK_SUBJECTS = [
  { value: "Historia", label: "História" },
  { value: "Geografia", label: "Geografia" },
  { value: "Fisica", label: "Física" },
  { value: "Quimica", label: "Química" },
  { value: "Biologia", label: "Biologia" },
  { value: "Matematica", label: "Matemática" },
  { value: "Linguagens", label: "Linguagens / Redação" },
  { value: "Geral", label: "Geral" },
];

// Rótulo curto para os botões de matéria (o `label` da API pode ser longo).
export const SHORT_LABELS = { Linguagens: "Linguagens" };

export const SUBJECT_ICONS = {
  Historia: "🏛️",
  Geografia: "🌎",
  Fisica: "⚛️",
  Quimica: "🧪",
  Biologia: "🧬",
  Matematica: "➗",
  Linguagens: "✍️",
  Geral: "📚",
};

// Exemplos de pergunta por matéria. Servem de ponto de partida; o conteúdo real
// depende dos PDFs cadastrados.
export const EXAMPLES = {
  Fisica: [
    "O que é velocidade média?",
    "Qual a diferença entre massa e peso?",
    "Como funciona a Lei de Ohm?",
    "O que diz a terceira lei de Newton?",
  ],
  Quimica: [
    "O que é uma ligação covalente?",
    "Como balancear uma equação química?",
    "O que é pH e como interpretar?",
    "Qual a diferença entre ácido e base?",
  ],
  Biologia: [
    "Como funciona a fotossíntese?",
    "Qual a diferença entre mitose e meiose?",
    "O que diz a Primeira Lei de Mendel?",
    "Como ocorre a seleção natural?",
  ],
  Matematica: [
    "Como resolver uma equação do 2º grau?",
    "O que é uma progressão aritmética?",
    "Como calcular juros compostos?",
    "Quando usar o teorema de Pitágoras?",
  ],
  Historia: [
    "Quais foram as causas da Revolução Francesa?",
    "O que foi a Era Vargas?",
    "Como funcionava a escravidão no Brasil colonial?",
    "O que foi a Guerra Fria?",
  ],
  Geografia: [
    "O que é urbanização?",
    "Quais são os tipos de clima do Brasil?",
    "O que são placas tectônicas?",
    "O que é globalização?",
  ],
  Linguagens: [
    "Como estruturar uma redação do ENEM?",
    "O que são figuras de linguagem?",
    "Qual a diferença entre denotação e conotação?",
    "O que é uma proposta de intervenção?",
  ],
  Geral: [
    "Como montar um cronograma de estudos?",
    "Como funciona a nota do ENEM?",
    "Como interpretar textos mais rápido?",
    "O que mais cai nas provas de vestibular?",
  ],
};

// Sem matéria escolhida: uma pergunta de cada área, como alternativas de uma prova.
export const MIXED_EXAMPLES = [
  { subject: "Fisica", text: EXAMPLES.Fisica[0] },
  { subject: "Historia", text: EXAMPLES.Historia[1] },
  { subject: "Biologia", text: EXAMPLES.Biologia[0] },
  { subject: "Matematica", text: EXAMPLES.Matematica[0] },
  { subject: "Linguagens", text: EXAMPLES.Linguagens[0] },
];

// Atalhos depois de uma resposta. Funcionam porque a API busca também com a pergunta anterior.
export const FOLLOW_UPS = ["Explique de outro jeito", "Dê um exemplo", "Me faça uma pergunta para treinar"];

export const LETTERS = ["A", "B", "C", "D", "E"];
