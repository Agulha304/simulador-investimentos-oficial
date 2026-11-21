# Tributos de empresas brasileiras - referência para o simulador

Data de referência: **21/11/2026**. Salário mínimo 2026: **R$ 1.621,00**. Teto do INSS 2026: **R$ 8.475,55**.
Convenção de confiança: **[OFICIAL]** = lido no texto da lei (Planalto) nesta consulta; **[SECUNDÁRIA]** = confirmado só em imprensa/consultorias; **[CONHECIMENTO]** = regra estável conhecida, não rebuscada nesta consulta; **[NÃO CONFIRMADO]**.

---

## 0. O que mudou em 2026 (resumo)

| Tema | Situação em nov/2026 | Afeta Simples/MEI? |
|---|---|---|
| Reforma do consumo (LC 214/2025, alterada pela LC 227/2026) | 2026 é **ano de teste**: CBS 0,9% + IBS 0,1% (art. 343 e 346). O valor recolhido é compensado com PIS/COFINS do mesmo período (art. 348), e o recolhimento é dispensado a quem cumprir as obrigações acessórias. **[OFICIAL]** | **Não.** O art. 348, III, "c" diz que as alíquotas de teste **não se aplicam às operações de optantes do Simples Nacional**. Nada muda no DAS em 2026. **[OFICIAL]** |
| 2027-2028 | CBS plena (alíquota de referência menos 0,1 p.p.), IBS 0,05% estadual + 0,05% municipal (art. 344, 347). PIS/COFINS passam a ser substituídos pela CBS. **[OFICIAL]** | Simples: IBS/CBS ficam dentro do DAS, com a opção de apurar IBS/CBS "por fora" pelo regime regular (art. 41 §3º). **[OFICIAL]** MEI: valor fixo ganha parcelas de CBS/IBS (ver 1.1). |
| 2033 | Fim da transição (ICMS e ISS extintos; IBS/CBS plenos). **[SECUNDÁRIA]** | - |
| LC 224/2025 (corte linear de benefícios) | Lucro Presumido: **+10% nos percentuais de presunção** só sobre a parcela da receita bruta que passa de **R$ 5 mi/ano** (art. 4º §4º VII e §5º). **[OFICIAL]** | Não afeta Simples/MEI. |
| Lei 15.270/2025 | **Dividendos acima de R$ 50 mil/mês por PJ por sócio: retenção de 10% sobre o total.** Isenção de IRPF até R$ 5 mil/mês de renda. **[OFICIAL]** | Ver seção 3. |
| LC 238/2026 (21/10/2026) | Limite do MEI sobe: **R$ 110 mil em 2027** e **R$ 140 mil a partir de 2028**; em 2026 continua **R$ 81 mil**. Remissão de dívidas de MEI até 13/10/2026. **[OFICIAL]** | Sim (só MEI, a partir de 2027). |
| Limite do Simples | **R$ 4,8 mi/ano continua**, sublimite de ICMS/ISS R$ 3,6 mi. PLP 140/2026 (até R$ 12 mi) ainda é projeto. **[SECUNDÁRIA]** | - |

---

## 1. Regimes

### 1.1 MEI (LC 123, art. 18-A; LC 238/2026)

- **Limite de faturamento**: R$ 81.000/ano (R$ 6.750/mês média) em 2026 **[OFICIAL, texto vigente da LC 123]**. Início de atividade: R$ 6.750 x meses (proporcional) **[CONHECIMENTO]**. 2027: R$ 110.000 (R$ 9.166,67/mês no início de atividade). 2028+: R$ 140.000 (R$ 11.666,67/mês). **[OFICIAL, LC 238]**
- Excesso até 20% (R$ 97.200): paga DAS complementar sobre o excedente e migra para ME no ano seguinte; acima de 20%: desenquadramento retroativo. **[CONHECIMENTO]**
- **Restrições**: 1 sócio único (empresário individual), sem participação em outra empresa como sócio/titular, máx. **1 empregado** (recebendo 1 salário mínimo ou piso da categoria; a LC 238 menciona até 2 empregados no MEI rural, art. 18-C, da redação nova), não pode ter atividades vedadas (profissões intelectuais regulamentadas, como médico, advogado, engenheiro; cuja lista está na Resolução CGSN). **[CONHECIMENTO + OFICIAL para o empregado]**
- **DAS-MEI 2026** = 5% do salário mínimo (INSS) + R$ 1 (ICMS) e/ou R$ 5 (ISS). **[OFICIAL para a fórmula; valores numéricos conferidos em várias fontes secundárias; portal gov.br bloqueou acesso automatizado]**

| Atividade | Composição | Valor mensal 2026 |
|---|---|---|
| Comércio / indústria / produtor rural | INSS 81,05 + ICMS 1,00 | **R$ 82,05** |
| Serviços | INSS 81,05 + ISS 5,00 | **R$ 86,05** |
| Comércio + serviços | 81,05 + 1 + 5 | **R$ 87,05** |
| MEI Caminhoneiro (limite R$ 251.600/ano) | 12% do SM = 194,52 + ICMS 1,00 | **R$ 195,52** (ou 200,52 se também ISS) - cálculo próprio; fontes secundárias divergiram entre si |

