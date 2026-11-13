import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

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

    for service, dependency in (("api", "scoring"), ("frontend", "api")):
        block = service_block(service)
        assert direct_key(block, "depends_on")
        dependency_match = re.search(
            rf"(?ms)^      {dependency}:\s*\n(?P<body>(?:        .*(?:\n|$))*)",
            block,
        )
        assert dependency_match is not None
        assert re.search(
            r"(?m)^        condition:\s*service_healthy\s*$",
            dependency_match.group("body"),
        )


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


def test_nginx_exposes_health_ready_and_api_but_never_internal_scoring():
    nginx = read_required(NGINX_PATH)

    assert re.search(r"location\s+=\s+/health\s*\{", nginx)
    assert re.search(r"location\s+=\s+/ready\s*\{", nginx)
    assert re.search(r"location\s+/api/\s*\{", nginx)
    assert re.search(r"proxy_pass\s+http://api:8000(?:/|;)", nginx)
    assert re.search(r"location\s+[^*{]*internal", nginx) is None
    assert re.search(r"proxy_pass\s+http://scoring(?::|\s|;)", nginx) is None


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
