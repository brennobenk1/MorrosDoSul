#!/usr/bin/env python3
"""Gera dados.js a partir de dados/morros_sul.json.

O site lê os dados por <script src="dados.js">, e não por fetch(), para que
o index.html funcione ao ser aberto direto do disco (file://), sem servidor.
Rode este script sempre que editar o JSON:  python3 build.py
"""
import json, pathlib

raiz = pathlib.Path(__file__).parent
dados = json.loads((raiz / "dados" / "morros_sul.json").read_text(encoding="utf-8"))
dados["morros"].sort(key=lambda m: -m["altitude"])

js = "/* gerado por build.py — edite dados/morros_sul.json, não este arquivo */\n"
js += "window.MORROS_SUL = " + json.dumps(dados, ensure_ascii=False, indent=1) + ";\n"
(raiz / "dados.js").write_text(js, encoding="utf-8")
print(f"dados.js gerado com {len(dados['morros'])} morros")
