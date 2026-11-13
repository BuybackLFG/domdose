"""Разбор nginx.conf для статических сторожей frontend.

Дерево директив с учётом кавычек, комментариев и вложенных блоков;
наследование директив по цепочке location -> server -> http и разрешение
адреса proxy_pass через set-переменную или upstream-блок.
"""

import re
from dataclasses import dataclass, field

API_ORIGIN = "http://api:8000"
DOCKER_RESOLVER = "127.0.0.11"
MAX_RESOLVER_VALID_SECONDS = 30
_UNITS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}
_VARIABLE = re.compile(r"^\$(?:\{(\w+)\}|(\w+))")


@dataclass(eq=False)
class Node:
    """Директива; children не None — блок."""

    name: str
    args: tuple[str, ...]
    children: list["Node"] | None = None
    parent: "Node | None" = field(default=None, repr=False)

    def own(self, name):
        """Прямые директивы блока с именем name."""
        return [child for child in self.children or () if child.name == name]

    def walk(self):
        """Все вложенные директивы в порядке текста."""
        for child in self.children or ():
            yield child
            yield from child.walk()

    def chain(self):
        """Сам блок и его предки до корня, без условных if-блоков."""
        node = self
        while node is not None:
            if node.name != "if":
                yield node
            node = node.parent

    def effective(self, name):
        """Директивы name ближайшего уровня, где они объявлены (наследование nginx)."""
        for node in self.chain():
            found = node.own(name)
            if found:
                return found
        return []


def _tokens(text):
    """Слова и разделители { } ; без комментариев; кавычки снимаются."""
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
        elif char == "#":
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
        elif char in "{};":
            yield char, char
            index += 1
        elif char in "\"'":
            quote, index, value = char, index + 1, []
            while index < length and text[index] != quote:
                if text[index] == "\\" and index + 1 < length:
                    index += 1
                value.append(text[index])
                index += 1
            if index >= length:
                raise ValueError("unterminated quoted string")
            index += 1
            yield "word", "".join(value)
        else:
            start = index
            while index < length and not text[index].isspace():
                if text[index] in ";}":
                    break
                if text[index] == "{":
                    if index > start and text[index - 1] == "$":
                        closing = text.find("}", index)
                        index = length if closing < 0 else closing + 1
                        continue
                    break
                index += 1
            yield "word", text[start:index]


def parse(text):
    """Корень (http-контекст) с деревом директив; синтаксический отказ — ValueError."""
    root = Node("", (), [])
    stack, words = [root], []
    for kind, value in _tokens(text):
        if kind == "word":
            words.append(value)
            continue
        if kind == "}":
            if words or len(stack) == 1:
                raise ValueError("unexpected }")
            stack.pop()
            continue
        if not words:
            raise ValueError(f"empty directive before {kind}")
        node = Node(words[0], tuple(words[1:]), [] if kind == "{" else None, stack[-1])
        stack[-1].children.append(node)
        if kind == "{":
            stack.append(node)
        words = []
    if words or len(stack) != 1:
        raise ValueError("unterminated block or directive")
    return root


def locations(root):
    return [node for node in root.walk() if node.name == "location"]


def location(root, *args):
    """Единственный location с аргументами args или None."""
    found = [node for node in locations(root) if node.args == args]
    assert len(found) <= 1, f"duplicate location {args}"
    return found[0] if found else None


def find_target_location(root, uri):
    """location, который обслужит uri: exact, named, затем самый длинный префикс."""
    candidates = locations(root)
    for node in candidates:
        if node.args == ("=", uri) or (uri.startswith("@") and node.args == (uri,)):
            return node
    if uri.startswith("@"):
        return None
    best, best_length = None, -1
    for node in candidates:
        prefix = node.args[-1]
        modifier = node.args[0] if len(node.args) == 2 else ""
        if modifier not in ("", "^~"):
            continue
        if uri.startswith(prefix) and len(prefix) > best_length:
            best, best_length = node, len(prefix)
    return best