- DAS fixo, independe do faturamento. Em 2027-2028 o valor fixo passa a ter **CBS 0,994 + IBS 0,006** dentro dos R$ 1 (ICMS) + R$ 5 (ISS) (Anexo VII da LC 214, incluído na LC 123) - ou seja, o total de tributos sobre consumo não muda, só a composição. **[OFICIAL]**
- Dono do MEI **não faz pró-labore** nem paga IRPF sobre o lucro do negócio até o limite de isenção (lucro presumido por atividade: 8% comércio/indústria/transporte carga, 16% transp. passageiros, 32% serviços) **[CONHECIMENTO: IN RFB 1.700/2017 / Lei 9.250 - não rebuscado]**. Para o jogo: "lucro isento = receita x % de presunção".
- Atividades 'plausíveis' para o jogo: cafeteria/restaurante pequeno, loja de roupas, oficina, agência de marketing pequena (MEI marketing pode se ocupar com serviços permitidos), e-commerce. Supermercado, construtora, indústria e imobiliária ficam inviáveis no MEI pela escala (limite) ou por vedações (corretor de imóveis é regulamentado: **[NÃO CONFIRMADO]** se pode ser MEI; não usar).

### 1.2 Simples Nacional (LC 123/2006) - **[OFICIAL, Planalto, texto compilado consultado hoje]**

- Limite: **R$ 4.800.000/ano de RBT12** (ME até 360 mil; EPP até 4,8 mi). **Sublimite de ICMS/ISS: R$ 3,6 mi** (acima disso, ICMS e ISS são pagos fora do DAS, nas faixas excedentes). **[sublimite: SECUNDÁRIA]**
- **Alíquota efetiva** = `(RBT12 x Alíquota nominal - Parcela a deduzir) / RBT12`.
  - RBT12 = receita bruta acumulada nos 12 meses anteriores ao período de apuração. Para empresa nova, usa-se a média proporcional.
  - O DAS do mês = `receita do mês x alíquota efetiva` (por atividade, se houver mais de um anexo).
  - Partilha do DAS = alíquota efetiva x percentual de repartição **da faixa** (tabelas abaixo). Fora da 6ª faixa, 'ISS' e 'ICMS' nunca passam de 5% da receita (excesso migra para tributos federais proporcionalmente nos Anexos III e IV na 5ª faixa).
- **Fator R** (Anexos III/V): `r = Folha de salários 12 meses (inclui pró-labore, encargos, FGTS) / RBT12`. Se **r >= 28%**: Anexo III; se **r < 28%**: Anexo V. **[OFICIAL, art. 18 §5º-J e Anexo V]**

#### Anexo I - Comércio (alíquota nominal / PD / repartição na faixa)
| Faixa | RBT12 (R$) | Alíq. | Deduzir | IRPJ | CSLL | COFINS | PIS | CPP | ICMS |
|---|---|---|---|---|---|---|---|---|---|
| 1 | até 180.000 | 4,00% | 0 | 5,50 | 3,50 | 12,74 | 2,76 | 41,50 | 34,00 |
| 2 | 180.000,01-360.000 | 7,30% | 5.940 | 5,50 | 3,50 | 12,74 | 2,76 | 41,50 | 34,00 |
| 3 | 360.000,01-720.000 | 9,50% | 13.860 | 5,50 | 3,50 | 12,74 | 2,76 | 42,00 | 33,50 |
| 4 | 720.000,01-1.800.000 | 10,70% | 22.500 | 5,50 | 3,50 | 12,74 | 2,76 | 42,00 | 33,50 |
| 5 | 1.800.000,01-3.600.000 | 14,30% | 87.300 | 5,50 | 3,50 | 12,74 | 2,76 | 42,00 | 33,50 |
| 6 | 3.600.000,01-4.800.000 | 19,00% | 378.000 | 13,50 | 10,00 | 28,27 | 6,13 | 42,10 | - |

#### Anexo II - Indústria
| Faixa | RBT12 (R$) | Alíq. | Deduzir | IRPJ | CSLL | COFINS | PIS | CPP | IPI | ICMS |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | até 180.000 | 4,50% | 0 | 5,50 | 3,50 | 11,51 | 2,49 | 37,50 | 7,50 | 32,00 |
| 2 | 180.000,01-360.000 | 7,80% | 5.940 | 5,50 | 3,50 | 11,51 | 2,49 | 37,50 | 7,50 | 32,00 |
| 3 | 360.000,01-720.000 | 10,00% | 13.860 | 5,50 | 3,50 | 11,51 | 2,49 | 37,50 | 7,50 | 32,00 |
| 4 | 720.000,01-1.800.000 | 11,20% | 22.500 | 5,50 | 3,50 | 11,51 | 2,49 | 37,50 | 7,50 | 32,00 |
| 5 | 1.800.000,01-3.600.000 | 14,70% | 85.500 | 5,50 | 3,50 | 11,51 | 2,49 | 37,50 | 7,50 | 32,00 |
| 6 | 3.600.000,01-4.800.000 | 30,00% | 720.000 | 8,50 | 7,50 | 20,96 | 4,54 | 23,50 | 35,00 | - |

