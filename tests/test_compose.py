import posixpath
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

import nginx_config

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "compose.yaml"
COMPOSE_TEXT = COMPOSE_PATH.read_text(encoding="utf-8")
SERVICES = ("api", "scoring", "frontend")
LOG_VOLUMES = ("api_logs", "scoring_logs", "frontend_logs")
DOCKERFILES = {
    "api": ROOT / "api" / "Dockerfile",
    "scoring": ROOT / "api" / "scoring.Dockerfile",
    "frontend": ROOT / "frontend" / "Dockerfile",
}
NGINX_PATH = ROOT / "frontend" / "nginx.conf"
MAP_ASSET = ROOT / "frontend" / "public" / "maps" / "vladivostok-pilot.png"
MAP_MANIFEST_URL = "/maps/vladivostok-pilot.manifest.json"
REQUIREMENTS_PATH = ROOT / "requirements.txt"
CONSTRAINTS_PATH = ROOT / "constraints.txt"
DOCKERIGNORE_PATH = ROOT / ".dockerignore"
PYTHON_DOCKERFILES = (DOCKERFILES["api"], DOCKERFILES["scoring"])


def top_section(name, text=COMPOSE_TEXT):
    lines = text.splitlines()
    try:
        start = lines.index(f"{name}:")
    except ValueError:
        raise AssertionError(f"missing top-level {name}: section") from None
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line and not line[0].isspace() and re.match(r"^[A-Za-z0-9_-]+:", line):
            break
        end += 1
    return "\n".join(lines[start:end])


def service_block(name):
    section = top_section("services")
    match = re.search(rf"(?m)^  {re.escape(name)}:\s*$", section)
    assert match is not None, f"missing service {name}"
    following = re.search(r"(?m)^  [A-Za-z0-9_-]+:\s*$", section[match.end() :])
    end = match.end() + following.start() if following else len(section)
    return section[match.start() : end]


def direct_key(block, key):
    return re.search(rf"(?m)^    {re.escape(key)}:", block) is not None


def list_entries(block, key):
    match = re.search(rf"(?m)^    {re.escape(key)}:\s*\n", block)
    if match is None:
        return []
    entries = []
    for line in block[match.end() :].splitlines():
        if not line.strip():
            continue
        item = re.match(r"^      -\s+(.+?)\s*$", line)
        if item is None:
            break
        entries.append(item.group(1).strip("'\""))
    return entries