def variable_name(value):
    """Имя переменной в начале значения ($name или ${name}) или None."""
    match = _VARIABLE.match(value)
    return None if match is None else (match.group(1) or match.group(2))


def mentions_variable(text, name):
    """Есть ли в тексте ссылка на переменную name."""
    return re.search(r"\$(?:\{" + name + r"\}|" + name + r"(?!\w))", text) is not None


def set_value(node, name):
    """Литерал set $name ближайшего уровня цепочки или None."""
    for level in node.chain():
        for directive in level.own("set"):
            if len(directive.args) == 2 and variable_name(directive.args[0]) == name:
                return directive.args[1]
    return None


def upstream(root, name):
    found = [
        node
        for node in root.own("upstream")
        if node.args == (name,) and node.children is not None
    ]
    return found[0] if found else None


def upstream_resolves_api(block):
    """upstream с общей зоной и единственным server api:8000 ... resolve."""
    entries = block.own("server")
    return (
        bool(block.own("zone"))
        and len(entries) == 1
        and entries[0].args[:1] == ("api:8000",)
        and "resolve" in entries[0].args[1:]
    )


@dataclass(frozen=True)
class ProxyTarget:
    """Адрес proxy_pass после подстановки.

    kind: static, variable, upstream или upstream-unresolved (без zone/resolve).
    """

    kind: str
    url: str
    resolver_scope: Node = field(repr=False)


def proxy_target(node, root):
    """Разрешённый proxy_pass location или None, если его нет или не разрешается."""
    directives = node.own("proxy_pass")
    if len(directives) != 1 or len(directives[0].args) != 1:
        return None
    raw = directives[0].args[0]
    match = _VARIABLE.match(raw)
    if match is not None:
        value = set_value(node, match.group(1) or match.group(2))
        if value is None or "$" in value:
            return None
        return ProxyTarget("variable", value + raw[match.end() :], node)
    match = re.match(r"^http://([A-Za-z0-9_.-]+)(.*)$", raw)
    if match is not None:
        block = upstream(root, match.group(1))
        if block is not None:
            if not upstream_resolves_api(block):
                return ProxyTarget("upstream-unresolved", raw, block)
            return ProxyTarget("upstream", API_ORIGIN + match.group(2), block)
    return ProxyTarget("static", raw, node)


def _seconds(value):
    match = re.fullmatch(r"(\d+)([smhd]?)", value)
    return None if match is None else int(match.group(1)) * _UNITS[match.group(2)]


def resolver_ok(directive):
    """resolver только на DNS Docker с valid= не больше 30 секунд."""
    addresses = [arg for arg in directive.args if "=" not in arg]
    options = dict(arg.split("=", 1) for arg in directive.args if "=" in arg)
    valid = _seconds(options.get("valid", ""))
    return (
        bool(addresses)
        and all(
            re.fullmatch(re.escape(DOCKER_RESOLVER) + r"(?::53)?", item)
            for item in addresses
        )
        and valid is not None
        and 0 < valid <= MAX_RESOLVER_VALID_SECONDS
    )


def reresolves_api(node, root, path=""):
    """proxy_pass location переразрешает имя api в runtime и ведёт на api+path.

    path "" — исходный URI запроса (допустимы также $request_uri и /api/).
    """
    target = proxy_target(node, root)
    if target is None or target.kind not in ("variable", "upstream"):
        return False
    if path:
        allowed = {API_ORIGIN + path}
    else:
        allowed = {API_ORIGIN, API_ORIGIN + "$request_uri", API_ORIGIN + "/api/"}
    if target.url not in allowed:
        return False
    if target.kind == "upstream":
        # resolve в upstream берёт resolver из самого upstream или из http.
        resolvers = target.resolver_scope.own("resolver") or root.own("resolver")
    else:
        resolvers = node.effective("resolver")
    return len(resolvers) == 1 and resolver_ok(resolvers[0])