#### Anexo III - Serviços (locação de bens móveis e serviços gerais; Anexo V com r >= 28%)
| Faixa | RBT12 (R$) | Alíq. | Deduzir | IRPJ | CSLL | COFINS | PIS | CPP | ISS |
|---|---|---|---|---|---|---|---|---|---|
| 1 | até 180.000 | 6,00% | 0 | 4,00 | 3,50 | 12,82 | 2,78 | 43,40 | 33,50 |
| 2 | 180.000,01-360.000 | 11,20% | 9.360 | 4,00 | 3,50 | 14,05 | 3,05 | 43,40 | 32,00 |
| 3 | 360.000,01-720.000 | 13,50% | 17.640 | 4,00 | 3,50 | 13,64 | 2,96 | 43,40 | 32,50 |
| 4 | 720.000,01-1.800.000 | 16,00% | 35.640 | 4,00 | 3,50 | 13,64 | 2,96 | 43,40 | 32,50 |
| 5 | 1.800.000,01-3.600.000 | 21,00% | 125.640 | 4,00 | 3,50 | 12,82 | 2,78 | 43,40 | 33,50 (*) |
| 6 | 3.600.000,01-4.800.000 | 33,00% | 648.000 | 35,00 | 15,00 | 16,03 | 3,47 | 30,50 | - |

(*) ISS efetivo máximo 5%: se a alíquota efetiva da 5ª faixa passar de 14,92537%, o ISS fica fixo em 5% da receita e o excesso vai para IRPJ/CSLL/COFINS/PIS/CPP (6,02 / 5,26 / 19,28 / 4,18 / 65,26% do excesso, aproximado - **os dois últimos percentuais do rateio não foram lidos por completo; não usar no jogo, basta limitar ISS a 5%**).

#### Anexo IV - Serviços (construção, vigilância, limpeza, advocacia). **Sem CPP no DAS.**
| Faixa | RBT12 (R$) | Alíq. | Deduzir | IRPJ | CSLL | COFINS | PIS | ISS |
|---|---|---|---|---|---|---|---|---|
| 1 | até 180.000 | 4,50% | 0 | 18,80 | 15,20 | 17,67 | 3,83 | 44,50 |
| 2 | 180.000,01-360.000 | 9,00% | 8.100 | 19,80 | 15,20 | 20,55 | 4,45 | 40,00 |
| 3 | 360.000,01-720.000 | 10,20% | 12.420 | 20,80 | 15,20 | 19,73 | 4,27 | 40,00 |
| 4 | 720.000,01-1.800.000 | 14,00% | 39.780 | 17,80 | 19,20 | 18,90 | 4,10 | 40,00 |
| 5 | 1.800.000,01-3.600.000 | 22,00% | 183.780 | 18,80 | 19,20 | 18,08 | 3,92 | 40,00 (*) |
| 6 | 3.600.000,01-4.800.000 | 33,00% | 828.000 | 53,50 | 21,50 | 20,55 | 4,45 | - |

#### Anexo V - Serviços intelectuais/técnicos (r < 28%)
| Faixa | RBT12 (R$) | Alíq. | Deduzir | IRPJ | CSLL | COFINS | PIS | CPP | ISS |
|---|---|---|---|---|---|---|---|---|---|
| 1 | até 180.000 | 15,50% | 0 | 25,00 | 15,00 | 14,10 | 3,05 | 28,85 | 14,00 |
| 2 | 180.000,01-360.000 | 18,00% | 4.500 | 23,00 | 15,00 | 14,10 | 3,05 | 27,85 | 17,00 |
| 3 | 360.000,01-720.000 | 19,50% | 9.900 | 24,00 | 15,00 | 14,92 | 3,23 | 23,85 | 19,00 |
| 4 | 720.000,01-1.800.000 | 20,50% | 17.100 | 21,00 | 15,00 | 15,74 | 3,41 | 23,85 | 21,00 |
| 5 | 1.800.000,01-3.600.000 | 23,00% | 62.100 | 23,00 | 12,50 | 14,10 | 3,05 | 23,85 | 23,50 |
| 6 | 3.600.000,01-4.800.000 | 30,50% | 540.000 | 35,00 | 15,50 | 16,44 | 3,56 | 29,50 | - |

(Observação: a lei traz a repartição do Anexo V na Tabela V-B; os valores acima coincidem com ela. A lei também lista uma redação com Anexo V alternativa para quando o r muda de faixa dentro do anexo (tabelas V-A, 'I..M') - **não confirmada em detalhes; irrelevante para o jogo**.)