def read_required(path):
    assert path.is_file(), f"FileNotFound: required file {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_compose_has_exactly_three_application_services():
    services = re.findall(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", top_section("services"))

    assert set(services) == set(SERVICES)
    assert len(services) == len(SERVICES)


def test_single_internal_network_is_shared_by_all_services():
    networks = top_section("networks")

    assert re.search(r"(?m)^  internal:\s*$", networks)
    assert re.search(r"(?m)^    internal:\s*true\s*$", networks)
    for service in SERVICES:
        block = service_block(service)
        assert direct_key(block, "networks")
        assert "internal" in list_entries(block, "networks")


def test_api_and_scoring_join_only_internal_network():
    for service in ("api", "scoring"):
        assert list_entries(service_block(service), "networks") == ["internal"]


def test_only_frontend_publishes_loopback_8080_to_container_80():
    for service in ("api", "scoring"):
        assert not direct_key(service_block(service), "ports")

    frontend = service_block("frontend")
    ports = list_entries(frontend, "ports")
    assert ports == ["127.0.0.1:8080:80"]


def test_each_service_has_independent_execution_log_volume():
    declared = set(re.findall(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", top_section("volumes")))

    assert set(LOG_VOLUMES) <= declared
    for service, volume in zip(SERVICES, LOG_VOLUMES, strict=True):
        entries = list_entries(service_block(service), "volumes")
        expected = f"{volume}:/var/log/domdossier"
        assert any(
            entry == expected or entry == f"{expected}:rw" for entry in entries
        )
        for other in LOG_VOLUMES:
            if other != volume:
                assert all(not entry.startswith(f"{other}:") for entry in entries)


def test_dataset_is_read_only_and_mounted_only_into_api():
    api_volumes = list_entries(service_block("api"), "volumes")
    dataset_mounts = [entry for entry in api_volumes if "dataset" in entry]

    assert dataset_mounts
    assert all(entry.endswith(":ro") for entry in dataset_mounts)
    for service in ("scoring", "frontend"):
        volumes = list_entries(service_block(service), "volumes")
        assert all("dataset" not in entry for entry in volumes)
    assert not any(
        entry.startswith("dataset:")
        for entry in api_volumes + list_entries(service_block("scoring"), "volumes")
    )


def test_health_readiness_dependencies_and_grace_period():
    for service in SERVICES:
        block = service_block(service)
        assert direct_key(block, "healthcheck")
        assert "/health" in block
        assert "/ready" in block
        assert re.search(r"(?m)^    stop_grace_period:\s*30s\s*$", block)

    # frontend стартует и при неготовом api: иначе код отказа данных отдать некому.
    for service, dependency, condition in (
        ("api", "scoring", "service_healthy"),
        ("frontend", "api", "service_started"),
    ):
        block = service_block(service)
        assert direct_key(block, "depends_on")
        dependency_match = re.search(
            rf"(?ms)^      {dependency}:\s*\n(?P<body>(?:        .*(?:\n|$))*)",
            block,
        )
        assert dependency_match is not None
        conditions = re.findall(
            r"(?m)^        condition:\s*(\S+)\s*$", dependency_match.group("body")
        )
        assert conditions == [condition], (service, dependency, conditions)


def test_runtime_configuration_forbids_online_geo_services_and_extra_backends():
    runtime_text = "\n".join(
        [COMPOSE_TEXT, *(read_required(path) for path in DOCKERFILES.values())]
    )
    forbidden = re.compile(
        r"(?i)(?:tile\.openstreetmap|nominatim|photon|valhalla|postgres(?:ql)?|map-tiles)"
    )
    allowed_hosts = {"api", "scoring", "frontend", "localhost", "127.0.0.1"}

    assert forbidden.search(runtime_text) is None
    for url in re.findall(r"https?://[^\s\"'<>]+", runtime_text):
        host = urlsplit(url.rstrip(");,")).hostname
        assert host in allowed_hosts, f"external runtime URL is forbidden: {url}"


def test_base_images_are_pinned_and_latest_is_absent():
    texts = [COMPOSE_TEXT]
    texts.extend(read_required(path) for path in DOCKERFILES.values())

    assert re.search(r"(?i):latest(?:\s|$|@)", "\n".join(texts)) is None
    for text in texts[1:]:
        stage_names = set(
            re.findall(r"(?im)^FROM\s+\S+\s+AS\s+([A-Za-z0-9_-]+)\s*$", text)
        )
        for reference in re.findall(r"(?im)^FROM\s+(\S+)(?:\s+AS\s+\S+)?\s*$", text):
            if reference == "scratch" or reference in stage_names:
                continue
            image_name = reference.rsplit("/", 1)[-1]
            assert "@sha256:" in reference or ":" in image_name, (
                f"base image must have an exact tag or digest: {reference}"
            )


def nginx_tree():
    return nginx_config.parse(read_required(NGINX_PATH))


def test_nginx_exposes_health_ready_and_api_but_never_internal_scoring():
    nginx = read_required(NGINX_PATH)
    root = nginx_config.parse(nginx)

    assert re.search(r"location\s+=\s+/health\s*\{", nginx)
    assert re.search(r"location\s+=\s+/ready\s*\{", nginx)
    assert re.search(r"location\s+/api/\s*\{", nginx)
    assert nginx_config.location_names_with_internal(root) == []
    assert not nginx_config.proxies_to_scoring(root)
    assert re.search(r"proxy_pass\s+http://scoring(?::|\s|;)", nginx) is None


def test_nginx_api_proxy_reresolves_api_name_at_runtime():
    root = nginx_tree()
    api = nginx_config.location(root, "/api/")

    assert api is not None, "location /api/ is missing"
    target = nginx_config.proxy_target(api, root)
    assert target is not None and target.kind in ("variable", "upstream"), (
        f"/api/ must proxy through a resolver-backed variable or upstream: {target}"
    )
    assert nginx_config.reresolves_api(api, root), (
        "/api/ must reach http://api:8000 with resolver 127.0.0.11 valid<=30s"
    )


def test_nginx_spa_documents_are_gated_by_api_readiness():
    problems = nginx_config.spa_gate_problems(nginx_tree())

    assert problems == [], problems


def test_nginx_health_stays_independent_of_api():
    problems = nginx_config.health_problems(nginx_tree())

    assert problems == [], problems


def test_nginx_ready_fails_when_api_is_not_ready():
    problems = nginx_config.ready_problems(nginx_tree())

    assert problems == [], problems


REFERENCE_NGINX = """
resolver 127.0.0.11 valid=10s ipv6=off;

map $gate_error $gate_code {
    ""      api_unavailable;
    default $gate_error;
}

server {
    listen 80;
    set $api_origin http://api:8000;
    # location /internal-comment { proxy_pass http://scoring:8001; }

    location = /health {
        return 200 '{"status":"ok"}';
    }

    location = /ready {
        if (!-f $document_root/index.html) {
            return 503 '{"status":"not_ready"}';
        }
        proxy_pass $api_origin/api/ready;
        error_page 502 504 =503 @ready_unavailable;
    }

    location @ready_unavailable {
        return 503 '{"status":"not_ready","reason":"api_unavailable"}';
    }

    location = /_gate {
        internal;
        proxy_pass $api_origin/api/ready;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
    }

    location /api/ {
        proxy_pass $api_origin;
    }

    location /assets/ {
        try_files $uri =404;
    }

    location /maps/ {
        try_files $uri =404;
    }

    location = /index.html {
        auth_request /_gate;
        auth_request_set $gate_error $upstream_http_x_domdossier_error;
        error_page 500 = @data_unavailable;
    }

    location / {
        auth_request /_gate;
        auth_request_set $gate_error $upstream_http_x_domdossier_error;
        error_page 500 = @data_unavailable;
        try_files $uri $uri/ /index.html;
    }

    location @data_unavailable {
        default_type text/plain;
        add_header X-DomDossier-Error $gate_code always;
        return 503 "Данные недоступны: $gate_code";
    }
}
"""

def replaced(text, *replacements):
    """Текст с заменами; каждая заменяемая строка обязана присутствовать."""
    for old, new in replacements:
        assert old in text, old
        text = text.replace(old, new)
    return text


def nginx_variant(*replacements, base=REFERENCE_NGINX):
    return nginx_config.parse(replaced(base, *replacements))


UPSTREAM_NGINX = replaced(
    REFERENCE_NGINX,
    (
        "server {\n    listen 80;",
        "upstream api_backend {\n    zone api_backend 64k;\n"
        "    server api:8000 resolve;\n}\n\nserver {\n    listen 80;",
    ),
    ("proxy_pass $api_origin;", "proxy_pass http://api_backend;"),
)


def api_location_ok(root):
    return nginx_config.reresolves_api(nginx_config.location(root, "/api/"), root)


@pytest.mark.parametrize(
    ("root", "expected"),
    [
        pytest.param(nginx_variant(), True, id="variable-with-resolver"),
        pytest.param(nginx_variant(base=UPSTREAM_NGINX), True, id="upstream-resolve"),
        pytest.param(
            nginx_variant(("proxy_pass $api_origin;", "proxy_pass http://api:8000;")),
            False,
            id="static-proxy-pass",
        ),
        pytest.param(
            nginx_variant(("valid=10s", "valid=60s")), False, id="valid-over-30s"
        ),
        pytest.param(
            nginx_variant(("valid=10s", "valid=1m")), False, id="valid-one-minute"
        ),
        pytest.param(nginx_variant((" valid=10s", "")), False, id="no-valid"),
        pytest.param(
            nginx_variant(("127.0.0.11", "8.8.8.8")), False, id="external-resolver"
        ),
        pytest.param(
            nginx_variant(("resolver 127.0.0.11 valid=10s ipv6=off;", "")),
            False,
            id="no-resolver",
        ),
        pytest.param(
            nginx_variant(("set $api_origin http://api:8000;", "")),
            False,
            id="undefined-variable",
        ),
        pytest.param(
            nginx_variant(
                ("set $api_origin http://api:8000;", "set $api_origin http://scoring:8001;")
            ),
            False,
            id="variable-to-scoring",
        ),
        pytest.param(
            nginx_variant(("zone api_backend 64k;\n", ""), base=UPSTREAM_NGINX),
            False,
            id="upstream-without-zone",
        ),
        pytest.param(
            nginx_variant(("server api:8000 resolve;", "server api:8000;"), base=UPSTREAM_NGINX),
            False,
            id="upstream-without-resolve",
        ),
    ],
)
def test_nginx_reresolve_evaluator(root, expected):
    assert api_location_ok(root) is expected


COMPOSITE_MAP_NGINX = replaced(
    REFERENCE_NGINX,
    (
        'map $gate_error $gate_code {\n    ""      api_unavailable;\n'
        "    default $gate_error;\n}",
        'map "$gate_status|$gate_error" $gate_code {\n'
        '    "~\\|(?<code>[a-z_]{1,64})$" $code;\n'
        "    default api_unavailable;\n}",
    ),
    (
        "        auth_request_set $gate_error",
        "        auth_request_set $gate_status $upstream_status;\n"
        "        auth_request_set $gate_error",
    ),
)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(REFERENCE_NGINX, id="variable"),
        pytest.param(UPSTREAM_NGINX, id="upstream"),
        pytest.param(COMPOSITE_MAP_NGINX, id="composite-map"),
    ],
)
def test_nginx_reference_config_passes_every_gate_check(text):
    root = nginx_config.parse(text)

    assert nginx_config.spa_gate_problems(root) == []
    assert nginx_config.health_problems(root) == []
    assert nginx_config.ready_problems(root) == []
    assert nginx_config.location_names_with_internal(root) == []
    assert not nginx_config.proxies_to_scoring(root)


@pytest.mark.parametrize(
    ("replacements", "check", "fragment"),
    [
        pytest.param(
            [("    location / {\n        auth_request /_gate;\n", "    location / {\n")],
            "spa",
            "location /: no auth_request",
            id="fallback-not-gated",
        ),
        pytest.param(
            [("location = /_gate {\n        internal;\n", "location = /_gate {\n")],
            "spa",
            "lacks internal directive",
            id="gate-not-internal",
        ),
        pytest.param(
            [("location = /_gate", "location = /internal_gate"), ("/_gate;", "/internal_gate;")],
            "spa",
            "gate name contains internal",
            id="gate-named-internal",
        ),
        pytest.param(
            [("proxy_pass $api_origin/api/ready;\n        proxy_pass_request_body",
              "proxy_pass $api_origin/api/houses;\n        proxy_pass_request_body")],
            "spa",
            "gate does not proxy re-resolved api /api/ready",
            id="gate-wrong-path",
        ),
        pytest.param(
            [("try_files $uri $uri/ /index.html;", "return 200 'spa';")],
            "spa",
            "bypasses auth_request",
            id="return-bypasses-gate",
        ),
        pytest.param(
            [("error_page 500 = @data_unavailable;\n        try_files",
              "error_page 500 @data_unavailable;\n        try_files")],
            "spa",
            "must set the code",
            id="error-page-keeps-500",
        ),
        pytest.param(
            [("add_header X-DomDossier-Error $gate_code always;",
              "add_header X-DomDossier-Error $gate_code;")],
            "spa",
            "lacks add_header",
            id="header-without-always",
        ),
        pytest.param(
            [('return 503 "Данные недоступны: $gate_code";',
              'return 503 "Данные недоступны";')],
            "spa",
            "does not carry the code",
            id="body-without-code",
        ),
        pytest.param(
            [('return 503 "Данные недоступны: $gate_code";',
              'return 503 \'<div id="root"></div> $gate_code\';')],
            "spa",
            "contains SPA",
            id="body-is-spa",
        ),
        pytest.param(
            [('    ""      api_unavailable;\n', "")],
            "spa",
            "no api_unavailable",
            id="no-api-unavailable-default",
        ),
        pytest.param(
            [("location / {", "location /spa/ {")],
            "spa",
            "SPA fallback location / is missing",
            id="no-fallback-location",
        ),
        pytest.param(
            [("return 200 '{\"status\":\"ok\"}';", "proxy_pass $api_origin/api/health;")],
            "health",
            "/health",
            id="health-depends-on-api",
        ),
        pytest.param(
            [("proxy_pass $api_origin/api/ready;\n        error_page 502",
              "return 200 'ready';\n        proxy_pass $api_origin/api/ready;\n"
              "        error_page 502")],
            "ready",
            "bypasses api check",
            id="ready-return-200",
        ),
        pytest.param(
            [("proxy_pass $api_origin/api/ready;\n        error_page 502 504 =503 @ready_unavailable;",
              "try_files /index.html =503;")],
            "ready",
            "does not check api readiness",
            id="ready-without-api",
        ),
        pytest.param(
            [("error_page 502 504 =503 @ready_unavailable;", "")],
            "ready",
            "no error_page for 502",
            id="ready-api-down-is-502",
        ),
    ],
)
def test_nginx_gate_evaluator_reports_each_defect(replacements, check, fragment):
    root = nginx_variant(*replacements)
    problems = {
        "spa": nginx_config.spa_gate_problems,
        "health": nginx_config.health_problems,
        "ready": nginx_config.ready_problems,
    }[check](root)

    assert any(fragment in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("server { location = /_gate { internal; } }", []),
        ("server { location /internal/ { return 404; } }", [("/internal/",)]),
        ("server { location ~ ^/Internal/v1 { return 404; } }", [("~", "^/Internal/v1")]),
        ("server {\n# location /internal/ {}\nlocation / { internal; } }", []),
    ],
)
def test_nginx_internal_location_name_is_not_the_internal_directive(text, names):
    assert nginx_config.location_names_with_internal(nginx_config.parse(text)) == names