def proxies_to_scoring(root):
    """Любое упоминание хоста scoring в proxy_pass, set или upstream server."""
    for node in root.walk():
        if node.name in ("proxy_pass", "set", "server", "grpc_pass", "fastcgi_pass"):
            if any(re.search(r"(?:^|//|\s)scoring(?::|/|$)", arg) for arg in node.args):
                return True
    return False


def location_names_with_internal(root):
    """location, в имени (аргументах) которых есть слово internal."""
    return [
        node.args
        for node in locations(root)
        if any("internal" in arg.lower() for arg in node.args)
    ]


def returns(node):
    """Все return внутри location, включая if-блоки."""
    return [child for child in node.walk() if child.name == "return"]


def success_returns(node):
    """return с кодом ниже 400 (или URL без кода) — обход access-фазы."""
    result = []
    for directive in returns(node):
        code = directive.args[0] if directive.args else ""
        if not code.isdigit() or int(code) < 400:
            result.append(directive)
    return result


# --- Закрытие документов SPA проверкой готовности api ----------------------

GATE_HEADER = "x-domdossier-error"
GATE_SOURCE = "$upstream_http_x_domdossier_error"
UNAVAILABLE_TEXT = "Данные недоступны"
OPEN_PREFIXES = ("/assets/", "/maps/")


def _label(node):
    return "location " + " ".join(node.args)


def _auth_request(node):
    """Действующий auth_request location или None (нет либо off)."""
    directives = node.effective("auth_request")
    if len(directives) != 1 or directives[0].args[:1] in ((), ("off",)):
        return None
    return directives[0]


def gate_problems(root, node):
    """auth_request location ведёт на internal-проверку api /api/ready."""
    label = _label(node)
    directive = _auth_request(node)
    if directive is None:
        return [f"{label}: no auth_request"]
    gate = find_target_location(root, directive.args[0])
    if gate is None:
        return [f"{label}: auth_request target location is missing"]
    problems = []
    if not gate.own("internal"):
        problems.append(f"{label}: gate {_label(gate)} lacks internal directive")
    if any("internal" in arg.lower() for arg in gate.args):
        problems.append(f"{label}: gate name contains internal")
    if not reresolves_api(gate, root, "/api/ready"):
        problems.append(f"{label}: gate does not proxy re-resolved api /api/ready")
    return problems


def error_fallback(root, node, code):
    """(location отказа, None) для error_page code с итоговым 503 или (None, причина)."""
    for directive in node.effective("error_page"):
        codes = [arg for arg in directive.args[:-1] if not arg.startswith("=")]
        if code not in codes:
            continue
        overrides = [arg for arg in directive.args[:-1] if arg.startswith("=")]
        if overrides not in (["="], ["=503"]):
            return None, f"error_page {code} must set the code with = or =503"
        target = find_target_location(root, directive.args[-1])
        if target is None:
            return None, f"error_page {code} target location is missing"
        own_returns = target.own("return")
        if not own_returns or own_returns[-1].args[:1] != ("503",):
            return None, f"error_page {code} target must return 503"
        return target, None
    return None, f"no error_page for {code}"


def auth_code_variable(node):
    """Переменная auth_request_set с заголовком X-DomDossier-Error ответа api."""
    for directive in node.effective("auth_request_set"):
        if len(directive.args) == 2 and directive.args[1].lower() == GATE_SOURCE:
            return variable_name(directive.args[0])
    return None


def _has_api_unavailable_default(root, target, source, header):
    """Пустой код проверки (api недоступен) превращается в api_unavailable."""
    for block in root.own("map"):
        if (
            len(block.args) == 2
            and block.args[1] == f"${header}"
            and mentions_variable(block.args[0], source)
            and any("api_unavailable" in entry.args for entry in block.children or ())
        ):
            return True
    return any(
        directive.name == "set"
        and len(directive.args) == 2
        and variable_name(directive.args[0]) == header
        and "api_unavailable" in directive.args[1]
        for directive in target.walk()
    )


