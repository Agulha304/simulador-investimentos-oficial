"""Motor econômico e de mercado (puro, sem banco): estado macro, inflação por categoria, regimes, crises e ativos.

Tudo aqui é função determinística de (semente, mês, estado anterior, parâmetros). A persistência e a ligação com os
outros módulos ficam em `economy_service`. Veja `world.step` para a ordem do processamento mensal.
"""