#### Qual anexo vale para cada empresa do jogo
| Empresa | Anexo | Observação |
|---|---|---|
| Restaurante | I | Venda de refeições/bebidas. **[CONHECIMENTO]** (RFB trata restaurante como comércio no Simples; confirmar atividade/CNAE) |
| Cafeteria | I | idem |
| Loja de roupas | I | |
| Supermercado | I | Atenção a produtos com ICMS-ST/monofásico (PIS/COFINS/ICMS segregados) - ignorar no jogo |
| Oficina mecânica | III | Serviço de manutenção/reparação; peças vendidas na OS seguem Anexo I **[CONHECIMENTO]** |
| Tecnologia (software) | III se r >= 28%, senão V | Desenvolvimento de software está no §5º-I/§5º-D (Fator R). **[CONHECIMENTO]** |
| Agência de marketing | III se r >= 28%, senão V | Publicidade/propaganda: Fator R. **[CONHECIMENTO]** |
| Indústria | II | Fabricação própria. **IPI** dentro do DAS. |
| Construtora | IV | Obras/empreitada por serviço. Incorporação/venda de imóveis próprios tem tratamento específico **[NÃO CONFIRMADO]** |
| Transporte de cargas | III | Municipal: ISS. Intermunicipal/interestadual: ICMS no lugar do ISS **[CONHECIMENTO, não rebuscado]** |
| Imobiliária | III | Corretagem/intermediação e locação. **[CONHECIMENTO]** |
| E-commerce | I | Venda de mercadorias. Marketplace-só-intermediação: III **[CONHECIMENTO]** |

#### Impactos do Simples
- Anexos I, II, III e V incluem **CPP (INSS patronal)** no DAS; **Anexo IV não** (a empresa paga INSS patronal 20% + RAT por fora, GPS). Terceiros (Sistema S, salário-educação) **não** são devidos no Simples (art. 13 §3º). **[OFICIAL para CPP no DAS e Anexo IV; terceiros: CONHECIMENTO]**
- FGTS, 13º, férias, INSS do empregado (retido) continuam por fora em todos.

### 1.3 Lucro Presumido (Lei 9.249/95 arts. 15 e 20; Lei 9.430; LC 224/2025) - **[OFICIAL: Lei 9.249 art. 15; LC 224 art. 4º]**

Presunção da base de IRPJ sobre a receita bruta (trimestral):
| Atividade | IRPJ | CSLL |
|---|---|---|
| Comércio, indústria, construção c/ fornecimento de materiais, transporte de carga, serviços hospitalares | **8%** | **12%** |
| Revenda de combustíveis | 1,6% | 12% |
| Transporte de passageiros | 16% | 12% |
| Serviços em geral, intermediação de negócios, administração/locação de imóveis/bens, construção só mão de obra | **32%** | **32%** |

(CSLL por Lei 9.249, art. 20: 12%, ou 32% para as atividades do art. 15 §1º III. **[CONHECIMENTO]**)
- **LC 224/2025**: acima de R$ 5 mi/ano de receita (controle trimestral, R$ 1,25 mi/trimestre com ajuste nos seguintes), os percentuais ganham +10% (ex.: 8% vira 8,8%; 12% vira 13,2%; 32% vira 35,2%) **somente sobre a parcela excedente**. Efeitos: IRPJ desde 01/01/2026; **CSLL a partir de 01/04/2026** (art. 14: tributos sob anterioridade nonagesimal, 4º mês após a publicação). Há ações judiciais (TRF-3 suspendeu para um autor). **[OFICIAL para o texto; leitura de datas é interpretação - NÃO CONFIRMADO pelo Q&A da Receita]**
- **IRPJ**: 15% sobre a base + **adicional 10%** sobre a parcela da base que exceder **R$ 20.000/mês (R$ 60.000/trimestre)**. **CSLL 9%**. **[CONHECIMENTO, estável]**
- **PIS 0,65% + COFINS 3,00%** (cumulativos, sobre a receita) em 2026; sem créditos. **[CONHECIMENTO]** CBS substituirá PIS/COFINS a partir de 2027.
- Limite de adesão: receita bruta até **R$ 78 mi/ano** **[CONHECIMENTO]**.
- **ISS** (municipal; LC 116/2003 art. 8º: máximo 5%; art. 8º-A: mínimo 2%) **[OFICIAL]**. Típicos: 2% a 5%; capitais costumam cobrar 2% a 5% (SP capital 2%-5% por item; **[NÃO CONFIRMADO por cidade]**). Sugestão para o jogo: TI 2-3%; marketing 2-5%; construção 2-5%; imobiliária (corretagem) 3-5%; oficina 2-5%. Transporte de carga municipal 2-5%; intermunicipal paga ICMS.
- **ICMS** (estadual; só venda de mercadorias, transporte intermunicipal e comunicação; não serviço puro): alíquota interna típica **17% a 23%** conforme estado; **SP 18%** **[SECUNDÁRIA]**. RJ 22% (inclui 2% FECP) e MG 18% **[CONHECIMENTO, a pesquisa não confirmou]**; um estado listou 19% e MA 23%. Não-cumulativo: débito de vendas - crédito de compras. Restaurantes no Lucro Presumido tipicamente pagam ICMS sobre refeição.
- **IPI** (indústria): alíquota da TIPI por produto, de 0% a dezenas de %; para o jogo, 5%-15% típicos como valor lúdico **[CONHECIMENTO, simplificação]**. Não cumulativo.

---

