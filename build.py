#!/usr/bin/env python3
"""Gera dados.js a partir das duas camadas do catálogo.

  dados/morros_sul.json     camada curada — ficha completa, escrita à mão
  dados/mapeados_sul.json   camada mapeada — só nome, altitude e coordenada
                            (opcional; gerada por coletar_sul.py)

O site lê os dados por <script src="dados.js">, e não por fetch(), para que
o index.html funcione ao ser aberto direto do disco (file://), sem servidor.
Rode este script sempre que editar qualquer um dos JSON:  python3 build.py
"""
import json
import pathlib

raiz = pathlib.Path(__file__).parent

curado = json.loads((raiz / "dados" / "morros_sul.json").read_text(encoding="utf-8"))
morros = curado["morros"]
for morro in morros:
    morro["ficha"] = True

arquivo_mapeados = raiz / "dados" / "mapeados_sul.json"
mapeados = []
if arquivo_mapeados.exists():
    mapeados = json.loads(arquivo_mapeados.read_text(encoding="utf-8"))["mapeados"]
    for mapeado in mapeados:
        mapeado["ficha"] = False
        mapeado.setdefault("municipios", [])
        mapeado.setdefault("regiao", "")

todos = morros + mapeados
todos.sort(key=lambda m: -m["altitude"])

saida = {
    "metadata": {
        **curado.get("metadata", {}),
        "total": len(todos),
        "com_ficha": len(morros),
        "mapeados": len(mapeados),
    },
    "morros": todos,
}

js = "/* gerado por build.py — edite os JSON em dados/, não este arquivo */\n"
js += "window.MORROS_SUL = " + json.dumps(saida, ensure_ascii=False, indent=1) + ";\n"
(raiz / "dados.js").write_text(js, encoding="utf-8")

print(f"dados.js gerado: {len(todos)} elevações "
      f"({len(morros)} com ficha, {len(mapeados)} mapeadas)")