def test_nginx_ready_checks_spa_and_required_local_map_asset():
    nginx = read_required(NGINX_PATH)
    frontend_healthcheck = service_block("frontend")

    assert "try_files" in nginx
    assert "/maps/vladivostok-pilot.png" in nginx
    assert "/maps/vladivostok-pilot.png" in frontend_healthcheck
    assert re.search(r"(?i)(?:return\s+503|proxy_intercept_errors\s+on)", nginx)


def test_nginx_ready_also_requires_map_manifest():
    nginx = read_required(NGINX_PATH)

    assert MAP_MANIFEST_URL in nginx


def test_content_security_policy_is_same_origin():
    nginx = read_required(NGINX_PATH)

    assert "Content-Security-Policy" in nginx
    assert re.search(r"default-src\s+'self'", nginx)
    assert re.search(r"connect-src\s+'self'", nginx)
    csp_lines = [line for line in nginx.splitlines() if "Content-Security-Policy" in line]
    assert csp_lines
    assert all("http://" not in line and "https://" not in line for line in csp_lines)


def test_all_services_write_file_execution_log_in_their_own_mount():
    for service, dockerfile in DOCKERFILES.items():
        implementation = "\n".join(
            [service_block(service), read_required(dockerfile)]
        )
        if service == "frontend":
            implementation += "\n" + read_required(NGINX_PATH)
        assert "/var/log/domdossier/execution.log" in implementation