def document_fallback_problems(root, node):
    """Отказ проверки: 503, X-DomDossier-Error с кодом и короткое тело без SPA."""
    label = _label(node)
    source = auth_code_variable(node)
    problems = [] if source else [f"{label}: no auth_request_set of {GATE_SOURCE}"]
    target, problem = error_fallback(root, node, "500")
    if problem:
        return problems + [f"{label}: {problem}"]
    body = " ".join(target.own("return")[-1].args[1:])
    headers = [
        directive
        for directive in target.effective("add_header")
        if directive.args[:1] and directive.args[0].lower() == GATE_HEADER
    ]
    if len(headers) != 1 or len(headers[0].args) != 3 or headers[0].args[2] != "always":
        return problems + [
            f"{label}: fallback lacks add_header X-DomDossier-Error <code> always"
        ]
    header = variable_name(headers[0].args[1])
    if header is None:
        problems.append(f"{label}: X-DomDossier-Error value is not a variable")
    elif not mentions_variable(body, header):
        problems.append(f"{label}: fallback body does not carry the code")
    if UNAVAILABLE_TEXT not in body:
        problems.append(f"{label}: fallback body lacks {UNAVAILABLE_TEXT}")
    if 'id="root"' in body or "/assets/index-" in body:
        problems.append(f"{label}: fallback body contains SPA")
    if source and header and (
        header == source
        or not _has_api_unavailable_default(root, target, source, header)
    ):
        problems.append(f"{label}: no api_unavailable code for unreachable api")
    return problems


def is_open_location(node):
    """Не документ SPA: health, ready, api, assets, maps, internal и named."""
    args = node.args
    if node.own("internal") or args[0].startswith("@"):
        return True
    if args in (("=", "/health"), ("=", "/ready"), ("/api/",)):
        return True
    modifier = args[0] if len(args) == 2 else ""
    return modifier in ("", "^~") and args[-1].startswith(OPEN_PREFIXES)


def spa_gate_problems(root):
    """Все location, способные отдать документ SPA, закрыты проверкой api."""
    problems = [] if location(root, "/") else ["SPA fallback location / is missing"]
    for node in locations(root):
        if is_open_location(node):
            continue
        problems.extend(gate_problems(root, node))
        problems.extend(
            f"{_label(node)}: return {' '.join(item.args)} bypasses auth_request"
            for item in success_returns(node)
        )
        problems.extend(document_fallback_problems(root, node))
    return problems


def health_problems(root):
    """/health отвечает 200 сам, без обращения к api."""
    node = location(root, "=", "/health")
    if node is None:
        return ["location = /health is missing"]
    problems = []
    if not any(item.args[:1] == ("200",) for item in node.own("return")):
        problems.append("/health must return 200 itself")
    if node.own("proxy_pass") or node.own("auth_request"):
        problems.append("/health must not depend on api")
    return problems


def ready_problems(root):
    """/ready даёт 503 при неготовности api: auth_request или прокси к /api/ready."""
    node = location(root, "=", "/ready")
    if node is None:
        return ["location = /ready is missing"]
    problems = [
        f"/ready: return {' '.join(item.args)} bypasses api check"
        for item in success_returns(node)
    ]
    if _auth_request(node) is not None:
        problems.extend(gate_problems(root, node))
        codes = ("500",)
    elif node.own("proxy_pass"):
        if not reresolves_api(node, root, "/api/ready"):
            problems.append("/ready: proxy_pass is not re-resolved api /api/ready")
        codes = ("502", "504")
    else:
        return problems + ["/ready does not check api readiness"]
    for code in codes:
        _, problem = error_fallback(root, node, code)
        if problem:
            problems.append(f"/ready: {problem}")
    return problems