## 2. Encargos sobre a folha

| Encargo | Alíquota | Observação |
|---|---|---|
| INSS patronal (CPP) | **20%** da folha | Lucro Presumido/Real. Simples Anexos I, II, III, V: **já incluído** no DAS. Anexo IV e MEI: veja abaixo. **[CONHECIMENTO + OFICIAL Simples]** |
| RAT/SAT x FAP | 1%, 2% ou 3% x FAP (0,5 a 2,0) | Por CNAE. Fora do DAS no Anexo IV e Lucro Presumido. **[SECUNDÁRIA]** |
| Terceiros (Sistema S, salário-educação, INCRA) | ~**5,8%** (varia 3,3%-7,8% por FPAS) | Lucro Presumido/Real; **não no Simples**. **[SECUNDÁRIA]** |
| FGTS | **8%** do salário | Todos (MEI com empregado também, 8% + 3% INSS patronal). |
| 13º salário | 1/12 (8,33%) do salário | provisão mensal; reflete em INSS/FGTS. |
| Férias + 1/3 | 1/12 + 1/3 de 1/12 = **11,11%** | provisão; reflete em INSS/FGTS. |
| FGTS sobre rescisão | multa de 40% sem justa causa | **[CONHECIMENTO]** |
| INSS do empregado | descontado do salário (7,5%/9%/12%/14%, progressivo; teto 8.475,55; máx. R$ 988,09) | quem paga é o empregado, a empresa só repassa. **[SECUNDÁRIA]** |

- **Custo aproximado** (Lucro Presumido): INSS 20% + RAT 1-3% + terceiros 5,8% + FGTS 8% = **34,8% a 36,8%** de encargos diretos; com 13º+férias (+reflexos) o custo total fica ~**1,6x a 1,8x** o salário **[SECUNDÁRIA, 55-65% acima]**.
- Simples I/II/III/V: encargos diretos = FGTS 8% (+ provisões 13º/férias). Simples IV: INSS 20% + RAT + FGTS 8% (+provisões), sem terceiros.
- MEI com 1 empregado: 3% INSS patronal + 8% FGTS **[CONHECIMENTO]**.

---

## 3. Tributos pessoais do dono

- **Pró-labore**: remuneração de sócio/administrador, no mínimo **1 salário mínimo (R$ 1.621)** em empresa com sócio ativo (obrigatória no Simples Anexo III/V para atender ao Fator R). **[CONHECIMENTO]**
- **INSS sobre pró-labore: 11%** (contribuinte individual, art. 21 Lei 8.212), até o teto de R$ 8.475,55 (máx. **R$ 932,31**). Empresa paga adicionalmente 20% sobre pró-labore (fora do Simples I/II/III/V). **[CONHECIMENTO; teto OFICIAL via portaria MPS/MF 13/2026, SECUNDÁRIA]**
- **IRPF (tabela mensal 2026)** - base = pró-labore - INSS - dependentes. **[SECUNDÁRIA, confirmado em 2 fontes]**

| Base mensal (R$) | Alíquota | Deduzir (R$) |
|---|---|---|
| até 2.428,80 | isento | - |
| 2.428,81 - 2.826,65 | 7,5% | 182,16 |
| 2.826,66 - 3.751,05 | 15% | 394,16 |
| 3.751,06 - 4.664,68 | 22,5% | 675,49 |
| acima de 4.664,68 | 27,5% | 908,73 |

  **Redutor 2026 (Lei 15.270, vigente desde 01/01/2026)**: rendimento tributável mensal **até R$ 5.000** => imposto **zero**; de 5.000,01 a 7.350 => redutor = `978,62 - 0,133145 x renda` (limitado ao imposto); acima de 7.350 => sem redutor. **[OFICIAL para o anual (Art. 11-A); mensal SECUNDÁRIA]**
- **Distribuição de lucros**: segue **isenta** até **R$ 50.000/mês por PJ/por sócio**. **A partir de jan/2026 (Lei 15.270, art. 6º-A, texto lido no Planalto): acima de R$ 50 mil no mês, retenção de 10% sobre o TOTAL pago (não só o excedente), sem deduções.** Lucros apurados até 2025 (e distribuição aprovada até 31/12/2025) ficam fora. **[OFICIAL]**
  - Imposto mínimo para altas rendas (> R$ 600 mil/ano), exercício 2027: **[SECUNDÁRIA]**, sem implicação direta para o jogo.
  - Se a retenção também vale para optantes do Simples: o texto do art. 6º-A não diferencia o tipo de PJ; fonte secundária (Conjur) diz que sim. **[NÃO CONFIRMADO em norma regulamentar]**
  - Lucro isento no Simples/Presumido: no Presumido, lucro isento = base presumida (8%/32% da receita, após IRPJ/CSLL/PIS/COFINS) ou o lucro contábil se houver escrituração. No Simples, o isento é limitado ao lucro presumido da atividade menos o DAS ou o lucro contábil. **[CONHECIMENTO]** Para o jogo: tratar distribuição como livre até R$ 50 mil/mês; acima, retém 10%.