def test_frontend_map_asset_is_not_optional():
    assert MAP_ASSET.is_file(), (
        "NOT_IMPLEMENTED: required offline frontend asset is missing: "
        "frontend/public/maps/vladivostok-pilot.png"
    )
    assert MAP_ASSET.stat().st_size > 0


@pytest.mark.parametrize("path", list(DOCKERFILES.values()), ids=lambda path: path.name)
def test_required_container_build_files_exist(path):
    assert path.is_file(), f"FileNotFound: {path.relative_to(ROOT)}"
    assert "FROM " in path.read_text(encoding="utf-8")


def requirement_lines(path):
    """Логические строки pip-файла без комментариев, с учётом переносов."""
    joined = re.sub(r"\\\r?\n", " ", path.read_text(encoding="utf-8"))
    lines = []
    for raw in joined.splitlines():
        line = re.sub(r"(?:^|\s)#.*$", "", raw).strip()
        if line:
            lines.append(line)
    return lines


def required_names(path):
    """PEP 503-имена требований файла; -r раскрывается, прочие опции пропускаются."""
    names = set()
    for line in requirement_lines(path):
        nested = re.fullmatch(r"(?:-r|--requirement)(?:\s+|=)?(\S+)", line)
        if nested:
            names |= required_names(path.parent / nested.group(1))
        elif not line.startswith("-"):
            names.add(canonicalize_name(Requirement(line).name))
    return names


