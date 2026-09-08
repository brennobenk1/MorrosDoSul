# Acima de 500

Catálogo de elevações acima de 500 m no Paraná, Santa Catarina e Rio Grande do Sul,
organizado para quem vai acampar.

## Arquivos

    index.html                      o site inteiro, sem dependência de build
    dados.js                        gerado — é o que o site lê
    dados/morros_sul.json           camada curada: ficha completa, escrita à mão
    dados/mapeados_sul.json         camada mapeada: gerada por coletar_sul.py
    dados/picos_brasil_legado.json  a base nacional anterior, guardada para a expansão
    coletar_sul.py                  puxa OSM + Wikidata para a camada mapeada
    build.py                        junta as duas camadas em dados.js

## Rodar

Abra o `index.html` direto no navegador. Os dados entram por `<script src="dados.js">`
em vez de `fetch()`, então funciona sem servidor local.

Depois de editar o JSON:

    python3 build.py

## O piso de 500 m

O site abre mostrando só o que passa de **500 m**, que é o corte útil para acampar.
A faixa de 300 a 500 continua no acervo e não foi apagada — ela entra pelo chip
**"Incluir 300–500 m"** na barra de filtros, ou arrastando a alça de baixo da régua
de altitude. Arrastar abaixo de 500 acende o chip sozinho.

São 39 morros acima de 500 m e 8 entre 300 e 500, quase todos no Rio Grande do Sul,
que fora dos Aparados é um estado baixo.

O `coletar_sul.py` coleta a partir de 300 m de propósito, para que a faixa baixa exista
quando alguém pedir. Para mudar isso: `python3 coletar_sul.py --piso 500`.

## As duas camadas

O catálogo tem dois tipos de registro, e a diferença é proposital.

**Com ficha** (`dados/morros_sul.json`) traz o que muda a viagem: dificuldade, km de
subida, ganho de elevação, água, pernoite, acesso e época. Isso não existe em nenhuma
base pública — é levantamento manual, um morro por vez. São os 47 de hoje.

**Mapeado** (`dados/mapeados_sul.json`) traz nome, altitude e coordenada, e mais nada.
Vem do OpenStreetMap e do Wikidata, e serve para o catálogo cobrir os três estados de
verdade em vez de mostrar só o que já foi visitado. O site marca esses como "sem ficha"
e nunca inventa trilha, água ou pernoite para eles.

Para gerar a camada mapeada:

    pip install requests
    python3 coletar_sul.py --altitude
    python3 build.py

O `--altitude` usa o Open-Elevation para preencher a altitude dos pontos que o OSM não
traz, e é o que faz a diferença entre algumas centenas e alguns milhares de registros.
A coleta leva de 5 a 15 minutos. O `--municipios` existe, mas roda a 1 requisição por
segundo no Nominatim, então com milhares de pontos leva horas — deixe para depois.

O coletor nunca sobrescreve um morro com ficha: se o nome bate e o ponto está a menos de
1 km de um registro curado, ele é descartado como duplicata. Dá para rodar de novo sempre
que quiser atualizar, sem medo de perder curadoria.

## Adicionar um morro

Copie um registro de `dados/morros_sul.json` e preencha:

| campo | o que é |
|---|---|
| `altitude` | metros acima do nível do mar |
| `dificuldade` | 1 leve · 2 moderada · 3 puxada · 4 difícil · 5 técnica |
| `trilha_km`, `tempo_h`, `ganho_m` | só a subida, não a ida e volta |
| `acampamento` | `cume`, `percurso`, `base`, `camping`, `proibido` ou `verificar` |
| `agua` | `percurso`, `base`, `sazonal` ou `nenhuma` |
| `confianca` | `alta` quando conferido em campo ou em fonte oficial; `media` mostra o aviso na ficha |

A escala de cores é hipsométrica e vem do próprio dado: musgo até 600 m, erva até 1000,
palha até 1400, ferrugem até 1700, geada acima disso. Não há cor decorativa no site —
toda cor forte significa altitude.

## O que falta

- Rodar `coletar_sul.py` para sair dos 47 e cobrir os três estados
- Levantar mais morros do RS acima de 500 m, onde o acervo é mais fino
- Conferir em campo os 31 registros com `"confianca": "media"`
- Promover mapeados a ficha completa, começando pelos mais procurados
- Fotos e tracks GPX
- Campings e pousadas de apoio na base
- São Paulo e Minas Gerais, reaproveitando `picos_brasil_legado.json`