- Estratégia clássica de educação: pró-labore baixo (mínimo) + lucros isentos - ainda válida em 2026, com o novo teto de R$ 50 mil/mês.

---

## 4. Dados prontos para o jogo (Python)

```python
# ---------- Parâmetros gerais (2026) ----------
SALARIO_MINIMO = 1621.00
TETO_INSS = 8475.55
LIMITE_SIMPLES = 4_800_000.0
SUBLIMITE_SIMPLES = 3_600_000.0   # ICMS/ISS fora do DAS acima disso (fonte secundária)

# ---------- MEI ----------
MEI = {
    "limite_anual": {2026: 81_000.0, 2027: 110_000.0, 2028: 140_000.0},  # LC 238/2026
    "limite_caminhoneiro_2026": 251_600.0,
    "max_empregados": 1,
    "das_2026": {
        "inss": round(0.05 * SALARIO_MINIMO, 2),  # 81.05
        "comercio_industria": 82.05,   # + ICMS 1
        "servicos": 86.05,             # + ISS 5
        "comercio_servicos": 87.05,
        "caminhoneiro": 195.52,        # 12% SM + ICMS 1 (calculo proprio)
    },
    "excesso_tolerado": 0.20,
}

# ---------- Simples: faixas (limite_superior RBT12, aliquota nominal, parcela a deduzir) ----------
SIMPLES_FAIXAS = {
    "I":   [(180_000, .0400, 0), (360_000, .0730, 5_940), (720_000, .0950, 13_860),
            (1_800_000, .1070, 22_500), (3_600_000, .1430, 87_300), (4_800_000, .1900, 378_000)],
    "II":  [(180_000, .0450, 0), (360_000, .0780, 5_940), (720_000, .1000, 13_860),
            (1_800_000, .1120, 22_500), (3_600_000, .1470, 85_500), (4_800_000, .3000, 720_000)],
    "III": [(180_000, .0600, 0), (360_000, .1120, 9_360), (720_000, .1350, 17_640),
            (1_800_000, .1600, 35_640), (3_600_000, .2100, 125_640), (4_800_000, .3300, 648_000)],
    "IV":  [(180_000, .0450, 0), (360_000, .0900, 8_100), (720_000, .1020, 12_420),
            (1_800_000, .1400, 39_780), (3_600_000, .2200, 183_780), (4_800_000, .3300, 828_000)],
    "V":   [(180_000, .1550, 0), (360_000, .1800, 4_500), (720_000, .1950, 9_900),
            (1_800_000, .2050, 17_100), (3_600_000, .2300, 62_100), (4_800_000, .3050, 540_000)],
}

# Repartição do DAS por faixa (1..6), em % do DAS, na ordem das colunas indicadas
SIMPLES_REPARTICAO = {
    "I": {"colunas": ["IRPJ","CSLL","COFINS","PIS","CPP","ICMS"],
          "faixas": [[5.50,3.50,12.74,2.76,41.50,34.00],[5.50,3.50,12.74,2.76,41.50,34.00],
                     [5.50,3.50,12.74,2.76,42.00,33.50],[5.50,3.50,12.74,2.76,42.00,33.50],
                     [5.50,3.50,12.74,2.76,42.00,33.50],[13.50,10.00,28.27,6.13,42.10,0.0]]},
    "II": {"colunas": ["IRPJ","CSLL","COFINS","PIS","CPP","IPI","ICMS"],
           "faixas": [[5.50,3.50,11.51,2.49,37.50,7.50,32.00]]*5 + [[8.50,7.50,20.96,4.54,23.50,35.00,0.0]]},
    "III": {"colunas": ["IRPJ","CSLL","COFINS","PIS","CPP","ISS"],
            "faixas": [[4.00,3.50,12.82,2.78,43.40,33.50],[4.00,3.50,14.05,3.05,43.40,32.00],
                       [4.00,3.50,13.64,2.96,43.40,32.50],[4.00,3.50,13.64,2.96,43.40,32.50],
                       [4.00,3.50,12.82,2.78,43.40,33.50],[35.00,15.00,16.03,3.47,30.50,0.0]]},
    "IV": {"colunas": ["IRPJ","CSLL","COFINS","PIS","ISS"],   # sem CPP: INSS patronal fora do DAS
           "faixas": [[18.80,15.20,17.67,3.83,44.50],[19.80,15.20,20.55,4.45,40.00],
                      [20.80,15.20,19.73,4.27,40.00],[17.80,19.20,18.90,4.10,40.00],
                      [18.80,19.20,18.08,3.92,40.00],[53.50,21.50,20.55,4.45,0.0]]},
    "V": {"colunas": ["IRPJ","CSLL","COFINS","PIS","CPP","ISS"],
          "faixas": [[25.00,15.00,14.10,3.05,28.85,14.00],[23.00,15.00,14.10,3.05,27.85,17.00],
                     [24.00,15.00,14.92,3.23,23.85,19.00],[21.00,15.00,15.74,3.41,23.85,21.00],
                     [23.00,12.50,14.10,3.05,23.85,23.50],[35.00,15.50,16.44,3.56,29.50,0.0]]},
}

FATOR_R_MIN = 0.28  # r >= 28% -> Anexo III; senão Anexo V

def aliquota_efetiva(anexo, rbt12):
    for lim, aliq, ded in SIMPLES_FAIXAS[anexo]:
        if rbt12 <= lim:
            return (rbt12 * aliq - ded) / rbt12
    raise ValueError("RBT12 acima do limite do Simples")

# Anexo por tipo de empresa (None = depende do Fator R)
ANEXO_POR_EMPRESA = {
    "restaurante": "I", "cafeteria": "I", "loja_roupas": "I", "supermercado": "I",
    "oficina_mecanica": "III", "tecnologia": "FATOR_R", "agencia_marketing": "FATOR_R",
    "industria": "II", "construtora": "IV", "transporte_cargas": "III",
    "imobiliaria": "III", "ecommerce": "I",
}
SIMPLES_INCLUI_INSS_PATRONAL = {"I": True, "II": True, "III": True, "IV": False, "V": True}

# ---------- Lucro Presumido ----------
PRESUNCAO = {   # (IRPJ, CSLL) sobre a receita bruta
    "comercio": (0.08, 0.12), "industria": (0.08, 0.12), "transporte_carga": (0.08, 0.12),
    "construcao_com_material": (0.08, 0.12), "combustivel": (0.016, 0.12),
    "transporte_passageiros": (0.16, 0.12),
    "servicos": (0.32, 0.32), "intermediacao": (0.32, 0.32), "locacao_imoveis": (0.32, 0.32),
}
PRESUNCAO_EMPRESA = {
    "restaurante": "comercio", "cafeteria": "comercio", "loja_roupas": "comercio",
    "supermercado": "comercio", "oficina_mecanica": "servicos", "tecnologia": "servicos",
    "agencia_marketing": "servicos", "industria": "industria", "construtora": "construcao_com_material",
    "transporte_cargas": "transporte_carga", "imobiliaria": "intermediacao", "ecommerce": "comercio",
}
LP = {
    "irpj_aliquota": 0.15, "irpj_adicional": 0.10, "irpj_adicional_limite_mes": 20_000.0,
    "csll": 0.09, "pis_cumulativo": 0.0065, "cofins_cumulativo": 0.03,
    "limite_adesao": 78_000_000.0,
    # LC 224/2025: +10% nos % de presunção sobre a parcela da receita acima de 5 mi/ano
    "lc224_receita_limite_ano": 5_000_000.0, "lc224_acrescimo_presuncao": 0.10,
}
ISS = {"min": 0.02, "max": 0.05, "tipico": {"tecnologia": 0.03, "agencia_marketing": 0.03,
       "construtora": 0.03, "oficina_mecanica": 0.03, "imobiliaria": 0.04, "transporte_cargas": 0.03}}
ICMS_INTERNO = {"SP": 0.18, "MG": 0.18, "RJ": 0.22, "RS": 0.17, "faixa_geral": (0.17, 0.23)}  # só SP confirmado
IPI_TIPICO = 0.10  # simplificação do jogo; real depende da TIPI

# ---------- Encargos sobre folha ----------
ENCARGOS = {
    "inss_patronal": 0.20, "rat_base": (0.01, 0.02, 0.03), "fap": (0.5, 2.0),
    "terceiros": 0.058, "fgts": 0.08,
    "decimo_terceiro": 1/12, "ferias_mais_terco": (1/12) * (4/3),
    "mei_inss_patronal_empregado": 0.03,
}
# Quais encargos pagos fora do DAS por regime
ENCARGOS_REGIME = {
    "mei": ["fgts", "inss_patronal_3pct"],
    "simples_I_II_III_V": ["fgts"],
    "simples_IV": ["fgts", "inss_patronal", "rat"],
    "lucro_presumido": ["fgts", "inss_patronal", "rat", "terceiros"],
}

# ---------- Dono ----------
INSS_PROLABORE = {"aliquota": 0.11, "teto_base": TETO_INSS, "maximo": round(0.11 * TETO_INSS, 2)}
INSS_EMPREGADO_2026 = [(1621.00, .075), (2902.84, .09), (4354.27, .12), (TETO_INSS, .14)]  # progressivo
IRPF_MENSAL_2026 = [(2428.80, 0.0, 0.0), (2826.65, .075, 182.16), (3751.05, .15, 394.16),
                    (4664.68, .225, 675.49), (float("inf"), .275, 908.73)]
def irpf_redutor_2026(renda_mensal):
    if renda_mensal <= 5000: return None        # imposto zerado
    if renda_mensal <= 7350: return 978.62 - 0.133145 * renda_mensal
    return 0.0
DIVIDENDOS = {"isento_ate_mes": 50_000.0, "retencao_acima": 0.10,   # sobre o total no mês (Lei 15.270)
              "vigencia": "2026-01"}

# ---------- Reforma do consumo ----------
REFORMA = {
    2026: {"cbs": 0.009, "ibs": 0.001, "compensado_pis_cofins": True, "simples_e_mei_afetados": False},
    2027: {"cbs": "aliq_ref - 0.1pp", "ibs_estadual": 0.0005, "ibs_municipal": 0.0005},
    2033: "ICMS e ISS extintos (transicao ate 2033)",
}
```