def exact_pins(path):
    """Пины constraints {имя: (версия, строка)}; не-пин — AssertionError."""
    pins = {}
    for line in requirement_lines(path):
        bare = re.sub(r"\s+--hash=sha256:[0-9a-f]{64}", "", line).strip()
        assert not bare.startswith("-"), f"option is not an exact pin: {line}"
        try:
            requirement = Requirement(bare)
        except InvalidRequirement as exc:
            raise AssertionError(f"invalid constraint line: {line}") from exc
        specifiers = list(requirement.specifier)
        assert requirement.url is None and not requirement.extras, line
        assert len(specifiers) == 1 and specifiers[0].operator == "==", (
            f"constraint must be name==version: {line}"
        )
        assert "*" not in specifiers[0].version, f"wildcard pin: {line}"
        name = canonicalize_name(requirement.name)
        assert name not in pins, f"duplicate constraint: {name}"
        pins[name] = (specifiers[0].version, line)
    return pins


def dockerfile_instructions(text):
    """Инструкции Dockerfile (KEYWORD, аргументы) со склеенными переносами."""
    instructions, current = [], ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue
        current += stripped
        keyword, _, arguments = current.partition(" ")
        instructions.append((keyword.upper(), arguments.strip()))
        current = ""
    return instructions


def dockerignore_pattern(pattern):
    """Регулярное выражение шаблона .dockerignore: *, ?, ** и классы []."""
    out, index = "", 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            out, index = out + "(?:.*/)?", index + 3
            continue
        if pattern.startswith("**", index):
            out, index = out + ".*", index + 2
            continue
        if char == "*":
            out += "[^/]*"
        elif char == "?":
            out += "[^/]"
        elif char == "[" and "]" in pattern[index + 1 :]:
            end = pattern.index("]", index + 1)
            body = pattern[index + 1 : end]
            if body[:1] in ("!", "^"):
                body = "^" + body[1:]
            out += "[" + body + "]"
            index = end
        else:
            out += re.escape(char)
        index += 1
    return re.compile(out)


