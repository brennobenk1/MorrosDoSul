# Acima de 300

Catálogo de elevações acima de 300 m no Paraná, Santa Catarina e Rio Grande do Sul,
organizado para quem vai acampar.

## Arquivos

    index.html                      o site inteiro, sem dependência de build
    dados.js                        gerado — é o que o site lê
    dados/morros_sul.json           a fonte da verdade, edite aqui
    dados/picos_brasil_legado.json  a base nacional anterior, guardada para a expansão
    build.py                        gera dados.js a partir do JSON

## Rodar

Abra o `index.html` direto no navegador. Os dados entram por `<script src="dados.js">`
em vez de `fetch()`, então funciona sem servidor local.

Depois de editar o JSON:

    python3 build.py

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

- Conferir em campo os 19 registros com `"confianca": "media"`
- Fotos e tracks GPX
- Campings e pousadas de apoio na base
- São Paulo e Minas Gerais, reaproveitando `picos_brasil_legado.json`