---

## 5. Fontes (consultadas em 21/11/2026)

Oficiais (Planalto, texto lido diretamente):
- LC 123/2006 (Anexos I-V, Fator R, MEI 81 mil): https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm
- LC 238/2026 (limite MEI): https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp238.htm
- LC 224/2025 (presunção +10%): https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp224.htm
- LC 214/2025 (IBS/CBS, transição, Simples; arts. 41, 343-348, Anexo VII MEI): https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm
- Lei 15.270/2025 (dividendos, IRPF): https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/L15270.htm
- Lei 9.249/1995 art. 15 (presunções): https://www.planalto.gov.br/ccivil_03/leis/l9249.htm
- LC 116/2003 (ISS 2%-5%): https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm

Secundárias (não oficiais):
- DAS-MEI 2026: https://agenciabrasil.ebc.com.br/economia/noticia/2026-01/recolhimento-do-mei-sobe-para-r-8105-em-2026 ; https://fastcompanybrasil.com/money/mei-contribuicao-do-das-muda-em-2026-confira-os-novos-valores/
- Tabela IRPF/INSS 2026: https://meutudo.com.br/blog/noticias/2026/01/07/faixas-e-aliquotas-sao-atualizadas-na-nova-tabela-do-imposto-de-renda-2026/ ; https://documentacao.senior.com.br/exigenciaslegais/destaques/imposto-de-renda-2026 ; https://www.debit.com.br/blog/tabela-inss-2026-teto-aliquotas
- LC 224 resumo: https://www.contabeis.com.br/noticias/75261/lucro-presumido-tera-aumento-de-10-na-base-do-irpj-e-csll-em-2026/ ; Receita Federal Q&A: https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/beneficios-fiscais/perguntas-e-respostas-reducao-dos-incentivos-e-beneficios-tributarios-v5-final.pdf (listado na busca, **não lido**)
- Reforma/Simples: https://www.migalhas.com.br/depeso/463764/simples-nacional-e-ibs-cbs-impactos-para-fornecedor-e-cliente
- Dividendos: https://www.mayerbrown.com/pt/insights/publications/2025/12/enactment-of-law-no-15270-2025-which-establishes-dividend-taxation-expands-the-exemption-threshold-and-introduces-a-minimum-tax-on-high-incomes
- ICMS estados: https://agilize.com.br/blog/gestao-contabil-e-fiscal/tabela-de-icms-2026/
- Encargos: https://www.gupy.io/blog/inss-patronal ; https://jornalcontabil.com.br/noticia/encargos-sociais-e-impostos-na-folha-de-pagamento/
- Sublimite Simples: https://jornalcontabil.com.br/noticia/simples-nacional-2026-sublimite-de-icms-e-iss-se-mantem-em-r-36-milhoes/amp/