def dockerignore_excludes(text, path):
    """Исключён ли путь контекста: побеждает последний совпавший шаблон.

    Совпадение с родительским каталогом исключает и вложенный путь.
    """
    parts = path.split("/")
    candidates = ["/".join(parts[: depth + 1]) for depth in range(len(parts))]
    excluded = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        pattern = line[1:].strip() if negate else line
        regex = dockerignore_pattern(posixpath.normpath(pattern).lstrip("/"))
        if any(regex.fullmatch(candidate) for candidate in candidates):
            excluded = not negate
    return excluded


@pytest.mark.parametrize(
    ("text", "path", "expected"),
    [
        ("*\n!requirements.txt\n", "requirements.txt", False),
        ("*\n!requirements.txt\n", "constraints.txt", True),
        ("*\n!*.txt\n", "constraints.txt", False),
        ("*\n!constraints.txt\n**/*.txt\n", "constraints.txt", True),
        ("*\n!api/\n**/__pycache__\n", "api/main.py", False),
        ("*\n!api/\n**/__pycache__\n", "api/__pycache__/main.pyc", True),
        ("# *\n*.py[cod]\n", "main.pyc", True),
    ],
)
def test_dockerignore_evaluator_uses_last_matching_pattern(text, path, expected):
    assert dockerignore_excludes(text, path) is expected


