import ast
import operator
import math
import re
from typing import Optional

# Permite apenas operações matemáticas seguras (evita execução de código malicioso)
ALLOWED_NAMES = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "sqrt": math.sqrt,
    "pi": math.pi,
    "e": math.e,
    "abs": abs,
    "round": round,
}


class CalculatorPlugin:

    def __init__(self):
        # Detecta se o texto parece uma expressão matemática (números e operadores)
        self.pattern = re.compile(
            r"^[\d\s\+\-\*\/\%\(\)\.\,\^a-z_]+$", re.IGNORECASE
        )

    def evaluate(self, query: str) -> Optional[str]:
        query = query.strip()

        # Ignora se for muito curto ou se não contiver nenhum operador matemático
        if (
            len(query) < 2
            or not any(char in query for char in "+-*/%^")
            and not any(func in query for func in ALLOWED_NAMES)
        ):
            return None

        # Substitui vírgula por ponto e ^ por potência ** do Python
        expr = query.replace(",", ".").replace("^", "**")

        if len(expr) > 256 or not self.pattern.fullmatch(expr):
            return None

        try:
            tree = ast.parse(expr, mode="eval")
            if sum(1 for _ in ast.walk(tree)) > 64:
                return None
            result = self._evaluate_node(tree.body)

            if isinstance(result, (int, float)):
                # Se for inteiro exato (ex: 4.0), exibe como 4
                if isinstance(result, float) and result.is_integer():
                    return str(int(result))
                return f"{result:.4f}".rstrip("0").rstrip(".")
        except Exception:
            return None

        return None

    def _evaluate_node(self, node, depth=0):
        if depth > 16:
            raise ValueError("Expressão muito profunda")
        evaluate = lambda child: self._evaluate_node(child, depth + 1)
        operations = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Mod: operator.mod, ast.Pow: operator.pow,
        }
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.Name) and node.id in ("pi", "e"):
            value = ALLOWED_NAMES[node.id]
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            if isinstance(node.op, ast.USub):
                value = -value
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Expoente muito grande")
            value = operations[type(node.op)](left, right)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in ALLOWED_NAMES and callable(ALLOWED_NAMES[node.func.id])
              and not node.keywords and 1 <= len(node.args) <= 2):
            value = ALLOWED_NAMES[node.func.id](*(evaluate(arg) for arg in node.args))
        else:
            raise ValueError("Operação não permitida")
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("Resultado fora dos limites")
        return value