---

## 6. Incertezas / o que não consegui confirmar

1. **Portal do Empreendedor/gov.br (valores do DAS-MEI)** e **Portal do Simples** bloquearam acesso automatizado (captcha). DAS-MEI 2026 foi conferido pela fórmula legal (5% do SM) e por fontes secundárias; MEI Caminhoneiro foi calculado (12% SM + 1 ICMS) e as fontes divergiram.
2. **Sublimite R$ 3,6 mi** e **IRPF/INSS 2026 (tabelas e redutor mensal)**: só em fontes secundárias; o redutor anual está no texto da Lei 15.270.
3. **LC 224 - datas exatas** (IRPJ jan/2026 e CSLL abr/2026 é a minha leitura do art. 14); o Q&A da Receita não foi aberto. Possíveis liminares judiciais.
4. **Alíquotas de ICMS** por estado: só SP 18% apareceu; RJ 22% e MG 18% são de conhecimento prévio, **não confirmados**.
5. **ISS por cidade**: apenas o intervalo legal 2%-5%; valores típicos por atividade são sugestão para o jogo.
6. **Anexo por atividade**: classificação de restaurante, transporte (ICMS interestadual), imobiliária, construtora/incorporação e e-commerce marketplace é do meu conhecimento, não validada na Resolução CGSN 140/2018 nesta consulta.
7. **Anexo III, 5ª faixa**: rateio do excesso de ISS está incompleto no texto lido; use só "ISS limitado a 5%".
8. **Retenção de 10% sobre dividendos de optantes do Simples**: texto legal não distingue; interpretação por imprensa.
9. **Presunção para MEI** e regras de isenção de lucro no Simples: conhecimento prévio, não rebuscado.
10. **RAT/FAP e terceiros**: faixas de blogs; o percentual real depende do CNAE/FPAS.
11. **Restrições de atividade do MEI** (lista de ocupações): não obtida; **corretor de imóveis como MEI: não confirmado**.
12. **IPI**: alíquota depende da TIPI; o valor do jogo é simplificação.
13. **Fim da transição em 2033** e demais datas de 2029-2033: só fontes secundárias (a LC 214 foi lida apenas nos arts. 343-348).