def test_constraints_pin_every_runtime_requirement_exactly():
    assert CONSTRAINTS_PATH.is_file(), "FileNotFound: constraints.txt"
    pins = exact_pins(CONSTRAINTS_PATH)
    required = required_names(REQUIREMENTS_PATH)

    assert required, "requirements.txt declares no packages"
    assert sorted(required - set(pins)) == [], "requirements without exact pin"
    for line in requirement_lines(REQUIREMENTS_PATH):
        if line.startswith("-"):
            continue
        requirement = Requirement(line)
        version, pin = pins[canonicalize_name(requirement.name)]
        assert requirement.specifier.contains(version, prereleases=True), (
            f"{pin} violates requirements.txt range {line}"
        )


PIP_INSTALL = re.compile(r"\bpip3?\s+install\b")
REQUIREMENTS_FLAG = re.compile(
    r"(?:^|\s)(?:-r|--requirement)(?:\s+|=)?(?:\./)?requirements\.txt(?=\s|$)"
)
CONSTRAINTS_FLAG = re.compile(
    r"(?:^|\s)(?:-c|--constraint)(?:\s+|=)?(?:\./)?constraints\.txt(?=\s|$)"
)


@pytest.mark.parametrize("path", PYTHON_DOCKERFILES, ids=lambda path: path.name)
def test_python_images_install_requirements_under_constraints(path):
    instructions = dockerfile_instructions(read_required(path))
    pip_runs = [
        index
        for index, (keyword, arguments) in enumerate(instructions)
        if keyword == "RUN" and PIP_INSTALL.search(arguments)
    ]
    assert pip_runs, f"{path.name}: no pip install"
    copied = [
        arguments.split()
        for keyword, arguments in instructions[: pip_runs[0]]
        if keyword == "COPY"
    ]
    assert any("constraints.txt" in tokens for tokens in copied), (
        f"{path.name}: constraints.txt is not copied before pip install"
    )
    installs = [
        command
        for index in pip_runs
        for command in re.split(r"&&|\|\||;", instructions[index][1])
        if PIP_INSTALL.search(command)
    ]
    assert all(CONSTRAINTS_FLAG.search(command) for command in installs), installs
    assert any(REQUIREMENTS_FLAG.search(command) for command in installs), installs


def test_dockerignore_keeps_requirements_and_constraints_in_context():
    text = read_required(DOCKERIGNORE_PATH)

    for name in ("requirements.txt", "constraints.txt"):
        assert not dockerignore_excludes(text, name), f".dockerignore excludes {name}"
